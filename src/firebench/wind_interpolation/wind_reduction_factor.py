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

    This function computes the wind speed at a new height (h2) by applying a wind reduction factor to the wind speed at the initial height (h1).
    It is designed to handle various types of inputs for the wind reduction factor, offering flexibility in how the factor is provided.

    The function uses polymorphism to handle different input scenarios:

    - If `wind_reduction_factor` is provided as a float, it uses this value directly.
    - If `wind_reduction_factor` is provided as a list or numpy array, it uses `fuel_cat` to select the appropriate factor from the list or array.
    - If `wind_reduction_factor` is not provided, it retrieves the factor from `fuel_dict`:
        - If the value in `fuel_dict` at key `svn.FUEL_WIND_REDUCTION_FACTOR` is a list or numpy array, then `fuel_cat` is mandatory to select the factor.
        - If it's a float, then `fuel_cat` is not needed.

    Parameters
    ----------
    wind_speed : float
        The wind speed at the initial height h1.

    wind_reduction_factor : float or list or np.ndarray, optional
        The wind reduction factor from height h1 to h2. If a float, it is used directly.
        If a list or numpy array, it should contain wind reduction factors indexed by fuel category.

    fuel_dict : dict, optional
        A dictionary containing fuel parameters, including the key `svn.FUEL_WIND_REDUCTION_FACTOR` as described in `StandardVariableNames`. This key should map to either a float or a list/numpy array of wind reduction factors.

    fuel_cat : int, optional
        The fuel category index used to retrieve the wind reduction factor from a list or array when `wind_reduction_factor` or `fuel_dict` contains multiple values.

    Returns
    -------
    float
        The wind speed at the new height h2, calculated by applying the wind reduction factor.

    Raises
    ------
    ValueError
        If insufficient parameters are provided to compute the wind reduction factor.
    IndexError
        If `fuel_cat` is out of bounds for the provided list or array.
    KeyError
        If the required keys are missing in `fuel_dict`.

    Notes
    -----
    **Wind Reduction Factor Application:**

    The wind reduction factor adjusts the wind speed from one height to another, accounting for the change in wind speed due to atmospheric conditions and surface roughness.

    **Input Scenarios:**

    - **Direct Factor Provided:**
        - When `wind_reduction_factor` is a float:
          ```python
          new_wind_speed = wind_speed * wind_reduction_factor
          ```
    - **Factor List or Array with Fuel Category:**
        - When `wind_reduction_factor` is a list or array, and `fuel_cat` is provided:
          ```python
          factor = wind_reduction_factor[fuel_cat]
          new_wind_speed = wind_speed * factor
          ```
    - **Factor Retrieved from `fuel_dict`:**
        - When `wind_reduction_factor` is not provided, but `fuel_dict` is:
            - If `fuel_dict[svn.FUEL_WIND_REDUCTION_FACTOR]` is a float:
              ```python
              factor = fuel_dict[svn.FUEL_WIND_REDUCTION_FACTOR]
              new_wind_speed = wind_speed * factor
              ```
            - If it is a list or array and `fuel_cat` is provided:
              ```python
              factor = fuel_dict[svn.FUEL_WIND_REDUCTION_FACTOR][fuel_cat]
              new_wind_speed = wind_speed * factor
              ```
            - If `fuel_cat` is not provided when required, a `ValueError` is raised.

    **Example Usage:**

    ```python
    # Example 1: Using a direct wind reduction factor
    new_wind_speed = use_wind_reduction_factor(
        wind_speed=10.0,
        wind_reduction_factor=0.8
    )
    # Result: new_wind_speed = 8.0

    # Example 2: Using wind reduction factors from a list with a fuel category
    wind_reduction_factors = [0.7, 0.8, 0.9]
    fuel_cat = 2
    new_wind_speed = use_wind_reduction_factor(
        wind_speed=10.0,
        wind_reduction_factor=wind_reduction_factors,
        fuel_cat=fuel_cat
    )
    # Result: new_wind_speed = 8.0 (using factor 0.8 from index 1)

    # Example 3: Using a fuel dictionary with a fuel category
    fuel_dict = {svn.FUEL_WIND_REDUCTION_FACTOR: [0.7, 0.8, 0.9]}
    fuel_cat = 2
    new_wind_speed = use_wind_reduction_factor(
        wind_speed=10.0,
        fuel_dict=fuel_dict,
        fuel_cat=fuel_cat
    )
    # Result: new_wind_speed = 8.0

    # Example 4: Using a fuel dictionary without a fuel category
    fuel_dict = {svn.FUEL_WIND_REDUCTION_FACTOR: 0.8}
    new_wind_speed = use_wind_reduction_factor(
        wind_speed=10.0,
        fuel_dict=fuel_dict
    )
    # Result: new_wind_speed = 8.0
    ```

    **Error Handling:**

    - A `ValueError` is raised if insufficient parameters are provided to compute the wind reduction factor.
    - An `IndexError` is raised if `fuel_cat` is provided but out of range for the list or array.
    - A `KeyError` is raised if the expected key `svn.FUEL_WIND_REDUCTION_FACTOR` is missing in `fuel_dict`.

    **Important Considerations:**

    - **One-Based Indexing:** Note that `fuel_cat` uses one-based indexing to align with natural fuel category numbering (i.e., the first fuel category is `fuel_cat = 1`).
    - **Data Types:** The function accepts `wind_reduction_factor` as a float, list, or numpy array. Ensure that your inputs are of the correct type.
    - **Units Consistency:** Make sure that the units of `wind_speed` and the wind reduction factor are consistent. Typically, wind speeds are in meters per second (m/s) or miles per hour (mph), and the wind reduction factor is dimensionless.

    References
    ----------
    StandardVariableNames module provides standardized keys for fuel parameters.

    """  # pylint: disable=line-too-long
    if isinstance(wind_reduction_factor, float):
        # Case 1: wind_reduction_factor is provided directly as a float
        return wind_speed * wind_reduction_factor

    if isinstance(wind_reduction_factor, (list, np.ndarray)):
        # Case 2: wind_reduction_factor is a dict; use fuel_cat to get the factor
        if fuel_cat is None:
            raise ValueError("fuel_cat must be provided when wind_reduction_factor is a list.")
        try:
            factor = wind_reduction_factor[fuel_cat - 1]
        except IndexError as exc:
            raise IndexError(
                f"Fuel category {fuel_cat-1} not found in wind_reduction_factor array."
            ) from exc
        return wind_speed * factor

    if fuel_dict is not None and fuel_cat is not None:
        # Case 3: Retrieve wind_reduction_factor from fuel_dict using fuel_cat
        try:
            list_wrf = fuel_dict[svn.FUEL_WIND_REDUCTION_FACTOR]
        except KeyError as exc:
            raise KeyError(f"Key {svn.FUEL_WIND_REDUCTION_FACTOR} not found in fuel_dict.") from exc
        try:
            factor = list_wrf[fuel_cat - 1]
        except IndexError as exc:
            raise IndexError(f"Fuel category {fuel_cat-1} not found in fuel_dict.") from exc
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
    flame_height: float,
    vegetation_height: float | list | np.ndarray = None,
    fuel_dict: dict = None,
    fuel_cat: int = None,
):
    r"""
    Calculate the wind reduction factor in unsheltered land based on Baughman and Albini (1980).

    This function computes the wind reduction factor for converting a 20-foot wind speed (measured 20 feet above the fuel surface) to the average wind between the top of the vegetation layer and the top of the flame.
    The midflame wind is then the average wind between `h` and `h+h_f`.
    The calculation is based on empirical formulas provided by Baughman and Albini (1980).

    The function uses polymorphism to handle different types of input for the vegetation height:

    - If `vegetation_height` is provided as a float, it uses it directly.
    - If `vegetation_height` is provided as a list or numpy array, it uses `fuel_cat` to retrieve the vegetation height corresponding to the specific fuel category.
    - If `vegetation_height` is not provided, it retrieves the vegetation height from `fuel_dict`:
        - If the value in `fuel_dict` at key `svn.FUEL_HEIGHT` is a list or numpy array, then `fuel_cat` is mandatory.
        - If it's a float, then `fuel_cat` is not needed.

    Parameters
    ----------
    flame_height : float
        The height at which to calculate the wind speed [ft].

    vegetation_height : float or list or np.ndarray, optional
        The vegetation height [ft]. If a float, it is used directly.
        If a list or numpy array, it should contain vegetation heights indexed by fuel category.

    fuel_dict : dict, optional
        A dictionary containing fuel parameters, including the key `svn.FUEL_HEIGHT` as described in `StandardVariableNames`. This key should map to either a float or a list/numpy array of vegetation heights.

    fuel_cat : int, optional
        The fuel category index used to retrieve the vegetation height from a list or array when `vegetation_height` or `fuel_dict` contains multiple values.

    Returns
    -------
    float
        The wind reduction factor between the 20-foot wind and the wind at the specified interpolation height.

    Raises
    ------
    ValueError
        If insufficient parameters are provided to compute the wind reduction factor.
    IndexError
        If `fuel_cat` is out of bounds for the provided list or array.
    KeyError
        If the required keys are missing in `fuel_dict`.

    Notes
    -----
    The wind reduction factor is computed using the formula from Baughman and Albini (1980):

    .. math::

        \text{Wind Reduction Factor} = \left(1 + 0.36 \frac{H_v}{H_i}\right) \left( \ln\left( \frac{0.36 + \frac{H_i}{H_v}}{0.13} \right) - 1 \right) \Bigg/ \ln\left( \frac{20 + 0.36 H_v}{0.13 H_v} \right)

    where:

    - :math:`H_v` is the vegetation height.
    - :math:`H_i` is the flame height.

    **Reference Heights:**

    - **20-foot Wind Height:** Wind speed measured 20 feet above the vegetation surface.
    - **Flame Height:** Typically the flame height where the fire is burning.

    **Example Usage:**

    ```python
    # Example 1: Using a direct vegetation height
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=6.0,
        vegetation_height=2.0
    )

    # Example 2: Using vegetation heights from a list with a fuel category
    vegetation_heights = [1.5, 2.0, 2.5]
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=6.0,
        vegetation_height=vegetation_heights,
        fuel_cat=2
    )

    # Example 3: Using a fuel dictionary with a fuel category
    fuel_dict = {svn.FUEL_HEIGHT: [1.5, 2.0, 2.5]}
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=6.0,
        fuel_dict=fuel_dict,
        fuel_cat=2
    )

    # Example 4: Using a fuel dictionary without a fuel category
    fuel_dict = {svn.FUEL_HEIGHT: 2.0}
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=6.0,
        fuel_dict=fuel_dict
    )
    ```

    **Important Considerations:**

    - **One-Based Indexing:** Note that `fuel_cat` uses one-based indexing to align with natural fuel category numbering (i.e., the first fuel category is `fuel_cat = 1`).
    - **Data Types:** The function accepts `vegetation_height` as a float, list, or numpy array. Ensure that your inputs are of the correct type.
    - **Units Consistency:** Make sure that the units of `vegetation_height` and the `flame_height` are feet [ft].

    References
    ----------
    Baughman, R. G., & Albini, F. A. (1980).
    Estimating midflame windspeeds.
    In Proceedings, Sixth Conference on Fire and Forest Meteorology, Seattle, WA (pp. 88-92).

    """  # pylint: disable=line-too-long
    # Case 1: vegetation_height is provided directly as a float
    if isinstance(vegetation_height, float):
        return __Baughman_20ft_wind_reduction_factor_unsheltered(flame_height, vegetation_height)

    # Case 2: wind_reduction_factor is a dict; use fuel_cat to get the factor
    if isinstance(vegetation_height, (list, np.ndarray)):
        if fuel_cat is None:
            raise ValueError("fuel_cat must be provided when vegetation_height is a list.")
        try:
            veg_height = vegetation_height[fuel_cat - 1]
        except IndexError as exc:
            raise IndexError(f"Fuel category {fuel_cat-1} not found in vegetation_height array.") from exc
        return __Baughman_20ft_wind_reduction_factor_unsheltered(flame_height, veg_height)

    # Case 3: Retrieve vegetation_height from fuel_dict using fuel_cat
    if fuel_dict is not None and fuel_cat is not None:
        try:
            list_wrf = fuel_dict[svn.FUEL_HEIGHT]
        except KeyError as exc:
            raise KeyError(f"Key {svn.FUEL_HEIGHT} not found in fuel_dict.") from exc
        try:
            veg_height = list_wrf[fuel_cat - 1]
        except IndexError as exc:
            raise IndexError(f"Fuel category {fuel_cat-1} not found in fuel_dict.") from exc
        return __Baughman_20ft_wind_reduction_factor_unsheltered(flame_height, veg_height)

    # Case 4: Retrieve vegetation_height from fuel_dict
    if fuel_dict is not None and fuel_cat is None:
        try:
            veg_height = fuel_dict[svn.FUEL_HEIGHT]
        except KeyError as exc:
            raise KeyError(f"Key {svn.FUEL_HEIGHT} not found in fuel_dict.") from exc
        return __Baughman_20ft_wind_reduction_factor_unsheltered(flame_height, veg_height)

    # Insufficient parameters provided
    raise ValueError(
        "Insufficient parameters provided. Please provide either "
        "`vegetation_height` as a float, or as a dict with `fuel_cat`, "
        "or provide `fuel_dict` with `fuel_cat`."
    )


def __Baughman_20ft_wind_reduction_factor_unsheltered(
    flame_height: float,
    vegetation_height: float,
):
    """
    Compute the unsheltered wind reduction factor using Baughman and Albini's (1980) formula.
    """  # pylint: disable=line-too-long
    return (
        (1 + 0.36 * vegetation_height / flame_height)
        * (np.log((0.36 + flame_height / vegetation_height) / 0.13) - 1)
        / np.log((20 + 0.36 * vegetation_height) / (0.13 * vegetation_height))
    )


def Baughman_generalized_wind_reduction_factor_unsheltered(
    input_wind_height: float,
    flame_height: float,
    vegetation_height: float | list | np.ndarray = None,
    fuel_dict: dict = None,
    fuel_cat: int = None,
    is_source_wind_height_above_veg: bool = False,
):
    r"""
    Calculate the wind reduction factor in unsheltered land based on Baughman and Albini (1980).

    This function computes the wind reduction factor for converting a wind speed at a certain height (defined hereafter) to the average wind between the top of the vegetation layer and the top of the flame.
    The midflame wind is then the average wind between `h` and `h+h_f`.
    The calculation is the generalization of the method presented in Baughman and Albini (1980) and Albini (1979).

    If `is_source_wind_height_above_veg=True`, then the input wind is considered at height h + h_u, where h_u is given by `input_wind_height`.
    If the flag is set to False, the input wind is

    The function uses polymorphism to handle different types of input for the vegetation height:

    - If `vegetation_height` is provided as a float, it uses it directly.
    - If `vegetation_height` is provided as a list or numpy array, it uses `fuel_cat` to retrieve the vegetation height corresponding to the specific fuel category.
    - If `vegetation_height` is not provided, it retrieves the vegetation height from `fuel_dict`:
        - If the value in `fuel_dict` at key `svn.FUEL_HEIGHT` is a list or numpy array, then `fuel_cat` is mandatory.
        - If it's a float, then `fuel_cat` is not needed.

    Parameters
    ----------
    input_wind_height : float
        The height at which the input wind is given `h_u` (any length unit).

    flame_height : float
        The height at which to calculate the wind speed (any length unit).

    vegetation_height : float or list or np.ndarray, optional
        The vegetation height (any length unit). If a float, it is used directly.
        If a list or numpy array, it should contain vegetation heights indexed by fuel category.

    fuel_dict : dict, optional
        A dictionary containing fuel parameters, including the key `svn.FUEL_HEIGHT` as described in `StandardVariableNames`. This key should map to either a float or a list/numpy array of vegetation heights.

    fuel_cat : int, optional
        The fuel category index used to retrieve the vegetation height from a list or array when `vegetation_height` or `fuel_dict` contains multiple values.

    is_source_wind_height_above_veg : bool, optional
        Consider that the input wind hieght is given above vegetation top if set to True. Default: False.

    Returns
    -------
    float
        The wind reduction factor between the input wind height wind and the wind at the specified interpolation height.

    Raises
    ------
    ValueError
        If insufficient parameters are provided to compute the wind reduction factor.
    IndexError
        If `fuel_cat` is out of bounds for the provided list or array.
    KeyError
        If the required keys are missing in `fuel_dict`.

    Notes
    -----

    **Reference Heights:**

    - **Input Wind Height:** Wind speed at `h + h_u` if `is_source_wind_height_above_veg` set to True, at `h_u` else.
    - **Flame Height:** Typically the flame height where the fire is burning.

    **Example Usage:**

    ```python
    # Example 1: Using a direct vegetation height
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=6.0,
        vegetation_height=2.0
    )

    # Example 2: Using vegetation heights from a list with a fuel category
    vegetation_heights = [1.5, 2.0, 2.5]
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=6.0,
        vegetation_height=vegetation_heights,
        fuel_cat=2
    )

    # Example 3: Using a fuel dictionary with a fuel category
    fuel_dict = {svn.FUEL_HEIGHT: [1.5, 2.0, 2.5]}
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=6.0,
        fuel_dict=fuel_dict,
        fuel_cat=2
    )

    # Example 4: Using a fuel dictionary without a fuel category
    fuel_dict = {svn.FUEL_HEIGHT: 2.0}
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=6.0,
        fuel_dict=fuel_dict
    )
    ```

    **Important Considerations:**

    - **One-Based Indexing:** Note that `fuel_cat` uses one-based indexing to align with natural fuel category numbering (i.e., the first fuel category is `fuel_cat = 1`).
    - **Inout wind height:** Make sure that the input wind height has been set up correctly using the flag `is_source_wind_height_above_veg`.
    - **Data Types:** The function accepts `vegetation_height` as a float, list, or numpy array. Ensure that your inputs are of the correct type.
    - **Units Consistency:** Make sure that the units of `vegetation_height`, `flame_height`, and `input_wind_height` are consistent (meter or feet valid).

    References
    ----------
    Baughman, R. G., & Albini, F. A. (1980).
    Estimating midflame windspeeds.
    In Proceedings, Sixth Conference on Fire and Forest Meteorology, Seattle, WA (pp. 88-92).

    Albini, F. A. (1979). Estimating windspeeds for predicting wildland fire behavior (Vol. 221).
    Intermountain Forest and Range Experiment Station, Forest Service, US Department of Agriculture.

    """  # pylint: disable=line-too-long
    # Case 1: vegetation_height is provided directly as a float
    if isinstance(vegetation_height, float):
        return __Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height, flame_height, vegetation_height, is_source_wind_height_above_veg
        )

    # Case 2: wind_reduction_factor is a dict; use fuel_cat to get the factor
    if isinstance(vegetation_height, (list, np.ndarray)):
        if fuel_cat is None:
            raise ValueError("fuel_cat must be provided when vegetation_height is a list.")
        try:
            veg_height = vegetation_height[fuel_cat - 1]
        except IndexError as exc:
            raise IndexError(f"Fuel category {fuel_cat-1} not found in vegetation_height array.") from exc
        return __Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height, flame_height, veg_height, is_source_wind_height_above_veg
        )

    # Case 3: Retrieve vegetation_height from fuel_dict using fuel_cat
    if fuel_dict is not None and fuel_cat is not None:
        try:
            list_wrf = fuel_dict[svn.FUEL_HEIGHT]
        except KeyError as exc:
            raise KeyError(f"Key {svn.FUEL_HEIGHT} not found in fuel_dict.") from exc
        try:
            veg_height = list_wrf[fuel_cat - 1]
        except IndexError as exc:
            raise IndexError(f"Fuel category {fuel_cat-1} not found in fuel_dict.") from exc
        return __Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height, flame_height, veg_height, is_source_wind_height_above_veg
        )

    # Case 4: Retrieve vegetation_height from fuel_dict
    if fuel_dict is not None and fuel_cat is None:
        try:
            veg_height = fuel_dict[svn.FUEL_HEIGHT]
        except KeyError as exc:
            raise KeyError(f"Key {svn.FUEL_HEIGHT} not found in fuel_dict.") from exc
        return __Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height, flame_height, veg_height, is_source_wind_height_above_veg
        )

    # Insufficient parameters provided
    raise ValueError(
        "Insufficient parameters provided. Please provide either "
        "`vegetation_height` as a float, or as a dict with `fuel_cat`, "
        "or provide `fuel_dict` with `fuel_cat`."
    )


def __Baughman_generalized_wind_reduction_factor_unsheltered(
    input_wind_height: float,
    flame_height: float,
    vegetation_height: float,
    is_source_wind_height_above_veg: bool,
):
    """
    Compute the unsheltered wind reduction factor generalized from Baughman and Albini's (1980) and Albini (1979) formulae.
    """  # pylint: disable=line-too-long
    d_0 = 0.64 * vegetation_height  # zero plane displacement
    z_0 = 0.13 * vegetation_height  # roughness length
    # numerator
    num = (
        __primitive_log_profile(vegetation_height + flame_height, d_0, z_0)
        - __primitive_log_profile(vegetation_height, d_0, z_0)
    ) / flame_height
    if is_source_wind_height_above_veg:
        # consider input wind at height h + h_u
        denom = np.log((input_wind_height + vegetation_height - d_0) / z_0)
    else:
        # consider input wind at height h_u
        denom = np.log((input_wind_height - d_0) / z_0)
    return num / denom


def __primitive_log_profile(z, d_0, z_0):
    """Calculate the primitive of ln((z - d_0) / z_0) with respect to z.""" # pylint: disable=line-too-long
    return (z - d_0) * np.log((z - d_0) / z_0) - z
