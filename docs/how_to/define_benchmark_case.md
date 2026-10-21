# Define a benchmark case from a dataset

A benchmark case such as Caldor (FB001) is written in Python inside FireBench. A case can also be a
**definition**: a JSON document (schema `fb-case-v1`) that says which periods and which families of
KPIs a standard file is scored on. FireBench checks a definition against its file and runs it with
its own KPI functions, so a new fire needs no FireBench code.

A definition never carries a number that changes a score. It names the parameter set it uses, and
every threshold, normalization, and weight is in FireBench's parameter file
`src/firebench/resources/benchmarks/fire_case.toml`, identified by its `version`.

## Propose a definition

```bash
firebench case propose fire.h5 --start 2026-08-22T00:00Z --end 2026-09-15T00:00Z -o case.json
```

The proposal holds every family the file allows, and says why it left out the others:

| Family | Data | KPIs |
|---|---|---|
| `fire_perimeters` | `/polygons/*` with `time` and `rel_path` | Jaccard and Dice indices (min, mean, max) per period, final burn area bias, burn area RMSE, in the case's projection (EPSG:5070) |
| `building_damage` | `/points/building_damaged/building_damage` | the six binary structure-loss metrics of FB001 |
| `burn_severity_cbi` | `/spatial_2d/ravg_cbi/ravg_composite_burn_index_severity` | the six binary metrics of high severity, where high is RAVG's class 4 (CBI ≥ 2.25) |
| `canopy_cover_loss` | `/spatial_2d/ravg_cc/ravg_canopy_cover_loss`, and the LANDFIRE canopy height, base height, and bulk density (`/spatial_2d/landfire_ch`, `landfire_cbh`, `landfire_cbd`, written by `standardize_landfire_canopy`) | RAVG's five classes (1: 0 %, 2: >0-<25 %, 3: 25-<50 %, 4: 50-<75 %, 5: 75-100 %) compared on the cells where every LANDFIRE layer is above 0 and not its fill value, and both the observations and the model give a class from 1 to 5: a cell either side leaves unburnt (9) or without a value (0) is left out, so the family scores how much canopy a model consumes where it burns, not where it burns. Class accuracy, accuracy within one class, quadratic weighted kappa, macro F1, mean absolute class error, mean class bias, the precision, recall, and F1 of high loss (class 5), and the share of the observed cells the model gives a class |
| `weather_stations` | `/time_series/station_*` | MAE, RMSE, and bias (circular for wind direction) of each station variable, min, mean, and max over stations, on trusted (TSO) and all stations |
| `fire_radiative_power` | the fire detection streams, `/unstructured/fire_detections/<stream>` (`standardize_firms_bundle`, `standardize_goes_fdc`); the model's `/time_series/fire_total` | per period: the share of the satellite FRP totals (one per overpass or scan in the case's frame, `frp_time_series`) inside the band of FRP the model gives, `fire_radiative_power_lower` to `fire_radiative_power_upper`, one KPI per observing system (geostationary, polar orbiters) and one pooled; the shares above and below the band (see `fire_case_frp`) |
| `radar_plume` | the radar cross sections, `/spatial_3d/radar/<SITE>/sections/<name>` (`radar_cross_section`), and the sweeps of the sites of `echo_top`; the model's `/spatial_3d/plume` at the radar's times and places (`fire_case_radar_model`) | per section and period: the IoU of the plume masks (radar: the plume mask of `radar.toml`; model: its tracer above a share of its largest value), the error on the plume top (90th percentile of heights) and on the plume centroid, the rank correlation of reflectivity and log tracer, and the RMSE and bias of radial velocity folded into the Nyquist interval; per site of `echo_top` and period, over the part of the site's frame the radar sees: the error and bias of the plume top, the 90th percentile of the heights of the radar's plume gates (`radar_echo_top_series`) against that of the model's plume cells; and on the radar's map grid, the IoU of both plume footprints, the error and bias of the plume top where both have one, and the distance between the footprints' centroids weighted by the top (see `fire_case_radar`). `echo_top` is optional; `propose_case` lists every site with a section |

and these periods:

- `P01`: the window given, or the span of the file's data (perimeters, station series, radar
  volumes, and fire detections);
