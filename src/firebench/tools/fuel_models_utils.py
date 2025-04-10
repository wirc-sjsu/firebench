import numpy as np
from pint import Quantity
from pint.errors import DimensionalityError
from .namespace import StandardVariableNames as svn
from .logging_config import logger
from .read_data import read_fuel_data_file


def find_closest_fuel_class_by_properties(
    fuel_model_dict: dict[str, Quantity],
    properties_to_test: dict[str, Quantity],
    weights: dict[str, float] = None,
) -> int:
    """
    Find the fuel class index that has the closest properties to the given set of properties.

    This function compares a set of fuel classes defined in `fuel_model_dict` with a target set of properties
    provided in `properties_to_test`. It calculates a weighted L1 distance between the properties of each
    fuel class and the target properties, returning the index (1-based) of the fuel class that is closest.

    Parameters
    ----------
    fuel_model_dict : dict[str, Quantity]
        A dictionary where each key is a property name and each value is a list of `Quantity` objects
        representing that property for each fuel class.
    properties_to_test : dict[str, Quantity]
        A dictionary where each key is a property name and each value is a `Quantity` object representing
        the target value for that property.
    weights : dict[str, float], optional
        A dictionary of weights for the different properties. Must have the same keys as `properties_to_test`.
        If not provided, weights are set to the inverse of the target property values (if non-zero) to balance
        the error between properties.

    Returns
    -------
    int
        The one-based index of the fuel class with the closest properties to the target properties.

    Raises
    ------
    KeyError
        If a property key in `properties_to_test` is not found in `fuel_model_dict`.
    ValueError
        If units cannot be converted between the fuel model and the properties to test.
    """  # pylint: disable=line-too-long
    # Initialize variables
    fuel_model_converted = {}
    default_weights = {}
    nb_fuel_classes = None

    # Convert units and prepare default weights
    for prop_key, target_value in properties_to_test.items():
        # Ensure the property exists in the fuel model dictionary
        if prop_key not in fuel_model_dict:
            raise KeyError(f"Property '{prop_key}' not found in fuel_model_dict.")

        nb_fuel_classes = len(fuel_model_dict[prop_key])

        try:
            # Convert the fuel model properties to the units of the test properties
            fuel_model_converted[prop_key] = fuel_model_dict[prop_key].to(target_value.units)
        except DimensionalityError as exc:
            raise ValueError(f"Cannot convert units for property '{prop_key}': {exc}") from exc

        # Set default weight (inverse of the target magnitude, if non-zero)
        if target_value.magnitude != 0:
            default_weights[prop_key] = 1.0 / abs(target_value.magnitude)
        else:
            default_weights[prop_key] = 1.0  # Avoid division by zero

    # Use provided weights or default weights
    if weights is None:
        weights = default_weights
    else:
        # Ensure that weights have the same keys as properties_to_test
        if set(weights.keys()) != set(properties_to_test.keys()):
            raise ValueError("Weights must have the same keys as properties_to_test.")

    # Compute weighted distances for each fuel class
    num_properties = len(properties_to_test)
    distances = np.zeros((num_properties, nb_fuel_classes))
    for idx, prop_key in enumerate(properties_to_test):
        target_magnitude = properties_to_test[prop_key].magnitude
        weight = weights[prop_key]
        for class_index in range(nb_fuel_classes):
            distances[idx, class_index] = weight * (
                abs(fuel_model_converted[prop_key][class_index].magnitude - target_magnitude)
            )

    # Return the one-based index of the fuel class with the minimum total distance
    closest_index = np.argmin(np.sum(distances, axis=0)) + 1  # Return 1-based index
    return closest_index


