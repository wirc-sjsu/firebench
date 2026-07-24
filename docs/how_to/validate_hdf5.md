# Validate an Existing HDF5 File

Use standard validation first, then validate the paths required by a benchmark target.

```python
import h5py

from firebench.standardize import validate_h5_requirement, validate_h5_std


requirements = {
    "/spatial_2d/surface/time": ["units", "time_origin"],
    "/spatial_2d/surface/rate_of_spread": ["units", "dimensions"],
}

with h5py.File("model_output.h5", "r") as h5:
    validate_h5_std(h5)
    valid, missing = validate_h5_requirement(h5, requirements)
    if not valid:
        raise ValueError(f"Missing benchmark requirement: {missing}")
```

`validate_h5_std` accepts the current standard version and versions explicitly declared compatible
with it. Missing, malformed, unknown, and unsupported versions raise `ValueError`.

For paths under `/polygons`, requirement validation also enforces the standard `rel_path`,
`file_size_bytes`, and `sha256` attributes. The referenced path is resolved relative to the HDF5
file, and the actual file size and SHA-256 digest must match the stored metadata.

For a registered case, inspect the exact target before building a requirements dictionary:

```bash
firebench list 2021_Caldor H013_P --obs-data v2026.2/Caldor.h5
```

Common failures are missing root attributes, a dataset at the wrong path, absent `units`, malformed
ISO 8601 time metadata, a missing CRS, incompatible shapes, and polygon references whose external
files are missing or no longer match their recorded size and digest. Use `h5.visit(print)` to
compare the actual tree with the target specification. Validation raises at the first violated
rule; fix that rule and run it again until both standard and target-specific checks pass.
