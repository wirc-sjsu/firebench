# Score a Forecast Model over a Long Period

A forecast cycle covers a few days at most: HRRR's 00, 06, 12, and 18 UTC cycles reach 48 hours. A
case's study period can be much longer: Caldor's `P01` (W1) lasts 24 days. `firebench wx stitch`
joins successive cycles into one station series over the period, which a case target then scores
like any model output.

## Choose a stitch rule

A rule names the UTC hours of the cycles and the leads each cycle gives. Every valid hour comes from
the cycle of the rule with the shortest lead within the range:

| Rule | `--cycle-hours` | `--leads` | What it measures |
|---|---|---|---|
| Freshest 6 h | `0,6,12,18` | `1-6` | The best forecast available at each hour |
| Day ahead | `0` | `25-48` | The forecast made the day before |

The leads must span the time between two cycles of the rule, otherwise some hours have no forecast
and FireBench refuses the rule. Two rules give different scores: compare models within one rule.

## Plan, stitch, and score

```bash
firebench wx stitch HRRR hrrr_P02.h5 --obs-data v2026.3/Caldor.h5 --case 2021_Caldor --period P02 \
  --cycle-hours 0,6,12,18 --leads 1-6 --plan-only
firebench wx stitch HRRR hrrr_P02.h5 --obs-data v2026.3/Caldor.h5 --case 2021_Caldor --period P02 \
  --cycle-hours 0,6,12,18 --leads 1-6 -n "HRRR, freshest 6 h"
firebench run 2021_Caldor P02_T hrrr_P02.h5 --obs-data v2026.3/Caldor.h5 -n "HRRR, freshest 6 h"
```

`--plan-only` lists the cycles, the leads each gives, and the estimated download, without touching
the network. A cycle the model's archive does not hold (NAM before 2021-09-16, GFS before version
16) or a lead beyond a cycle's horizon is refused with the reason. Use `--start` and `--end` instead
of `--case` and `--period` for any other period.

For each cycle, FireBench downloads forecast hour 0 (which carries the terrain) and the leads the
rule takes, samples them at the stations of the observation file with the model's adapter, and
deletes the GRIB files unless `--keep-grib`. The station file of each cycle is kept in
`--workdir` (by default, the output's name followed by `_segments`).

## What the file holds

- One `/time_series/station_<STID>` group per station of the observation file, at the
  station's **observation times within the period**: a case benchmark such as Caldor's pairs model
  and observation samples one by one.
- The stitched hourly values, interpolated linearly in time to those times; the wind direction is
  interpolated through the sine and cosine of its angle. A time outside the stitched hours, or next
  to a missing value, is NaN.
- The heights and adjustments the adapter declared, unchanged; FireBench refuses cycles that
  declare different heights for one station and variable.
- An observed variable the model does not forecast (10-hour fuel moisture for HRRR) as NaN, with
  the attribute `not_forecast`. Caldor's targets need every variable, so its group scores 0 instead
  of stopping the run: compare group scores.
- Root attributes: `stitch_plan` (rule, cycles, leads, estimate), `stitch_model_versions` (the
  model version of each cycle), and `time_interpolation`.

From Python, the same steps are `stitch_plan`, `fetch_segment`, and `stitch_station_files` in
`firebench.workflows.wx_stitch`.