def add_scott_and_burgan_total_fuel_load(fuel_data_dict, overwrite=False):
    """
    Add the total dry fuel load to the fuel data dictionary by summing individual dry fuel loads
    according to the Scott and Burgan 40 fuel model.

    The total dry fuel load is calculated as the sum of the following individual fuel loads:

    - ``FUEL_LOAD_DRY_1H``
    - ``FUEL_LOAD_DRY_10H``
    - ``FUEL_LOAD_DRY_100H``
    - ``FUEL_LOAD_DRY_LIVE_HERB``
    - ``FUEL_LOAD_DRY_LIVE_WOODY``

    The result is stored under the key ``FUEL_LOAD_DRY_TOTAL`` in ``fuel_data_dict``.

    Parameters
    ----------
    fuel_data_dict : dict
        Dictionary containing individual fuel load values with specific keys.

    overwrite : bool, optional
        If ``True``, overwrites the existing total fuel load if it exists.
        If ``False`` and the total fuel load already exists, raises a ``ValueError``. Default is ``False``.

    Raises
    ------
    ValueError
        If ``FUEL_LOAD_DRY_TOTAL`` already exists in ``fuel_data_dict`` and ``overwrite`` is ``False``.

    KeyError
        If any required individual fuel load keys are missing from ``fuel_data_dict``.

    Notes
    -----
    This function assumes that ``fuel_data_dict`` contains the required keys defined in the
    Scott and Burgan 40 fuel model constants.

    Examples
    --------
    **Example 1: Basic usage**

    .. code-block:: python

        from firebench import svn
        fuel_data = {
            svn.FUEL_LOAD_DRY_1H: 0.1,
            svn.FUEL_LOAD_DRY_10H: 0.2,
            svn.FUEL_LOAD_DRY_100H: 0.3,
            svn.FUEL_LOAD_DRY_LIVE_HERB: 0.4,
            svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.5,
        }
        add_scott_and_burgan_total_fuel_load(fuel_data)
        print(fuel_data[svn.FUEL_LOAD_DRY_TOTAL])  # Outputs: 1.5
    """  # pylint: disable=line-too-long
    total_key = svn.FUEL_LOAD_DRY_TOTAL

    if total_key in fuel_data_dict:
        if not overwrite:
            raise ValueError(
                f"Key '{total_key}' already exists in fuel_data_dict. Use overwrite=True to overwrite it."
            )
        logger.info("Key '%s' exists and will be overwritten.", total_key)

    # List of individual fuel load keys to sum
    individual_keys = [
        svn.FUEL_LOAD_DRY_1H,
        svn.FUEL_LOAD_DRY_10H,
        svn.FUEL_LOAD_DRY_100H,
        svn.FUEL_LOAD_DRY_LIVE_HERB,
        svn.FUEL_LOAD_DRY_LIVE_WOODY,
    ]

    try:
        # Sum individual fuel loads to calculate total fuel load
        fuel_data_dict[total_key] = sum(fuel_data_dict[key] for key in individual_keys)
    except KeyError as e:
        missing_key = e.args[0]
        raise KeyError(f"Missing required key '{missing_key}' in fuel_data_dict.") from e


