# CLI Reference

FireBench provides commands for benchmark discovery, managed data downloads, single-model runs,
multi-model runs, and plotting:

Command | Purpose
------- | -------
`firebench list` | List benchmark cases or inspect the targets for a case
`firebench data` | List or download registered benchmark data
`firebench run` | Run one benchmark target against model output
`firebench multirun` | Run and compare models from a YAML configuration
`firebench plot` | Generate plots from a TOML configuration

Use the built-in Click help for the options supported by the installed FireBench version:

```bash
firebench --help
firebench COMMAND --help
```

The detailed option and error-behavior reference is still being expanded. For a complete current
workflow, see [Run the Caldor Benchmark from the CLI](../tutorials/cli_caldor_benchmark.md).
