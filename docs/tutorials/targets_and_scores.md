# Understand Benchmark Targets and Scores

A FireBench run combines a case, a target, model output, and observations. The case chooses the
scientific evaluation; the target selects a time period, KPI groups, and aggregation.

## Read a target

In `H013_P`, `H013` is the 13th 48-hour HRRR-aligned period and `P` selects fire-perimeter KPIs.
Period flags can combine building damage (`B`), perimeters (`P`), and TSO-only weather (`T`), so
`H013_BPT` selects all three groups without all-sources diagnostics. Use `W` instead of `T` to
include both TSO and all-sources weather KPIs. Curated periods use `P01` through `P04`.

```bash
firebench list 2021_Caldor
firebench list 2021_Caldor H013_P --obs-data v2026.2/Caldor.h5
```

The first command is the discovery view. The second is the reproducibility view: it prints the
resolved period, groups, observations, KPI identifiers, weights, and normalization parameters.

## Follow a score

For each KPI, FireBench computes a metric in its physical or statistical units. A normalization
function maps that value to a unit score from 0 to 100. KPI weights form a group score, and group
weights form the total score on the same 0-to-100 scale. The target defines which of these branches
exist.

The following `Caldor_rslt.json` is the result of the five-minute smoke test, which uses the Caldor
observations as both model output and reference data. Only the timestamp, hashes, and
evaluated-model label have been anonymized; the benchmark IDs, KPI values, scores, weights, and
target metadata are unchanged.

```json
{
  "benchmark_script": "<anonymized SHA-256>",
  "benchmark_short_name": "2021_Caldor",
  "benchmarks": {
    "FB001_FPH097": {
      "Average Jaccard Index WH13": 1.0,
      "Score": 100.0
    },
    "FB001_FPH098": {
      "Minimum Jaccard Index WH13": 1.0,
      "Score": 100.0
    },
    "FB001_FPH099": {
      "Maximum Jaccard Index WH13": 1.0,
      "Score": 100.0
    },
    "FB001_FPH100": {
      "Average Dice-Sorensen Index WH13": 0.9999999999999998,
      "Score": 99.99999999999997
    },
    "FB001_FPH101": {
      "Minimum Dice-Sorensen Index WH13": 0.9999999999999997,
      "Score": 99.99999999999997
    },
    "FB001_FPH102": {
      "Maximum Dice-Sorensen Index WH13": 1.0,
      "Score": 100.0
    },
    "FB001_FPH103": {
      "Final Burn Area Bias WH13": 0.0,
      "Score": 100.0
    },
    "FB001_FPH104": {
      "Burn Area RMSE WH13": 0.0,
      "Score": 100.0
    }
  },
  "case_id": "FB001",
  "case_name": "Caldor 2021",
  "case_version": "2026.2",
  "created_on": "<anonymized ISO 8601 timestamp>",
  "evaluated_model_name": "<anonymized model name>",
  "firebench_version": "0.10",
  "model_output": "<anonymized SHA-256>",
  "obs_dataset_hash": "<same anonymized SHA-256 as model_output>",
  "score_card": {
    "Scheme": {
      "FP_H13": {
        "benchmarks": {
          "FB001_FPH097": 2,
          "FB001_FPH098": 1,
          "FB001_FPH099": 0,
          "FB001_FPH100": 0,
          "FB001_FPH101": 0,
          "FB001_FPH102": 0,
          "FB001_FPH103": 1,
          "FB001_FPH104": 1
        },
        "weight": 1
      }
    },
    "Score FP_H13": 100.0,
    "Score Total": 100.0,
    "aggregation_scheme_name": "H013_P",
    "benchmark_target_name": "H013_P",
    "group_display_names": {
      "FP_H13": "Fire Perimeters"
    }
  },
  "score_card_report_hash": "<anonymized SHA-256>"
}
```

Read the result from the bottom of the hierarchy upward:

1. `benchmarks` contains each raw KPI value and its normalized 0-to-100 `Score`. For example, the
   average Jaccard value is `1.0`, while its normalized score is `100.0`.
2. `Scheme.FP_H13.benchmarks` assigns aggregation weights. A weight of `0` retains a diagnostic in
   the result without allowing it to affect the group or total score.
3. `Score FP_H13` is the weighted fire-perimeter group score. Because this target contains one
   group with weight `1`, `Score Total` is also `100.0`.

Values such as `99.99999999999997` are normal floating-point representations of a value that is
effectively 100. The PDF rounds scores for display but presents the same hierarchy. Do not compare
totals produced by different targets, weights, normalization parameters, or FireBench versions.

See [Metrics, KPIs, Normalization, and Scores](../metrics/index.md) for the formulas and the
[Caldor specification](../benchmarks/California/01_Caldor.md#benchmark-targets-in-firebench-010)
for retained and period-based targets.
