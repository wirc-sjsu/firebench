# Add a Benchmark Case

Implement the case under `src/firebench/benchmarks/` and keep scientific configuration separate
from execution where practical. A case integration needs:

- a callable accepting model output, target, output paths, overwrite, signing, and observation data;
- target normalization and discovery functions with clear `ValueError` messages;
- a debug function for `run --no-run`;
- defaults for logs, observations, JSON, and PDF outputs;
- unit, functional, and regression tests for selection and stable identifiers.

Register those functions in `src/firebench/benchmarks/registry.py` under a zero-padded case ID.
Include a unique short name, documentation URL, data versions, and defaults. Then verify all public
entry points:

```bash
firebench list
firebench list CASE
firebench list CASE TARGET --obs-data observations.h5
firebench run CASE TARGET model_output.h5 --no-run
firebench data versions CASE
```

Add the case specification under `docs/benchmarks/`, link it from the benchmark index, document
dataset provenance and licensing, and add an `[Unreleased]` changelog entry.
