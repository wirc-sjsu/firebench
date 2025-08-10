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
- ![Accuracy](../_static/static_badges/metric-Accuracy-4477AA.svg)
- ![Efficiency](../_static/static_badges/metric-Efficiency-66CCEE.svg)
- ![Sensitivity](../_static/static_badges/metric-Sensitivity-228833.svg)
- ![Validity Range](../_static/static_badges/metric-Validity_range-CCBB44.svg)
- ![Inter-Compatibility](../_static/static_badges/metric-Inter--Compatibility-EE6677.svg)


### Model context
- ![2D fire spread/ensemble](../_static/static_badges/2D_Fire_Model-Ensemble-b8e3b2.svg)
- ![2D fire spread/8h_Forecast](../_static/static_badges/2D_Fire_Model-8h_Forecast-7dc87e.svg)
- ![2D fire spread/24h_Forecast](../_static/static_badges/2D_Fire_Model-24h_Forecast-3ba458.svg)
- ![2D fire spread/7days_Forecast](../_static/static_badges/2D_Fire_Model-7days_Forecast-0d7836.svg)
- ![2D fire spread/7days_Forecast](../_static/static_badges/2D_Fire_Model-WUI-00441b.svg)
- ![3D coupled dynamics/fire atmosphere coupling](../_static/static_badges/3D_Coupled_Dynamics-Fire_Atmosphere_Coupling-b6b6d8.svg)

- ![3D coupled dynamics/plume dynamics](../_static/static_badges/3D_Coupled_Dynamics-Plume_Dynamics-8683bd.svg)
- ![3D coupled dynamics/smoke forecast](../_static/static_badges/3D_Coupled_Dynamics-Smoke_Forecast-61409b.svg)
- ![3D coupled dynamics/high fidelity](../_static/static_badges/3D_Coupled_Dynamics-High_Fidelity-3f007d.svg)




- ![fire submodel/Crown fire](../_static/static_badges/Fire_Submodel-Crown_Fire-fee187.svg)
- ![fire submodel/Emission](../_static/static_badges/Fire_Submodel-Emission-fed673.svg)
- ![fire submodel/Flame geometry](../_static/static_badges/Fire_Submodel-Flame_Geometry-fec35e.svg)
- ![fire submodel/Fireline intensity](../_static/static_badges/Fire_Submodel-Fireline_Intensity-feaf4b.svg)
- ![fire submodel/Front tracking](../_static/static_badges/Fire_Submodel-Front_Tracking-fd9d43.svg)
- ![fire submodel/Fuel consumption](../_static/static_badges/Fire_Submodel-Fuel_Consumption-fd8a3b.svg)
- ![fire submodel/Fuel load](../_static/static_badges/Fire_Submodel-Fuel_Load-fc6a32.svg)
- ![fire submodel/Heat flux](../_static/static_badges/Fire_Submodel-Heat_Fluxes-fb4b29.svg)
- ![fire submodel/Ignition](../_static/static_badges/Fire_Submodel-Ignition-ee3122.svg)
- ![fire submodel/Radiative-Convective heat transfer](../_static/static_badges/Fire_Submodel-Radiative_Convective_Heat_Transfer-e2191c.svg)
- ![fire submodel/Rate of spread](../_static/static_badges/Fire_Submodel-Rate_of_Spread-cf0c21.svg)
- ![fire submodel/Spotting](../_static/static_badges/Fire_Submodel-Spotting-bb0026.svg)
- ![fire submodel/Terrain projection](../_static/static_badges/Fire_Submodel-Terrain_Projection-9d0026.svg)
- ![fire submodel/Wind interpolation](../_static/static_badges/Fire_Submodel-Wind_Interpolation-800026.svg)
- ![fuel moisture/canopy](../_static/static_badges/Fuel_Moisture-Canopy-c6dbef.svg)
- ![fuel moisture/dead](../_static/static_badges/Fuel_Moisture-Dead-6aaed6.svg)
- ![fuel moisture/dead/1h](../_static/static_badges/Fuel_Moisture-Dead_1h-5ba3d0.svg)
- ![fuel moisture/dead/10h](../_static/static_badges/Fuel_Moisture-Dead_10h-4a98c9.svg)
- ![fuel moisture/dead/100h](../_static/static_badges/Fuel_Moisture-Dead_100h-3b8bc2.svg)
- ![fuel moisture/dead/1000h](../_static/static_badges/Fuel_Moisture-Dead_1000h-2e7ebc.svg)
- ![fuel moisture/live](../_static/static_badges/Fuel_Moisture-Live-2070b4.svg)
- ![fuel moisture/live/herbaceous](../_static/static_badges/Fuel_Moisture-Live_herbaceous-105ba4.svg)
- ![fuel moisture/live/woody](../_static/static_badges/Fuel_Moisture-Live_woody-08468b.svg)
- ![fuel moisture/soil](../_static/static_badges/Fuel_Moisture-Soil-08306b.svg)
- ![risk/7days](../_static/static_badges/Risk-_7days-fbb6bc.svg)
- ![risk/Seasonal](../_static/static_badges/Risk-Seasonal-ed549d.svg)
- ![risk/5years](../_static/static_badges/Risk-5_Years-99017b.svg)


