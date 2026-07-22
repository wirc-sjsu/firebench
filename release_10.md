# FireBench 0.10 Documentation Refactoring Plan

## Objective

Refactor the FireBench documentation around common user goals, make the examples reliable and
runnable, and document the workflows introduced by the current package and CLI.

## Existing Strengths to Preserve

- Detailed scientific documentation for fuel models, rate-of-spread models, metrics, KPIs,
  normalization, and scoring.
- Comprehensive and reproducible benchmark specifications, particularly for the Caldor Fire case.
- Existing Sphinx and MyST infrastructure, API generation, diagrams, and navigation trees.
- A first end-to-end CLI tutorial for the Caldor benchmark.
- Existing separation of models, datasets, metrics, benchmarks, tutorials, and API material.

## Priority 0: Complete the Caldor 0.9 to 0.10 Transition

### Preserve Benchmark Identity

- [x] Preserve the FireBench 0.9 meanings of the curated Caldor weather benchmark identifiers
  `FB001_WX001` through `FB001_WX312`.
- [x] Register all curated weather periods before the new HRRR-aligned periods so that HRRR weather
  identifiers begin at `FB001_WX313`.
- [x] Add regression tests for the established curated weather ID ranges and their KPI names.
- [x] Document that FireBench 0.10 perimeter weights and normalization changed, so scores are not
  directly comparable with 0.9 scores even when a retained scheme name is used.

### Connect Retained Schemes to the Target CLI

- [x] Make `firebench list CASE TARGET` describe retained schemes without crashing, including `A`,
  `S`, `CC`, `CDI`, `BS3`, `WX1` through `WX4`, `short_all`, `WX_short`, and `0`.
- [x] Make `firebench run --report` support those retained schemes through the same target-description
  path.
- [x] Detect the new `PERIOD_FLAGS` syntax explicitly instead of treating every target containing an
  underscore as a period target.
- [x] Derive displayed KPI categories from the selected benchmark groups rather than from characters
  in a retained scheme name.
- [x] Handle target `0` explicitly as an unaggregated selection when listing target details and
  generating a report.
- [x] Retain the intentional 0.10 CLI syntax `firebench run CASE TARGET MODEL_OUTPUT`; do not restore
  the removed `-c` and `-a` options.

### Complete Target Discovery

- [x] Expose `B`, `S`, and `CC` as documented standalone targets for building damage, burn severity,
  and canopy-cover loss.
- [x] Implement the documented standalone `FP` target using all four curated fire-perimeter groups.
- [x] Continue using period-based targets for building damage, perimeters, and weather with the
  `B`, `P`, and `W` flags.
- [x] Do not add period-qualified burn-severity or canopy-cover targets because those evaluations are
  not filtered by the selected period.
- [x] Canonicalize combined target flags in `B`, `P`, `W` order while accepting flags entered in any
  order.
- [x] Show standalone targets, period syntax, available periods, and combinable flags in
  `firebench list CASE`.
- [x] Ensure every KPI printed by `firebench list CASE TARGET` has a nonempty descriptive name,
  including building damage, burn severity, canopy-cover loss, and curated perimeter KPIs.

### Document the Migration and Target Model

- [x] Explain that curated study periods `W1` through `W4` are exposed by the new CLI as `P01`
  through `P04`.
- [x] Explain that `H001` through `H062` are 48-hour HRRR-aligned periods.
- [x] Explain the `B`, `P`, and `W` target flags and show combined examples such as `H013_BPW`.
- [x] Add a 0.9-to-0.10 mapping table covering `B`, `S`, `CC`, `WX1` through `WX4`, `A`, `CDI`,
  `BS3`, `short_all`, `WX_short`, `FP`, and `0`.
- [x] Document the exact CLI migration from `firebench run -c CASE -a SCHEME MODEL_OUTPUT` to
  `firebench run CASE TARGET MODEL_OUTPUT`.
- [x] Clarify that tutorial target `H013_P` is a small perimeter-only example and is not equivalent
  to the former `CDI` tutorial command.
- [x] Update the CLI tutorial to inspect the case and selected target with `firebench list` before
  running the benchmark.
- [x] Update the Caldor specification to distinguish standalone targets, retained schemes, curated
  period targets, and HRRR-aligned targets.