def add_scott_and_burgan_total_savr(fuel_data_dict, overwrite=False):
    r"""
    Add the total Surface Area to Volume Ratio (SAVR) to the fuel data dictionary by computing
    the weighted average of individual SAVRs according to the Scott and Burgan 40 fuel model.

    The total SAVR is calculated using the weighted average formula:

    .. math::

        \text{total\_SAVR} = \frac{\sum_i \left( \text{fuel\_load}_i \cdot \text{SAVR}_i \right)}{\sum_i \text{fuel\_load}_i}

    where:

    - ``fuel_load_i`` is the fuel load of the *i*-th component.
    - ``SAVR_i`` is the surface area to volume ratio of the *i*-th component.

    The components considered are:

    - ``FUEL_LOAD_DRY_1H`` with ``FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H``
    - ``FUEL_LOAD_DRY_LIVE_HERB`` with ``FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB``
    - ``FUEL_LOAD_DRY_LIVE_WOODY`` with ``FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY``

    The result is stored under the key ``FUEL_SURFACE_AREA_VOLUME_RATIO`` in ``fuel_data_dict``.

    Parameters
    ----------
    fuel_data_dict : dict
        Dictionary containing individual fuel load and SAVR values with specific keys.

    overwrite : bool, optional
        If ``True``, overwrites the existing total SAVR if it exists.
        If ``False`` and the total SAVR already exists, raises a ``ValueError``. Default is ``False``.

    Raises
    ------
    ValueError
        If ``FUEL_SURFACE_AREA_VOLUME_RATIO`` already exists in ``fuel_data_dict`` and ``overwrite`` is ``False``.

    KeyError
        If any required keys are missing from ``fuel_data_dict``.

    Notes
    -----
    This function assumes that ``fuel_data_dict`` contains the required keys defined in the
    Scott and Burgan 40 fuel model constants.

    Examples
    --------
    **Example 1: Compute total SAVR from basic components**

    .. code-block:: python

        from firebench import svn
        fuel_data = {
            svn.FUEL_LOAD_DRY_1H: 0.1,
            svn.FUEL_LOAD_DRY_LIVE_HERB: 0.2,
            svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.3,
            svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H: 2000,
            svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB: 1500,
            svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY: 1800,
        }
        add_scott_and_burgan_total_savr(fuel_data)
        print(fuel_data[svn.FUEL_SURFACE_AREA_VOLUME_RATIO])  # Outputs the total SAVR
    """  # pylint: disable=line-too-long
    total_key = svn.FUEL_SURFACE_AREA_VOLUME_RATIO

    if total_key in fuel_data_dict:
        if not overwrite:
            raise ValueError(
                f"Key '{total_key}' already exists in fuel_data_dict. Use overwrite=True to overwrite it."
            )
        logger.info("Key '%s' exists and will be overwritten.", total_key)

    # Lists of fuel load and SAVR keys
    savr_keys = [
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY,
    ]
    fuel_load_keys = [
        svn.FUEL_LOAD_DRY_1H,
        svn.FUEL_LOAD_DRY_LIVE_HERB,
        svn.FUEL_LOAD_DRY_LIVE_WOODY,
    ]
    for key in savr_keys + fuel_load_keys:
        if key not in fuel_data_dict.keys():
            raise KeyError(f"Missing required key '{key}' in fuel_data_dict.")

    # Calculate the numerator and denominator for the weighted average
    num = sum(fuel_data_dict[fuel_load_keys[k]] * fuel_data_dict[savr_keys[k]] for k in range(3))
    denom = sum(fuel_data_dict[fuel_load_keys[k]] for k in range(3))

    # Store the total SAVR in the dictionary
    fuel_data_dict[total_key] = num / denom


