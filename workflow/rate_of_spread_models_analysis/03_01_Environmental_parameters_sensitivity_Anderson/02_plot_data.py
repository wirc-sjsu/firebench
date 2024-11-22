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
input_data_filename = "Rothermel_SFIRE.h5"
figure_name = "sobol_index.png"
figure_title = "Rothermel_SFIRE ros model"
overwrite_figure = True

#######################################################################################
#                             DATA RETRIEVAL
#######################################################################################
# Generate output file path
if input_data_filename.endswith(".h5"):
    output_file_path = input_data_filename
else:
    output_file_path = f"{input_data_filename}.h5"

# Get the data
output_dict = {}
with h5py.File(output_file_path, "r") as f:
    outputs_grp = f["outputs"]
    fuel_model_name = f["fuel"].attrs["fuel_model_name"]
    sobol_keys = [
        "Sobol_first_order",
        "Sobol_first_order_confidence",
        "Sobol_total_order",
        "Sobol_total_order_confidence",
    ]
    for key in sobol_keys:
        sobol_dataset = outputs_grp[key]
        output_dict[key] = {
            "unit": sobol_dataset.attrs["units"],
            "column_names": sobol_dataset.attrs["column_names"],
            "data": sobol_dataset[:],
        }

fuel_classes = np.arange(1, np.size(output_dict["Sobol_first_order"]["data"], 0) + 1, 1)
parameters = np.array(output_dict["Sobol_first_order"]["column_names"], dtype=str)

#######################################################################################
#                             PLOTTING
#######################################################################################

# Create a new figure
mpl.rcParams.update({"font.size": 7})
plt.rcParams["text.usetex"] = True
fig, ax = plt.subplots(figsize=(5, 3), constrained_layout=True)

# Plotting the first order indices as bar plots
bar_width = 1/ (len(parameters)+1) # width of the bars
x_positions = np.arange(len(fuel_classes))  # the label locations

# ax.axhline(1, color="k", linewidth=0.5, linestyle="--")
colors = ["b", "r", "g", "m", "y", "darkred"]
for i, param in enumerate(parameters):
    ax.bar(
        x_positions + i * bar_width,
        output_dict["Sobol_first_order"]["data"][:, i],
        bar_width,
        color=colors[i],
    )

# Plotting the total order indices as scatter plots
for i, param in enumerate(parameters):
    ax.scatter(
        x_positions + i * bar_width,
        output_dict["Sobol_total_order"]["data"][:, i],
        marker="d",
        s=4,
        color=colors[i],
    )

# Adding labels and title
ax.set_xlabel("Anderson 13 Fuel Class")
ax.set_ylabel("Sobol Indices [-]")
ax.set_title(figure_title)
ax.set_xticks(x_positions + bar_width)
ax.set_xticklabels(fuel_classes, rotation=0, ha="center")

legend_elements = [
    Line2D([0], [0], color="k", linestyle="-", lw=3, label="First order"),
    Line2D([0], [0], color="k", linestyle="none", marker="d", markersize=4, label="Total order"),
]
for i, param in enumerate(parameters):
    legend_elements.append(
        Line2D([0], [0], color=colors[i], linestyle="-", lw=2, label=param),
    )

ax.legend(
    handles=legend_elements,
    frameon=False,
    ncol=1,
    loc="center left",
    bbox_to_anchor=(1, 0.5)
)

ax.grid(axis="y", which="major", alpha=0.2)

ax.tick_params(direction="in", top=True, right=True, bottom=False, which="both")
fig.set_constrained_layout_pads(w_pad=0.0, h_pad=0.03, hspace=0.0, wspace=0.0)
fig.savefig(figure_name, dpi=160)
