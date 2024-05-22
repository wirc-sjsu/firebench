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
from firebench import ureg

#######################################################################################
#                             STEP 1: DESIGN OF EXPERIMENT 
#######################################################################################

# Import fuel data


# Create wind [m s-1], slope [deg] and moisture [%] data
## Create the dict of variable name, units and range 
input_vars_info = {
    "wind": (ureg.meter / ureg.second, [-20, 20]),
    "slope": (ureg.degree, [-45, 45]),
    "moisture": (ureg.percent, [1, 50]),
}

fbt.sobol_seq(5, input_vars_info)