def add_scott_and_burgan_dead_fuel_ratio(fuel_data_dict, overwrite=False):
    """
    Calculate and add the dead fuel load ratio to a fuel data dictionary based on the
    Anderson 13 or Scott and Burgan 40 fuel model.

    The dead fuel load ratio represents the fraction of the total fuel load that is
    attributed to dead fuels. It is calculated as the ratio of the sum of specific
    dead fuel loads to the sum of all fuel loads (dead and live).

    **Dead fuel loads considered**

    - ``FUEL_LOAD_DRY_1H``
    - ``FUEL_LOAD_DRY_10H``
    - ``FUEL_LOAD_DRY_100H``

    **Live fuel loads considered**

    - ``FUEL_LOAD_DRY_LIVE_HERB``
    - ``FUEL_LOAD_DRY_LIVE_WOODY``

    The result is stored under the key ``FUEL_LOAD_DEAD_RATIO`` in ``fuel_data_dict``.

    Parameters
    ----------
    fuel_data_dict : dict
        Dictionary containing individual fuel load values with specific keys.

    overwrite : bool, optional
        If ``True``, overwrites the existing dead fuel ratio if it exists. If ``False`` and the value already exists, raises a ``ValueError``. Default is ``False``.

    Raises
    ------
    ValueError
        If ``FUEL_LOAD_DEAD_RATIO`` already exists in ``fuel_data_dict`` and ``overwrite`` is ``False``.

    KeyError
        If any required individual fuel load keys are missing from ``fuel_data_dict``.

    Notes
    -----
    This function assumes that ``fuel_data_dict`` contains the required keys defined in the
    Anderson 13 or Scott and Burgan 40 fuel model constants.

    Examples
    --------
    **Example 1: Basic usage**

    .. code-block:: python

        from firebench import svn
        fuel_data = {
            svn.FUEL_LOAD_DRY_1H: 0.1,
            svn.FUEL_LOAD_DRY_10H: 0.2,
            svn.FUEL_LOAD_DRY_100H: 0.3,
            svn.FUEL_LOAD_DRY_LIVE_HERB: 0.4,
            svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.5,
        }
        add_anderson_dead_fuel_ratio(fuel_data)
        print(fuel_data[svn.FUEL_LOAD_DEAD_RATIO])  # Outputs: 0.4
    """  # pylint: disable=line-too-long
    total_key = svn.FUEL_LOAD_DEAD_RATIO

    if total_key in fuel_data_dict:
        if not overwrite:
            raise ValueError(
                f"Key '{total_key}' already exists in fuel_data_dict. Use overwrite=True to overwrite it."
            )
        logger.info("Key '%s' exists and will be overwritten.", total_key)

    # List of individual fuel load keys to sum
    dead_fuels_keys = [
        svn.FUEL_LOAD_DRY_1H,
        svn.FUEL_LOAD_DRY_10H,
        svn.FUEL_LOAD_DRY_100H,
    ]
    live_fuels_keys = [
        svn.FUEL_LOAD_DRY_LIVE_HERB,
        svn.FUEL_LOAD_DRY_LIVE_WOODY,
    ]

    for key in dead_fuels_keys + live_fuels_keys:
        if key not in fuel_data_dict.keys():
            raise KeyError(f"Missing required key '{key}' in fuel_data_dict.")

    # Calculate the numerator and denominator
    dead_load = sum(fuel_data_dict[dead_fuel] for dead_fuel in dead_fuels_keys)
    live_load = sum(fuel_data_dict[live_fuel] for live_fuel in live_fuels_keys)

    fuel_data_dict[total_key] = dead_load / (dead_load + live_load)


def import_scott_burgan_40_fuel_model(add_complementary_fields=True):
    """
    Import and return the Scott and Burgan 40 fuel model data, with optional complementary computations.

    This function serves as a convenient wrapper to read the Scott and Burgan 40 fuel model
    data from a file and optionally compute additional derived fields. The base dataset contains
    a set of standard fuel load parameters defined by the Scott and Burgan 40 model. By default,
    this function also adds complementary fields that summarize or characterize the data,
    if requested.

    When ``add_complementary_fields`` is ``True``, the following additional fields are computed and
    included in the returned dictionary:

    - **Total Fuel Load**: The sum of all fuel load values (dead and live) stored under
      ``svn.FUEL_LOAD_DRY_TOTAL``.

    - **Total SAVR (Surface-Area-to-Volume Ratio)**: An aggregated value of surface-area-to-volume
      ratios for the various fuel classes stored under ``svn.FUEL_SURFACE_AREA_VOLUME_RATIO``.

    - **Dead Fuel Ratio**: The fraction of the total fuel load that is attributable to dead fuels
      stored under ``svn.FUEL_LOAD_DEAD_RATIO``.

    Parameters
    ----------
    add_complementary_fields : bool, optional
        If ``True`` (default), computes and adds complementary fields (total fuel load, total SAVR,
        and dead fuel ratio) to the returned fuel data dictionary. If ``False``, the function returns
        only the raw fuel data as read from the file.

    Returns
    -------
    dict
        A dictionary containing the Scott and Burgan 40 fuel model data with keys following the
        Standard Variable Namespace (svn) convention. If ``add_complementary_fields`` is ``True``,
        it will also include ``svn.FUEL_LOAD_DRY_TOTAL``, ``svn.FUEL_SURFACE_AREA_VOLUME_RATIO``,
        and ``svn.FUEL_LOAD_DEAD_RATIO``.

    Raises
    ------
    FileNotFoundError
        If the "ScottandBurgan40" data file cannot be found.

    KeyError
        If required keys are missing when computing the complementary fields.

    Examples
    --------
    **Example 1: Import with complementary fields**

    .. code-block:: python

        from firebench import svn
        fuel_data = import_scott_burgan_40()
        print(svn.FUEL_LOAD_DRY_TOTAL in fuel_data)  # True
        print(svn.FUEL_SURFACE_AREA_VOLUME_RATIO in fuel_data)  # True
        print(svn.FUEL_LOAD_DEAD_RATIO in fuel_data)  # True

    **Example 2: Import raw data without complementary fields**

    .. code-block:: python

        from firebench import svn
        raw_fuel_data = import_scott_burgan_40(add_complementary_fields=False)
        print(svn.FUEL_LOAD_DRY_TOTAL in raw_fuel_data)  # False
        print(svn.FUEL_SURFACE_AREA_VOLUME_RATIO in raw_fuel_data)  # False
        print(svn.FUEL_LOAD_DEAD_RATIO in raw_fuel_data)  # False
    """  # pylint: disable=line-too-long
    DATASET_NAME = "ScottandBurgan40"
    fuel_data = read_fuel_data_file(DATASET_NAME)
    if add_complementary_fields:
        add_scott_and_burgan_total_fuel_load(fuel_data)
        add_scott_and_burgan_total_savr(fuel_data)
        add_scott_and_burgan_dead_fuel_ratio(fuel_data)
    return fuel_data


