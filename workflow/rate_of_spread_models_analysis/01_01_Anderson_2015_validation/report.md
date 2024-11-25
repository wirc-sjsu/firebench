# Rate of spread model sensitivity to environmental inputs for Anderson 13 fuel model

## Workflow information

- Documentation page:
- Version: 1.0
- Date of record creation: 2024-11-24
- Date of upload to firebench:
- Version/tag/commit firebench: 0.3.0a1

## Configuration

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
**Fig.1** ...
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
<!-- end of firebench-hash-list -->