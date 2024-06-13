"""
Workflow: 03_01_sensitivity_env_var.py
Category: Sensitivity Analysis

Description:
This workflow performs a sensitivity analysis on rate of spread models using a static fuel database (e.g. Anderson, Scott & Burgan)
The analysis considers the impact of environmental variables on fire behavior, specifically focusing on:
- Wind
- Slope
- Fuel Moisture

This workflow is part of the FireBench project, aimed at systematic benchmarking and inter-comparisons 
of fire models to enhance their scientific and operational applications.
"""
import firebench.ros_models as rm
import firebench.tools as fbt
import numpy as np
from firebench import svn, ureg
from pint import Quantity
from SALib.analyze import sobol

#######################################################################################
#                             STEP 1: DESIGN OF EXPERIMENT
#######################################################################################

# Import fuel data
fuel_data = fbt.read_fuel_data_file(
    "Anderson13",
)

# Choose ROS model
ros_model = rm.Rothermel_SFIRE

# Create wind [m s-1], slope [deg] and moisture [%] data
## Choose number of point for Sobol sequence
nb_sobol_pts = 2**14  # better if 2^N
## Create the dict of variable name, units and range
input_vars_info = {
    svn.WIND: (ureg.meter / ureg.second, [-10, 10]),
    svn.SLOPE_ANGLE: (ureg.degree, [-30, 30]),
    svn.FUEL_MOISTURE_CONTENT: (ureg.percent, [1, 50]),
}

## Create the
input_vars_dict, sobol_problem, nb_pts_total = fbt.sobol_seq(nb_sobol_pts, input_vars_info)

# Concatenate inputs
input_dict = fbt.merge_dictionaries(fuel_data, input_vars_dict)

#######################################################################################
#                             STEP 2: DATA QUALITY CHECK
#######################################################################################

# Completness
fbt.check_input_completeness(input_dict, ros_model.metadata)

# unit conversion
input_converted = fbt.convert_input_data_units(input_dict, ros_model.metadata)

# validity range
fbt.check_validity_range(input_converted, ros_model.metadata)

# create final input dict
final_input = input_converted.copy()
# extract data
for key, value in final_input.items():
    final_input[key] = final_input[key].magnitude

# select fuel cat
final_input[svn.FUEL_CLASS] = 7
# loop over sobol sequence

ros = np.zeros(nb_pts_total)
ref_dict = final_input.copy()

for k in range(nb_pts_total):
    for key in input_vars_info.keys():
        final_input[key] = ref_dict[key][k]

    ros[k] = ros_model.compute_ros(final_input)

# Assign unit

ros_unit = Quantity(ros, ros_model.metadata["output_rate_of_spread"]["units"])

# Perform Sobol analysis
sobol_indices = sobol.analyze(sobol_problem, ros, print_to_console=True)

# Extract first-order and total-order indices
first_order_indices = sobol_indices["S1"]
total_order_indices = sobol_indices["ST"]
