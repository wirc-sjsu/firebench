import numpy as np

from ..tools import get_value_by_category


def Masson_canyon(
    wind_speed_atm: float,
    input_wind_height: float,
    building_height: float | list | np.ndarray,
    building_separation: float | list | np.ndarray,
    fuel_cat: int = 0,
):
    """
    Compute the wind speed in an urban canyon using the Masson (2000) model.

    This function estimates the wind speed in an urban canyon based on the atmospheric wind speed,
    building height, and building separation distance. If the building height and separation distance
    are provided as lists or NumPy arrays, the function selects the appropriate value based on the
    specified `fuel_cat` index.

    Parameters
    ----------
    wind_speed_atm : float
        Wind speed above buildings [m/s].
    input_wind_height : float
        Height at which wind speed is given above buildings [m].
    building_height : float, list, or np.ndarray
        Building height [m]. If a list or array, `fuel_cat` is used to select the value.
    building_separation : float, list, or np.ndarray
        Average building separation distance [m]. If a list or array, `fuel_cat` is used to select the value.
    fuel_cat : int, optional
        Index for selecting values from list or array inputs. Default is 0.

    Returns
    -------
    float
        Estimated wind speed in the urban canyon [m/s].

    Raises
    ------
    ValueError
        If `fuel_cat` is out of range for the provided list or array inputs.

    Notes
    -----
    **One-Based Indexing:**
    `fuel_cat` uses one-based indexing to align with natural fuel category numbering
    (i.e., the first fuel category is `fuel_cat=1`).

    **Roughness Length Calculation:**
    The roughness length (`z_0`) is estimated as 10% of the building height, with a minimum value of 5m.

    References
    ----------
    Masson, V. (2000). A physically-based scheme for the urban energy budget in atmospheric models.
    Boundary-Layer Meteorology, 94, 357-397.
    """ # pylint: disable=line-too-long
    h_b = get_value_by_category(building_height, fuel_cat)  # Building height [m]
    d_b = get_value_by_category(building_separation, fuel_cat)  # Building separation [m]

    z_0 = 0.1 * max(5, h_b)  # Roughness length estimation

    return (
        (2 / np.pi)
        * np.exp(-0.25 * h_b / d_b)
        * np.log(h_b / (3 * z_0))
        / np.log((input_wind_height - 2 * h_b / 3) / z_0)
        * np.abs(wind_speed_atm)
    )
