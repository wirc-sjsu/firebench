from pathlib import Path

import firebench.standardize as fs
import firebench.tools as ft

# --- Read JSON file ---
data_source_path = Path("./situ_data.json")

output_file = "../processed/California_weather_data.h5"

compression_lvl = 3  # 1 = no compression, 22 = max compression
logging_lvl = 10  # 0 NOTSET, 10 DEBUG, 20 INFO, 30 WARNING, 40 ERROR, 50 CRITICAL

skip_stations = []

ft.set_logging_level(logging_lvl)

# Create new standard file
h5 = fs.new_std_file(
    output_file,
    "Aurelien Costes, SJSU; Angel F. Caus, SJSU; Muthu K. Selvaraj, WPI; Adam Kochanski, SJSU; Abtin Olaee, SJSU;",
    overwrite=True,
)

# Add short description
h5.attrs["description"] = (
    "FireBench weather-station data for California. "
    "Contains: standardized Synoptic weather-station datasets for 2024-01-01 to 2024-01-10."
)

# Process the Synoptic json data. See implementation to have the list of variable processes
fs.standardize_synoptic_raws_from_json(
    data_source_path,
    h5,
    skip_stations=skip_stations,
    overwrite=True,
    compression_lvl=compression_lvl,
    export_trusted_history=True,
)

h5.close()