- [x] Avoid manually listing every generated HRRR KPI; use CLI target inspection as the detailed
  source of truth.

### Add Transition Regression Coverage

- [x] Test that `WX1` through `WX4` select the same groups as `P01_W` through `P04_W`.
- [x] Test that standalone `B`, `S`, `CC`, and `FP` select their documented groups.
- [x] Test target listing and report metadata for representative retained schemes, underscore-named
  schemes, and target `0`.
- [x] Test deterministic normalization of combined target flags.
- [x] Test that every discoverable target produces KPI names and clear errors instead of tracebacks.

## Priority 1: Restructure the Documentation

- [x] Replace the numbered, package-oriented top-level navigation with four user-oriented areas:
  **Getting Started**, **Tutorials**, **How-to Guides**, and **Reference and Concepts**.
- [x] Move installation and the shortest successful workflow into **Getting Started**.
- [x] Put guided, end-to-end learning material in **Tutorials**.
- [x] Put focused operational instructions, such as validation, plotting, signing, and custom data
  preparation, in **How-to Guides**.
- [x] Group the file standard, namespace, CLI reference, API reference, benchmark methodology,
  models, metrics, and datasets under **Reference and Concepts**.
- [x] Separate contributor and developer documentation from end-user documentation.
- [x] Remove hard-coded section numbers from page titles so pages can be reorganized safely.
- [x] Add clear links from the landing page for the main user goals: run a benchmark, prepare model
  output, compare runs, and extend FireBench.
- [x] Reduce duplication between `README.md` and `docs/index.md`, keeping the README concise and
  directing readers to the maintained documentation.

## Priority 2: Repair and Update Existing Documentation

- [x] Update the documentation version in `docs/conf.py` so it follows the package version instead
  of remaining fixed at `0.7.0`.
- [x] Update `docs/content.md` for FireBench 0.10 or replace the manually maintained inventory with
  generated/reference pages.
- [x] Synchronize `docs/dependencies.md` with `pyproject.toml`, including Click, Contextily, Numba,
  PyYAML, and conditional Tomli.
- [x] Fix the broken `CONTRIBUTE.md` link in `README.md`.
- [x] Fix malformed email links in the Caldor benchmark documentation.
- [ ] Correct spelling, grammar, capitalization, and naming inconsistencies across user-facing pages.
- [x] Repair the custom fuel-model tutorial so its JSON example is valid and can be copied directly.
- [ ] Rewrite the custom ROS model tutorial as a complete executable example with correct imports,
  variable names, metadata keys, method signatures, and unit handling.
- [ ] Check installation instructions for clean environments and state supported Python versions,
  recommended environment setup, and development installation separately.
- [ ] Review statements that require users to contact the FireBench team and replace them with
  self-service instructions wherever the necessary tools are public.
- [ ] Review local links, images, code references, and external URLs throughout the documentation.

## Priority 3: Add Core Tutorials

### FireBench in Five Minutes

- [ ] Install FireBench in a clean environment.
- [ ] Run `firebench list` and explain the result.
- [ ] Download the Caldor dataset.
- [ ] List the available Caldor targets and explain how to select one.
- [ ] Run one small benchmark workflow.
- [ ] Identify and briefly interpret the generated JSON, PDF, and log files.
- [ ] End with links to model-output preparation and the detailed Caldor tutorial.

### Prepare a Model-Output HDF5 File

- [ ] Start from a minimal model result or small synthetic array.
- [ ] Create a FireBench standard HDF5 file using public library functions.
- [ ] Add required root attributes, groups, datasets, units, time information, and spatial metadata.
- [ ] Use names from the standard namespace.
- [ ] Validate the generated file and demonstrate how to inspect validation failures.
- [ ] Use the completed file in a benchmark command.
- [ ] Provide the complete runnable script and expected HDF5 tree.

### Understand Benchmark Targets and Scores

- [ ] Explain benchmark case identifiers and target identifiers such as `H013_P`.
- [ ] Explain temporal periods and KPI group flags.
- [ ] Explain metrics, normalization, KPI unit scores, weights, aggregation schemes, and total scores.
- [ ] Show how `firebench list CASE` and `firebench list CASE TARGET` help users inspect targets.
- [ ] Walk through a small JSON scorecard and relate it to the PDF scorecard.

