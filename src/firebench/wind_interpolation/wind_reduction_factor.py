import numpy as np

from ..tools.namespace import StandardVariableNames as svn


def use_wind_reduction_factor(
    wind_speed: float,
    wind_reduction_factor: float | list | np.ndarray = None,
    fuel_dict: dict = None,
    fuel_cat: int = None,
):
    """
    Calculate the wind speed at a different height using the wind reduction factor.

    This function uses polymorphism to handle different types of input:
    - If `wind_reduction_factor` is provided as a float, it uses it directly.
    - If `wind_reduction_factor` is provided as a list, it uses `fuel_cat` to retrieve the factor.
    - If `wind_reduction_factor` is not provided, it retrieves the factor from `fuel_dict` using `fuel_cat`.
    - If `wind_reduction_factor` and `fuel_cat` are not provided, it retrieves the factor from `fuel_dict` not using `fuel_cat`.

    Parameters
    ----------
    wind_speed : float
        The wind speed at the initial height h1.

    wind_reduction_factor : float or dict, optional
        The wind reduction factor from height h1 to h2. If a float, it is used directly.
        If a list, it should contain wind reduction factors indexed by fuel category.

    fuel_dict : dict, optional
        A dictionary containing fuel parameters, including FUEL_WIND_REDUCTION_FACTOR keys as described in StandardVariableNames.

    fuel_cat : int, optional
        The fuel category used to retrieve the wind reduction factor.

    Returns
    -------
    float
        The wind speed at the new height h2.

    Raises
    ------
    ValueError
        If insufficient parameters are provided to compute the wind reduction factor.
    """  # pylint: disable=line-too-long
    if isinstance(wind_reduction_factor, float):
        # Case 1: wind_reduction_factor is provided directly as a float
        return wind_speed * wind_reduction_factor

    if isinstance(wind_reduction_factor, (list, np.ndarray)):
        # Case 2: wind_reduction_factor is a dict; use fuel_cat to get the factor
        if fuel_cat is None:
            raise ValueError("fuel_cat must be provided when wind_reduction_factor is a list.")
        try:
            factor = wind_reduction_factor[fuel_cat]
        except IndexError as exc:
            raise IndexError(f"Fuel category {fuel_cat} not found in wind_reduction_factor array.") from exc
        return wind_speed * factor

    if fuel_dict is not None and fuel_cat is not None:
        # Case 3: Retrieve wind_reduction_factor from fuel_dict using fuel_cat
        try:
            list_wrf = fuel_dict[svn.FUEL_WIND_REDUCTION_FACTOR]
        except KeyError as exc:
            raise KeyError(f"Key {svn.FUEL_WIND_REDUCTION_FACTOR} not found in fuel_dict.") from exc
        try:
            factor = list_wrf[fuel_cat]
        except IndexError as exc:
            raise IndexError(f"Fuel category {fuel_cat} not found in fuel_dict.") from exc
        return wind_speed * factor

    if fuel_dict is not None and fuel_cat is None:
        # Case 4: Retrieve wind_reduction_factor from fuel_dict
        try:
            factor = fuel_dict[svn.FUEL_WIND_REDUCTION_FACTOR]
        except KeyError as exc:
            raise KeyError(f"Key {svn.FUEL_WIND_REDUCTION_FACTOR} not found in fuel_dict.") from exc
        return wind_speed * factor

    # Insufficient parameters provided
    raise ValueError(
        "Insufficient parameters provided. Please provide either "
        "`wind_reduction_factor` as a float, or as a dict with `fuel_cat`, "
        "or provide `fuel_dict` with `fuel_cat`."
    )


def Baughman_20ft_wind_reduction_factor_unsheltered(
    interpolation_height: float,
    vegetation_height: float | list | np.ndarray = None,
    fuel_dict: dict = None,
    fuel_cat: int = None,
):
    """
    Compute the wind reduction factor in unsheltered land from Baughman and Albini (1980)

    The wind reduction factor is computed for a 20ft wind (20ft above the fuel surface).
    The interpolation height is often the midflame height.

    Reference
    ---------

    Baughman, R. G., & Albini, F. A. (1980, April).
    Estimating midflame windspeeds.
    In Proceedings, Sixth Conference on Fire and Forest Meteorology, Seattle, WA (pp. 88-92).

    """  # pylint: disable=line-too-long
    # Case 1: vegetation_height is provided directly as a float
    if isinstance(vegetation_height, float):
        return __Baughman_20ft_wind_reduction_factor_unsheltered(interpolation_height, vegetation_height)

    # Case 2: wind_reduction_factor is a dict; use fuel_cat to get the factor
    if isinstance(vegetation_height, (list, np.ndarray)):
        if fuel_cat is None:
            raise ValueError("fuel_cat must be provided when vegetation_height is a list.")
        try:
            veg_height = vegetation_height[fuel_cat]
        except IndexError as exc:
            raise IndexError(f"Fuel category {fuel_cat} not found in vegetation_height array.") from exc
        return __Baughman_20ft_wind_reduction_factor_unsheltered(interpolation_height, veg_height)

    # Case 3: Retrieve vegetation_height from fuel_dict using fuel_cat
    if fuel_dict is not None and fuel_cat is not None:
        try:
            list_wrf = fuel_dict[svn.FUEL_HEIGHT]
        except KeyError as exc:
            raise KeyError(f"Key {svn.FUEL_HEIGHT} not found in fuel_dict.") from exc
        try:
            veg_height = list_wrf[fuel_cat]
        except IndexError as exc:
            raise IndexError(f"Fuel category {fuel_cat} not found in fuel_dict.") from exc
        return __Baughman_20ft_wind_reduction_factor_unsheltered(interpolation_height, veg_height)

    # Case 4: Retrieve vegetation_height from fuel_dict
    if fuel_dict is not None and fuel_cat is None:
        try:
            veg_height = fuel_dict[svn.FUEL_HEIGHT]
        except KeyError as exc:
            raise KeyError(f"Key {svn.FUEL_HEIGHT} not found in fuel_dict.") from exc
        return __Baughman_20ft_wind_reduction_factor_unsheltered(interpolation_height, veg_height)
    
    # Insufficient parameters provided
    raise ValueError(
        "Insufficient parameters provided. Please provide either "
        "`vegetation_height` as a float, or as a dict with `fuel_cat`, "
        "or provide `fuel_dict` with `fuel_cat`."
    )


def __Baughman_20ft_wind_reduction_factor_unsheltered(
    interpolation_height: float,
    vegetation_height: float,
):
    """
    Compute the wind reduction factor in unsheltered land from Baughman and Albini (1980)
    """  # pylint: disable=line-too-long
    return (
        (1 + 0.36 * vegetation_height / interpolation_height)
        * (np.log((0.36 + interpolation_height / vegetation_height) / 0.13) - 1)
        / np.log((20 + 0.36 * vegetation_height) / (0.13 * vegetation_height))
    )
