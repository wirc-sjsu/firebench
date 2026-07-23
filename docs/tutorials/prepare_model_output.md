# Prepare a Model-Output HDF5 File

This tutorial turns a small synthetic rate-of-spread array into a FireBench standard HDF5 file.
It demonstrates the public creation and validation functions, required root attributes, standard
names, units, time, and spatial metadata.

## Create the file

Save and run the complete script below from an empty directory:

```{literalinclude} ../examples/create_model_output.py
:language: python
:caption: create_model_output.py
```

```bash
python create_model_output.py
```

`new_std_file` writes `FireBench_io_version`, `created_on`, and `created_by`. The script adds model
metadata and a `/spatial_2d/surface` group. Each numeric dataset has Pint-compatible units; the
relative time coordinate supplies an ISO 8601 origin; the spatial group supplies a CRS.

The resulting tree is:

```text
/
└── spatial_2d
    └── surface
        ├── position_x       (3,) meter
        ├── position_y       (2,) meter
        ├── rate_of_spread   (2, 2, 3) meter / second
        └── time             (2,) second since 2021-08-17T00:00:00+00:00
```

## Inspect and validate it

`validate_h5_std` raises an exception for missing or incompatible standard metadata. Inspect the
file without loading the arrays:

```python
import h5py
from firebench.standardize import validate_h5_std

with h5py.File("model_output.h5", "r") as h5:
    validate_h5_std(h5)
    h5.visit(print)
```

If validation fails, use [Validate an HDF5 File](../how_to/validate_hdf5.md) to isolate the missing
path or attribute.

## Use the file with a benchmark

Standard-file validation and case requirements are separate. A benchmark accepts this filename at
the normal model-output position:

```bash
firebench run CASE TARGET model_output.h5 --obs-data OBSERVATIONS.h5
```

Before running, add every dataset reported by `firebench list CASE TARGET --obs-data
OBSERVATIONS.h5`; the synthetic file intentionally contains only `rate_of_spread`, so it is a
starting point rather than a Caldor-compatible result. For Caldor, follow the
[model-specific conversion guide](../how_to/convert_model_output.md) and then run the command shown
in the [Caldor tutorial](cli_caldor_benchmark.md).
