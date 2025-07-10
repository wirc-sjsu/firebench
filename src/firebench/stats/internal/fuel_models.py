import numpy as np
import matplotlib.pyplot as plt
from ...tools import (
    read_data_file,
    import_scott_burgan_40_fuel_model,
    find_closest_fuel_class_by_properties,
)
from ...tools.logging_config import logger
from ...tools.namespace import StandardVariableNames as svn
from math import ceil
from ..utils.hist import auto_bins


def anderson_2015_stats(
    output_filename: str = None, unit_wind: str = "m/s", unit_ros: str = "m/s", dpi: int = 150
):
    """
    Plot statistics from the Anderson 2015 dataset.

    This function processes the Anderson (2015) dataset and visualizes:
        - Histogram of observed rate of spread (ROS)
        - Scatter plot of wind speed vs dead fuel moisture
        - Histogram of closest Scott and Burgan 40 (SB40) fuel model matches

    Parameters
    ----------
    output_filename : str, optional
        If provided, the resulting figure will be saved to this file path.
        If None, the figure is displayed interactively. Default None.
    unit_wind : str, optional
        Unit to which wind speed observations are converted (e.g., "km/h"). Default "m/s".
    unit_ros : str, optional
        Unit to which rate of spread observations are converted (e.g., "ft/min"). Default "m/s".
    dpi : int, optional
        The resolution in dots per inch. Default 150.

    Notes
    -----
    For more details about the dataset structure and variables, refer to the
    documentation page for the Anderson (2015) validation dataset.
    """  # pylint: disable=line-too-long
    # Load Anderson 2015 data
    anderson_2015_data = read_data_file("Table_A1", "ros_model_validation/Anderson_2015")
    N_anderson = anderson_2015_data["nb_fuel_classes"]

    # Load SB40 fuel model data
    sb40_data = import_scott_burgan_40_fuel_model()

    # Initialize arrays
    obs_ros = np.full(N_anderson, np.nan)
    obs_wind = np.full(N_anderson, np.nan)
    obs_dead_fmc = np.full(N_anderson, np.nan)
    obs_closest_sb40_cat = np.zeros(N_anderson, dtype=np.int32)

    for i in range(N_anderson):
        logger.debug(f"row {i+1}")

        # Extract and validate target variables
        obs_tmp_data = {
            svn.FUEL_LOAD_DRY_TOTAL: anderson_2015_data[svn.FUEL_LOAD_DRY_TOTAL][i],
            svn.FUEL_HEIGHT: anderson_2015_data[svn.FUEL_HEIGHT][i].to("m"),
        }

        if any(np.isnan(v.magnitude) for v in obs_tmp_data.values()):
            logger.warning(f"data incomplete for row {i+1}")
            continue

        # Convert observed values
        obs_ros[i] = anderson_2015_data[svn.RATE_OF_SPREAD][i].to(unit_ros).magnitude
        obs_wind[i] = anderson_2015_data[svn.WIND_SPEED][i].to(unit_wind).magnitude
        obs_dead_fmc[i] = (
            anderson_2015_data[svn.FUEL_MOISTURE_CONTENT_ELEVATED_DEAD][i].to("percent").magnitude
        )

        # Find closest SB40 fuel class based on physical properties
        obs_closest_sb40_cat[i] = find_closest_fuel_class_by_properties(
            sb40_data,
            obs_tmp_data,
            weights=None,  # equal weights
        )
        logger.debug(
            f"Closest SB40 class: {obs_closest_sb40_cat[i]} — "
            f"Target: ({obs_tmp_data[svn.FUEL_LOAD_DRY_TOTAL].to('kg/m^2')}, {obs_tmp_data[svn.FUEL_HEIGHT].to('m')}), "
            f"Match: ({sb40_data[svn.FUEL_LOAD_DRY_TOTAL][obs_closest_sb40_cat[i]-1].to('kg/m^2'):.2f}, "
            f"{sb40_data[svn.FUEL_HEIGHT][obs_closest_sb40_cat[i]-1].to('m'):.2f})"
        )

    fig, axes = plt.subplots(3, 1, figsize=(6, 10), constrained_layout=True)
    ax1, ax2, ax3 = axes

    # Plot histogram of observed rate of spread
    ax1.hist(obs_ros, bins=auto_bins(obs_ros), edgecolor="black")
    ax1.set_xlabel(f"Observed rate of spread [{unit_ros}]")
    ax1.set_ylabel("Number of observations [-]")

    # Plot wind speed vs dead fuel moisture
    ax2.plot(obs_wind, obs_dead_fmc, "ko", ms=5)
    ax2.set_xlabel(f"Wind speed [{unit_wind}]")
    ax2.set_ylabel("Dead fuel moisture [%]")
    ax2.set_xlim([-0.5, 0.5 + ceil(np.nanmax(obs_wind))])
    ax2.set_ylim([0, 38])

    # Plot histogram of closest SB40 classes
    ax3.hist(obs_closest_sb40_cat, bins=range(0, 42), align="left", edgecolor="black")
    ax3.set_xlabel("Closest Scott and Burgan fuel class (based on fuel load and height)")
    ax3.set_ylabel("Number of observations [-]")
    ax3.set_xticks(range(0, 41))
    fuel_labels = ["invalid"] + list(sb40_data["fuel_model_code"])
    ax3.set_xticklabels(fuel_labels, rotation=90, fontsize=8)

    for ax in axes:
        ax.tick_params(direction="in", top=True, right=True, which="both")
    fig.get_layout_engine().set(w_pad=0.0, h_pad=0.03, hspace=0.0, wspace=0.0)

    # interactive figure is ignored for coverage
    if output_filename is None:
        plt.show()  # pragma: no cover
    else:
        fig.savefig(output_filename, dpi=dpi)
