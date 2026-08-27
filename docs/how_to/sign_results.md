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
