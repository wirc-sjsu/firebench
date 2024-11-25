from datetime import datetime
import os

import firebench.ros_models as rm
import firebench.tools as ft
import firebench.wind_interpolation as wi
import h5py
import numpy as np
from firebench import Quantity, svn

#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Workflow Configuration
output_filename = "output_data"
logging_level = 20 # DEBUG (10), INFO (20), WARNING (30), ERROR (40), CRITICAL (50)

# parameters
fixed_flame_fuel_height_ratio = 1
is_source_wind_height_above_veg = True
ros_model = rm.Rothermel_SFIRE

#######################################################################################
#                             STEP 1: GET INPUT DATA
#######################################################################################

# create logging file
ft.logging_config.create_file_handler("firebench.log")
ft.set_logging_level(logging_level)  

# Import Anderson 2015 dataset
anderson_2015_data = ft.read_data_file("Table_A1", "ros_model_validation/Anderson_2015")

# Import Scott and Burgan fuel model
sb40_data = ft.read_fuel_data_file("ScottandBurgan40")
ft.add_scott_and_burgan_total_fuel_load(sb40_data)
ft.add_scott_and_burgan_total_savr(sb40_data)

#######################################################################################
#                             STEP 2: RUN ROS MODEL
#######################################################################################

n_valid = 0

expected_ros = []
computed_ros = []

for i in range(anderson_2015_data["nb_fuel_classes"]):
    ft.logger.debug(f"row {i+1}")
    # get Anderson 2015 data for each case
    input_dict = {
        svn.FUEL_LOAD_DEAD_RATIO: anderson_2015_data[svn.FUEL_LOAD_FINE_DEAD][i]
        / (anderson_2015_data[svn.FUEL_LOAD_FINE_LIVE][i] + anderson_2015_data[svn.FUEL_LOAD_FINE_DEAD][i]),
        svn.FUEL_LOAD_DRY_TOTAL: anderson_2015_data[svn.FUEL_LOAD_DRY_TOTAL][i],
        svn.SLOPE_ANGLE: anderson_2015_data[svn.SLOPE_ANGLE][i],
        svn.FUEL_HEIGHT: anderson_2015_data[svn.FUEL_HEIGHT][i].to("m"),
        svn.FUEL_MOISTURE_CONTENT: anderson_2015_data[svn.FUEL_MOISTURE_CONTENT_ELEVATED_DEAD][i],
        svn.IGNITION_LENGTH: anderson_2015_data[svn.IGNITION_LENGTH][i],
        svn.FUEL_WIND_HEIGHT: anderson_2015_data[svn.FUEL_WIND_HEIGHT][i],
        svn.WIND_SPEED: anderson_2015_data[svn.WIND_SPEED][i],
    }

    # skip if data not complete
    if any(np.isnan(value.magnitude) for value in input_dict.values()):
        ft.logger.warning(f"data incomplete for row {i+1}")
        continue

    # Default data (From Anderson 13 Fuel model)
    default_inputs = {
        svn.FUEL_DENSITY: Quantity(32, "lb/ft^3"),
        svn.FUEL_CHAPARRAL_FLAG: Quantity(0, "dimensionless"),
        svn.FUEL_MINERAL_CONTENT_TOTAL: Quantity(0.0555, "dimensionless"),
        svn.FUEL_MINERAL_CONTENT_EFFECTIVE: Quantity(0.01, "dimensionless"),
    }

    # get fuel moisture of extinction and sav ratio from SB40 fuel model
    # by looking for the closest fuel cat comparing fuel load, fuel height
    sb40_fuel_cat = ft.find_closest_fuel_class_by_properties(
        sb40_data,
        dict((k, input_dict[k]) for k in [svn.FUEL_LOAD_DRY_TOTAL, svn.FUEL_HEIGHT]),
        weights=None,  # equal weights
    )
    inputs_from_sb40 = {
        svn.FUEL_MOISTURE_EXTINCTION: sb40_data[svn.FUEL_MOISTURE_EXTINCTION][sb40_fuel_cat - 1],
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO: sb40_data[svn.FUEL_SURFACE_AREA_VOLUME_RATIO][sb40_fuel_cat - 1],
    }
    ft.logger.debug(
        f"closest SB40 cat {sb40_fuel_cat}: tgt: ({input_dict[svn.FUEL_LOAD_DRY_TOTAL]}, {input_dict[svn.FUEL_HEIGHT]}), SB40 class: ({sb40_data[svn.FUEL_LOAD_DRY_TOTAL][sb40_fuel_cat-1].to('kg/m^2'):.2f}, {sb40_data[svn.FUEL_HEIGHT][sb40_fuel_cat-1].to('m'):.2f})"
    )

    # Compute wind reduction factor
    wind_height = input_dict[svn.FUEL_WIND_HEIGHT].to("m")
    wind_speed = input_dict[svn.WIND_SPEED].to("m/s")
    fuel_height = input_dict[svn.FUEL_HEIGHT].to("m")   
    wrf = wi.Baughman_generalized_wind_reduction_factor_unsheltered(
        wind_height.magnitude,
        fixed_flame_fuel_height_ratio * fuel_height.magnitude,
        fuel_height.magnitude,
        is_source_wind_height_above_veg=is_source_wind_height_above_veg,
    )
    input_dict[svn.WIND_SPEED] = wind_speed * wrf
    ft.logger.debug(f"wind red factor: {wrf:.3f}, source wind speed: {wind_speed:.3f}, midflame wind speed: {input_dict[svn.WIND_SPEED]:.3f}")

    # Concatenate input dictionaries
    final_input = {
        **input_dict,
        **inputs_from_sb40,
        **default_inputs,
    }

    # check data quality
    input_checked = ft.check_data_quality_ros_model(final_input, ros_model)

    # compute rate of spread
    rate_of_spread_from_model = ros_model.compute_ros_with_units(final_input)
    expected_rate_of_spread = anderson_2015_data[svn.RATE_OF_SPREAD][i].to("m/s")
    ft.logger.debug(f"expected ros: {expected_rate_of_spread:.2f}, from model: {rate_of_spread_from_model:.2f}")
    
    expected_ros.append(expected_rate_of_spread.magnitude)
    computed_ros.append(rate_of_spread_from_model.magnitude)

    n_valid += 1

ft.logger.info(f"number of valid cases: {n_valid}/{anderson_2015_data['nb_fuel_classes']}")

#######################################################################################
#                             STEP 4: SAVE DATA
#######################################################################################

# Generate output file path
if output_filename.endswith(".h5"):
    output_file_path = output_filename
else:
    output_file_path = f"{output_filename}.h5"

with h5py.File(output_file_path, "w") as f:
    # Add file attributes
    f.attrs["description"] = "Sensitivity workflow for rate of spread model using firebench package"
    f.attrs["date"] = str(datetime.now())

    output_group = f.create_group("outputs")
    output_group.attrs["description"] = "Rate of spread outputs"
    ros_expected_dataset = output_group.create_dataset("rate_of_spread_expected", data=expected_ros)
    ros_expected_dataset.attrs["units"] = str(expected_rate_of_spread.units)
    ros_computed_dataset = output_group.create_dataset("rate_of_spread_computed", data=computed_ros)
    ros_computed_dataset.attrs["units"] = str(expected_rate_of_spread.units)
