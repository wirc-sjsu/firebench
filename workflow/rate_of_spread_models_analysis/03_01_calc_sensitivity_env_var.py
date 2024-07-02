"""
Workflow: 03_01_sensitivity_env_var.py
Category: Sensitivity Analysis
version: 1.0

Description:
This workflow performs a sensitivity analysis on rate of spread models using a static fuel database (e.g. Anderson, Scott & Burgan)
The analysis considers the impact of environmental variables on fire behavior, specifically focusing on:
- Wind
- Slope
- Fuel Moisture

Documentation page:
"""
import os

import firebench.ros_models as rm
import firebench.tools as fbt
import numpy as np
from firebench import svn, ureg
from pint import Quantity
from SALib.analyze import sobol
import h5py
from datetime import datetime


#######################################################################################
#                             STEP 1: DESIGN OF EXPERIMENT
#######################################################################################

########################## SET UP

# File management
# Name of the case
# TODO: record logic
record_name = "Sensitivity_env_var_Anderson13_Rothermel"
overwrite_record = True

# Fuel model choice
# TODO: how to use existing fuel DB + how to use a personalized one
fuel_model_name = "Anderson13"  #
local_path_json_fuel_db = None

# Choose ROS model
# TODO: How to change ROS model in the workflow
ros_model = rm.Rothermel_SFIRE

# Create wind [m s-1], slope [deg] and moisture [%] data
# TODO: adapt number of point for sobol analysis
nb_pts_sobol_seq = 2**10  # Choose number of point for Sobol sequence, better if 2^N

## Create the dict of variable name, units and range
# TODO: variable dict with range and unit or unit and value
input_vars_info = {
    svn.WIND_SPEED: {"unit": ureg.meter / ureg.second, "range": [-15, 15]},
    svn.SLOPE_ANGLE: {"unit": ureg.degree, "range": [-45, 45]},
    svn.FUEL_MOISTURE_CONTENT: {"unit": ureg.percent, "range": [1, 50]},
}

# set logging parameters
# set logging level, from lower to higher: NOTSET (0), DEBUG (10), INFO (20), WARNING (30), ERROR (40), CRITICAL (50)
fbt.logger.setLevel(0)
########################## END OF SET UP

# Create workflow record directory (working directory for the current workflow)
fbt.create_record_directory(record_name, overwrite_record)

# copy script file to record
fbt.copy_file_to_workflow_record(record_name, __file__)

# Import fuel data
fuel_data = fbt.read_fuel_data_file(
    fuel_model_name,
    local_path_json_fuel_db=local_path_json_fuel_db,
)

## Create the final data
input_vars_dict, sobol_problem, nb_pts_total = fbt.sobol_seq(nb_pts_sobol_seq, input_vars_info)
input_dict = fbt.merge_dictionaries(fuel_data, input_vars_dict)

#######################################################################################
#                             STEP 2: DATA QUALITY CHECK
#######################################################################################

final_input = fbt.check_data_quality_ros_model(input_dict=input_dict, ros_model=ros_model)

#######################################################################################
#                             STEP 3: ROS MODEL
#######################################################################################

# Sobol indices array (N_pts, 4, N_vars) with 2nd dimension for first order, first order confidence, total order, total order confidence
sobol_indices = np.zeros((fuel_data["nb_fuel_classes"], 4, 3))

original_dict = final_input.copy()

i_exp = 0
for i_fc in range(fuel_data["nb_fuel_classes"]):
    final_input[svn.FUEL_CLASS] = i_fc + 1

    ros = np.zeros((nb_pts_total, fuel_data["nb_fuel_classes"]))
    ref_dict = original_dict.copy()

    for k in range(nb_pts_total):
        for key in input_vars_info.keys():
            final_input[key] = ref_dict[key][k]

        ros[k, i_fc] = ros_model.compute_ros(final_input)

    # Perform Sobol analysis
    sobol_indices_output = sobol.analyze(sobol_problem, ros[:, i_fc], print_to_console=False)

    # Extract first-order and total-order indices
    sobol_indices[i_exp, 0, :] = sobol_indices_output["S1"]
    sobol_indices[i_exp, 1, :] = sobol_indices_output["S1_conf"]
    sobol_indices[i_exp, 2, :] = sobol_indices_output["ST"]
    sobol_indices[i_exp, 3, :] = sobol_indices_output["ST_conf"]

    i_exp += 1

