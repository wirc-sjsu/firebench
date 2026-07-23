# Generate a Benchmark Report Skeleton

Add `--report` to a normal run:

```bash
firebench run 2021_Caldor H013_P model_output.h5 \
  --obs-data Caldor.h5 --report
```

FireBench writes `firebench_report.md` and `figures/` in the current directory. The Markdown file
records the selected target and creates sections for model description, setup, inputs,
post-processing, adapter details, review comments, and results. Caldor perimeter targets also add
comparison figures when their source geometries are available.

Edit the comments in place and keep the figures directory beside the report. The report path is
fixed; run from a dedicated result directory to isolate artifacts. Existing reports are protected
unless `--overwrite` is supplied.
