import hmac
import hashlib
import json

from . import _secret_key


def canonical_json_dumps(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_hmac(json_bytes: bytes) -> str:
    """
    Compute the HMAC-SHA256 of the given JSON bytes using the secret key
    stored in the compiled extension.
    """
    key = _secret_key.get_secret_key()
    mac = hmac.new(key, json_bytes, hashlib.sha256).digest()
    return mac.hex()


def sign_output_dict(data: dict) -> dict:
    """
    Return a copy of the dictionary with an added "mac" field.

    The MAC is computed on the canonical JSON representation of the input
    dictionary *without* the "mac" field. Any change to the content will
    invalidate the MAC.
    """
    json_bytes = canonical_json_dumps(data)
    mac = compute_hmac(json_bytes)

    out = dict(data)
    out["mac"] = mac
    return out


def verify_output_dict(signed_data: dict) -> bool:
    """
    Verify that the 'mac' field in the given dictionary matches the HMAC
    computed from the remaining content.

    Returns
    -------
    bool
        True if the MAC is valid, False otherwise.
    """
    mac = signed_data.get("mac")
    if mac is None:
        return False

    data_without_mac = dict(signed_data)
    data_without_mac.pop("mac", None)

    json_bytes = canonical_json_dumps(data_without_mac)
    expected_mac = compute_hmac(json_bytes)

    return hmac.compare_digest(mac, expected_mac)
