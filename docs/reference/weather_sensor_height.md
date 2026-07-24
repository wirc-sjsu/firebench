# Weather Sensor Height and Trust

Weather observations and model values must refer to a clearly defined measurement height. This is
especially important for wind: wind speed and direction can change materially with height, so a
comparison is only scientifically meaningful when the model value is prepared at the
observational sensor height.

This page defines the sensor-height and station-selection contract used by the Caldor weather
benchmarks.

```{important}
The **all-sources** station set includes every station in **Trusted Sources Only (TSO)** as well as
stations whose heights are unverified or unknown. FireBench does not currently provide an
untrusted-only station set.
```

## Terms

Sensor height
: The vertical distance between the sensor and the local ground surface. It is stored on each
  weather-variable dataset as numeric `sensor_height`, with its Pint-compatible unit in
  `sensor_height_units`.

Height source
: The origin of the height value, stored in `sensor_height_source`. Examples include downloaded
  provider metadata, a FireBench station record, or a fallback default.

Confidence level
: A numeric assessment of the height source, stored in
  `sensor_height_source_confidence_lvl`. It describes confidence in the sensor-height metadata,
  not a general assessment of the weather measurements.

Trusted Sources Only (TSO)
: The authoritative, scored station set. It includes only observational variables with confidence
  level 2. Model values used by TSO must be prepared at the trusted observational sensor height.

All sources
: An informational station set containing confidence levels 0, 1, and 2. It therefore overlaps
  with and includes TSO. Its KPIs have weight 0 and do not contribute to the aggregate score.

## Confidence levels

Newly standardized observational weather data must store the confidence as a scalar integer.
Human-readable text belongs in the separate
`sensor_height_source_confidence_description` attribute and must never control station selection.

Level | Meaning | TSO | All sources
----- | ------- | --- | -----------
0 | Unknown, guessed, or missing source metadata | Excluded | Included
1 | Provider default, not verified for the station | Excluded | Included
2 | Verified measurement or accepted trusted record | Included | Included

A reader treats a missing, malformed, or unknown confidence value as level 0 and reports a warning
with the affected station and variable. Newly standardized files must write a valid value instead
of relying on this fallback.

FireBench validates confidence metadata for the selected weather variables and periods before
executing their KPIs. It uses the same selector for benchmark execution and the station counts
shown by `firebench list`. The run log records the included and excluded stations, their confidence
levels, and exclusion reasons. If no station is eligible for a KPI, that KPI is ignored: it has no
value or score and contributes nothing to aggregation.

## Source precedence

FireBench uses the first available height in this order:

Priority | Source | Stored `sensor_height_source` | Confidence
-------- | ------ | ----------------------------- | ----------
1 | Sensor position in downloaded Synoptic metadata | `from_data` | 2
2 | FireBench per-station trusted database | `firebench_trusted_stations` | 2
3 | FireBench trusted-history database | `firebench_trusted_history` | 2
4 | Provider-wide default | `firebench_providers_default` | 1
5 | FireBench variable default | `firebench_default` | 0

Sensor-height metadata supplied by Synoptic is accepted as a verified source. Later sources are
fallbacks only; they do not override an earlier source.

## Variable fallback heights

Variable | Fallback height
-------- | ---------------
Air temperature | 2 m
Relative humidity | 2 m
Wind direction | 10 m
Wind speed | 10 m
Wind gust | 10 m
Solar radiation | 2 m
10-hour fuel moisture | 0.3 m

These values let an all-sources comparison run when station-specific metadata is unavailable. A
fallback is not evidence that a particular sensor was installed at that height.

## Model preparation for TSO

For every TSO station and variable, prepare the model value at the trusted height recorded on the
corresponding observational dataset. Height-aware interpolation, including vertical wind
interpolation, must use that observational height rather than a provider-wide or FireBench
fallback. Record the resulting model height in `sensor_height` and `sensor_height_units`.

Do not interpret a matching station ID alone as evidence that model and observation heights match.
FireBench validates the model height contract separately from the observational confidence used to
select TSO stations.

## Scientific limitations of all-sources comparisons

All-sources KPIs are useful diagnostics for spatial and temporal coverage, but some comparisons use
guessed, default, or otherwise unverified heights. Their differences may combine model error with
an unknown vertical-offset error. This is particularly consequential for wind and can also affect
near-surface temperature and humidity.

For that reason, all-sources KPIs have weight 0. Use them to investigate behavior and coverage, not
as an independent score or as an untrusted-only control group.

## Caldor weather KPI identifiers

Caldor defines 312 curated weather KPIs followed by 4,836 HRRR-aligned KPIs:

- `FB001_WX001` through `FB001_WX312` cover curated periods `W1` through `W4`.
- `FB001_WX313` through `FB001_WX5148` cover HRRR-aligned periods `WH1` through `WH62`.

Within each period set, IDs are generated in this order: variable, period, metric, station set, then
summary statistic (`min`, `mean`, `max`). The variable order is air temperature, relative
humidity, wind speed, wind direction, and 10-hour fuel moisture. For each metric, the TSO trio is
followed by the all-sources trio.

The static tables in the [Caldor specification](../benchmarks/California/01_Caldor.md) list the
curated KPIs. Inspect generated HRRR-aligned IDs, names, station counts, weights, and normalization
parameters from an observational file with:

```bash
firebench list 2021_Caldor H013_W --obs-data v2026.2/Caldor.h5
```
