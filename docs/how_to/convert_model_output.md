# Convert Model-Specific Output

Keep conversion separate from the simulation and benchmark. A repeatable adapter should:

1. read native coordinates, times, and variables without changing the source;
2. map each variable to the [standard namespace](../namespace.md);
3. convert values to documented Pint-compatible units;
4. write the appropriate standard group with `new_std_file`;
5. attach time origins, coordinate units, CRS, descriptions, and provenance;
6. validate and close the output before invoking a benchmark.

Start from the complete [synthetic HDF5 script](../examples/create_model_output.py). Replace its
NumPy literal with the native reader and preserve the same explicit metadata pattern. Do not copy a
native name into the standard file when an established FireBench name exists.

## Supported adapters

Model adapters are maintained as separate packages so their releases can follow the upstream model
and its native output format. The currently supported adapter family is:

- **WRF-SFIRE** — The adapter converts native WRF-SFIRE output into the FireBench standard format.
  Its first public release is in development for FireBench 1.0. Installation instructions and
  repository, Read the Docs, and PyPI links will be added when the adapter reaches version 1.0.

Until that release is available, treat WRF-SFIRE adapter output as pre-release and record the exact
adapter revision used to create each standard file. Additional supported adapters will be listed
here with their release status and installation documentation.

For GeoTIFF, Synoptic, MTBS, LANDFIRE, and RAVG inputs, check the public functions under
`firebench.standardize` before writing a custom converter. For polygon data, keep each KML beside
the HDF5 file at the location named by `rel_path`, and record its SHA-256 digest.

After conversion:

```bash
firebench list CASE TARGET --obs-data OBSERVATIONS.h5
firebench run CASE TARGET converted_model_output.h5 --obs-data OBSERVATIONS.h5
```

Record the adapter version, source files, transformations, and unit conversions in the model report.
