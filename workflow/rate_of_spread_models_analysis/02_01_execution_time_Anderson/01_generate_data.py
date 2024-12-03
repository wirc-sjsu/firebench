from datetime import datetime

import firebench.ros_models as rm
import firebench.tools as ft
import h5py
import numpy as np
from firebench import svn, Quantity
from SALib.analyze import sobol
import time

#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Workflow Configuration
output_data_filename = "output_data"
logging_level = 20  # DEBUG (10), INFO (20), WARNING (30), ERROR (40), CRITICAL (50)

# Rate of Spread Model as RateOfSpreadModel class
## Vegetation ROS models
##   - rm.Rothermel_SFIRE
##   - rm.Balbi_2022_fixed_SFIRE
ros_model = rm.Rothermel_SFIRE
compute_ros_func = ros_model.rothermel
# ros_model = rm.Balbi_2022_fixed_SFIRE
# compute_ros_func = ros_model.balbi_2022_fixed

# Environmental variables to check for the rate of spread models (can differ for each tested model)
# Typical variables for Rothermel
input_vars_info = {
    svn.WIND_SPEED: {"unit": "m/s", "range": [-15, 15]},
    svn.SLOPE_ANGLE: {"unit": "degree", "range": [-45, 45]},
    svn.FUEL_MOISTURE_CONTENT: {"unit": "percent", "range": [1, 50]},
}

# Sobol Sequence Configuration
num_sobol_points = 2**10  # Number of points for Sobol sequence, better if 2^N

#######################################################################################
#                             STEP 1: DESIGN OF EXPERIMENT
#######################################################################################

# Fuel Model Configuration
fuel_model_name = "Anderson13"
local_path_json_fuel_db = None

# create logging file
ft.logging_config.create_file_handler("firebench.log")
ft.set_logging_level(logging_level)

# Import fuel data
fuel_data = ft.read_fuel_data_file(fuel_model_name, local_path_json_fuel_db=local_path_json_fuel_db)

# Add constant missing data
fuel_data[svn.FUEL_LOAD_DEAD_RATIO] = Quantity(1, "dimensionless")

# Create Sobol sequence and final data dictionary
input_vars_dict, sobol_problem, num_total_points = ft.sobol_seq(num_sobol_points, input_vars_info)
input_dict = ft.merge_dictionaries(fuel_data, input_vars_dict)

#######################################################################################
#                             STEP 2: DATA QUALITY CHECK
#######################################################################################

input_checked = ft.check_data_quality_ros_model(input_dict=input_dict, ros_model=ros_model)
final_input = ft.extract_magnitudes(input_checked)

#######################################################################################
#                             STEP 3: ROS MODEL
#######################################################################################

# Compute rate of spread (ROS) and Sobol indices
ros = np.zeros((num_total_points, fuel_data["nb_fuel_classes"]))
time_execution = np.zeros((num_total_points, fuel_data["nb_fuel_classes"]))
model_inputs = final_input.copy()

for k in range(num_total_points):
    # select variable from sobol sequence
    for key in input_vars_info.keys():
        model_inputs[key] = final_input[key][k]

    for i, fuel_class in enumerate(range(1, fuel_data["nb_fuel_classes"] + 1)):

        input_dict_ros_model = ros_model.prepare_fuel_properties(
            model_inputs, ros_model.metadata, fuel_cat=fuel_class
        )

        # time rate of spread function
        start_time = time.perf_counter()
        ros[k, i] = compute_ros_func(**input_dict_ros_model)
        time_execution[k, i] = time.perf_counter() - start_time

# Assign unit to ROS and convert to m/s
ros_quantity = Quantity(ros, ros_model.metadata["rate_of_spread"]["units"]).to("m/s")
time_execution_q = Quantity(time_execution, "s")

#######################################################################################
#                             STEP 4: SAVE DATA
#######################################################################################

# Generate output file path
if output_data_filename.endswith(".h5"):
    output_file_path = output_data_filename
else:
    output_file_path = f"{output_data_filename}.h5"

with h5py.File(output_file_path, "w") as f:
    # Add file attributes
    f.attrs["description"] = "Sensitivity workflow for rate of spread model using firebench package"
    f.attrs["date"] = str(datetime.now())

    # Save fuel input data
    fuel_group = f.create_group("fuel")
    fuel_group.attrs["description"] = "Fuel Model data"
    fuel_group.attrs["fuel_model_name"] = fuel_model_name
    for key, value in fuel_data.items():
        is_standard_var = isinstance(key, ft.StandardVariableNames)
        key = key.value if is_standard_var else key
        unit = getattr(value, "units", None)
        magnitude = getattr(value, "magnitude", value)
        dataset = fuel_group.create_dataset(key, data=magnitude)
        dataset.attrs["units"] = str(unit)
        dataset.attrs["is_part_of_firebench_StandardVariableNames"] = is_standard_var

    # Save sensitivity input variables
    sensitivity_group = f.create_group("sensitivity_vars")
    sensitivity_group.attrs["description"] = "Variables used for the sensitivity analysis"
    for key, value in input_vars_dict.items():
        is_standard_var = isinstance(key, ft.StandardVariableNames)
        key = key.value if is_standard_var else key
        unit = getattr(value, "units", None)
        magnitude = getattr(value, "magnitude", value)
        dataset = sensitivity_group.create_dataset(key, data=magnitude)
        dataset.attrs["units"] = str(unit)
        dataset.attrs["is_part_of_firebench_StandardVariableNames"] = is_standard_var

    # Save raw outputs
    output_group = f.create_group("outputs")
    output_group.attrs["description"] = "Output of the workflow"

    # Save ROS data
    ros_dataset = output_group.create_dataset("rate_of_spread", data=ros_quantity.magnitude)
    ros_dataset.attrs["units"] = str(ros_quantity.units)
    # Save ROS data
    ros_dataset = output_group.create_dataset("time_exec", data=time_execution_q.magnitude)
    ros_dataset.attrs["units"] = str(time_execution_q.units)
