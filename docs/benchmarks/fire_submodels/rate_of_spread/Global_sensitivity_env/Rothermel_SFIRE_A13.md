# Rothermel SFIRE using Anderson fuel model

## Workflow information

- Documentation page:
- Version: 1.1
- Date of record creation: 2024-11-22
- Date of upload to firebench: 2024-11-22
- Version/tag/commit firebench: 0.3.2a1

## Configuration
<!-- Add specific input details for the model/data you are using -->

- Rate of spread model: Rothermel using `firebench.ros_models.Rothermel_SFIRE` implementation.
- Number of point Sobol: 32,768 = 2^15
- The environmental variables chosen for this test are:
  - `WIND_SPEED` from -15 m s-1 to 15 m s-1,
  - `SLOPE_ANGLE` from -45 deg to 45 deg,
  - `FUEL_MOISTURE_CONTENT` from 1% to 50%.

## Results

<!-- Fill in with your results -->
**Fig.1** shows the first and total order Sobol indices for the Rothermel_SFIRE rate of the spread model for each class of the Anderson 13 fuel model.
The wind (blue bars) is the most important parameter, with more than 80% of the variance explained.
Then, the fuel moisture content (green bars) is important for fuel categories representing coarser fuels, which explains around 10% of the rate of spread variance.
The slope (red bars) is of relatively minor importance for Rothermel and does not significantly affect the rate of spread in the range of input chosen.

The total order indices are higher than the first order indices, indicating coupling effects between variables, mostly between wind and moisture.

![blockdiagram](../../_static/workflow/rate_of_spread/sensitivity/Rothermel_SFIRE_A13.png)
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Sensitivity analysis of Rothermel_SFIRE rate of spread model for Anderson 13 fuel model. 
    </em>
</p>

## Data
<!-- Add path or source of the record used for the test and its record -->
- path to data: `firebench/data/workflow_results/0D_models/rate_of_spread/sensitivity_anderson13/Rothermel_SFIRE.zip`
<!-- firebench-hash-list -->
- **01_generate_data.py**: `35465abd1b8503c7782131805cc8923bbcf2bae447ca685955e41a9570951ab4`
- **02_plot_data.py**: `26f50288582c32274544245aae4f64fe78724068c016b60f0ac4f4db59ce2dc4`
- **03_create_record.py**: `082b06e8c5ee55ed2c2c5993a5ec0c18f00fbd0e7efdb77ceda44f96783ab53c`
- **firebench.log**: `f8ff766820aeab45815beffd584a8bfd6b30d97d2db5439caa4e38f3c2ba50ff`
- **output_data.h5**: `d73c6fce42e9e7d204e400ed6b6bc2eb505ffca5df6c46e4a53cf8aef7d3a7d1`
- **sobol_index.png**: `f0ff229a4bf16772f17612a4052f86b495a4641c9b48a4a9840490821cd5755c`
<!-- end of firebench-hash-list -->