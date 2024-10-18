"""
Workflow: 03_01_sensitivity_env_var
Category: Sensitivity Analysis
Version: 1.0

Description:
This workflow performs a sensitivity analysis on rate of spread models using a static fuel database (e.g., Anderson, Scott & Burgan).
The analysis considers the impact of environmental variables on fire behavior, specifically focusing on:
- Wind
- Slope
- Fuel Moisture

Documentation page: https://wirc-sjsu.github.io/firebench/workflows/sensitivity/ros_sensitivity.html
"""

from datetime import datetime

import firebench.ros_models as rm
import firebench.tools as ft
import h5py
import numpy as np
from firebench import svn, ureg
from SALib.analyze import sobol

#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Workflow Configuration
workflow_record_name = "Sensitivity_env_var_Anderson13_Rothermel"
overwrite_files_in_record = True
output_filename = "Rothermel_SFIRE"

# Fuel Model Configuration
## Vegetation fuel models
##   - Anderson13
## Urban fuel models
##   - WUDAPT_urban
fuel_model_name = "Anderson13"
local_path_json_fuel_db = None

# Rate of Spread Model as RateOfSpreadModel class
## Vegetation ROS models
##   - rm.Rothermel_SFIRE
##   - rm.Balbi_2022_fixed_SFIRE
## Urban  ROS models
##   - rm.Hamada_1
##   - rm.Hamada_2
ros_model = rm.Rothermel_SFIRE
output_ros_unit = ureg.meter / ureg.second

# Sobol Sequence Configuration
num_sobol_points = 2**13  # Number of points for Sobol sequence, better if 2^N

# Input Variables Configuration
# use firebecnh unit registry ureg to define units
input_vars_info = {
    svn.WIND_SPEED: {"unit": ureg.meter / ureg.second, "range": [-15, 15]},
    svn.SLOPE_ANGLE: {"unit": ureg.degree, "range": [-45, 45]},
    svn.FUEL_MOISTURE_CONTENT: {"unit": ureg.percent, "range": [1, 50]},
}

# Logging Configuration
# set logging level, from lower to higher: NOTSET (0), DEBUG (10), INFO (20), WARNING (30), ERROR (40), CRITICAL (50)
ft.logger.setLevel(0)

#######################################################################################
#                             STEP 1: DESIGN OF EXPERIMENT
#######################################################################################

# Create workflow record directory
ft.create_record_directory(workflow_record_name)

# Copy script file to record
ft.copy_file_to_workflow_record(workflow_record_name, __file__, overwrite=overwrite_files_in_record)

# Import fuel data
fuel_data = ft.read_fuel_data_file(fuel_model_name, local_path_json_fuel_db=local_path_json_fuel_db)

# Create Sobol sequence and final data dictionary
input_vars_dict, sobol_problem, num_total_points = ft.sobol_seq(num_sobol_points, input_vars_info)
input_dict = ft.merge_dictionaries(fuel_data, input_vars_dict)

#######################################################################################
#                             STEP 2: DATA QUALITY CHECK
#######################################################################################

final_input = ft.check_data_quality_ros_model(input_dict=input_dict, ros_model=ros_model)

#######################################################################################
#                             STEP 3: ROS MODEL
#######################################################################################

# Initialize Sobol indices array (N_pts, 4, N_vars)
sobol_indices = np.zeros((fuel_data["nb_fuel_classes"], 4, len(input_vars_info)))

# Compute rate of spread (ROS) and Sobol indices
ros = np.zeros((num_total_points, fuel_data["nb_fuel_classes"]))
model_inputs = final_input.copy()
for i, fuel_class in enumerate(range(1, fuel_data["nb_fuel_classes"] + 1)):

    # Add fuel class to inputs
    model_inputs[svn.FUEL_CLASS] = fuel_class

    # select variable from sobol sequence
    for k in range(num_total_points):
        for key in input_vars_info.keys():
            model_inputs[key] = final_input[key][k]

        ros[k, i] = ros_model.compute_ros(model_inputs)

    # Perform Sobol analysis
    sobol_results = sobol.analyze(sobol_problem, ros[:, i], print_to_console=False)

    # Extract first-order and total-order indices
    sobol_indices[i, 0, :] = sobol_results["S1"]
    sobol_indices[i, 1, :] = sobol_results["S1_conf"]
    sobol_indices[i, 2, :] = sobol_results["ST"]
    sobol_indices[i, 3, :] = sobol_results["ST_conf"]

# Assign unit to ROS
ros_quantity = ureg.Quantity(ros, ros_model.metadata["output_rate_of_spread"]["units"])
# convert to user defined output unit
ros_quantity = ureg.Quantity(ros_quantity, output_ros_unit)

#######################################################################################
#                             STEP 4: SAVE DATA
#######################################################################################

# Generate output file path
output_file_path = ft.generate_file_path_in_record(
    f"output_{output_filename}.h5", workflow_record_name, overwrite_files_in_record
)

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

    # Save Sobol indices
    for name, index in [
        ("Sobol_first_order", 0),
        ("Sobol_first_order_confidence", 1),
        ("Sobol_total_order", 2),
        ("Sobol_total_order_confidence", 3),
    ]:
        sobol_dataset = output_group.create_dataset(name, data=sobol_indices[:, index, :])
        sobol_dataset.attrs["units"] = "dimensionless"
        sobol_dataset.attrs["column_names"] = np.string_(sobol_problem["names"])
