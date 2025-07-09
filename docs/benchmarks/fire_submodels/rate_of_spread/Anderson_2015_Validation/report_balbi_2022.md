# Balbi 2022

## Workflow information

- Documentation page:
- Version: 1.0
- Date of record creation: 2024-11-24
- Date of upload to firebench:
- Version/tag/commit firebench: 0.3.0a1

## Configuration

- Rate of spread model: Balbi 2022 using `firebench.ros_models.Balbi_2022_fixed_SFIRE` implementation.
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
**Fig.1** shows that Balbi 2022 is over predicting the rate fo spread in most cases.

![blockdiagram](../../../_static/workflow/rate_of_spread/Anderson_2015_Validation/Balbi_2022.png)
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
- **01_generate_data.py**: `844b5c6e877925377dea85b1b6a517f3c2aa085954e5ff6dfc67a0bbfc328ae6`
- **02_plot_data.py**: `2b613aec56ed5afb697262856e19a0b99203eb924ed54ed70487cc47a3e205bd`
- **03_create_record.py**: `7f4090fba976d4e2c9688fc697c7329724807108dad92362003fd9435b0c192d`
- **firebench.log**: `c5711d26513540d9bdcefa00862a293ead9ac18a594769388bef47d336066fba`
- **output_data.h5**: `ce9d76689d3318b6f18c9591d60f6408e8b53bf41486a3882545376d27776cd6`
- **anderson_2015_validation.png**: `3e7512f10b617f195d02c54e68e65e8753f108531978a51dddc404bd3f811efb`
<!-- end of firebench-hash-list -->