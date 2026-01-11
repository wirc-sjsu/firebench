import os
import json
import subprocess
import hashlib
import tempfile


def _canonical_json_dumps(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_json_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_hex(hex_digest: str, n: int = 32) -> str:
    return hex_digest[:n]


def _is_excluded(path: str, exclude_prefixes: list[str]) -> bool:
    return any(path == p or path.startswith(p + "/") for p in exclude_prefixes)


def gpg_detached_sign_armor(message: bytes, signer: str) -> str:
    """
    Create an ASCII-armored detached signature over message bytes.
    Requires interactive pinentry to work (set GPG_TTY).
    """
    p = subprocess.run(
        ["gpg", "--batch", "--yes", "--armor", "--detach-sign", "-u", signer, "--output", "-", "--"],
        input=message,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if p.returncode != 0:
        raise RuntimeError("GPG signing failed:\n" + p.stderr.decode("utf-8", errors="replace"))
    return p.stdout.decode("utf-8")


def gpg_verify_detached_with_pubkey(message: bytes, signature_armor: str, public_key_armor: str) -> None:
    """
    Verify detached signature using ONLY the provided public key.
    """
    if not public_key_armor.strip():
        raise ValueError("Public key armor is required to verify.")

    with tempfile.TemporaryDirectory() as gnupghome:
        env = os.environ.copy()
        env["GNUPGHOME"] = gnupghome

        imp = subprocess.run(
            ["gpg", "--batch", "--yes", "--import"],
            input=public_key_armor.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        if imp.returncode != 0:
            raise RuntimeError("Public key import failed:\n" + imp.stderr.decode("utf-8", errors="replace"))

        sig_path = os.path.join(gnupghome, "sig.asc")
        with open(sig_path, "w", encoding="utf-8") as f:
            f.write(signature_armor)

        ver = subprocess.run(
            ["gpg", "--batch", "--verify", sig_path, "-"],
            input=message,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        if ver.returncode != 0:
            raise RuntimeError(
                "Signature verification failed:\n" + ver.stderr.decode("utf-8", errors="replace")
            )
