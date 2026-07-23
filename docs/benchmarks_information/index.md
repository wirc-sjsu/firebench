# Benchmark Methodology

This section gives an overview of the FireBench benchmarking process.

1. **Collection of observational data**
   FireBench collects and curates observational datasets related to fire across multiple scales, including:

   * Large wildfire events
   * Prescribed burns
   * Laboratory-scale experiments

2. **Diversity of observations**
   Observational datasets may describe different aspects of fire-related phenomena, such as:

   * Fire spread and progression
   * Weather and atmospheric conditions
   * Fuel properties
   * Building damage and impacts

3. **Standardization of observational data**
   All observational datasets are standardized and stored in a **FireBench standard file format**.
   This common format:

   * Simplifies benchmarking operations
   * Ensures consistency across datasets
   * Centralizes heterogeneous observations under a single structure

4. **Standardization of model outputs**
   Evaluated model outputs are converted to the same standard file format using FireBench's public
   standardization tools.

   * Follow [Prepare a Model-Output HDF5 File](../tutorials/prepare_model_output.md) for a runnable
     example.
   * Use [validation guidance](../how_to/validate_hdf5.md) to diagnose incompatible files.

5. **Benchmark execution**
   Once both:

   * an observational standard file, and
   * a model output standard file

   are available, FireBench provides **benchmark scripts** (Python files) that:

   * Run a predefined or custom set of benchmarks
   * Compare model outputs against observations

6. **Scorecard generation**
   Each benchmark run produces a **scorecard** that summarizes evaluation results:

   * Qualitative and quantitative performance indicators
   * Delivered as both **JSON** (machine-readable) and **PDF** (human-readable) formats

7. **Metrics and evaluation methodology**
   The definitions of:

   * Metrics
   * Key Performance Indicators (KPIs)
   * Normalization and aggregation functions

   are described in detail in the documentation and are shared across all benchmarks for transparency and reproducibility.

8. **Distribution of benchmarks**
   Benchmark datasets and benchmark scripts are distributed via **Zenodo**.
   Running the benchmarks requires the **FireBench Python library**.

9. **Certification and authenticity (optional)**
   FireBench's public signing and verification functions support certificates of authenticity.
   These certificates can be used to:

   * Authenticate datasets
   * Certify benchmark executions
   * Validate published benchmarking results

   See [Sign and Verify Results](../how_to/sign_results.md) for the available API and trust model.
