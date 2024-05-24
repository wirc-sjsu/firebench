def check_input_completeness(input_data: dict, metadata_dict: dict):
    """
    Check the completeness of the input data against the metadata dictionary.

    Parameters
    ----------
    input_data : dict
        Dictionary containing the input data.
    metadata_dict : dict
        Dictionary containing metadata, where each key is a metadata item and each value is a dictionary
        with at least the key "std_name" representing the standard name of the data item.

    Raises
    ------
    KeyError
        If any standard name specified in the metadata is missing in the input data.
    """
    for item in metadata_dict.values():
        std_name_metadata = item["std_name"]
        if std_name_metadata not in input_data:
            raise KeyError(f"The data '{std_name_metadata}' is missing in the input dict")