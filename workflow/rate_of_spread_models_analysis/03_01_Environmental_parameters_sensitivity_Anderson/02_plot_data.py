import h5py
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Workflow Configuration
input_data_filename = "output_data.h5"  # Name of the input data file
figure_name = "sobol_index.png"         # Output figure filename
figure_title = "Rothermel_SFIRE ros model"  # Title for the figure
overwrite_figure = True                # Whether to overwrite the figure if it exists

#######################################################################################
#                             DATA RETRIEVAL
#######################################################################################

# Ensure correct file path for input data
if input_data_filename.endswith(".h5"):
    output_file_path = input_data_filename
else:
    output_file_path = f"{input_data_filename}.h5"

# Retrieve data from the HDF5 file
output_dict = {}  # Dictionary to store output data
with h5py.File(output_file_path, "r") as f:
    outputs_grp = f["outputs"]
    fuel_model_name = f["fuel"].attrs["fuel_model_name"]  # Retrieve fuel model name
    
    # Keys for Sobol indices datasets
    sobol_keys = [
        "Sobol_first_order",
        "Sobol_first_order_confidence",
        "Sobol_total_order",
        "Sobol_total_order_confidence",
    ]

    # Load each Sobol dataset into the dictionary
    for key in sobol_keys:
        sobol_dataset = outputs_grp[key]
        output_dict[key] = {
            "unit": sobol_dataset.attrs["units"],
            "column_names": sobol_dataset.attrs["column_names"],
            "data": sobol_dataset[:],
        }

# Define the fuel classes and parameters based on the loaded data
fuel_classes = np.arange(1, np.size(output_dict["Sobol_first_order"]["data"], 0) + 1, 1)
parameters = np.array(output_dict["Sobol_first_order"]["column_names"], dtype=str)

#######################################################################################
#                             PLOTTING
#######################################################################################

# Configure matplotlib settings
mpl.rcParams.update({"font.size": 7})  # Set default font size
plt.rcParams["text.usetex"] = True    # Enable LaTeX for text rendering

# Create figure and axes
fig, axes = plt.subplots(2, 1, figsize=(5, 6), constrained_layout=True, sharex=False)
ax1, ax2 = axes

# Bar width configuration
bar_width = 1 / (len(parameters) + 2)  # Width of the bars
x_positions = np.arange(len(fuel_classes))  # Label positions

# Define colors for the bars
colors = ["b", "r", "g", "m", "y", "darkred"]

# Plot First Order Sobol Indices
for i, param in enumerate(parameters):
    ax1.bar(
        x_positions + i * bar_width,
        output_dict["Sobol_first_order"]["data"][:, i],
        bar_width,
        color=colors[i],
    )
    ax1.errorbar(
        x_positions + i * bar_width,
        output_dict["Sobol_first_order"]["data"][:, i],
        yerr=output_dict["Sobol_first_order_confidence"]["data"][:, i],
        fmt="",  
        ecolor="k",  
        elinewidth=0.6,  
        capsize=1.5,
        linestyle="none",
    )

# Plot Total Order Sobol Indices
for i, param in enumerate(parameters):
    ax2.bar(
        x_positions + i * bar_width,
        output_dict["Sobol_total_order"]["data"][:, i],
        bar_width,
        color=colors[i],
    )
    ax2.errorbar(
        x_positions + i * bar_width,
        output_dict["Sobol_total_order"]["data"][:, i],
        yerr=output_dict["Sobol_total_order_confidence"]["data"][:, i],
        fmt="",  
        ecolor="k",  
        elinewidth=0.6,  
        capsize=1.5,
        linestyle="none",
    )

# Add labels and title
ax1.set_ylabel("First order Sobol Index [-]")
ax1.set_title(figure_title)
ax2.set_ylabel("Total order Sobol Index [-]")
ax2.set_xlabel("Anderson 13 Fuel Class")

# Add legend
legend_elements = [
    Line2D([0], [0], color=colors[i], linestyle="-", lw=2, label=param)
    for i, param in enumerate(parameters)
]
ax1.legend(handles=legend_elements, frameon=False, ncol=1, loc=0)

# Add gridlines and format ticks
ax1.grid(axis="y", which="major", alpha=0.2)

for ax in axes:
    ax.set_ylim([-0.05, 1.05])  # Set y-axis limits
    ax.set_xticks(x_positions + bar_width)
    ax.set_xticklabels(fuel_classes, rotation=0, ha="center")
    ax.tick_params(direction="in", top=True, right=True, bottom=False, which="both")

# Adjust layout and save the figure
fig.set_constrained_layout_pads(w_pad=0.0, h_pad=0.03, hspace=0.0, wspace=0.0)
fig.savefig(figure_name, dpi=160)