# Assign unit
ros_unit = Quantity(ros, ros_model.metadata["output_rate_of_spread"]["units"])

#######################################################################################
#                             STEP 4: SAVE DATA
#######################################################################################

tmp_file_path = os.path.join(fbt.get_local_db_path(), record_name, f"output_{record_name}.h5")

with h5py.File(tmp_file_path, 'w') as f:
    # Info about the file
    f.attrs["description"] = "Sensitivity workflow for rate of spread model using firebench package"
    f.attrs["date"] = str(datetime.now())
    # save fuel input data
    fuel_grp = f.create_group("fuel")
    fuel_grp.attrs["description"] = f"Fuel Model data"
    fuel_grp.attrs["fuel_model_name"] = fuel_model_name
    for key, value in fuel_data.items():
        if type(key) is fbt.StandardVariableNames:
            key = key.value
            is_part_of_firebench_StandardVariableNames = True
        else:
            is_part_of_firebench_StandardVariableNames = False

        try:
            tmp_unit = value.units
            tmp_array = value.magnitude
        except:
            tmp_unit = None
            tmp_array = value
        new_ds = fuel_grp.create_dataset(key, data=tmp_array)
        new_ds.attrs["units"] = str(tmp_unit)
        new_ds.attrs["is_part_of_firebench_StandardVariableNames"] = is_part_of_firebench_StandardVariableNames

    # Save wind, slope, fmc inputs
    sensitivity_input_grp = f.create_group("sensitivity_vars")
    sensitivity_input_grp.attrs["description"] = "variables used for the sensitivity analysis"
    for key, value in input_vars_dict.items():
        if type(key) is fbt.StandardVariableNames:
            key = key.value
            is_part_of_firebench_StandardVariableNames = True
        else:
            is_part_of_firebench_StandardVariableNames = False
        try:
            tmp_unit = value.units
            tmp_array = value.magnitude
        except:
            tmp_unit = None
            tmp_array = value
        new_ds = sensitivity_input_grp.create_dataset(key, data=tmp_array)
        new_ds.attrs["units"] = str(tmp_unit)
        new_ds.attrs["is_part_of_firebench_StandardVariableNames"] = is_part_of_firebench_StandardVariableNames

    # Save raw output
    raw_output_grp = f.create_group("outputs")
    raw_output_grp.attrs["description"] = "output of the workflow"

    # ros
    new_ds = raw_output_grp.create_dataset("rate_of_spread", data=ros)
    new_ds.attrs["units"] = str(ros_model.metadata["output_rate_of_spread"]["units"])

    # sobol indices
    new_ds = raw_output_grp.create_dataset("Sobol_first_order", data=sobol_indices[:, 0, :])
    new_ds.attrs["units"] = "dimensionless"
    new_ds.attrs["column_names"] = np.string_(sobol_problem["names"])
    new_ds = raw_output_grp.create_dataset("Sobol_first_order_confidence", data=sobol_indices[:, 1, :])
    new_ds.attrs["units"] = "dimensionless"
    new_ds.attrs["column_names"] = np.string_(sobol_problem["names"])
    new_ds = raw_output_grp.create_dataset("Sobol_total_order", data=sobol_indices[:, 2, :])
    new_ds.attrs["units"] = "dimensionless"
    new_ds.attrs["column_names"] = np.string_(sobol_problem["names"])
    new_ds = raw_output_grp.create_dataset("Sobol_total_order_confidence", data=sobol_indices[:, 3, :])
    new_ds.attrs["units"] = "dimensionless"
    new_ds.attrs["column_names"] = np.string_(sobol_problem["names"])
