from datetime import datetime

import firebench.tools as ft

#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Record and file configuration
record_name = "Anderson_Rothermel" # Name of the record directory to be created
data_filename = "output_data.h5"       # Name of the data file to include in the record
figure_filename = "anderson_2015_validation.png"    # Name of the figure file to include in the record
overwrite_existing_record = True       # Whether to overwrite existing files in the record

# List of mandatory files to include in the record
mandatory_files = [
    "01_generate_data.py",
    "02_plot_data.py",
    "03_create_record.py",
    "firebench.log",
    f"{data_filename}",
    f"{figure_filename}",
]

#######################################################################################
#                             RECORD CREATION
#######################################################################################

# Create the record directory
ft.create_record_directory(record_name)

# Copy mandatory files to the record directory and compute their hashes
hash_dict = {}
for file in mandatory_files:
    hash_dict[file] = ft.copy_file_to_workflow_record(
        record_name, file, overwrite=overwrite_existing_record
    )

#######################################################################################
#                             REPORT UPDATE
#######################################################################################

# Update the markdown report with file hashes
ft.update_markdown_with_hashes("report.md", hash_dict)

# Get the current date in a readable format
current_date = datetime.now().strftime("%Y-%m-%d")
ft.update_date_in_markdown("report.md", current_date)

# Copy the updated report to the record directory
ft.copy_file_to_workflow_record(record_name, "report.md", overwrite=overwrite_existing_record)
