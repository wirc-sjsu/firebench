"""
Workflow: 03_01_sensitivity_env_var.py
Category: Sensitivity Analysis

Description:
This workflow performs a sensitivity analysis on rate of spread models using a static fuel database (e.g., Anderson, Scott & Burgan).
The analysis considers the impact of environmental variables on fire behavior, specifically focusing on:
- Wind
- Slope
- Fuel Moisture

This workflow is part of the FireBench project, aimed at systematic benchmarking and inter-comparisons 
of fire models to enhance their scientific and operational applications.
"""

import firebench.tools as ft
import numpy as np
import matplotlib.pyplot as plt
import h5py

#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Workflow Configuration
workflow_record_name = "Sensitivity_env_var_Anderson13_Rothermel"
figure_name = "sobol_index.png"
overwrite_figure = True

#######################################################################################
#                             DATA RETRIEVAL
#######################################################################################

# Get the data
output_h5_path = ft.get_file_path_in_record(f"output_{workflow_record_name}.h5", workflow_record_name)
output_dict = {}

with h5py.File(output_h5_path, "r") as f:
    outputs_grp = f["outputs"]

    sobol_keys = ["Sobol_first_order", "Sobol_first_order_confidence", "Sobol_total_order", "Sobol_total_order_confidence"]
    for key in sobol_keys:
        sobol_dataset = outputs_grp[key]
        output_dict[key] = {
            "unit": sobol_dataset.attrs["units"],
            "column_names": sobol_dataset.attrs["column_names"],
            "data": sobol_dataset[:]
        }

fuel_classes = np.arange(1, np.size(output_dict["Sobol_first_order"]["data"], 0) + 1, 1)
parameters = np.array(output_dict["Sobol_first_order"]["column_names"], dtype=str)

#######################################################################################
#                             PLOTTING
#######################################################################################

# Generate figure path
figure_path = ft.generate_file_path_in_record(figure_name, workflow_record_name, overwrite=overwrite_figure)

# Create a new figure
fig, ax = plt.subplots(figsize=(12, 8))

# Plotting the first order indices as bar plots
bar_width = 0.25  # width of the bars
x_positions = np.arange(len(fuel_classes))  # the label locations

ax.axhline(1, color="k", linewidth=0.5, linestyle="--")
colors = ["b", "r", "g"]
for i, param in enumerate(parameters):
    ax.bar(x_positions + i * bar_width, output_dict["Sobol_first_order"]["data"][:, i], bar_width, label=f"First Order - {param}", color=colors[i])

# Plotting the total order indices as scatter plots
for i, param in enumerate(parameters):
    ax.scatter(x_positions + i * bar_width, output_dict["Sobol_total_order"]["data"][:, i], label=f"Total Order - {param}", marker="d", color=colors[i])

# Adding labels and title
ax.set_xlabel("Anderson Fuel Classes")
ax.set_ylabel("Sobol Indices")
ax.set_title("Sobol Indices for Different Fuel Classes and Parameters")
ax.set_xticks(x_positions + bar_width)
ax.set_xticklabels(fuel_classes, rotation=0, ha="center")
ax.legend(frameon=False, ncols=2)

# Display the plot
plt.tight_layout()
fig.savefig(figure_path, dpi=300)

# Output the data for verification
print(output_dict)
