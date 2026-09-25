from enum import Enum
import json
from .std_files import verify_certificates_in_h5
from .utils import (
    _canonical_json_dumps,
    canonical_json_bytes,
    gpg_detached_sign_armor,
    gpg_verify_detached_with_pubkey,
    sha256_hex,
    short_hex,
    GPGNotAvailable,
    SignatureInvalid,
    SignatureVerificationError,
)
from .certificates import Certificates, get_public_key
from ..standardize import current_datetime_iso8601


class Verification_lvl(Enum):
    Aplus = "VL-A+"
    A = "VL-A"
    B = "VL-B"
    C = "VL-C"
    D = "VL-D"


VERIFICATION_LEVEL_COLORS = {
    Verification_lvl.D.value: "#7F1D1D",
    Verification_lvl.C.value: "#B03A2E",
    Verification_lvl.B.value: "#D4AC0D",
    Verification_lvl.A.value: "#2E86C1",
    Verification_lvl.Aplus.value: "#1E8449",
}

RULES = [
    (
        {
            "fb-benchmark-run-internal",
            "obs-fb-verified-obs-dataset",
            "model-fb-model-run-internal",
            "model-fb-verified-input-requirements",
        },
        Verification_lvl.Aplus.value,
    ),
    (
        {"fb-benchmark-run-internal", "obs-fb-verified-obs-dataset", "model-fb-model-run-internal"},
        Verification_lvl.A.value,
    ),
    ({"fb-benchmark-run-internal", "obs-fb-verified-obs-dataset"}, Verification_lvl.B.value),
    ({"obs-fb-verified-obs-dataset"}, Verification_lvl.C.value),
]

DEFAULT_VL = Verification_lvl.D.value


def retrieve_h5_certificates(obs_file_path, model_file_path=None):
    certificates = {}
    certificates["from_obs_std_file"] = verify_certificates_in_h5(obs_file_path)
    if model_file_path is not None:
        certificates["from_model_std_file"] = verify_certificates_in_h5(model_file_path)
    return certificates


def get_observation_certificate_verification(certificates_input: dict) -> dict | None:
    """Return verification details for the required observational dataset certificate."""
    return certificates_input.get("from_obs_std_file", {}).get(Certificates.FB_VERIFIED_OBS_DATASET.value)


def compute_input_verification_lvl(
    certificates_input: dict,
    benchmark_run_verified: bool = False,
) -> str:
    """Compute a level from verified input certificates and an optional signed benchmark run."""
    found = {"fb-benchmark-run-internal": benchmark_run_verified}
    for source, prefix in (
        ("from_model_std_file", "model"),
        ("from_obs_std_file", "obs"),
    ):
        for certificate_name, verification in certificates_input.get(source, {}).items():
            found[f"{prefix}-{certificate_name}"] = bool(verification.get("valid", False))
    return compute_verification_lvl(found)


def write_case_results(path: str, output_dict: dict):
    with open(path, "w") as f:
        json.dump(output_dict, f, indent=4, sort_keys=True)


def add_certificate_to_dict(
    data: dict,
    key_in_dict: str,
    cert_name: str,
    key_id: str,
    signer: str,
    spec: str = "fb-cert-v1",
):
    if key_in_dict not in data or not isinstance(data[key_in_dict], dict):
        data[key_in_dict] = {}

    signed_at = current_datetime_iso8601()

    unsigned_data = dict(data)
    unsigned_data.pop(key_in_dict, None)

    subject_digest = sha256_hex(_canonical_json_dumps(unsigned_data))

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

    # Insert certificate
    data[key_in_dict] = {
        "certificate_id": cert_id,
        "payload": payload,
        "signature_armor": signature_armor,
    }

    return data, cert_id


def verify_certificate_in_dict(
    data: dict,
    key_in_dict: str,
):
    """
    Verify the final certificate embedded in a dict.

    The dict must contain:
      - data[key_in_dict]["certificate_id"]
      - data[key_in_dict]["payload"]
      - data[key_in_dict]["signature_armor"]

    Returns a dict with:
      - valid: bool
      - error: str | None
      - payload: dict
      - subject_digest_sha256: str
    """
    if key_in_dict not in data or not isinstance(data[key_in_dict], dict):
        return {
            "valid": False,
            "error": "missing final certificate",
            "payload": None,
            "subject_digest_sha256": None,
        }

    cert = data[key_in_dict]

    required_keys = {"certificate_id", "payload", "signature_armor"}
    if not required_keys.issubset(cert):
        return {
            "valid": False,
            "error": "certificate structure incomplete",
            "payload": None,
            "subject_digest_sha256": None,
        }

    cert_id = cert["certificate_id"]
    payload = cert["payload"]
    sig_txt = cert["signature_armor"]

    # --- Compute subject digest (exclude certificates) ---
    unsigned_data = dict(data)
    unsigned_data.pop(key_in_dict, None)

    subject_digest = sha256_hex(canonical_json_bytes(unsigned_data))

    payload_bytes = canonical_json_bytes(payload)

    ok = True
    err = None

    # --- Check certificate_id matches payload hash ---
    payload_sha = sha256_hex(payload_bytes)
    expected_id = short_hex(payload_sha, 32)

    if expected_id != cert_id:
        ok = False
        err = f"certificate_id mismatch: expected {expected_id}, found {cert_id}"

    # --- Check subject digest binding ---
    if ok and payload.get("subject_digest_sha256") != subject_digest:
        ok = False
        err = "subject_digest mismatch: JSON content changed or wrong file"

    # --- Verify signature ---
    if ok:
        try:
            key_id = payload.get("key_id")
            if not key_id:
                raise SignatureVerificationError("missing key_id in payload")

            public_key_armor = get_public_key(key_id)
            gpg_verify_detached_with_pubkey(payload_bytes, sig_txt, public_key_armor)

        except GPGNotAvailable as e:
            ok = False
            err = f"verification unavailable: {e}"
        except SignatureInvalid as e:
            ok = False
            err = f"signature invalid: {e}"
        except SignatureVerificationError as e:
            ok = False
            err = f"verification error: {e}"

    return {
        "cert_id": cert_id,
        "valid": ok,
        "error": err,
        "payload": payload,
        "subject_digest_sha256": subject_digest,
    }


def certify_benchmark_run(
    data: dict,
    key_id: str,
    signer: str,
    spec: str = "fb-cert-v1",
):
    # add the certificate of benchmark run
    data, _ = add_certificate_to_dict(
        data, "certificate", Certificates.FB_BENCHMARK_RUN_INTERNAL.value, key_id, signer, spec
    )
    verif = verify_certificate_in_dict(data, "certificate")
    input_verif: dict = data.get("certificates_input", {})
    data["verification_lvl"] = compute_input_verification_lvl(input_verif, verif["valid"])

    data, _ = add_certificate_to_dict(
        data, "certificate_verif_lvl", Certificates.FB_VERIFICATION_LVL.value, key_id, signer, spec
    )

    return data


def compute_verification_lvl(present: set[str] | dict[str, bool]) -> str:
    if isinstance(present, dict):
        present = {certificate for certificate, valid in present.items() if valid}
    for required, value in RULES:
        if required.issubset(present):
            return value
    return DEFAULT_VL
