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
import firebench.tools as ft
import numpy as np

import matplotlib.pyplot as plt
import h5py

########################## SET UP

record_name = "Sensitivity_env_var_Anderson13_Rothermel"
figure_name = "sobol_index.png"
overwrite_fig = True

########################## SET UP


# get the data
output_h5_path = ft.get_file_path_in_record(f"output_{record_name}.h5", record_name)

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

fuel_classes = np.arange(1, np.size(output_dict["Sobol_first_order"]["data"], 0)+1, 1)
parameters = np.array(output_dict["Sobol_first_order"]["column_names"], dtype=str)

fig_path = ft.generate_file_path_in_record(figure_name, record_name, overwrite=overwrite_fig)

# Create a new figure
fig, ax = plt.subplots(figsize=(12, 8))

# Plotting the first order indices as bar plots
width = 0.25  # width of the bars
x = np.arange(len(fuel_classes))  # the label locations

ax.axhline(1, c="k", lw=0.5, ls="--")
colors = ["b", "r", "g"]
for i, param in enumerate(parameters):
    ax.bar(x + i * width, output_dict["Sobol_first_order"]["data"][:, i], width, label=f"First Order - {param}", color=colors[i])

# Plotting the total order indices as scatter plots
for i, param in enumerate(parameters):
    ax.scatter(x + i * width, output_dict["Sobol_total_order"]["data"][:, i], label=f"Total Order - {param}", marker="d", color=colors[i])

# Adding labels and title
ax.set_xlabel("Anderson Fuel Classes")
ax.set_ylabel("Sobol Indices")
ax.set_title("Sobol Indices for Different Fuel Classes and Parameters")
ax.set_xticks(x + width)
ax.set_xticklabels(fuel_classes, rotation=0, ha="center")
ax.legend(frameon=False, ncols=2)

# Display the plot
plt.tight_layout()
fig.savefig(fig_path, dpi=300)

print(output_dict)