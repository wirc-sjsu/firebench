---
layout: default
title: "Balbi 2022 sensitivity to env var for Scott and Burgan"
parent: "Rate of spread models workflows"
grand_parent: "0D models"
nav_order: 1
---
# Rate of spread model sensitivity to environmental inputs for Scott and Burgan 40 fuel model

## Workflow information

- Documentation page:
- Version: 1.0
- Date of record creation: 2024-12-16
- Date of upload to firebench: 2024-12-16
- Version/tag/commit firebench: 0.3.2a1

## Configuration

- Rate of spread model: Balbi 2022 using `firebench.ros_models.Balbi_2022_fixed_SFIRE` implementation.
- Number of point Sobol: 2^15

## Specific inputs
<!-- Add specific input details for the model/data you are using -->
The environmental variables chosen for this test are:
- Number of point Sobol: 32,768 = 2^15
- The environmental variables chosen for this test are:
  - `WIND_SPEED` from -15 to 15 m s-1,
  - `SLOPE_ANGLE` from -45 to 45 deg,
  - `FUEL_MOISTURE_CONTENT` from 1% to 50%.
  - `AIR_DENSITY` from 0.9 to 1.3 kg m-3.
  - `AIR_TEMPERATURE` from -20 to 45 celsius.
  - `FUEL_TEMPERATURE_IGNITION` from 450 to 700 K.
  - `IGNITION_LENGTH` from 10 to 50 m.
  
## Results

<!-- Fill in with your results -->
**Fig.1** shows the first and total order Sobol indices for the Balbi_2022_fixed_SFIRE rate of the spread model for each class of the Scott and Burgan 40 fuel model.
The most important parameters are the wind speed and the fuel moisture content for all fuel classes.
The wind represents most of the variability (around 55%) for fuel classes 1-14, 16-18, 20-22, and 25.
The fuel moisture content explains most of the rate of spread variance (between 50% and 80%) for classes 15, 19, 23-24, and 26-40.
The other parameters are minor as their effect on the rate of spread is limited.
In particular, the slope angle does not affect the rate of spread significantly.
The ambient environment variable (air temperature and density) is not important for the rate of spread computation, and using default values (300 K, 1.2 kg m-3) is sufficient.

<div style="text-align: center;">
    <img src="sobol_index.png" alt="Sobol index" style="width: 100%; max-width: 1200px;"/>
</div>
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Sensitivity analysis of Balbi 2022 rate of spread model for Scott and Burgan fuel model. 
    </em>
</p>

## Data
<!-- Add path or source of the record used for the test and its record -->
- path to data:
<!-- firebench-hash-list -->
- **01_generate_data.py**: `25f9b24e871e0cc9ff41abd55388631ae336d619ecf3993bca3ac057bb8e6852`
- **02_plot_data.py**: `97e82d5b8496393c0f169ef403f9373d92932bf515ed644c333322409e022dcc`
- **03_create_record.py**: `9c713448395a33afe8e7d99318f8da9f4839179b6980187c9ab81a61ad1d8e1c`
- **firebench.log**: `aea4888678681f0f2dd8721e112765b112a87d9e94918d9d35ba9de9f3f22352`
- **output_data.h5**: `19ed2214f2bdcc3e84bf332aa84df89baa52e49566a4b38bfbf70d4e55d03c40`
- **sobol_index.png**: `a4128180801dd9a3d88fba4694395cd316dc0bbad354cba5c0b80f35080af6a8`
<!-- end of firebench-hash-list -->
