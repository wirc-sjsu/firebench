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
import numpy as np
import firebench.ros_models as rm
import firebench.tools as fbt
from firebench import ureg, svn
from pint import Quantity

#######################################################################################
#                             STEP 1: DESIGN OF EXPERIMENT
#######################################################################################

# Import fuel data
fuel_data = fbt.read_fuel_data_file(
    "Anderson13",
)

# print(fuel_data)

# Create wind [m s-1], slope [deg] and moisture [%] data
nb_sobol_pts = 4  # better if 2^N

## Create the dict of variable name, units and range
input_vars_info = {
    svn.WIND: (ureg.meter / ureg.second, [-20, 20]),
    svn.SLOPE_ANGLE: (ureg.degree, [-45, 45]),
    svn.FUEL_MOISTURE_CONTENT: (ureg.percent, [1, 50]),
}

sensitivity_vars = fbt.sobol_seq(nb_sobol_pts, input_vars_info)

print(sensitivity_vars)

# Concatenate inputs
input_dict = fbt.merge_dictionaries(fuel_data, sensitivity_vars)

#######################################################################################
#                             STEP 2: DATA QUALITY CHECK
#######################################################################################

# Completness
fbt.check_input_completeness(input_dict, rm.Rothermel_SFIRE.metadata)

# unit conversion
input_converted = fbt.convert_input_data_units(input_dict, rm.Rothermel_SFIRE.metadata)

# validity range
fbt.check_validity_range(input_converted, rm.Rothermel_SFIRE.metadata)

# create final input dict
final_input = input_converted.copy()
# extract data
for key, value in final_input.items():
    final_input[key] = final_input[key].magnitude

# select fuel cat
final_input[svn.FUEL_CLASS] = 1
# loop over sobol sequence

ros = np.zeros(nb_sobol_pts)
ref_dict = final_input.copy()

for k in range(nb_sobol_pts):
    print(k)
    for key in input_vars_info.keys():
        final_input[key] = ref_dict[key][k]

    ros[k] = rm.Rothermel_SFIRE.compute_ros(final_input)

# Assign unit

ros = Quantity(ros, rm.Rothermel_SFIRE.metadata["output_rate_of_spread"]["units"])

print(ros)