<!-- Following content is here to create the badges from shields.io -->
<!-- - ![status](https://img.shields.io/badge/metric-Accuracy-4477AA)
- ![status](https://img.shields.io/badge/metric-Efficiency-66CCEE)
- ![status](https://img.shields.io/badge/metric-Sensitivity-228833)
- ![status](https://img.shields.io/badge/metric-Validity_range-CCBB44)
- ![status](https://img.shields.io/badge/metric-Inter--Compatibility-EE6677) -->

<!-- - ![status](https://img.shields.io/badge/2D_Fire_Model-Ensemble-b8e3b2)
- ![status](https://img.shields.io/badge/2D_Fire_Model-8h_Forecast-7dc87e)
- ![status](https://img.shields.io/badge/2D_Fire_Model-24h_Forecast-3ba458)
- ![status](https://img.shields.io/badge/2D_Fire_Model-7days_Forecast-0d7836)
- ![status](https://img.shields.io/badge/2D_Fire_Model-WUI-00441b) -->
  
<!-- - ![status](https://img.shields.io/badge/3D_Coupled_Dynamics-Fire_Atmosphere_Coupling-b6b6d8)
- ![status](https://img.shields.io/badge/3D_Coupled_Dynamics-Plume_Dynamics-8683bd)
- ![status](https://img.shields.io/badge/3D_Coupled_Dynamics-Smoke_Forecast-61409b)
- ![status](https://img.shields.io/badge/3D_Coupled_Dynamics-High_Fidelity-3f007d) -->
  
<!-- - ![status](https://img.shields.io/badge/Fire_Submodel-Crown_Fire-fee187)
- ![status](https://img.shields.io/badge/Fire_Submodel-Emission-fed673)
- ![status](https://img.shields.io/badge/Fire_Submodel-Flame_Geometry-fec35e)
- ![status](https://img.shields.io/badge/Fire_Submodel-Fireline_Intensity-feaf4b)
- ![status](https://img.shields.io/badge/Fire_Submodel-Front_Tracking-fd9d43)
- ![status](https://img.shields.io/badge/Fire_Submodel-Fuel_Consumption-fd8a3b)
- ![status](https://img.shields.io/badge/Fire_Submodel-Fuel_Load-fc6a32)
- ![status](https://img.shields.io/badge/Fire_Submodel-Heat_Fluxes-fb4b29)
- ![status](https://img.shields.io/badge/Fire_Submodel-Ignition-ee3122)
- ![status](https://img.shields.io/badge/Fire_Submodel-Radiative_Convective_Heat_Transfer-e2191c)
- ![status](https://img.shields.io/badge/Fire_Submodel-Rate_of_Spread-cf0c21)
- ![status](https://img.shields.io/badge/Fire_Submodel-Spotting-bb0026)
- ![status](https://img.shields.io/badge/Fire_Submodel-Terrain_Projection-9d0026)
- ![status](https://img.shields.io/badge/Fire_Submodel-Wind_Interpolation-800026) -->

<!-- - ![status](https://img.shields.io/badge/Fuel_Moisture-Canopy-c6dbef)
- ![status](https://img.shields.io/badge/Fuel_Moisture-Dead-6aaed6)
- ![status](https://img.shields.io/badge/Fuel_Moisture-Dead_1h-5ba3d0)
- ![status](https://img.shields.io/badge/Fuel_Moisture-Dead_10h-4a98c9)
- ![status](https://img.shields.io/badge/Fuel_Moisture-Dead_100h-3b8bc2)
- ![status](https://img.shields.io/badge/Fuel_Moisture-Dead_1000h-2e7ebc)
- ![status](https://img.shields.io/badge/Fuel_Moisture-Live-2070b4)
- ![status](https://img.shields.io/badge/Fuel_Moisture-Live_herbaceous-105ba4)
- ![status](https://img.shields.io/badge/Fuel_Moisture-Live_woody-08468b)
- ![status](https://img.shields.io/badge/Fuel_Moisture-Soil-08306b) -->

<!-- - ![status](https://img.shields.io/badge/Danger\/Risk-<7days-fbb6bc)
- ![status](https://img.shields.io/badge/Danger\/Risk-Seasonal-ed549d)
- ![status](https://img.shields.io/badge/Danger\/Risk-5_Years-99017b) -->