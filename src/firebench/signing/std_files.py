import json
import os
import hashlib
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Iterable, Dict, Any, Tuple, Optional
import hdf5plugin

import h5py
import numpy as np

from .utils import (
    _canonical_json_dumps,
    _is_excluded,
    canonical_json_bytes,
    gpg_detached_sign_armor,
    gpg_verify_detached_with_pubkey,
    sha256_hex,
    short_hex,
)
from ..tools import calculate_sha256
from ..standardize import current_datetime_iso8601, CERTIFICATES
from .certificates import get_public_key

EXCLUDE_PREFIXES_DEFAULT = ["/certificates"]


def add_certificate_to_h5(
    h5_path: str,
    cert_name: str,
    key_id: str,
    signer: str,
    spec: str = "fb-cert-v1",
    exclude_prefixes: list[str] = EXCLUDE_PREFIXES_DEFAULT,
    remove_previous_certificates: bool = False,
):
    """
    Compute subject digest and add a signed certificate to /fb/certificates/<cert_id>/...
    Returns certificate_id.

    mode: a = append => add a new certificate
          w = write => delete previous certificates
    """
    signed_at = current_datetime_iso8601()
    subject_digest = hdf5_subject_digest_sha256(h5_path, exclude_prefixes=exclude_prefixes)

    payload = {
        "v": 1,
        "cert_name": cert_name,
        "spec": spec,
        "signed_at": signed_at,
        "key_id": key_id,
        "subject_digest_sha256": subject_digest,
    }

    payload_bytes = _canonical_json_dumps(payload)
    payload_sha = sha256_hex(payload_bytes)
    cert_id = short_hex(payload_sha, 32)

    signature_armor = gpg_detached_sign_armor(payload_bytes, signer=signer)

    with h5py.File(h5_path, "a") as f:
        if remove_previous_certificates and CERTIFICATES in f.keys():
            del f[f"/{CERTIFICATES}"]
        base = f.require_group(f"/{CERTIFICATES}").require_group(cert_id)
        # Store payload + signature as UTF-8 datasets
        if "payload" in base:
            del base["payload"]
        if "signature" in base:
            del base["signature"]
        base.create_dataset("payload", data=np.bytes_(payload_bytes.decode("utf-8")))
        base.create_dataset("signature", data=np.bytes_(signature_armor))

        # Helpful attrs for indexing
        base.attrs["cert_name"] = cert_name
        base.attrs["spec"] = spec
        base.attrs["signed_at"] = signed_at
        base.attrs["key_id"] = key_id
        base.attrs["subject_digest_sha256"] = subject_digest

    return cert_id


def verify_certificates_in_h5(
    h5_path: str,
    exclude_prefixes: list[str] = EXCLUDE_PREFIXES_DEFAULT,
):
    """
    Verify all certificates under /certificates.
    Returns dict cert_id -> info (payload fields, valid flag).
    """
    subject_digest = hdf5_subject_digest_sha256(h5_path, exclude_prefixes=exclude_prefixes)

    results = {}
    with h5py.File(h5_path, "r") as f:
        if f"/{CERTIFICATES}" not in f:
            return results

        certs = f[f"/{CERTIFICATES}"]
        for cert_id in sorted(certs.keys()):
            grp = certs[cert_id]
            payload_txt = (
                grp["payload"][()].decode("utf-8")
                if isinstance(grp["payload"][()], (bytes, np.bytes_))
                else str(grp["payload"][()])
            )
            sig_txt = (
                grp["signature"][()].decode("utf-8")
                if isinstance(grp["signature"][()], (bytes, np.bytes_))
                else str(grp["signature"][()])
            )

            public_key_armor = get_public_key(str(grp.attrs.get("key_id")))

            payload = json.loads(payload_txt)
            payload_bytes = canonical_json_bytes(payload)

            # Check certificate_id matches payload hash prefix
            payload_sha = sha256_hex(payload_bytes)
            expected_id = short_hex(payload_sha, 32)

            ok = True
            err = None

            if expected_id != cert_id:
                ok = False
                err = f"certificate_id mismatch: expected {expected_id}, found {cert_id}"

            # Check subject digest binding
            if ok and payload.get("subject_digest_sha256") != subject_digest:
                ok = False
                err = "subject_digest mismatch: HDF5 content changed (excluding certificates) or wrong file"

            # Verify signature
            if ok:
                try:
                    gpg_verify_detached_with_pubkey(payload_bytes, sig_txt, public_key_armor)
                except Exception as e:
                    ok = False
                    err = f"signature invalid: {e}"

            results[payload["cert_name"]] = {
                "cert_id": cert_id,
                "valid": ok,
                "error": err,
                "payload": payload,
                "subject_digest_sha256": subject_digest,
            }

    return results


