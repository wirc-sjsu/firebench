# Score a forecast window

A forecast window ([Define a forecast window](define_forecast_window.md)) is scored once the
observations exist, even while the window is still running. Two steps do it
(`firebench.benchmarks.fire_window_scoring`): `prepare_window_model` brings the model to the
observations' times and places, and `score_window` runs the KPIs of a generic case on the result.
Neither adds a KPI: the scores are those of `fire_case`.

```python
from datetime import datetime, timezone
from firebench.benchmarks import fire_window_scoring as fws

after = datetime(2026, 8, 22, 6, 0, tzinfo=timezone.utc)  # when the forecast was received
report = fws.prepare_window_model(definition, "model.h5", "observations.h5", "prepared.h5", after=after)
result = fws.score_window(
    definition,
    "prepared.h5",
    "observations.h5",
    after=after,
    output_json="window.json",
    score_card_report="window.pdf",
    name="My model",
)
```

## Join the observation fragments

`score_window` reads one observation file. When the observations arrive in pieces (one file per
hour of weather stations, per hour of satellite passes, per perimeter), join them first with
`firebench.standardize.join_std_files`:

```python
from firebench.standardize import join_std_files

join_std_files(["wx_12h.h5", "wx_13h.h5", "passes_12h.h5", "perimeter_1.h5"], "observations.h5")
```

The series of a station and the passes and detections of a satellite stream are appended in time
order, whatever the order of the list, and a perimeter goes side by side with the others. A time
present in two pieces keeps one sample when the values agree and raises `ValueError` when they do
not; so does an attribute that differs. The quality control is not run again: each piece keeps the
result it was given. `merge_std_files` stays the tool for files that hold different groups.

## The window so far

The window so far runs from its start to the last observation in it (`data_span` of the observation
file, no later than the end of the window). Only the observations of that span are used, and the
share of the period they cover is in the result.

## Prepare

`prepare_window_model` writes `prepared.h5` and returns a report (schema `fb-window-prepared-v1`).
It refuses, with the reason, a model output `check_model_for_window` does not accept, an observation
file that is a template, an `after` outside the period, and observations that end before the window
opens. The model output is opened read-only.

**Stations.** For each station and variable the window asks, the model's series is interpolated
linearly to the times that station was observed in the window so far, in the unit of the parameter
set. The wind direction goes along the shortest arc between two samples (350 to 10 degrees passes
through 0) and is written in [0, 360). `time` is written as the observation file encodes it, so the
case counts the same samples on both sides. A variable is made only when the model's finite samples
bracket every observed time with no step over `max_step_minutes` (`[window_preparation]` of
`fire_case.toml`, 60) around them; otherwise it is left out with its reason, and nothing is
extrapolated or written as NaN. A station the model does not give is left out the same way and the
others are scored.

**Perimeters.** The observed perimeters later than `after` (later than the start when `after` is
None) are the **target**. For each one, the burnt area of the model's `fire_arrival_time` field at
that time is written as a KML file in `<out>_perimeters/`, under the perimeter's own path. The area is
the contour at 0.5 of the cells whose arrival time is finite and at most that time
(`burnt_area_polygons`): one method, no smoothing. A model that burns no cell by then gives an empty
file, which the KPIs score as no overlap and no area. The last perimeter at or before `after` is the
**starting state**: it is named in the report and the result, and no KPI uses it. The perimeters are
left out, with the reason, when the family is not asked, the model's group cannot enter the window,
fewer than `min_perimeters` (1) follow `after`, or an observed perimeter is outside the model's grid
(the evaluation on arrival time is discarded).

## Score

`score_window` builds a case in memory: `P01` from the opening to the last observation, and `P02`
from `after` to the last observation when `after` is inside the window so far, so the same score
card holds the whole window and the ahead score. The fire perimeters are scored on `P01` with the
target, and the weather stations on both periods, with the stations the prepared file holds for each
variable. `check_case` is not called: its refusals (a period inside the data, two perimeters) are the
ones a window replaces.

The result is an ordinary score card (JSON and PDF, signable with `sign=(key, signer)`) with a
`window` block: the name and hash of the window definition, `after`, `observed_until`,
`observed_share`, the `target` and the `starting_state`, and per family its `status` (`scored` or
`null`), the `reason` when null, the perimeters used, the stations given of those asked per variable,
and the stations and samples of the observations used per variable and period. A family with nothing
to score is null; when nothing at all can be scored, `score_window` raises a `ValueError` that lists
each family's reason. A file prepared for another window, or for another `after`, is refused.
