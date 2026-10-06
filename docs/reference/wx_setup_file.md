# Weather Benchmark Setup File

`firebench wx init|plan|run|score` read a YAML setup file. The setup says *where* and *when* to
score, where observations come from, and how to score. Relative paths are resolved against the
directory of the setup file. Every datetime must carry a time zone (`Z` for UTC or an offset such as
`-07:00`) and is converted to UTC. Unknown keys are errors, and all problems of a setup are
reported at once.

```yaml
name: caldor_h12
output_dir: runs/caldor_h12
case: {id: 2021_Caldor, period: H012}
observations:
  synoptic_json: wx_caldor_fire.json
  context_hours: 24
  bbox_margin_deg: 0.0
qc:
  reviewer: firebench wx (conservative_auto)
  overrides: {}
model:
  name: HRRR
  cycle_hours: [0, 6, 12, 18]
  horizon_hours: 48
  download_workers: 8
  keep_grib: true
benchmark:
  cadences: [1]
  obs_tolerance_min: 10
  model_tolerance_s: 60
  min_coverage: 0.5
  lead_bins: [[1, 48]]
  informational_lead_bins: [[0, 0]]
  target: ALL
```

## Top level

| Key | Default | Description |
|---|---|---|
| `name` | file name | Workspace name: letters, digits, `.`, `_`, `-` |
| `output_dir` | `runs/<name>` | Workspace directory |
| `case` | none | Preset `{id, period}`: `id` is `2021_Caldor` (or `001`, `Caldor`); `period` is `H###` (HRRR cycle window) or `P##` (curated window). It sets the bounding box and window |
| `domain.bbox` | from `case` | `[lon_min, lat_min, lon_max, lat_max]` in degrees. It must lie inside the HRRR CONUS grid and overrides the preset |
| `window` | from `case` | `{start, end}` evaluation window. It overrides the preset |

The curated Caldor windows (`P##`) start and end at perimeter times, so no 48-hour cycle fits
inside them; list `model.cycles` explicitly when you use one.

## `observations`

| Key | Default | Description |
|---|---|---|
| `synoptic_json` | none | Saved Synoptic time-series payload, clipped to the window and domain. No download and no token |
| `h5` | none | Existing FireBench observation file used as is (no fetch, no QC). Mutually exclusive with `synoptic_json` |
| `token_file` | none | File holding the Synoptic token (otherwise `SYNOPTIC_TOKEN`, then `firebench keys set synoptic`) |
| `origin` | none | One concrete HTTP(S) origin; overrides `SYNOPTIC_ORIGIN` and token-linked saved origins |
| `networks` | all | Synoptic network filter, e.g. `[RAWS]` |
| `context_hours` | `24` | Observations fetched before and after the window, so the QC sees context |
| `bbox_margin_deg` | `0` | Growth of the station search box |
| `max_chunk_days` | `7` | Longest Synoptic request; shorter chunks are used automatically to stay under 100,000 station-hours |

Secrets (`token`, `api_key`, ...) are rejected in every section.

## `qc`

| Key | Default | Description |
|---|---|---|
| `reviewer` | `firebench wx (conservative_auto)` | Identity recorded by the QC finalization |
| `overrides` | `{}` | Tables of the weather QC policy (version 9), e.g. `{bounds: {air_temperature: [-40, 55, C]}}`. A table replaces the whole default table. `mode` is fixed to `conservative_auto` |
| `require_window` | `true` | Adds the evaluation window as a QC `required_windows` entry: stations with no finite observation in it are excluded |

## `model`

| Key | Default | Description |
|---|---|---|
| `name` | `HRRR` | Forecast model (HRRR only) |
| `cycle_hours` | `[0, 6, 12, 18]` | UTC cycle hours. Every cycle whose full forecast fits in the window is scored |
| `horizon_hours` | `48` | Scored horizon, clamped to the version horizon (48 h for HRRR v4, 36 h for v3) |
| `cycles` | none | Explicit list of cycles, used as given |
| `download_workers` | `8` | Parallel HRRR downloads |
| `keep_grib` | `true` | `false` deletes the cached GRIB files once a cycle is adapted |

## `benchmark`

| Key | Default | Description |
|---|---|---|
| `cadences` | `[1]` | Scoring cadences in hours: `1` and/or `3` (UTC `hour % 3 == 0`) |
| `obs_tolerance_min` | `10` | The observation of an hour is the nearest finite sample within this tolerance. It must be below half the cadence |
| `model_tolerance_s` | `60` | Tolerance on the model timestamps |
| `min_coverage` | `0.5` | Minimum share of the hours of a lead bin a station must observe to be scored |
| `lead_bins` | `[[1, 48]]` | Scored lead-time bins, in hours after the cycle |
| `informational_lead_bins` | `[[0, 0]]` | Lead bins scored in weight-0 groups (displayed, not in the total) |
| `target` | `ALL` | `ALL`, or one cadence tier such as `1H` |
| `full_name` | `false` | Show benchmark IDs in the score card |

See [Weather forecast benchmark](../benchmarks/weather_forecast.md) for the KPI definitions.
