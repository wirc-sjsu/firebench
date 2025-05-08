# How to customize a rate of spread model

In `FireBench,` a rate-of-spread model is a class inherited from `firebench.ros_models.RateOfSpreadModel`.
The goal of the class is to provide a wrapper to a function that computes the rate of spread. To be compatible with other parts of the library, the wrapper contains:
- a `compute_ros` static method that takes a dictionary as input and returns the rate of spread as a float. This provides a common interface to all the rate of spread models.
- a metadata dictionary containing information about the model’s inputs and outputs. This links the ros model internal variable names and the [Standard Variable Namespace](../namespace.md). It also provides expected units and ranges for conversion handling and range check functions.
- a `compute_ros_with_units` method to allow computation of the rate of spread with unit handling.

## Structure of Rothermel_SFIRE as an example


The class `firebench.ros_models.Rothermel_SFIRE` is built around the ros model described in the static method `Rothermel`. This function computes the rate of spread with inputs (fuel_data dictionary, fuel class numbers, wind speed, slope angle, and fuel moisture content).
The wrapper class `firebench.ros_models.Rothermel_SFIRE` contains the following metadata dictionary:

```python
metadata = {
        "fgi": {
            "std_name": svn.FUEL_LOAD_DRY_TOTAL,
            "units": ureg.kilogram / ureg.meter**2,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fueldepthm": {
            "std_name": svn.FUEL_HEIGHT,
            "units": ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fueldens": {
            "std_name": svn.FUEL_DENSITY,
            "units": ureg.pound / ureg.foot**3,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "savr": {
            "std_name": svn.FUEL_SURFACE_AREA_VOLUME_RATIO,
            "units": 1 / ureg.foot,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fuelmce": {
            "std_name": svn.FUEL_MOISTURE_EXTINCTION,
            "units": ureg.percent,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "st": {
            "std_name": svn.FUEL_MINERAL_CONTENT_TOTAL,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "se": {
            "std_name": svn.FUEL_MINERAL_CONTENT_EFFECTIVE,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "ichap": {
            "std_name": svn.FUEL_CHAPARRAL_FLAG,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "wind": {
            "std_name": svn.WIND_SPEED,
            "units": ureg.meter / ureg.second,
            "range": (-np.inf, np.inf),
            "type": ParameterType.input,
        },
        "slope": {
            "std_name": svn.SLOPE_ANGLE,
            "units": ureg.degree,
            "range": (-90, 90),
            "type": ParameterType.input,
        },
        "fmc": {
            "std_name": svn.FUEL_MOISTURE_CONTENT,
            "units": ureg.percent,
            "range": (0, 200),
            "type": ParameterType.input,
        },
        "rate_of_spread": {
            "std_name": svn.RATE_OF_SPREAD,
            "units": ureg.meter / ureg.second,
            "range": (0, np.inf),
            "type": ParameterType.output,
        },
    }
```

This dictionary contains each variable used in `rothermel` method:
- the name of the variable as used in the ros model function as key
- the corresponding standard name
- the expected unit of the variable
- the validity range
- the type of the variable (input, optional input, output)

In addition, the wrapper function `compute_ros` is dedicated to input redirection and data pre-processing.

## How to create a custom rate of spread class

We have a rate of spread function as follows:
```python
def custom_ros(sigma: float, wind: float):
    return 0.25 * sigma * wind ** 2
```
This function uses two variables, `sigma` and `wind`.
The metadata dictionary must contain information for each input and for the output. The wrapper function will be used to redirect inputs.

The wrapper class `MyCustomROS` can be defined as:
```python
class MyCustomROS(RateOfSpreadModel):
    metadata = {
        "sigma": {
            "std_name": svn.FUEL_LOAD_DRY_TOTAL,
            "units": ureg.kilogram / ureg.meter**2,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "wind": {
            "std_name": svn.WIND_SPEED,
            "units": ureg.meter / ureg.second,
            "range": (-np.inf, np.inf),
            "type": ParameterType.input,
        },
        "output_rate_of_spread": {
            "std_name": svn.RATE_OF_SPREAD,
            "units": ureg.meter / ureg.second,
            "range": (0, np.inf),
            "type": ParameterType.output,
        },
    }

    @staticmethod
    def custom_ros(fuel_data: dict, fuel_class: int, wind: float):
        return 0.5 * fuel_data["fgi"][fuel_class] * wind ** 2
    
    @staticmethod
    def compute_ros(
        input_dict: dict[str, list[float]],
        **opt,
    ) -> float:
        # Prepare fuel properties using the base class method
        fuel_properties = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict, metadata=MyCustomROS.metadata, fuel_cat=fuel_cat
        )

        # Calculate the rate of spread
        return MyCustomROS.custom_ros(**fuel_properties)

    @staticmethod
    def compute_ros_with_units(
        input_dict: dict[str, float | int | list[float] | list[int] | Quantity],
        fuel_cat: int = 0,
        **opt,
    ) -> Quantity:
        input_dict_no_units = extract_magnitudes(input_dict)

        return ureg.Quantity(
            MyCustomROS.compute_ros(input_dict_no_units, fuel_cat, **opt),
            MyCustomROS.metadata["rate_of_spread"]["units"],
        )
```

The function `custom_ros` is defined within the class here, but it can also be defined elsewhere and called within `compute_ros`.
