# Create a custom rate-of-spread model

FireBench rate-of-spread models inherit from
`firebench.ros_models.RateOfSpreadModel`. A compatible model provides:

- a `metadata` dictionary that maps the model's local variable names to the
  [standard variable namespace](../namespace.md);
- a `compute_ros` method for values that are already expressed as magnitudes in the metadata units;
- a `compute_ros_with_units` method that accepts Pint quantities, converts them to the metadata
  units, validates them, and returns a quantity.

The complete example below implements a deliberately simple wind-driven model:

\[
R = \alpha U,
\]

where \(R\) is the rate of spread in metres per second, \(U\) is the wind speed in metres per
second, and \(\alpha\) is a dimensionless wind factor. The model is useful as a compact example of
the FireBench interface; it is not intended to represent a physical fire-spread formulation.

## Define the model

Copy this code into `wind_driven_ros.py`:

```python
from pint import Quantity

import firebench.tools as ft
from firebench.ros_models import RateOfSpreadModel


class WindDrivenROS(RateOfSpreadModel):
    """Minimal wind-driven rate-of-spread model."""

    metadata = {
        "wind_speed": {
            "std_name": ft.StandardVariableNames.WIND_SPEED,
            "units": ft.ureg.meter / ft.ureg.second,
            "range": (0.0, 100.0),
            "type": ft.ParameterType.input,
        },
        "wind_factor": {
            "std_name": ft.StandardVariableNames.ALPHA,
            "units": ft.ureg.dimensionless,
            "range": (0.0, 1.0),
            "type": ft.ParameterType.optional,
            "default": 0.04,
        },
        "rate_of_spread": {
            "std_name": ft.StandardVariableNames.RATE_OF_SPREAD,
            "units": ft.ureg.meter / ft.ureg.second,
            "range": (0.0, float("inf")),
            "type": ft.ParameterType.output,
        },
    }

    @staticmethod
    def wind_driven_ros(wind_speed: float, wind_factor: float) -> float:
        """Return rate of spread in metres per second."""
        return wind_factor * wind_speed

    @staticmethod
    def compute_ros(input_dict: dict, fuel_cat: int = 0, **opt) -> float:
        """Compute ROS from magnitudes expressed in the metadata units."""
        del opt
        model_inputs = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict,
            metadata=WindDrivenROS.metadata,
            fuel_cat=fuel_cat,
        )
        return WindDrivenROS.wind_driven_ros(**model_inputs)

    @staticmethod
    def compute_ros_with_units(input_dict: dict, fuel_cat: int = 0, **opt) -> Quantity:
        """Convert and validate quantities before computing ROS."""
        converted_inputs = ft.check_data_quality_ros_model(input_dict, WindDrivenROS)
        input_magnitudes = ft.extract_magnitudes(converted_inputs)
        ros = WindDrivenROS.compute_ros(input_magnitudes, fuel_cat=fuel_cat, **opt)
        return ft.ureg.Quantity(ros, WindDrivenROS.metadata["rate_of_spread"]["units"])
```

The keys at the first level of `metadata`—such as `wind_speed`—must match the arguments of the
model function. Each `std_name` is the key that callers use in `input_dict`. The other fields define
the expected unit, accepted magnitude range, and whether the variable is required, optional, or an
output. An optional variable also needs a `default` value in its metadata unit.

`fuel_cat` is a one-based category number when an input contains multiple fuel-category values. It
is ignored for scalar values. Use the default `fuel_cat=0` when all inputs are scalar.

## Run the magnitude interface

`compute_ros` expects magnitudes that already use the metadata units. Here, the wind speed is
therefore in metres per second and the result is also in metres per second:

```python
import firebench.tools as ft

from wind_driven_ros import WindDrivenROS


inputs = {
    ft.StandardVariableNames.WIND_SPEED: 5.0,
}

ros = WindDrivenROS.compute_ros(inputs)
assert ros == 0.2
print(f"{ros} m/s")
```

The optional wind factor is absent, so the model uses its default value of `0.04`.

For category-based inputs, provide an array-like value and select a category with a one-based
index:

```python
import firebench.tools as ft

from wind_driven_ros import WindDrivenROS


inputs = {
    ft.StandardVariableNames.WIND_SPEED: [2.0, 4.0, 6.0],
}

ros = WindDrivenROS.compute_ros(inputs, fuel_cat=2)
assert ros == 0.16
```

## Run the unit-aware interface

Use `compute_ros_with_units` when values carry Pint units. The data-quality helper verifies required
inputs, converts values to the metadata units, and checks their validity ranges before calculation.
This example supplies wind speed in miles per hour and overrides the optional wind factor:

```python
import firebench.tools as ft

from wind_driven_ros import WindDrivenROS


inputs = {
    ft.StandardVariableNames.WIND_SPEED: 10.0 * ft.ureg.mile / ft.ureg.hour,
    ft.StandardVariableNames.ALPHA: 0.05 * ft.ureg.dimensionless,
}

ros = WindDrivenROS.compute_ros_with_units(inputs)
assert ros.units == ft.ureg.meter / ft.ureg.second
assert abs(ros.magnitude - 0.22352) < 1e-12
print(ros)
```

Keep the two interfaces separate: pass plain numbers in the declared metadata units to
`compute_ros`, and pass quantities to `compute_ros_with_units`. The latter returns a Pint quantity
whose unit comes from the output metadata entry.
