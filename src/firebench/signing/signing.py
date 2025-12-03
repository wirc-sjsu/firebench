import hmac
import hashlib
import json

try:
    from . import _secret_key
except ImportError:
    _secret_key = None

def _canonical_json_dumps(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_hmac(json_bytes: bytes) -> str:
    return _secret_key.compute_hmac(json_bytes)


def _finalize_payload(data: dict) -> dict:
    json_bytes = _canonical_json_dumps(data)
    mac = _compute_hmac(json_bytes)

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

    json_bytes = _canonical_json_dumps(data_without_mac)
    expected_mac = _compute_hmac(json_bytes)

    return hmac.compare_digest(mac, expected_mac)


def write_case_results(path: str, output_dict: dict):
    with open(path, "w") as f:
        json.dump(_finalize_payload(output_dict), f, indent=4, sort_keys=True)
