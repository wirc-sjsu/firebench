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

The KPI weights express confidence that model values were prepared and verified at the trusted
observational sensor height. They do not rate the general quality of a station's observed weather
values. TSO KPIs therefore have weight 1, while all-sources KPIs retain a value and score for
diagnosis but have weight 0.

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

### Reading packages standardized before 0.10

FireBench releases before 0.10 stored the confidence as a combined `"<level> - <description>"`
string rather than a scalar integer. A reader still recognizes those historical values so that
already published observational packages keep their verified stations in TSO. Only the three
strings that FireBench itself wrote are accepted:

- `0 - unknown (guessed or missing metadata)`
- `1 - provider default (not verified)`
- `2 - verified measurement`

Any other string is malformed and stays level 0, so a hand-edited description cannot promote a
station into TSO. Reading a historical value is logged once per station and variable. This is
read-only compatibility: newly standardized files always write the scalar integer, and
re-standardizing an older package converts it.

Those releases also wrote `sensor_height` itself as a decimal string whenever the height came from
the provider metadata, which is exactly the case for the verified heights. A reader accepts a
decimal string for observational data so those stations stay eligible for TSO. Model output is
always required to record a numeric height, because the model-preparation contract is new in 0.10
and has no historical files to read.

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
fallbacks only; they do not override an earlier source. The standardizer records the Synoptic
source JSON filename and SHA-256, provider, acceptance date, and accepting authority on the
resulting HDF5 variable so that this decision remains auditable. Synoptic Data PBC is identified
as the metadata authority.

## Trusted-height resource schema

The installed station-specific, historical, and provider-default resources use sensor-height
schema version 1. Each document identifies its `record_type`, shared provenance, and records.
Every record has a stable ID, provider, supported variables, numeric height, explicit length
units, numeric confidence, and lifecycle status. Station-specific and historical records also
identify the station.

Required provenance consists of a source reference or URL, verification date, and reviewer or
issuing authority. A source date is included when one is available, and optional notes preserve
limitations or review context. Records can override shared provenance for evidence that applies
only to that record.

Only `active` records participate in resolution. `proposed`, `superseded`, and `revoked` records
remain visible for review or audit but are not selected. Installed resources are validated for
schema and semantic errors before use, including duplicate selectors, unsupported variables,
invalid heights or units, missing provenance, and unknown confidence values.

The original resource dictionaries were migrated without inventing unavailable evidence dates.
Their provenance notes identify this limitation so that better-supported records can supersede
them. See [Curate Weather Sensor Heights](../how_to/manage_weather_sensor_heights.md) for the
submission, review, activation, supersession, and revocation workflow.

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

Use `firebench.adapter_common.trusted_observation_sensor_height` to obtain the interpolation target
from the observational HDF5 file. Pass that value directly to height-aware preparation; for wind,
it is the target height of the vertical wind interpolation. After preparing the station series,
use `firebench.adapter_common.write_model_sensor_height_metadata` to record the height actually
used.

```python
from firebench import adapter_common

target_height = adapter_common.trusted_observation_sensor_height(
    observations,
    "station_TEST",
    "wind_speed",
)
prepared_wind = interpolate_wind(
    model_wind_profile,
    target_height=target_height,
)
model_wind_speed[...] = prepared_wind
adapter_common.write_model_sensor_height_metadata(model_wind_speed, target_height)
```

The example `interpolate_wind` name represents the adapter's height-aware interpolation routine;
FireBench does not assume one atmospheric model or vertical interpolation method.

Do not interpret a matching station ID alone as evidence that model and observation heights match.
For TSO, FireBench requires both the observational and model variable datasets to contain numeric
`sensor_height` and Pint-compatible `sensor_height_units`. It converts both heights to meters and
accepts an absolute difference of at most 0.01 m. A station with missing attributes, incompatible
units, or a larger mismatch is excluded from that TSO KPI with the reason in the log. Other
eligible stations continue to run, and validation is limited to the variables, periods, and
stations selected by the target.

The one compatibility exception is a smoke test that opens the same physical observation HDF5 file
as both model and observation input. In that case FireBench accepts the legacy decimal-string
sensor heights written by older observation standardizers. A separate model file, including a copy
of the observation file, must still record canonical numeric model heights.

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

Use `H013_T` to list or run only the TSO KPI variants. `H013_W` retains both TSO and all-sources
variants; all-sources KPIs remain zero-weight diagnostics.
