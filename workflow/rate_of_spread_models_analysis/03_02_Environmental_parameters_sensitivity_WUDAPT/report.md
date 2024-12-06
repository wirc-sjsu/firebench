# Hamada 1 model validation using WUDAPT urban fuel model

## Workflow information

- Documentation page:
- Version: 1.0
- Date of record creation: 2024-12-05
- Date of upload to firebench:
- Version/tag/commit firebench:

## Configuration

- Rate of spread model: ... using ... implementation.
- Number of point Sobol: 2^15
- The spread direction is fixed with (`NORMAL_SPREAD_DIR_X`, `NORMAL_SPREAD_DIR_Y`) = (1, 0)
- The wind speed and wind direction with change in the Sobol sequence and then be projected to get the necessary input for Hamada model `WIND_SPEED_U` and `WIND_SPEED_V`.

## Specific inputs
<!-- Add specific input details for the model/data you are using -->
- Number of point Sobol: 32,768 = 2^15
- The environmental variables chosen for this test are:
  - `WIND_SPEED` from 0 to 15 m s-1,
  - `DIRECTION` from 0 to 360 deg,
  - ...
  
## Results

<!-- Fill in with your results -->
**Fig.1** shows Sobol indices for 

<div style="text-align: center;">
    <img src="sobol_index.png" alt="Sobol index" style="width: 100%; max-width: 1200px;"/>
</div>
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Sensitivity analysis of ... rate of spread model for WUDAPT urban fuel model. 
    </em>
</p>

## Data
<!-- Add path or source of the record used for the test and its record -->
- path to data:
<!-- firebench-hash-list -->
<!-- end of firebench-hash-list -->
