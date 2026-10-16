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
| `weather_stations` | `/time_series/station_*` | MAE, RMSE, and bias (circular for wind direction) of each station variable, min, mean, and max over stations, on trusted (TSO) and all stations |

and these periods:

- `P01`: the window given, or the span of the file's data;
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

The target is a scheme (`A` for every group, `B`, `S`, `FP`, `WX`), or a period and flags, such as
`P01_PW` (perimeters and weather stations of `P01`) or `H001_T` (trusted stations only). KPI ids are
`G-` and a family code (`FP`, `BD`, `SV`, `WX`) with a number that follows the definition.

The result file is the one `run_caldor_benchmark` writes, with `case_id` null and
`case_definition_sha256`, `case_schema`, and `parameters` (set, version, and the SHA-256 of the
parameter file). Whoever keeps the case gives it an id and turns the hash into it.

From Python, `load_case(definition, std_file)` (`firebench.benchmarks.fire_case`) returns the case,
with the interface of a case module: `build_registries`, `describe_available_targets`,
`resolve_benchmark_target`, `describe_composable_groups`, `compose_target`, and `run_benchmark`.
