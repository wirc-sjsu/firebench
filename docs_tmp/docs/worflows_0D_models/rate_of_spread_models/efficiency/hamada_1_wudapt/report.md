---
layout: default
title: "Hamada 1 execution time for WUDAPT urban fuel model"
parent: "Rate of spread models workflows"
grand_parent: "0D models"
math: mathjax
nav_order: 2
---
# Rate of spread model execution time using WUDAPT fuel model

## Workflow information

- Documentation page:
- Version: 1.0
- Date of record creation: 2024-12-16
- Date of upload to firebench: 2024-12-16
- Version/tag/commit firebench: 0.3.2a2

## Configuration

- Rate of spread model: Hamada 1
- Number of point Sobol: 2^10

## Specific inputs
<!-- Add specific input details for the model/data you are using -->
- The environmental variables chosen for this test are:
  - `WIND_SPEED` from 0 to 15 m s-1,
  - `DIRECTION` from 0 to 360 deg,
  - `BUILDING_RATIO_FIRE_RESISTANT` from 0 to 1.

## Hardware/software description

- Apple M2, macOS 14.7.1
- Python 3.10.8

## Results

<!-- Fill in with your results -->
**Fig.1**  shows the execution time aggregated for all fuel classes (total) and for each fuel class.
<div style="text-align: center;">
    <img src="efficiency_box.png" alt="Exec time" style="width: 100%; max-width: 1200px;"/>
</div>
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Execution time boxplot for Hamada 1 rate of spread model using WUDAPT_urban fuel model. Fliers points not shown on the figure. 
    </em>
</p>

## Data
<!-- Add path or source of the record used for the test and its record -->
- path to data:
<!-- firebench-hash-list -->
- **01_generate_data.py**: `cc9baf41221270cb9871160506871a15ced54f5b8bf2afa16360e07495702374`
- **02_plot_data.py**: `66eb5db4429df603ea34c0711ae79083431f9759339bb4992c8525a356ebef1b`
- **03_create_record.py**: `ae4e64e42bbd0d1057c7ff813f87e311c61db7804f565c89b110a47c78ea6ed2`
- **firebench.log**: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- **output_data.h5**: `1940474aa191fd35e1dc093f2c9de1a506adbd74fe8838e8070370b469708bc3`
- **efficiency_box.png**: `da87879e17245cbd5b0bb829492cccb33a1c5630234d3ce1a2a62e2f438383c0`
<!-- end of firebench-hash-list -->