def add_anderson_dead_fuel_ratio(fuel_data_dict, overwrite=False, use_1h_only=False):
    """
    Calculate and add the dead fuel load ratio to a fuel data dictionary based on the
    Anderson 13 fuel model.

    The dead fuel load ratio represents the fraction of the total fuel load that is
    attributed to dead fuels. It is calculated as the ratio of the sum of specific
    dead fuel loads to the sum of all fuel loads (dead and live).

    **Dead fuel loads considered**

    - ``FUEL_LOAD_DRY_1H``
    - ``FUEL_LOAD_DRY_10H``
    - ``FUEL_LOAD_DRY_100H``

    **Live fuel loads considered**

    - ``FUEL_LOAD_DRY_LIVE``

    The result is stored under the key ``FUEL_LOAD_DEAD_RATIO`` in ``fuel_data_dict``.

    Parameters
    ----------
    fuel_data_dict : dict
        Dictionary containing individual fuel load values with specific keys.

    overwrite : bool, optional
        If ``True``, overwrites the existing dead fuel ratio if it exists.
        If ``False`` and the value already exists, raises a ``ValueError``. Default is ``False``.

    use_1h_only : bool, optional
        If ``True``, use only ``FUEL_LOAD_DRY_1H`` for dead fuel load.
        If ``False``, use all dead fuel load keys. Default is ``False``.

    Raises
    ------
    ValueError
        If ``FUEL_LOAD_DEAD_RATIO`` already exists in ``fuel_data_dict`` and ``overwrite`` is ``False``.

    KeyError
        If any required individual fuel load keys are missing from ``fuel_data_dict``.

    Notes
    -----
    This function assumes that ``fuel_data_dict`` contains the required keys defined in the
    Anderson 13 fuel model constants.

    Examples
    --------
    **Example 1: Basic usage**

    .. code-block:: python

        from firebench import svn
        fuel_data = {
            svn.FUEL_LOAD_DRY_1H: 0.1,
            svn.FUEL_LOAD_DRY_10H: 0.2,
            svn.FUEL_LOAD_DRY_100H: 0.3,
            svn.FUEL_LOAD_DRY_LIVE: 0.6,
        }
        add_anderson_dead_fuel_ratio(fuel_data)
        print(fuel_data[svn.FUEL_LOAD_DEAD_RATIO])  # Outputs: 0.4
    """  # pylint: disable=line-too-long
    total_key = svn.FUEL_LOAD_DEAD_RATIO

    if total_key in fuel_data_dict:
        if not overwrite:
            raise ValueError(
                f"Key '{total_key}' already exists in fuel_data_dict. Use overwrite=True to overwrite it."
            )
        logger.info("Key '%s' exists and will be overwritten.", total_key)

    # List of individual fuel load keys to sum
    dead_fuels_keys = [
        svn.FUEL_LOAD_DRY_1H,
        svn.FUEL_LOAD_DRY_10H,
        svn.FUEL_LOAD_DRY_100H,
    ]
    dead_fuels_keys_1h_only = [
        svn.FUEL_LOAD_DRY_1H,
    ]
    live_fuels_keys = [
        svn.FUEL_LOAD_DRY_LIVE,
    ]

    for key in dead_fuels_keys + live_fuels_keys:
        if key not in fuel_data_dict.keys():
            raise KeyError(f"Missing required key '{key}' in fuel_data_dict.")

    # Calculate the numerator and denominator
    if use_1h_only:
        dead_load = sum(fuel_data_dict[dead_fuel] for dead_fuel in dead_fuels_keys_1h_only)
    else:
        dead_load = sum(fuel_data_dict[dead_fuel] for dead_fuel in dead_fuels_keys)
    live_load = sum(fuel_data_dict[live_fuel] for live_fuel in live_fuels_keys)

    fuel_data_dict[total_key] = dead_load / (dead_load + live_load)


