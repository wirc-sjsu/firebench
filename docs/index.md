# FireBench Documentation

<img src="_static/images/firebench_logo.png" alt="FireBench Logo" width="300px">

FireBench is an open-source Python library for systematic benchmarking and intercomparison of fire
models. It connects standardized model output with observational datasets, metrics, normalization,
and scorecards so model evaluation can be transparent and reproducible.

## Choose Your Goal

- [Run a benchmark](tutorials/cli_caldor_benchmark.md): download the Caldor data, inspect a target,
  and run a complete CLI workflow.
- [Prepare model output](standard_format.md): learn the required HDF5 structure, metadata, names,
  units, and spatial conventions.
- [Compare model runs](reference/cli.md): start with the `multirun` command and its installed CLI
  help while the full comparison tutorial is developed.
- [Extend FireBench](how_to/index.md): use a custom fuel or rate-of-spread model, or continue to the
  contributor documentation.

If FireBench is new to you, begin with [Getting Started](getting_started/index.md) for installation
and the shortest successful workflow.

## Documentation Areas

- [Getting Started](getting_started/index.md) covers installation and initial benchmark discovery.
- [Tutorials](tutorials/index.md) provide guided, end-to-end learning workflows.
- [How-to Guides](how_to/index.md) provide focused instructions for specific tasks.
- [Reference and Concepts](reference/index.md) contains standards, scientific background,
  benchmark specifications, CLI and API reference, models, metrics, and datasets.

## Project and Community

Use [GitHub Discussions](https://github.com/wirc-sjsu/firebench/discussions) for questions and
ideas. See [Contributor Documentation](contributing/index.md) to contribute code, data,
documentation, or workflows.

```{toctree}
:maxdepth: 2
:caption: User Documentation

getting_started/index.md
tutorials/index.md
how_to/index.md
reference/index.md
```

```{toctree}
:maxdepth: 1
:caption: Contributors

contributing/index.md
```
