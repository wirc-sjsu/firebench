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