def import_anderson_13_fuel_model(add_complementary_fields=True, use_1h_only=False):
    """
    Import and return the Anderson 13 fuel model data.

    This function reads the Anderson 13 fuel model dataset from a file and returns it
    as a dictionary. The Anderson 13 fuel models are a standardized set of fuel types widely
    referenced in fire behavior modeling. Each fuel model in this set characterizes a specific
    configuration of fuel loads, sizes, and other parameters essential for fire behavior prediction.

    The returned dataset includes key-value pairs following a Standard Variable Namespace (SVN)
    convention, ensuring consistency with other fuel data representations in the codebase.

    When ``add_complementary_fields`` is ``True``, the following additional fields are computed and
    included in the returned dictionary:
    - **Dead Fuel Ratio**: The fraction of the total fuel load that is attributable to dead fuels stored under ``svn.FUEL_LOAD_DEAD_RATIO``.

    Parameters
    ----------
    add_complementary_fields : bool, optional
        If ``True`` (default), computes and adds complementary fields to the returned fuel data dictionary. If ``False``, the function returns only the raw fuel data as read from the file.
    use_1h_only : bool, optional
        If ``True``, use only ``FUEL_LOAD_DRY_1H`` for dead fuel load for dead fuel ratio calculation.
        If ``False`` use all dead fuel load keys. Default is ``False``.

    Returns
    -------
    dict
        A dictionary containing the Anderson 13 fuel model data. Keys follow the SVN convention.

    Raises
    ------
    FileNotFoundError
        If the ``Anderson13`` data file cannot be found or accessed.

    Examples
    --------
    .. code-block:: python

        fuel_data = import_anderson_13_fuel_model()
    """  # pylint: disable=line-too-long
    DATASET_NAME = "Anderson13"
    fuel_data = read_fuel_data_file(DATASET_NAME)
    if add_complementary_fields:
        add_anderson_dead_fuel_ratio(fuel_data, use_1h_only=use_1h_only)
    return fuel_data


def import_wudapt_fuel_model():
    """
    Import and return the WUDAPT urban fuel model data.

    This function reads the Anderson 13 fuel model dataset from a file and returns it
    as a dictionary. The Anderson 13 fuel models are a standardized set of fuel types widely
    referenced in fire behavior modeling. Each fuel model in this set characterizes a specific
    configuration of fuel loads, sizes, and other parameters essential for fire behavior prediction.

    The returned dataset includes key-value pairs following a Standard Variable Namespace (SVN)
    convention, ensuring consistency with other fuel data representations in the codebase.

    Returns
    -------
    dict
        A dictionary containing the Anderson 13 fuel model data. Keys follow the SVN convention.

    Raises
    ------
    FileNotFoundError
        If the "Anderson13" data file cannot be found or accessed.

    Examples
    --------
    >>> fuel_data = import_anderson_13_fuel_model()
    """  # pylint: disable=line-too-long
    DATASET_NAME = "WUDAPT_urban"
    fuel_data = read_fuel_data_file(DATASET_NAME)
    return fuel_data
