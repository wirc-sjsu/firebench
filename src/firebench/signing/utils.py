import json
import subprocess
import hashlib


def _canonical_json_dumps(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


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
