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

Copy this complete, tested module into `wind_driven_ros.py`:

```{literalinclude} ../examples/wind_driven_ros.py
:language: python
:caption: wind_driven_ros.py
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

## Connect fuel data and test the model

Real spread formulations usually declare fuel properties in `metadata`. Load a bundled or custom
fuel model as described in [Use a Custom Fuel Model](change_fuel_model_ros.md), merge its standard
variable names into the input dictionary, and choose a one-based category with `fuel_cat`. The
base class selects scalar or category values before the formula runs.

Keep a numerical regression test beside a custom model. For this example, the essential assertion
is:

```python
import firebench.tools as ft
import pytest

assert WindDrivenROS.compute_ros(
    {ft.StandardVariableNames.WIND_SPEED: 5.0}
) == pytest.approx(0.2)
```

Use `compute_ros_with_units` at analysis boundaries so incompatible units and out-of-range values
fail early; use `compute_ros` only after inputs have already been standardized.
