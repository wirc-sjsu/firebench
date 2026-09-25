import json

import h5py
import numpy as np
import pytest

from firebench.signing import benchmarks, std_files, utils
from firebench.signing.certificates import Certificates

OBS_CERTIFICATE = Certificates.FB_VERIFIED_OBS_DATASET.value


def _verification(valid: bool, error: str | None = None) -> dict:
    return {"valid": valid, "error": error}


def _certificate_inputs(obs_valid: bool, **model_certificates: bool) -> dict:
    return {
        "from_obs_std_file": {OBS_CERTIFICATE: _verification(obs_valid)},
        "from_model_std_file": {
            certificate_name: _verification(valid) for certificate_name, valid in model_certificates.items()
        },
    }


@pytest.mark.parametrize(
    "certificates_input,benchmark_run_verified,expected",
    [
        ({}, False, "VL-D"),
        (_certificate_inputs(False), True, "VL-D"),
        (_certificate_inputs(True), False, "VL-C"),
        (_certificate_inputs(True), True, "VL-B"),
        (
            _certificate_inputs(True, **{"fb-model-run-internal": True}),
            True,
            "VL-A",
        ),
        (
            _certificate_inputs(
                True,
                **{
                    "fb-model-run-internal": True,
                    "fb-verified-input-requirements": True,
                },
            ),
            True,
            "VL-A+",
        ),
    ],
)
def test_compute_input_verification_level(
    certificates_input,
    benchmark_run_verified,
    expected,
):
    assert benchmarks.compute_input_verification_lvl(certificates_input, benchmark_run_verified) == expected


def test_false_certificate_entries_do_not_count_toward_level():
    present = {
        "fb-benchmark-run-internal": True,
        "obs-fb-verified-obs-dataset": False,
        "model-fb-model-run-internal": True,
        "model-fb-verified-input-requirements": True,
    }

    assert benchmarks.compute_verification_lvl(present) == "VL-D"


def _write_certificate_file(path, *, key_id="test-key"):
    with h5py.File(path, "w") as h5:
        h5.create_dataset("observations", data=[1.0, 2.0])

    subject_digest = std_files.hdf5_subject_digest_sha256(path)
    payload = {
        "v": 1,
        "cert_name": OBS_CERTIFICATE,
        "spec": "fb-cert-v1",
        "signed_at": "2026-09-25T00:00:00+00:00",
        "key_id": key_id,
        "subject_digest_sha256": subject_digest,
    }
    payload_bytes = utils.canonical_json_bytes(payload)
    certificate_id = utils.short_hex(utils.sha256_hex(payload_bytes), 32)

    with h5py.File(path, "a") as h5:
        certificate = h5.create_group(f"certificates/{certificate_id}")
        certificate.attrs["cert_name"] = OBS_CERTIFICATE
        certificate.create_dataset("payload", data=np.bytes_(json.dumps(payload)))
        certificate.create_dataset("signature", data=np.bytes_("signature"))


def test_verify_certificates_reports_missing_certificate(tmp_path):
    path = tmp_path / "observations.h5"
    with h5py.File(path, "w") as h5:
        h5.create_dataset("observations", data=[1.0, 2.0])

    assert std_files.verify_certificates_in_h5(path) == {}


def test_verify_certificates_reports_malformed_certificate(tmp_path):
    path = tmp_path / "observations.h5"
    with h5py.File(path, "w") as h5:
        certificate = h5.create_group("certificates/broken")
        certificate.attrs["cert_name"] = OBS_CERTIFICATE

    result = std_files.verify_certificates_in_h5(path)[OBS_CERTIFICATE]

    assert result["valid"] is False
    assert "certificate invalid" in result["error"]


@pytest.mark.parametrize(
    "verification_error,error_text",
    [
        (utils.GPGNotAvailable("gpg is unavailable"), "verification unavailable"),
        (utils.SignatureInvalid("bad signature"), "signature invalid"),
    ],
)
def test_verify_certificates_reports_signature_failures(
    monkeypatch,
    tmp_path,
    verification_error,
    error_text,
):
    path = tmp_path / "observations.h5"
    _write_certificate_file(path)
    monkeypatch.setattr(std_files, "get_public_key", lambda _key_id: "public key")

    def fail_verification(*_args):
        raise verification_error

    monkeypatch.setattr(std_files, "gpg_verify_detached_with_pubkey", fail_verification)

    result = std_files.verify_certificates_in_h5(path)[OBS_CERTIFICATE]

    assert result["valid"] is False
    assert error_text in result["error"]


def test_verify_certificates_reports_unknown_public_key(tmp_path):
    path = tmp_path / "observations.h5"
    _write_certificate_file(path, key_id="unknown-key")

    result = std_files.verify_certificates_in_h5(path)[OBS_CERTIFICATE]

    assert result["valid"] is False
    assert "verification error" in result["error"]
    assert "unknown-key" in result["error"]


def test_verify_certificates_accepts_valid_certificate(monkeypatch, tmp_path):
    path = tmp_path / "observations.h5"
    _write_certificate_file(path)
    monkeypatch.setattr(std_files, "get_public_key", lambda _key_id: "public key")
    monkeypatch.setattr(std_files, "gpg_verify_detached_with_pubkey", lambda *_args: None)

    result = std_files.verify_certificates_in_h5(path)[OBS_CERTIFICATE]

    assert result["valid"] is True
    assert result["error"] is None


def test_gpg_verification_reports_unavailable_executable(monkeypatch):
    monkeypatch.setattr(utils.shutil, "which", lambda _name: None)

    with pytest.raises(utils.GPGNotAvailable, match="approved gpg executable not found"):
        utils.gpg_verify_detached_with_pubkey(b"message", "signature", "public key")
