# Use Fuel Models

FireBench includes bundled fuel models and can load custom tabular fuel data from a CSV file plus a
JSON metadata file. The metadata maps each CSV column to the
[standard namespace](../namespace.md), a Pint-compatible unit, and a NumPy data type.

## Load a Bundled Fuel Model

Bundled models have wrapper functions that can add model-specific complementary fields. For
example:

```python
import firebench.tools as ft

anderson = ft.import_anderson_13_fuel_model(add_complementary_fields=True)
scott_burgan = ft.import_scott_burgan_40_fuel_model(add_complementary_fields=True)
```

Use the lower-level reader when no model-specific processing is needed:

```python
import firebench.tools as ft

scott_burgan = ft.read_fuel_data_file("ScottandBurgan40")
```

See [Models Used in FireBench](../fire_models_info/index.md) for the bundled model descriptions.

## Understand the File Pair

The CSV file contains one column per variable and one row per fuel class. The JSON file contains:

- `data_path`: the CSV filename, resolved relative to the JSON file;
- `metadata`: one entry for each CSV column;
- `variable_name`: a value from the FireBench standard namespace;
- `unit`: a unit understood by Pint;
- `type`: a NumPy data type used when the column is loaded.

The JSON metadata keys must match the CSV headers exactly.

## Create a Custom Fuel Model

Create a directory named `custom_fuel_models`. Save the following CSV content as
`custom_fuel_models/my_custom_fuel_model.csv`:

```text
height,load
0.3,0.7
1.0,1.2
```

Save the following valid JSON document as `custom_fuel_models/my_custom_fuel_model.json`:

```json
{
  "data_path": "my_custom_fuel_model.csv",
  "metadata": {
    "height": {
      "variable_name": "fuel_height",
      "unit": "m",
      "type": "float64"
    },
    "load": {
      "variable_name": "fuel_load_dry_total",
      "unit": "kg/m^2",
      "type": "float64"
    }
  }
}
```

## Load and Check the Custom Model

Run this script from the directory that contains `custom_fuel_models`:

```python
from pathlib import Path

import firebench.tools as ft

fuel_model_directory = Path("custom_fuel_models")
fuel_data = ft.read_fuel_data_file(
    fuel_model_name="my_custom_fuel_model",
    local_path_json_fuel_db=fuel_model_directory,
)

assert fuel_data["nb_fuel_classes"] == 2
assert fuel_data[ft.StandardVariableNames.FUEL_HEIGHT].to("m").magnitude.tolist() == [0.3, 1.0]
assert fuel_data[ft.StandardVariableNames.FUEL_LOAD_DRY_TOTAL].to("kg/m^2").magnitude.tolist() == [
    0.7,
    1.2,
]
```

If a model with that name is not found in `local_path_json_fuel_db`, FireBench falls back to its
bundled fuel-model data directory. A missing model raises `FileNotFoundError`; an unknown
`variable_name` is loaded without units and produces a warning.
