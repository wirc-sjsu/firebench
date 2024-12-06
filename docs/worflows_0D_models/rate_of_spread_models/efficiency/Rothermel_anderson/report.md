---
layout: default
title: "Rothermel execution time for Anderson fuel model"
parent: "Rate of spread models workflows"
grand_parent: "0D models"
math: mathjax
nav_order: 2
---
# Rothermel_SFIRE model execution time using Anderson 2015 dataset

## Workflow information

- Documentation page:
- Version: 1.0
- Date of record creation: 2024-12-03
- Date of upload to firebench: 2024-12-03
- Version/tag/commit firebench: 0.3.1a0

## Configuration

- Rate of spread model: Rothermel using `firebench.ros_models.Rothermel_SFIRE` implementation.
- Number of point Sobol: 2^10

## Specific inputs
<!-- Add specific input details for the model/data you are using -->
- The environmental variables chosen for this test are:
  - `WIND_SPEED` from -15 m s-1 to 15 m s-1,
  - `SLOPE_ANGLE` from -45 deg to 45 deg,
  - `FUEL_MOISTURE_CONTENT` from 1% to 50%.

## Hardware/software description

- Apple M2, macOS 14.7.1
- Python 3.10.8

## Results

<!-- Fill in with your results -->
**Fig.1**  shows the execution time aggregated for all fuel classes (total) and for each fuel class.
As fuel category 4 uses a different rate of spread calculation within the SFIRE implementation of Rothermel, a difference in performance is expected.
Overall, the performance is very similar for each fuel category and a mean execution time of 6.098 $$\mu$$s over 106,496 samples.

<div style="text-align: center;">
    <img src="efficiency_box.png" alt="Exec time" style="width: 100%; max-width: 1200px;"/>
</div>
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Execution time boxplot for Rothermel rate of spread model using Anderson13 fuel model. Fliers points not shown on the figure. 
    </em>
</p>

## Data
<!-- Add path or source of the record used for the test and its record -->
- path to data:
<!-- firebench-hash-list -->
- **01_generate_data.py**: `ab95fdc101ae108b3d1592ec0291febf07621e3001c989b0973f2c9d69e48af1`
- **02_plot_data.py**: `6e8398298215938a08900555bb04390e4a9281cbb250f6fbc59a66eedb28f854`
- **03_create_record.py**: `dfb138fe4ccaf999746eefdd9e23cc07453cd5b28ad8247f9eac15d7fa3d84ed`
- **firebench.log**: `8312985dbee60f749635721a6719ef0381eb2a16d4c0cdecc3cbcf67fb72d66f`
- **output_data.h5**: `ff3ad2b95c72eb61f13069329f5f0849865d653a28cd9ac0816387dfb612463f`
- **efficiency_box.png**: `ad49e9ca3f410f9df3cdc2d8dc1bc63cdba8809c149f0bc81b2172f259664235`
<!-- end of firebench-hash-list -->