import firebench.tools as ft
from firebench import ureg
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
import h5py


#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Workflow Configuration
input_data_filename = "output_data.h5"          # Name of the input data file
figure_name = "anderson_2015_validation.png"    # Output figure filename
figure_title = "Rothermel_SFIRE ros model"      # Title for the figure
overwrite_figure = True                         # Whether to overwrite the figure if it exists

#######################################################################################
#                             DATA RETRIEVAL
#######################################################################################

output_dict = {}
with h5py.File(input_data_filename, "r") as f:
    outputs_grp = f["outputs"]
    keys = [
        "rate_of_spread_expected",
        "rate_of_spread_computed",
    ]
    for key in keys:
        dataset = outputs_grp[key]
        output_dict[key] = {
            "unit": dataset.attrs["units"],
            "data": dataset[:],
        }

#######################################################################################
#                             DATA PROCESSING
#######################################################################################


rmse = np.sqrt(
    np.mean(
        np.power(
            output_dict["rate_of_spread_expected"]["data"] - output_dict["rate_of_spread_computed"]["data"],
            2,
        )
    )
)
pearson_coeff = np.corrcoef(
    output_dict["rate_of_spread_expected"]["data"], output_dict["rate_of_spread_computed"]["data"]
)
nmse = rmse / (
    np.max(output_dict["rate_of_spread_expected"]["data"])
    - np.min(output_dict["rate_of_spread_expected"]["data"])
)

#######################################################################################
#                             DATA PLOT
#######################################################################################

mpl.rcParams.update({"font.size": 7})
plt.rcParams["text.usetex"] = True
fig, ax1 = plt.subplots(1, 1, figsize=(4, 4), constrained_layout=True)

# ax1 = axes[0]
# ax2 = axes[1]

ax1.plot(
    output_dict["rate_of_spread_expected"]["data"],
    output_dict["rate_of_spread_computed"]["data"],
    "bo",
    ms=2,
)

ax1.plot([-0.1, 6.1], [-0.1, 6.1], "k", lw=0.5)

unit_x = ureg.parse_units(output_dict["rate_of_spread_expected"]["unit"])
unit_y = ureg.parse_units(output_dict["rate_of_spread_computed"]["unit"])

ax1.set_title(figure_title)
ax1.set_xlabel(f"Anderson 2015 dataset rate of spread [{unit_x:~}]")
ax1.set_ylabel(f"Computed rate of spread [{unit_y:~}]")
ax1.tick_params(direction="in", top=True, right=True, which="both")

ax1.set_xlim([-0.1, 6.1])
ax1.set_ylim([-0.1, 6.1])

ax1.text(
    0.98,
    0.10,
    f"RMSE [m/s]: {rmse:.2f}",
    transform=ax1.transAxes,
    horizontalalignment="right",
    verticalalignment="bottom",
    color="k",
)
ax1.text(
    0.98,
    0.06,
    f"NMSE [-]: {nmse:.2f}",
    transform=ax1.transAxes,
    horizontalalignment="right",
    verticalalignment="bottom",
    color="k",
)
ax1.text(
    0.98,
    0.02,
    f"Pearson [-]: {pearson_coeff[0, 1]:.2f}",
    transform=ax1.transAxes,
    horizontalalignment="right",
    verticalalignment="bottom",
    color="k",
)

fig.set_constrained_layout_pads(w_pad=0.0, h_pad=0.03, hspace=0.0, wspace=0.0)
fig.savefig(figure_name, dpi=160)
