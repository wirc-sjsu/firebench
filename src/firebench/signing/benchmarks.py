import hmac
import hashlib
import json

from .std_files import verify_certificates_in_h5

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

def retrieve_h5_certificates(obs_file_path, model_file_path):
    certificates = {}
    certificates["from_obs_std_file"] = verify_certificates_in_h5(obs_file_path)
    certificates["from_model_std_file"] = verify_certificates_in_h5(model_file_path)
    return certificates

def write_case_results(path: str, output_dict: dict):
    with open(path, "w") as f:
        json.dump(output_dict, f, indent=4, sort_keys=True)