### Compare Multiple Model Runs

- [ ] Introduce `firebench multirun` and its intended use.
- [ ] Provide a complete YAML configuration with at least two model outputs.
- [ ] Explain relative paths, output directories, overwrite behavior, naming, and optional fields.
- [ ] Describe the individual results and comparison scorecard that are generated.
- [ ] Include common configuration errors and how to resolve them.

### Plot and Report Benchmark Results

- [ ] Document `firebench plot` with a complete TOML configuration.
- [ ] Explain supported inputs, plot types, styling options, and generated files.
- [ ] Document `firebench run --report` and its report skeleton and figures directory.
- [ ] Show a simple workflow for adding user comments and preserving report artifacts.

### Add a Custom Rate-of-Spread Model

- [ ] Introduce the `RateOfSpreadModel` contract and metadata structure.
- [ ] Implement a minimal model with and without Pint units.
- [ ] Demonstrate input validation, unit conversion, validity ranges, and output units.
- [ ] Include a runnable example and a small test with an expected numerical result.
- [ ] Explain how the model can be connected to a fuel model and used in an analysis workflow.

## Priority 4: Add Focused How-to Guides

- [ ] How to validate an existing FireBench HDF5 file and diagnose common schema errors.
- [ ] How to convert model-specific output into the FireBench standard format.
- [ ] How to select Caldor temporal periods, KPI groups, and aggregation schemes.
- [ ] How to use custom fuel models.
- [ ] How to generate and customize plots from TOML.
- [ ] How to generate a benchmark report skeleton.
- [ ] How to sign benchmark results and verify FireBench certificates.
- [ ] How to add a benchmark case to the registry.
- [ ] How to add or update a standard namespace variable.

## Priority 5: Complete the Reference Material

- [ ] Add a complete CLI reference for `list`, `data`, `run`, `multirun`, and `plot`, including all
  options and exit/error behavior.
- [ ] Generate CLI reference content from Click where practical to prevent drift.
- [ ] Expand the API reference to cover `standardize`, `signing`, `benchmarks`, `sensors`, plotting,
  CLI, and adapter utilities.
- [ ] Review the existing API pages for missing public functions and obsolete modules.
- [ ] Correct the Sphinx import path and ensure autodoc works in a clean documentation environment.
- [ ] Document output filenames, overwrite behavior, logging, and default paths in one reference page.
- [ ] Clearly label stable, experimental, and internal APIs.

## Priority 6: Make Documentation Testable and Maintainable

- [ ] Add a CI job that installs documentation dependencies and builds Sphinx with warnings treated
  as errors.
- [ ] Add internal-link and external-link checking, with a documented policy for intermittent
  external services.
- [ ] Test Python snippets or move substantial examples into runnable files covered by `pytest`.
- [ ] Add CLI smoke tests for commands shown in tutorials.
- [ ] Add validation tests for JSON, YAML, and TOML examples.
- [ ] Add a documentation review item to the pull-request checklist for user-visible changes.
- [ ] Define a single source of truth for the package version and dependency list.
- [ ] Document how to build and preview the documentation locally.

## Suggested Delivery Sequence

- [ ] **Phase 1 — Reliable foundation:** repair broken links and examples, synchronize version and
  dependencies, and add the strict Sphinx CI build.
- [ ] **Phase 2 — User onboarding:** restructure the navigation and publish the five-minute and
  model-output HDF5 tutorials.
- [ ] **Phase 3 — Current workflows:** document targets and scores, multirun, plotting, and reports.
- [ ] **Phase 4 — Extension and reference:** replace the custom ROS tutorial, add focused how-to
  guides, and complete API and CLI reference coverage.

## Definition of Done

- [ ] A new user can install FireBench and complete a documented benchmark without undocumented
  steps.
- [ ] A model developer can create and validate a compatible HDF5 model-output file from a complete
  example.
- [ ] Every documented command and structured configuration example is checked automatically.
- [ ] The documentation builds without warnings in CI.
- [ ] Documentation version, dependencies, CLI options, and public API reference match FireBench
  0.10.
