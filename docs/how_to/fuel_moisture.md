# Standardize and score NFMDB fuel moisture

The adapter is based on Abtin Olaee's NFMDB converter. It reads CSV exports with columns
`STID, DATE, FUEL_TYPE, FUEL_VARIATION, PERCENT, NAME, GACC, GROUP, LAT, LON, ELE`.
Elevation is in feet and coordinates are WGS84 degrees. FMC values are percentages of dry mass;
values above 100 are valid for live fuels. The adapter preserves zeros, duplicates, and invalid
measurements (as NaN); it does not perform quality control.

```bash
firebench fmc standardize --input observations.csv --output observations.h5 \
  --timezone America/Los_Angeles --created-by 'Dataset contributors'
```

The timezone is required for date-only live-fuel records. Following the database convention,
`1-Hour`, `10-Hour`, `100-Hour`, and `1000-Hour` are dead fuels; every other type is live.
Live-fuel dates are assigned noon in the supplied IANA timezone, accounting for daylight saving.
Dead-fuel dates are stored at UTC midnight with date precision. ISO timestamps must include their
timezone and retain their actual instant. Files spanning zones should be standardized in separate
zone-specific batches. Assumed times are recorded, not represented as measured collection times.

Station series share a group only when all ordered time coordinates agree; otherwise every
fuel/variation series receives a separate group. Standardized numeric times have `time_origin`
and `time_units` attributes. Each FMC dataset retains `source_fuel_type`, `source_fuel_variation`,
and `fuel_category`, with companion boolean datasets `<variable>_date_only` and
`<variable>_time_assumed`. Station groups retain `station_id` and source metadata/hash.
The Python API is `firebench.standardize.standardize_nfmdb_csv(csv_path, h5file,
timezone=..., overwrite=False)`; the caller supplies an open standard file.

## Compare model and observed station series

```bash
firebench run FMC ALL model.h5 --obs-data observations.h5 \
  --mae-half-score-pp 10 --output-json results.json --score-card-report scorecard.pdf
```

The scale of 10 percentage points above is an example, not a calibrated scientific threshold.
Choose and report a suitable positive scale: primary MAE equal to this scale scores 50, and
zero error scores 100, using exponential normalization.

FMC is registered in the shared benchmark registry: `firebench list FMC` describes its target,
`firebench run FMC ALL model.h5 --no-run` describes the evaluation, and the usual `run` options
select outputs, model name, logging, signing, and report generation. `Fuel_Moisture` is an alias
for case `FMC`; `ALL` (or `A`) evaluates all observed series. `--obs-data` and
`--mae-half-score-pp` are required when running FMC. For `firebench multirun`, supply
`mae_half_score_pp` and optionally `event_tolerance_seconds` in the YAML alongside `case: FMC`,
`target: ALL`, and `obs_data`.

The model must be a FireBench standard HDF5 file with `/time_series` station groups, `station_id`,
and FMC datasets with `source_fuel_type`, `source_fuel_variation`, and compatible `units`.
Numeric time coordinates need `time_origin` with timezone and `time_units`; timezone-aware ISO
string coordinates are also accepted. Group names need not match observations. Missing time
provenance flags in model files mean timestamps are actual times. This command does not extract
station series from model grids.

For live fuels sampled roughly every two weeks, the primary KPIs compare individual sampling
visits to the nearest finite model sample within one hour (`--event-tolerance-seconds` changes
this tolerance). Ties select the earlier model timestamp. The same model sample may serve several
nearby visits; offsets and match counts are reported. There is no interpolation between visits.

Daily and hourly KPIs compare finite means in shared UTC bins. Native KPIs compare all exact
coincident timestamps. Duplicate timestamps are averaged for event/native scoring. Date-only dead
records contribute only to daily KPIs; assumed-noon live samples may contribute at every scale.
The JSON records sample counts, assumed times, unmatched visits, and exclusion reasons.

MAE, RMSE, and signed bias (model minus observations) are expressed in percentage points. The total
is the equal-weight mean of eligible series' primary MAE scores: sampling events for live fuels,
daily for dead fuels. Other metrics and time scales are diagnostic with zero total weight;
their displayed scores use the same scale on absolute error. Unmatched data are excluded and
reported; a total with no eligible primary comparison is unavailable, not zero. Coverage should
be inspected alongside the score. Existing outputs require `--overwrite`.
