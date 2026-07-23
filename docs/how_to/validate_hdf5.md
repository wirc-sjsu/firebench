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

For a registered case, inspect the exact target before building a requirements dictionary:

```bash
firebench list 2021_Caldor H013_P --obs-data v2026.2/Caldor.h5
```

Common failures are missing root attributes, a dataset at the wrong path, absent `units`, malformed
ISO 8601 time metadata, a missing CRS, incompatible shapes, and `rel_path` values whose external
files were not copied with the HDF5 file. Use `h5.visit(print)` to compare the actual tree with the
target specification. Validation raises at the first violated rule; fix that rule and run it again
until both standard and target-specific checks pass.
