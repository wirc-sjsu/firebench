# Metrics and Scores
This section describes the high-level metrics available in `FireBench`, listed as `Key Performance Indicator` (KPI). Each KPI represents one, and only one, quantitative evaluation of performance.
KPIs are based on metrics that correspond to the generalization of quantitative comparison of multiple datasets.
The KPI value can be normalized and multiple KPIs can be aggregated to construct a score.

We introduce the following definition:
- Metric is a quantifiable measure used to evaluate the performance.
- A Key Performance Indicator (KPI) is derived from one or more metrics and gives one quantitative
  evaluation for specific variables.
- Score is a number between 0 and 100, with 100 being best performance, allowing for comparison and aggregation.
- Normalization is the process to convert a KPI value (not necessarily bounded) to a Score (bounded between 0 and 100).
- Aggregation is the weighted combination of scores at the KPI-group level (Group Score) and the
  global level (Total Score).
- Benchmark is the group KPI + Normalization.

**More information about the components in the following pages**
```{toctree}
:maxdepth: 1

score.md
metrics.md
kpis.md
normalization.md
```


Figure 1 shows the relationship between the quantitative components. Each KPI is formed from one
or more metrics and can be converted to a score by a normalization function.

![blockdiagram](../_static/images/Metrics_diagram.png)
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Relationship between Metrics, KPI, Normalization and Score
    </em>
</p>

For implementation details, refer to the [API references](../api/index.rst).
A full list of metrics is also available on the [Content page](../content.md).
