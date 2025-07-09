# Hamada 2

## Workflow information

- Documentation page:
- Version: 1.0
- Date of record creation: 2024-12-16
- Date of upload to firebench: 
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

![blockdiagram](../../_static/workflow/rate_of_spread/efficiency/Hamada_2.png)
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Execution time boxplot for Hamda 1 rate of spread model using WUDAPT_urban fuel model. Fliers points not shown on the figure. 
    </em>
</p>

## Data
<!-- Add path or source of the record used for the test and its record -->
- path to data:
<!-- firebench-hash-list -->
- **01_generate_data.py**: `3e62bf5494c7c6123e5c51afa5fb374875679bc2a057b60ae1d636a585f26763`
- **02_plot_data.py**: `bc1c629dbf83d0670d634b9028c0b5c8caaa5ce95679cfc7913c0f92f4eed12c`
- **03_create_record.py**: `4a03bde596cfd51611433e83ddbed39217056e044a6d213bdca0d9b482e7e7a7`
- **firebench.log**: `662a8527ec9ba274f57419d2713da2a229b14b5e78f6f9433ebe2e99fdaa11e5`
- **output_data.h5**: `5bf5569df839b196925ca3e2190afbbd3803b8020feb1fd499cba2d7ba3a131e`
- **efficiency_box.png**: `3e32d3e5f6a38054a20309c8ab32007ac52deddb80cbcf8f65b1c491555e4a2b`
<!-- end of firebench-hash-list -->
