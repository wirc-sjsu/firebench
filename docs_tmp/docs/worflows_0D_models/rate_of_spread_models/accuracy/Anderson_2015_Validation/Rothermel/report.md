---
layout: default
title: "ROS Sensitivity to Environmental Variables"
parent: "Rate of spread models workflows"
grand_parent: "0D models"
nav_order: 1
---
# Rate of spread model validation using Anderson 2015 dataset

## Workflow information

- Documentation page:
- Version: 1.0
- Date of record creation: 2024-11-24
- Date of upload to firebench: 2024-11-24
- Version/tag/commit firebench: 0.3.0a1

## Configuration

- Rate of spread model: Rothermel using `firebench.ros_models.Rothermel_SFIRE` implementation.
- Input dataset: `firebench/data/ros_model_validation/Anderson_2015`, Table A1
- Complementary fuel data from Scott and Burgan 40.
- If fuel data is missing, use `firebench.tools.find_closest_fuel_class_by_properties` to retrieve the closest fuel category using total fuel load and fuel height with default weights.
- Use `Baughman_generalized_wind_reduction_factor_unsheltered` to compute wind reduction factor considering that the input wind height is above vegetation.

## Specific inputs
<!-- Add specific input details for the model/data you are using -->
Some fuel properties are considered as constant:
- fuel_density: 32 lb ft-3
- fuel_chaparral_flag: 0 [-]
- fuel_mineral_content_total: 0.0555 [-]
- fuel_mineral_content_effective: 0.01 [-]
  
## Results

<!-- Fill in with your results -->
**Fig.1** shows that Rothermel_SFIRE is over predicting the rate fo spread in most cases.

<div style="text-align: center;">
    <img src="anderson_2015_validation.png" alt="ROS error" style="width: 100%; max-width: 1200px;"/>
</div>
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Comparison of expected and computed rate of spread for Anderson 2015 dataset. 
    </em>
</p>

## Data
<!-- Add path or source of the record used for the test and its record -->
<!-- firebench-hash-list -->
- **01_generate_data.py**: `4ca260cf49fec8d05b61043017cdaf63d472e1705d09c25493e49de1b2577d0a`
- **02_plot_data.py**: `b9804b1d5097942017552992e6eedaa44dff1ea96cae3955e5d708e5a6d05ad9`
- **03_create_record.py**: `df451fa016231e232db32602f0f3e2668be9a235c648db5729239194471e982a`
- **firebench.log**: `4206228406a4c0fe4fdf329eea1c81f104cdbfe2ce7ed1a057b84fc1bc55c452`
- **output_data.h5**: `8aaff1cde3f1af1cde427e179ec9cd16b97aa039156a1faa1a1b488583ee9b1d`
- **anderson_2015_validation.png**: `da54b344f9cf71efb97cb06fc9444cacb12fc0bec8f66c31b49c13426c6ba803`
<!-- end of firebench-hash-list -->