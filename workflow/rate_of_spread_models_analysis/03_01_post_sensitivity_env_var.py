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
from tqdm import tqdm
import matplotlib.pyplot as plt

########################## SET UP

# File management
# Name of the case
record_name = "Sensitivity_env_var_Anderson13_Rothermel"

fuel_classes = [
    "1: Short grass",
    "2: Timber",
    "3: Tall grass",
    "4: Chaparral",
    "5: Brush",
    "6: Dormant brush",
    "7: Southern rough",
    "8: Closed timber litter",
    "9: Hardwood litter",
    "10: Timber",
    "11: Light logging slash",
    "12: Medium logging slash",
    "13: Heavy logging slash",
]
parameters = sobol_problem["names"]
colors = ["b", "r", "g"]

# Create a new figure
fig, ax = plt.subplots(figsize=(12, 8))

# Plotting the first order indices as bar plots
width = 0.25  # width of the bars
x = np.arange(len(fuel_classes))  # the label locations

ax.axhline(1, c="k", lw=0.5, ls="--")

for i, param in enumerate(parameters):
    ax.bar(x + i * width, sobol_S1[:, i], width, label=f"First Order - {param}", color=colors[i])

# Plotting the total order indices as scatter plots
for i, param in enumerate(parameters):
    ax.scatter(x + i * width, sobol_ST[:, i], label=f"Total Order - {param}", marker="d", color=colors[i])

# Adding labels and title
ax.set_xlabel("Anderson Fuel Classes")
ax.set_ylabel("Sobol Indices")
ax.set_title("Sobol Indices for Different Fuel Classes and Parameters")
ax.set_xticks(x + width)
ax.set_xticklabels(fuel_classes, rotation=45, ha="right")
ax.legend(frameon=False, ncols=2)

# Display the plot
plt.tight_layout()
fig.savefig("../../../IAB_tmp.png", dpi=300)
