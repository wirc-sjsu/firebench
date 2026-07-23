# Use a Custom Fuel Model

A custom fuel model consists of a CSV table and a JSON metadata file. The metadata maps each CSV
column to a standard variable name and Pint-compatible units; the CSV holds one category per row.

Follow [Change the Fuel Model Used by a Rate-of-Spread Model](../tutorials/change_fuel_model_ros.md)
for complete, copyable files. Then load the model explicitly:

```python
import firebench.tools as ft

fuel = ft.read_fuel_data_file(
    "my_fuel_model",
    local_path_json_fuel_db="fuel_models.json",
)
```

Check that every required ROS metadata `std_name` exists in `fuel`, select categories with the
model's one-based `fuel_cat` argument, and keep the JSON and CSV under version control together.
Use a unique model name: if the local metadata does not contain it, FireBench may fall back to a
bundled model with the same name.
