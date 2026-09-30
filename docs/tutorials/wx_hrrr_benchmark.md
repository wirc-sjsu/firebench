# Benchmark HRRR Forecasts Against Weather Stations

This tutorial runs the automated weather-forecast benchmark: from a bounding box and a time window,
FireBench builds both sides of the comparison and scores them.

1. **Observations.** Synoptic weather-station data are downloaded (or read from a saved Synoptic
   JSON), checked by the automatic `conservative_auto` weather QC, and written to a standard
   `obs.h5` tagged `data_tier: provisional`.
2. **Forecasts.** HRRR surface forecasts are downloaded from the anonymous NOAA Open Data bucket
   while the observations are processed. Only the needed GRIB2 messages are fetched.
3. **Adapter.** The embedded HRRR adapter samples each forecast cycle at the stations and declares
   every sensor-height adjustment.
4. **Scores.** Each forecast cycle is scored on an hourly cadence, and a score card is written.

Every stage is cached, so running the same setup again downloads and recomputes nothing.

## 1. Install FireBench with GRIB2 decoding

Decoding HRRR files needs the optional `eccodes` dependency:

```bash
pip install "firebench[hrrr]"
```

## 2. Create a setup from the Caldor H012 preset

A preset selects a benchmark case period and fills in the bounding box and time window for you.
`H012` is the Caldor HRRR cycle window of 2021-08-20 00Z, a single 48-hour forecast cycle.

This example uses a Synoptic JSON that was already downloaded, so no API token is needed:

```bash
firebench wx init caldor_h12.yml --case 2021_Caldor --period H012 --synoptic-json wx_caldor_fire.json
```

The command writes a commented setup file. Its core looks like this:

```yaml
name: caldor_h12
output_dir: runs/caldor_h12
case: {id: 2021_Caldor, period: H012}
observations:
  synoptic_json: wx_caldor_fire.json
  context_hours: 24
model: {name: HRRR, cycle_hours: [0, 6, 12, 18], horizon_hours: 48}
benchmark: {cadences: [1], obs_tolerance_min: 10, lead_bins: [[1, 48]], informational_lead_bins: [[0, 0]]}
```

Every key is described in the [setup file reference](../reference/wx_setup_file.md).

## 3. Check the plan

`plan` works offline. It prints the resolved domain, window, and forecast cycles, the Synoptic
request and key status, the HRRR files still to download, and which stages are up to date:

```bash
firebench wx plan caldor_h12.yml
```

## 4. Run the benchmark

```bash
firebench wx run caldor_h12.yml
```

The workspace (`runs/caldor_h12/`) contains:

| Path | Content |
|---|---|
| `observations/synoptic.json` | Synoptic payload clipped to the window (plus QC context) and domain |
| `observations/obs_qc.json`, `obs_qc.log` | QC manifest and audit log |
| `observations/obs.h5` | QC'd standard observation file (`data_tier: provisional`) |
| `models/hrrr_<YYYYMMDDHH>.h5` | HRRR sampled at the stations, one file per forecast cycle |
| `scores/HRRR_<YYYYMMDDHH>_rslt.json`, `_scorecard.pdf` | Benchmark results and score card per cycle |
| `summary.md` | Scores per cycle, excluded variables, station exclusions, declared heights |
| `wx_workflow.json`, `wx_workflow.log` | Stage manifest (cache identities) and log |

HRRR files are cached in the FireBench download cache, not in the workspace. See the cache location
and size with:

```bash
firebench cache info
```

## 5. Run it again

```bash
firebench wx run caldor_h12.yml
```

Every stage reports `skipped` and nothing is downloaded. Change a setup option and only the
affected stages run again. To force a stage, pass `--force` with `--steps`, for example
`--steps score --force`.

## 6. Use your own domain and window

Replace the preset with an explicit bounding box and a UTC window:

```bash
firebench wx init my_domain.yml --bbox=-120.8,38.6,-120.4,38.9 --start 2026-09-25T00:00Z --end 2026-09-27T00:00Z
```

FireBench scores every 00/06/12/18Z cycle whose full 48-hour forecast fits in the window. Without
`synoptic_json`, observations are downloaded from Synoptic, which needs an API token; see
[Download Synoptic observations with an API token](synoptic_api_token.md).

## 7. Score another model on the same observations

Any model file with one `/time_series/station_<STID>` group per station and hourly values can be
scored against the observations of the workspace:

```bash
firebench wx score caldor_h12.yml my_model_2021082000.h5 --cycle 2021-08-20T00:00Z --name MyModel
```

## What is scored

- **Variables.** Air temperature, relative humidity, wind speed and wind direction. HRRR has no
  10-hour fuel moisture, so that variable is listed as *excluded (no model data)* and is not scored
  as empty.
- **Cadence.** For every UTC hour, the observation is the nearest finite sample within ±10 minutes.
  A station that observes fewer than half of the hours of a lead bin is excluded from it, and the
  exclusion is reported.
- **Lead bins.** Hours 1–48 are scored. Hour 0 is the HRRR analysis, which assimilates surface
  observations, so it is shown in weight-0 groups: it is displayed but does not change the total.
- **Heights.**
  - The 10 m wind speed is brought to each station's sensor height with the neutral log law and
    HRRR's own roughness.
  - The 2 m temperature and humidity are assigned to screen-level sensors (1–3 m).
  - Each model file records the difference between the HRRR terrain height and the station
    elevation, which is a first-order temperature bias in mountains.

The full KPI specification is in [Weather forecast benchmark](../benchmarks/weather_forecast.md).
