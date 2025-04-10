# WUDAPT 10 fuel model
## Description

The **World Urban Database and Access Portal Tools (WUDAPT)** [1-3] is an international initiative aimed at collecting and providing consistent data on urban morphology and function across global cities. Utilizing the Local Climate Zone (LCZ) classification system, WUDAPT categorizes urban areas based on characteristics such as building height, density, and land cover. This standardized framework facilitates the analysis of urban environments in relation to climate, weather, and environmental studies. 

While WUDAPT primarily focuses on urban climate studies, the detailed information it offers on building properties—such as dimensions, materials, and spatial distribution—can be valuable for assessing urban fires. 

## Firebench dataset content

Variable name in dataset    | Unit  | Standard Variable Name    | type      | Source
------------------------    | ----  | ----------------------    | ----      | ------
side_length                 | m     | building_length_side      | float64   | [1,3]
separation                  | m     | building_length_separation| float64   | [1,3]

## Usage

Import the WUDAPT fuel model data using `FireBench` with:
```python
import firebench.tools as ft
fuel_data = ft.import_wudapt_fuel_model()
```
The data is stored in the dictionnary `fuel_data`. The keys are the standard variable names and the values are numpy array associated with pint unit.

![blockdiagram](../../_static/diagram_blocks/fuel_model/WUDAPT_urban.svg)

## Compatibility with fire models

Compatibility levels:
- **Full**: The data contained in the fuel model covers *all* the fuel input needed by the fire model
- **Partial**: The data contained in the fuel model covers *some* of the fuel input needed by the fire model
- **None**: The data contained in the fuel model covers *none* of the fuel input needed by the fire model


Fire model              | Category          | Compatibility level
----------              | --------          | -----------------
Rothermel_SFIRE         | ROS vegetation    | None
Balbi_2022_fixed_SFIRE  | ROS vegetation    | None
Hamada_1                | ROS urban         | Full
Hamada_2                | ROS urban         | Full


## References

[1] [Ching, J., Mills, G., Bechtel, B., See, L., Feddema, J., Wang, X., ... & Theeuwes, N. (2018). WUDAPT: An urban weather, climate, and environmental modeling infrastructure for the anthropocene. Bulletin of the American Meteorological Society, 99(9), 1907-1924.](https://doi.org/10.1175/BAMS-D-16-0236.1)

[2] [Bechtel, B., Alexander, P. J., Böhner, J., Ching, J., Conrad, O., Feddema, J., ... & Stewart, I. (2015). Mapping local climate zones for a worldwide database of the form and function of cities. ISPRS International Journal of Geo-Information, 4(1), 199-219.](https://doi.org/10.3390/ijgi4010199)

[3] [Stewart, I. D., & Oke, T. R. (2012). Local climate zones for urban temperature studies. Bulletin of the American Meteorological Society, 93(12), 1879-1900.](https://doi.org/10.1175/BAMS-D-11-00019.1)