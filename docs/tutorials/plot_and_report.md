# Plot and Report Benchmark Results

Use `firebench plot` to compare perimeter layers and `firebench run --report` to create an editable
Markdown report with benchmark context and figures.

## Generate a plot

Copy the following configuration beside `Caldor.h5` and `model_output.h5`:

```{literalinclude} ../examples/plot.toml
:language: toml
:caption: plot.toml
```

```bash
firebench plot plot.toml
```

`[[files]]` supplies the HDF5 inputs, labels, and colors. `[perimeter]` selects the HDF5 group or
specific dataset paths and controls projection, satellite tiles, opacity, line width, and figure
size. Set `satellite = false` for deterministic offline plots. The command creates one PNG per
common perimeter under `output_dir`; `dpi` controls raster resolution.

## Generate a report skeleton

Run the benchmark with `--report`:

```bash
firebench run 2021_Caldor H013_P model_output.h5 \
  --obs-data Caldor.h5 --report
```

In addition to JSON, PDF, and log outputs, this creates `firebench_report.md` and `figures/`. The
report records the normalized target, period, groups, perimeters, KPI details, and generated
figures. Add model configuration, inputs, post-processing, adapter information, and interpretation
under the supplied headings.

Keep the Markdown file and its `figures/` directory together so relative image links remain valid.
The command refuses to replace `firebench_report.md`; pass `--overwrite` only after preserving an
earlier report.