- `P02`: from the first perimeter to the last;
- `H001`, `H002`, …: the 48 h forecast windows, starting at 00, 06, 12, and 18 UTC, that hold at
  least two perimeters and lie inside `P01` (FB001's HRRR windows).

A perimeter belongs to a period when its time is after the start, at the latest at the end: the
model starts from the perimeter at the start. It belongs to a forecast window from its start.

## Edit and check it

A definition looks like this:

```json
{
  "schema": "fb-case-v1",
  "name": "2026 McCully Fire",
  "parameters": {"set": "fire_case", "version": "2026.1"},
  "projection": "EPSG:5070",
  "periods": [
    {"name": "P01", "start": "2026-08-22T00:00:00Z", "end": "2026-09-15T00:00:00Z", "origin": "window"},
    {"name": "H001", "start": "2026-08-25T12:00:00Z", "end": "2026-08-27T12:00:00Z", "origin": "forecast_window"}
  ],
  "families": [
    {"family": "fire_perimeters", "periods": [{"period": "H001", "perimeters": ["/polygons/perimeter_2026-08-25T23:57-07:00", "/polygons/perimeter_2026-08-27T00:45-07:00"]}]},
    {"family": "burn_severity_cbi", "dataset": "/spatial_2d/ravg_cbi/ravg_composite_burn_index_severity"},
    {"family": "weather_stations", "periods": ["P01", "H001"], "station_sets": ["TSO", "ALL"]}
  ]
}
```

Remove families or periods, or add a period with the origin `custom`, then check it:

```bash
firebench case check case.json fire.h5
```

The check lists every problem: an unknown family or schema, a path missing from the file, a period
outside the file's data or empty, a perimeter period with fewer than two perimeters, or a parameter
set this FireBench does not have.

## Keep it in the file

```python
from firebench.benchmarks.fire_case_definition import write_case_definition

write_case_definition("fire.h5", definition)
```

The definition is written at `/benchmark_case/definition` with its SHA-256, which names it. Write it
before the file is signed, so that the certificate covers it.

## Run it

```bash
firebench case run fire.h5 model.h5 -t A -n "My model"
```

The target is a scheme (`A` for every group, `B`, `S`, `CC`, `FP`, `WX`, `RP`, `FR`), or a period and
flags, such as `P01_PW` (perimeters and weather stations of `P01`), `H001_T` (trusted stations only),
`P01_R` (radar plume), or `P01_F` (fire radiative power); the flags are `B`, `S`, `C`, `P`, `T`, `W`,
`R`, and `F`. KPI ids are `G-` and a family code (`FP`, `BD`, `SV`, `CC`, `WX`, `RP`, `FR`) with a
number that follows the definition. A KPI with nothing to score is left out of its group: a radar
plume KPI no volume of its period can give (no model output time within `max_time_offset`, no plume
on either side), an FRP KPI with fewer than `min_observations` observations, a canopy cover loss KPI
when the model burns no cell the observations classify.

### The FRP band

A model gives the FRP it expects over the frame of the case's `fire_radiative_power` entry as a band,
because how its heat release becomes radiated power is uncertain. WRF-SFIRE's adapter integrates the
sensible heat flux over the frame and divides it by 10 and by 5 (the sensible heat flux is taken to
be 5 to 10 times the FRP). The KPI is the share of satellite observations inside the band, between 0
and 1: an instantaneous observation against a continuous range. FireBench converts nothing; a model
that computes FRP itself gives the same value as both bounds.

Each observing system of `[fire_radiative_power.systems]` in `fire_case.toml` (geostationary: ABI;
polar orbiters: VIIRS and MODIS) has its own KPI, so GOES, which looks every few minutes, does not
outweigh the polar orbiters, which look a few times a day. A stream whose instrument no system lists
is not scored; a new instrument (a constellation such as FireSat) is a new system in the parameter
file.

The result file is the one `run_caldor_benchmark` writes, with `case_id` null and
`case_definition_sha256`, `case_schema`, and `parameters` (set, version, and the SHA-256 of the
parameter file). Whoever keeps the case gives it an id and turns the hash into it.

From Python, `load_case(definition, std_file)` (`firebench.benchmarks.fire_case`) returns the case,
with the interface of a case module: `build_registries`, `describe_available_targets`,
`resolve_benchmark_target`, `describe_composable_groups`, `compose_target`, and `run_benchmark`.
