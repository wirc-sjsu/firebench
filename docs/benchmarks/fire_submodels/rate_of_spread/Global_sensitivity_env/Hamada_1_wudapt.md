# Hamada 1 using WUDAPT urban fuel model

## Workflow information

- Documentation page:
- Version: 1.0
- Date of record creation: 2024-12-05
- Date of upload to firebench: 2024-12-05
- Version/tag/commit firebench: 0.3.1

## Configuration

- Rate of spread model: Hamada 1 using `firebench.ros_models.Hamada_1` implementation.
- Number of point Sobol: 2^15
- The spread direction is fixed with (`NORMAL_SPREAD_DIR_X`, `NORMAL_SPREAD_DIR_Y`) = (1, 0)
- The wind speed and wind direction with change in the Sobol sequence and then be projected to get the necessary input for Hamada model `WIND_SPEED_U` and `WIND_SPEED_V`.

## Specific inputs
<!-- Add specific input details for the model/data you are using -->
- Number of point Sobol: 32,768 = 2^15
- The environmental variables chosen for this test are:
  - `WIND_SPEED` from 0 to 15 m s-1,
  - `DIRECTION` from 0 to 360 deg,
  - `BUILDING_RATIO_FIRE_RESISTANT` from 0 to 1.
  
## Results

<!-- Fill in with your results -->
**Fig.1** shows Sobol indices for Hamada 1 model for each fuel class of WUDAPT urban fuel model.
The wind direction is the most important parameter with around 65% of the variance explained.
Then wind speed is representing less then 20% of the variance. And finally the ratio of fire resistant building is marginal for most fuel class.
The small increase in total order shows a existing interaction between parameters (mostly wind direction and speed).

![blockdiagram](../../../../_static/workflow/rate_of_spread/sensitivity/Hamada_1_wudapt.png)
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Sensitivity analysis of Hamada 1 rate of spread model for WUDAPT urban fuel model. 
    </em>
</p>

## Data
<!-- Add path or source of the record used for the test and its record -->
- path to data:
<!-- firebench-hash-list -->
- **01_generate_data.py**: `c66aeada794bbfefca94875fe535f60aa4fcae7ee63fab4f190dfeb00afa7ec4`
- **02_plot_data.py**: `8141c2524e5a2d933dda0c9fb0b4ccbd571fcbccff620db16293735a52411d37`
- **03_create_record.py**: `ea3793981d43d321a618e8d646330dfcc28408d613035ca868d8311a3a9db35c`
- **firebench.log**: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- **output_data.h5**: `ad268aceb9e12b3c1c35c7bf98b00bb748d25b5934066fea6b1164c55e8bed72`
- **sobol_index.png**: `85f9c4d50a5dcc36a95f145520f7e608e3f7203daffca5911f87175e6c0a6492`
<!-- end of firebench-hash-list -->
