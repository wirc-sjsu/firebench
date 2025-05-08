# 3. Benchmarks information

This section contains information on how to create a new benchmark during the call for benchmark period.


## Benchmark proposal template

The benchmark proposal can be a submitted as a PFF file, a markdown file, a LaTeX source file, or a shared Google Document.
It is recommended to contain:

```markdown
# Benchmark Proposal: Title of the benchmark

The title should be concise and descriptive.

## Contributors
List of contributors name(s), affiliation(s), and contact email(s) of the proposer(s). Optionally ORCID, GitHub handle, or project link

## Tags
Official `FireBench` tags (list available at the end of this page)
It is recommended to add one *Metric type* tag, at least one *Model context* tag, and at least one *Application context* tag. 
These tags are important for referecing the proposed benchmark.
Optional free tags or keywords are welcome.

## Short description
A 1-2 sentence overview of the benchmark goal, scope, and what is being tested.

## Detailed description
It should contain:
- Scientific background and motiviation.
- Description of the modeled process or scenario.
- Relevance of the benchmark to real-world application or theoretical exploration.
- Diagrams/schematics of the benchmark are welcome.

## Data description
- Input data:
    - Description of required input dataset (terrain, fuels, weather, etc.).
    - Indicate availability (Open source, proprietary with access restriction, not yet available). Open source is prefered. 
    - Indicate if data is provided with the benchmark, if it can be access upon request for running the benchmark (under which conditions), and and if the data can be integrated within `FireBench` directly.
- Expected output data:
    - Defined expected output fields and format
    - Ground truth availability (if applicable). Indicate if this data is provided with the benchmark or available upon request (under which conditions), and and if the data can be integrated within `FireBench` directly.

## Initial conditions and configuration
- Detailed description of the initial setup.
- Simulation parameters or constant
- Timeline or duration of the benchmark
- Mesh properties

## Metrics definition
- Definition of primary metrics (RMSE, bias, runtime, etc.) and derived metrics (burned area agreement, time to ignition, statistical comparison of plumes, etc.)
- Usage of existing `FireBench` post processing tools (or need for tools)
- Units and interpretation.

## Publication status
- Is this benchmark:
    - linked to a publication (in review, published, preprint)?
    - embargoed until a specific date?
- Citation to use (if applicable)

## Licensing and Use Terms
- License for any data or code provided
- Attribution and reuse policy

## Additional notes

## Optional: Benchmark difficulty
Optional indicator for difficulty to run this benchmark:
- low: fast/approximate, educational or conceptual
- medium: realistic inputs, moderate compute
- high: high fidelity, coupled models, research grade
```

## Run a benchmark and submit your results
This guide explains how to run an existing benchmark and submit your results to the `FireBench` community. The list of existing benchmarks is shared [here](https://docs.google.com/spreadsheets/d/1Ee2G6FgD-c-5fu-oPcsI3ApyQnPQvxZJwKqVOYqtj28/edit?usp=sharing).

```markdown
# FireBench Benchmark Execution Guidelines

## 1. Before you start

### Select a benchmark
- Visit the submitted benchmarks registry
- Choose a benchmark that:
    - Matches the capabilities of your model(s)
    - Has clear input data and metric definition

### Review the Benchmark Page
Read the benchmark:
- Description and objectives
- Input/output requirements
- Metrics definition
- Tags
- Evaluation procedure
- Data availability/licensing

## 2. Prepare your Evaluation

### Model setup
Clearly document:
- Your model(s) name(s), version (commit if available to share), and configuration
- Any custom parameters, or simplification
- Whether it is operational, experimental, ML-based, etc.

### Input data processing
- Follow the benchmark's instruction precisely
- Document any necessary pre-processing (*e.g.* interpolation for resolution adjustment)
- Avoid any optional processing
- Confirm compatibility of coordinate system, units, formats

### Output Requirements
- Ensure your outputs match the required fields (document any special processing needed to obtain the requested outputs).
- If uncertain, contact the benchmark proposer or the FireBench team

## 3. Run the Benchmark
- Run the simulation(s) as defined in the benchmark scenario.
- Ensure reproducibility:
    - Fix seeds if stochastic components are used
    - Log software and hardward environment (*e.g.* CPU/GPU, OS)
    - Prefer containerization (*e.g.* Docker) is available

## 4. Report Your Results
Prepare a **benchmark evaluation report** using the following structure
1. Title and benchmark ID
Match the benchmark registry title.
2. Contributors
Name(s), affiliation(s), contact, ORCID
3. Model description
Type, versions, capabilities, known limitations, etc.
4. Run configuration
Inputs used, any modifications to benchmark setup, runtime
5. Results
Raw and unprocessed outputs, visuals (plot, contours, cross sections, etc.), and computed metrics (according to the benchmark definition).
6. Interpretation
Comment on model performance, strengths/weaknesses, unexpected behavior
7. Reproducibility
Link to code or container, software version, OS, runtime environment.

Acceptable formats: PDF, markdown, or reStructuredText

## 5. Submit Your Report
Send your completed report alongside any important data voa one of the following:
- Email: aurelien.costes@sjsu.edu
```

## List of tags

### Metric type
- metric/Accuracy
- metric/Efficiency
- metric/Sensitivity
- metric/Validity range
- metric/Inter-Compatibility

### Model context
- 2D fire spread/ensemble
- 2D fire spread/long forecast
- 2D fire spread/short forecast
- 2D fire spread/WUI
- 3D coupled dynamics/fire atmosphere coupling
- 3D coupled dynamics/plume dynamics
- 3D coupled dynamics/smoke forecast
- 3D coupled dynamics/high fidelity
- fire submodel/Crown fire
- fire submodel/Emission
- fire submodel/Flame geometry
- fire submodel/Fireline intensity
- fire submodel/Front tracking
- fire submodel/Fuel consumption
- fire submodel/Fuel load
- fire submodel/Heat flux
- fire submodel/Ignition
- fire submodel/Radiative-Convective heat transfer
- fire submodel/Rate of spread
- fire submodel/Spotting
- fire submodel/Terrain projection
- fire submodel/Wind interpolation
- fuel moisture/canopy
- fuel moisture/dead
- fuel moisture/dead/1h
- fuel moisture/dead/10h
- fuel moisture/dead/100h
- fuel moisture/dead/1000h
- fuel moisture/live
- fuel moisture/live/1h
- fuel moisture/live/10h
- fuel moisture/live/100h
- fuel moisture/live/1000h
- fuel moisture/soil
- risk/immediate
- risk/long term

### Application context
- Data Assimilation
- Grass fire
- Machine Learning
- Operational use
- Physics-based
- Plume dominated
- Real time compatible
- Risk forecasting
- Wind driven
- WUI