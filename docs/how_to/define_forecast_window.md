# Define a forecast window

A benchmark case ([Define a benchmark case from a dataset](define_benchmark_case.md)) is proposed
from a finished observation file. A **forecast window** is the reverse: the definition exists first,
the model output second, and the observations arrive afterwards. Its definition (schema
`fb-window-v1`, `firebench.benchmarks.fire_window`) says from itself alone what a model gives, so a
forecast of an active fire can be checked before anything was observed.

Nothing is scored yet: this page covers the definition, the model-output template, and the check of
a model output.

## The definition

```python
from datetime import datetime, timedelta, timezone
from firebench.benchmarks import fire_window as fw

opening = datetime(2026, 8, 22, 2, 17, tzinfo=timezone.utc)
proposal = fw.propose_window(
    "FW24-1",
    opening,
    opening + timedelta(hours=24),
    frame=[-120.6, 38.4, -120.2, 38.8],          # west, south, east, north
    fire_frame=[-120.42, 38.58, -120.38, 38.62],  # where the fire is at the opening
    std_files=["stations_01Z.h5", "stations_02Z.h5"],
)
definition = proposal["definition"]
```

| Key | What it says |
|---|---|
| `period` | `start` and `end`, UTC with `Z` |
| `frame` | the box the forecast is scored on |
| `fire_frame` | the box of the fire at the opening, inside `frame` |
| `parameters` | the parameter set of `fire_case.toml`, as in a case definition |
| `families` | what the model gives |

`std_files` are the observation files known at the opening, whole or in pieces. Only their stations
are read (names, positions, variables, sensor heights), never an observed value. A family that
cannot be asked is in `left_out` with the reason.

| Family | The model gives |
|---|---|
| `fire_arrival_time` | under `model_group` (`/spatial_2d/fire_window`): `fire_arrival_time` (n_y, n_x), a duration (`units`) after its `time_origin`, NaN where the fire did not arrive; `position_lat` and `position_lon` in degrees, each one-dimensional or the shape of the field; `time`, the times the simulation covers |
| `weather_stations` | for each station of `stations`, `/time_series/<station>/<variable>` and `time`, with a finite value at every time of `window_times(definition)`: the round edges of `cadence_minutes` from the last one at or before the start to the first one at or after the end |

`check_window(definition)` lists the problems of a document; an empty list means it can be used.
The SHA-256 of its canonical JSON names it (`fire_case_definition.definition_sha256`).

## The template

```python
fw.write_window_template(definition, "template.h5")
```

The template holds each station's group with its position, its `time`, and its variables as NaN in
the units of the parameter set, the empty group of the arrival time with what to write there, and
the definition (`read_window_definition`). It is marked `firebench_template`.

## Check a model output

```python
report = fw.check_model_for_window(definition, "model.h5")
```

The report (schema `fb-window-check-v1`) reads no observation. `accepted` is `False`, with the
`reason`, for a file that is not a FireBench standard file or is an unfilled template. Otherwise each
family has a `status`:

- `fire_arrival_time` is `eligible` when the group is whole, its `time` covers the period, and its
  grid holds `fire_frame`. `frame_coverage` is the share of `frame` the grid holds; below 1, a note
  says the model says nothing beyond its grid.
- `weather_stations` has one part per variable, `eligible` when every station asked gives it at
  every time asked, in units that convert to the parameter set's. The family is `partial` when only
  some variables are.