def hdf5_subject_digest_sha256(path: str, exclude_prefixes: list[str] = EXCLUDE_PREFIXES_DEFAULT) -> str:
    """
    Deterministic logical digest of an HDF5 file excluding some prefixes.
    """
    h = hashlib.sha256()
    with h5py.File(path, "r") as f:
        _hash_group(h, f["/"], exclude_prefixes)
    return h.hexdigest()


def _hash_attrs(h: hashlib._hashlib.HASH, attrs: h5py.AttributeManager):
    # Deterministic ordering by attribute name
    for k in sorted(attrs.keys()):
        v = attrs[k]
        h.update(b"ATTR\x00")
        h.update(k.encode("utf-8"))
        h.update(b"\x00")
        # Normalize attribute value to bytes deterministically
        if isinstance(v, bytes):
            vb = v
        elif isinstance(v, str):
            vb = v.encode("utf-8")
        elif np.isscalar(v):
            vb = str(v).encode("utf-8")
        else:
            arr = np.array(v)
            vb = arr.tobytes(order="C")
            h.update(b"SHAPE\x00" + str(arr.shape).encode("utf-8") + b"\x00")
            h.update(b"DTYPE\x00" + str(arr.dtype).encode("utf-8") + b"\x00")
        h.update(vb)
        h.update(b"\x00")


def _hash_dataset(h: hashlib._hashlib.HASH, ds: h5py.Dataset):
    h.update(b"DATASET\x00")
    h.update(ds.name.encode("utf-8"))
    h.update(b"\x00")
    h.update(b"SHAPE\x00" + str(ds.shape).encode("utf-8") + b"\x00")
    h.update(b"DTYPE\x00" + str(ds.dtype).encode("utf-8") + b"\x00")
    _hash_attrs(h, ds.attrs)

    # Hash data in chunks to avoid large memory usage
    # For scalar datasets, ds[()] is fine
    if ds.size == 0:
        h.update(b"EMPTY\x00")
        return

    # For simple numeric datasets: chunk along first axis
    if ds.ndim == 0:
        data = ds[()]
        h.update(np.array(data).tobytes(order="C"))
        h.update(b"\x00")
        return

    # Chunk size: ~4MB of raw bytes
    itemsize = ds.dtype.itemsize
    # Avoid division by zero
    row_bytes = int(np.prod(ds.shape[1:])) * itemsize if ds.ndim >= 2 else itemsize
    rows_per_chunk = max(1, (4 * 1024 * 1024) // max(1, row_bytes))

    for i0 in range(0, ds.shape[0], rows_per_chunk):
        i1 = min(ds.shape[0], i0 + rows_per_chunk)
        slab = ds[i0:i1, ...]
        h.update(np.asarray(slab).tobytes(order="C"))
    h.update(b"\x00")


def _hash_group(h: hashlib._hashlib.HASH, grp: h5py.Group, exclude_prefixes: Iterable[str]) -> None:
    h.update(b"GROUP\x00")
    h.update(grp.name.encode("utf-8"))
    h.update(b"\x00")
    _hash_attrs(h, grp.attrs)

    # Deterministic traversal by child name
    for name in sorted(grp.keys()):
        child = grp[name]
        if _is_excluded(child.name, exclude_prefixes):
            continue
        if isinstance(child, h5py.Group):
            _hash_group(h, child, exclude_prefixes)
        elif isinstance(child, h5py.Dataset):
            _hash_dataset(h, child)
        else:
            # Rare HDF5 types; include name only
            h.update(b"OTHER\x00" + child.name.encode("utf-8") + b"\x00")
