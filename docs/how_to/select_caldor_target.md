# Select Caldor Periods, Groups, and Schemes

Begin with discovery rather than memorizing generated targets:

```bash
firebench list 2021_Caldor
```

Choose a period: `P01` through `P04` are curated study periods and `H001` through `H062` are
48-hour HRRR-aligned periods. Append one or more flags: `B` for building damage, `P` for fire
perimeters, and `W` for weather. FireBench accepts any input order but canonicalizes it to `BPW`.

Examples:

```bash
firebench list 2021_Caldor P02_P --obs-data v2026.2/Caldor.h5
firebench list 2021_Caldor H013_BPW --obs-data v2026.2/Caldor.h5
```

Use standalone `B`, `S`, `CC`, or `FP` for building damage, burn severity, canopy-cover loss, or
all curated perimeters. Retained 0.9 names such as `CDI` and `WX_short` remain available, while `0`
returns unaggregated KPI scores. Inspect a retained scheme before use because 0.10 weights and
normalization make its scores incomparable with 0.9 scores.
