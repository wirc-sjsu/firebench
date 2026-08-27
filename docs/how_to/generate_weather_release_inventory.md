# Generate a Caldor Weather Release Inventory

Generate an inventory before publishing a Caldor observational-data package or a FireBench release
that changes weather selection. The inventory binds the result to the exact HDF5 file, FireBench
version, benchmark-data version, and installed trusted-height resources:

```bash
python -m firebench.benchmarks.weather_release_inventory \
  v2026.2/Caldor.h5 \
  weather-release-inventory-v2026.2.json \
  --benchmark-data-version 2026.2
```

The benchmark-data version argument must exactly match the HDF5 root `version` attribute. The
command refuses to replace an existing report unless `--overwrite` is supplied.

The JSON contains:

- the observational filename, size, SHA-256, standard version, creation date, and description;
- the FireBench and benchmark-data versions;
- the sensor-height resource schema version, expanded record counts, individual resource hashes,
  and one combined resource hash;
- counts for every weather variable and curated or HRRR-aligned period, split by interpreted
  confidence level and sensor-height source;
- total canonical, noncanonical, and missing confidence metadata counts; and
- release checks requiring scalar numeric confidence and its separate matching description.

Both values under `release_checks` must be `true` before treating the weather package as compatible
with the current TSO scoring contract. A descriptive legacy confidence string is intentionally
reported as noncanonical and interpreted as level 0, even when its text begins with `1` or `2`.

The inventory is local release evidence. Retain it with the external benchmark-data release or
release review records; do not commit the generated JSON or the observational HDF5 file to the
FireBench source repository.
