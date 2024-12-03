import h5py
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import ScalarFormatter
from matplotlib.lines import Line2D

#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Workflow Configuration
input_data_filename = "output_data.h5"  # Name of the input data file
figure_name_boxplot = "efficiency_box.png"  # Output figure filename
figure_title = "Rothermel_SFIRE ros model"  # Title for the figure
overwrite_figure = True  # Whether to overwrite the figure if it exists

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
with h5py.File(output_file_path, "r") as file:
    outputs_grp = file["outputs"]

    ros_obj = file["outputs"]["rate_of_spread"]
    ros = {
        "unit": ros_obj.attrs["units"],
        "data": ros_obj[:, :],
    }
    exec_time_obj = file["outputs"]["time_exec"]
    exec_time = {
        "unit": exec_time_obj.attrs["units"],
        "data": exec_time_obj[:, :],
    }

    nb_fuel_class = file["fuel/nb_fuel_classes"][()]


data = [exec_time["data"].flatten()]  # Total aggregated data (flattened array)

print(f"global mean value: {np.mean(data):.3e} s for {np.size(data):,d} sample")

data.extend([exec_time["data"][:, i] for i in range(nb_fuel_class)])  # Each fuel class


#######################################################################################
#                             PLOTTING
#######################################################################################

# Configure matplotlib settings
mpl.rcParams.update({"font.size": 7})  # Set default font size
plt.rcParams["text.usetex"] = True  # Enable LaTeX for text rendering

# Create figure and axes
fig, ax1 = plt.subplots(1, 1, figsize=(4, 4), constrained_layout=True, sharex=False)

# Define colors for the bars
colors = ["r", "y"]
lw = 1

box_parts = plt.boxplot(data, showmeans=True, patch_artist=True, meanline=True, showfliers=False)

# Customize the median and mean lines
for mean in box_parts["means"]:
    mean.set_color(colors[0])
    mean.set_linewidth(lw)
    mean.set_linestyle("-")

for median in box_parts["medians"]:
    median.set_color(colors[1])
    median.set_linewidth(lw)
    median.set_linestyle("--")

# Add labels and title
ax1.set_xticks(
    range(1, nb_fuel_class + 2),
    ["Total"] + [f"Fuel Class {i + 1}" for i in range(nb_fuel_class)],
    rotation=45,
    ha="right",
)

ax1.set_ylabel(f"Exec time [{exec_time['unit']}]")
ax1.set_title(figure_title)

# Add legend
legend_elements = [
    Line2D([0], [0], color=colors[0], linestyle="-", lw=lw, label="mean"),
    Line2D([0], [0], color=colors[1], linestyle="--", lw=lw, label="median"),
]
ax1.legend(handles=legend_elements, frameon=False, ncol=2, loc=0)

# for ax in axes:
ax1.tick_params(direction="in", top=True, right=True, bottom=True, which="both")
ax1.ticklabel_format(axis="y", style="sci", scilimits=(0, 0), useOffset=None)

# Adjust layout and save the figure
fig.set_constrained_layout_pads(w_pad=0.0, h_pad=0.03, hspace=0.0, wspace=0.0)
fig.savefig(figure_name_boxplot, dpi=160)
