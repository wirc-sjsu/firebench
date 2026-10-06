# Sign and Verify FireBench Results

Signing binds a benchmark result or HDF5 file to a GPG identity and a registered FireBench public
key. It does not independently certify scientific quality.

For a benchmark run, provide the registered key ID and a local GPG signer selector:

```bash
firebench run CASE TARGET model_output.h5 --sign KEY_ID SIGNER
```

The signer must already exist in the local GPG keyring. Verification is public:

```python
from firebench.signing.std_files import verify_certificates_in_h5

results = verify_certificates_in_h5("model_output.h5")
for certificate_name, result in results.items():
    print(certificate_name, result["valid"], result["error"])
```

`verify_certificates_in_h5` recomputes the logical HDF5 digest, checks certificate identity, loads
the packaged public key for its key ID, and verifies the detached signature. An empty dictionary
means no certificates are embedded. A changed subject, unknown key ID, unavailable GPG executable,
or invalid signature is reported as a failed verification. Never commit private keys.

Every benchmark run verifies the observational file's `fb-verified-obs-dataset` certificate. A
valid observation certificate permits verification level C for an unsigned run and levels B, A,
or A+ when the corresponding signed benchmark and model certificates are also valid. If the
observation certificate is missing, invalid, or cannot be checked because GPG is unavailable, the
benchmark continues at verification level D and emits a warning explaining the downgrade. The JSON
result records both the selected level and the observation certificate verification result.

## Certificates written by another signer

A certificate does not have to be written by `add_certificate_to_h5`. Another program can sign a
file with its own key, on a machine where FireBench does not run, and write the certificate itself.
`verify_certificates_in_h5` then checks it like one of its own. This section states the format as a
contract: FireBench keeps it stable.

The certificate name `fbf-reviewed-obs-dataset` is reserved for an observation dataset built on
firebench-web, reviewed by a curator, and signed with the FireBench Foundation's key. FireBench
verifies it, and it does not count towards a verification level.

- **Payload**: a JSON object with exactly these keys.

  ```json
  {
    "v": 1,
    "cert_name": "fbf-reviewed-obs-dataset",
    "spec": "fb-cert-v1",
    "signed_at": "2026-10-06T12:00:00+00:00",
    "key_id": "example-key-2026-01",
    "subject_digest_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
  }
  ```

  `v` is the integer 1, `spec` is `"fb-cert-v1"`, and `signed_at` is an ISO 8601 date and time.
- **Canonical bytes**: `json.dumps(payload, sort_keys=True, separators=(",", ":"))`, encoded as
  UTF-8. Keep every value ASCII: signing and verification serialize non-ASCII text differently.
- **Certificate id**: the first 32 hexadecimal characters of the SHA-256 of the canonical bytes.
- **Signature**: an ASCII-armored detached GPG signature of the canonical bytes.
- **Subject digest**: `firebench.signing.hdf5_subject_digest_sha256(path)`. It covers the whole
  file except `/certificates`, so write the certificate after the last change to the data.
- **Storage**: the group `/certificates/<certificate id>`, with two scalar byte-string datasets,
  `payload` (the canonical bytes) and `signature`, and the attributes `cert_name`, `spec`,
  `signed_at`, `key_id`, and `subject_digest_sha256`, each with the value it has in the payload.

A certificate whose `key_id` FireBench does not know is reported with `valid: False` and an error
that contains "Public key import failed". It is not an exception. FireBench knows a key id once
its public key is packaged with FireBench.
