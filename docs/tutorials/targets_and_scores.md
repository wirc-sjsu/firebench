# Understand Benchmark Targets and Scores

A FireBench run combines a case, a target, model output, and observations. The case chooses the
scientific evaluation; the target selects a time period, KPI groups, and aggregation.

## Read a target

In `H013_P`, `H013` is the 13th 48-hour HRRR-aligned period and `P` selects fire-perimeter KPIs.
Period flags can combine building damage (`B`), perimeters (`P`), and weather (`W`), so
`H013_BPW` selects all three groups. Curated periods use `P01` through `P04`.

```bash
firebench list 2021_Caldor
firebench list 2021_Caldor H013_P --obs-data Caldor.h5
```

The first command is the discovery view. The second is the reproducibility view: it prints the
resolved period, groups, observations, KPI identifiers, weights, and normalization parameters.

## Follow a score

For each KPI, FireBench computes a metric in its physical or statistical units. A normalization
function maps that value to a unit score from 0 to 1. KPI weights form a group score, and group
weights form the total score. The target defines which of these branches exist.

A shortened JSON scorecard looks like this:

```json
{
  "score_card": {
    "Scheme": {
      "Fire Perimeters": {
        "weight": 1,
        "FB001-FP001": {"weight": 1}
      }
    },
    "Score Fire Perimeters": 0.82,
    "Score Total": 0.82,
    "benchmark_target_name": "H013_P"
  }
}
```

The corresponding PDF presents the same hierarchy as a table. Start at `Score Total`, inspect each
group score, then inspect the metric and normalized unit score for individual KPIs. Do not compare
totals produced by different targets, weights, normalization parameters, or FireBench versions.

See [Metrics, KPIs, Normalization, and Scores](../metrics/index.md) for the formulas and the
[Caldor specification](../benchmarks/California/01_Caldor.md#benchmark-targets-in-firebench-010)
for retained and period-based targets.
