import numpy as np

from ..tools.namespace import StandardVariableNames as svn
from ..tools import is_scalar_quantity, get_value_by_category


def apply_wind_reduction_factor(
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
    flame_height: float | list | np.ndarray,
    vegetation_height: float | list | np.ndarray,
    fuel_cat: int = 0,
):
    r"""
    Calculate the wind reduction factor in unsheltered land based on Baughman and Albini (1980).

    This function computes the wind reduction factor for converting a 20-foot wind speed
    (measured 20 feet above the vegetation surface) to the average wind speed between the
    top of the vegetation layer and the top of the flame. The calculation is based on empirical
    formulas provided by Baughman and Albini (1980).

    Parameters
    ----------
    flame_height : float, list, or np.ndarray
        The flame height (:math:`H_i`) in feet [ft]. If a list or array, `fuel_cat` is used
        to select the appropriate value.

    vegetation_height : float, list, or np.ndarray
        The vegetation height (:math:`H_v`) in feet [ft]. If a list or array, `fuel_cat` is
        used to select the appropriate value.

    fuel_cat : int, optional
        The fuel category index used to select values from list or array inputs.
        Uses one-based indexing (i.e., the first category is `fuel_cat=1`).
        Required if any of the inputs are lists or arrays.

    Returns
    -------
    float
        The wind reduction factor between the 20-foot wind and the average wind speed at the midflame height.

    Raises
    ------
    ValueError
        If `fuel_cat` is not provided when required, or if inputs are invalid.
    IndexError
        If `fuel_cat` is out of bounds for the provided list or array inputs.

    Notes
    -----
    The wind reduction factor is computed using the formula from Baughman and Albini (1980):

    .. math::

        \text{Wind Reduction Factor} = \frac{\left(1 + 0.36 \frac{H_v}{H_i}\right)
        \left( \ln\left( \frac{0.36 + \frac{H_i}{H_v}}{0.13} \right) - 1 \right)}
        {\ln\left( \frac{20 + 0.36 H_v}{0.13 H_v} \right)}

    where:

    - :math:`H_v` is the vegetation height.
    - :math:`H_i` is the flame height.

    **Reference Heights:**

    - **20-foot Wind Height:** Wind speed measured 20 feet above the vegetation surface.
    - **Flame Height:** The height of the flame.

    **Example Usage:**

    ```python
    # Example 1: Using scalar inputs
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=6.0,
        vegetation_height=2.0
    )

    # Example 2: Using list inputs with a fuel category
    flame_heights = [5.0, 6.0, 7.0]
    vegetation_heights = [1.5, 2.0, 2.5]
    wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=flame_heights,
        vegetation_height=vegetation_heights,
        fuel_cat=2
    )
    ```

    **Important Considerations:**

    - **One-Based Indexing:** Note that `fuel_cat` uses one-based indexing to align with natural fuel category numbering (i.e., the first fuel category is `fuel_cat = 1`).
    - **Data Types:** The function accepts `flame_height` and `vegetation_height` as floats, lists, or numpy arrays. Ensure that your inputs are of the correct type.
    - **Units Consistency:** Make sure that the units of `flame_height` and `vegetation_height` are in feet [ft].

    References
    ----------
    Baughman, R. G., & Albini, F. A. (1980).
    Estimating midflame windspeeds.
    In Proceedings, Sixth Conference on Fire and Forest Meteorology, Seattle, WA (pp. 88-92).
    """  # pylint: disable=line-too-long
    # Extract scalar values using get_value_by_category
    vegetation_height_value = get_value_by_category(vegetation_height, fuel_cat)
    flame_height_value = get_value_by_category(flame_height, fuel_cat)

    return __Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height_value,
        vegetation_height_value,
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
    input_wind_height: float | list | np.ndarray,
    flame_height: float | list | np.ndarray,
    vegetation_height: float | list | np.ndarray,
    fuel_cat: int = 0,
    is_source_wind_height_above_veg: bool = False,
):
    r"""
    Calculate the wind reduction factor in unsheltered land based on Baughman and Albini (1980).

    This function computes the wind reduction factor for converting a wind speed at a specified height
    to the average wind speed between the top of the vegetation layer and the top of the flame.
    The calculation generalizes the method presented in Baughman and Albini (1980) and Albini (1979).

    Parameters
    ----------
    input_wind_height : float, list, or np.ndarray
        The height at which the input wind speed is given (`h_u`). If a list or array, `fuel_cat`
        is used to select the appropriate value.

    flame_height : float, list, or np.ndarray
        The flame height (`h_f`). If a list or array, `fuel_cat` is used to select the appropriate value.

    vegetation_height : float, list, or np.ndarray
        The vegetation height (`h`). If a list or array, `fuel_cat` is used to select the appropriate value.

    fuel_cat : int, optional
        The fuel category index used to select values from list or array inputs.
        Uses one-based indexing (i.e., the first category is `fuel_cat=1`).
        Required if any of the inputs are lists or arrays.

    is_source_wind_height_above_veg : bool, optional
        If `True`, the input wind height is considered to be above the vegetation top (i.e., at `h + h_u`).
        If `False` (default), the input wind height is considered to be from the ground level (i.e., at `h_u`).

    Returns
    -------
    float
        The wind reduction factor between the input wind height and the average wind at the midflame height.

    Raises
    ------
    ValueError
        If `fuel_cat` is not provided when required, or if inputs are invalid.

    IndexError
        If `fuel_cat` is out of bounds for the provided list or array inputs.

    Notes
    -----
    **Reference Heights:**

    - **Input Wind Height (`h_u`):** The height at which the input wind speed is given.
      If `is_source_wind_height_above_veg` is `True`, the input wind height is `h + h_u`.
      Otherwise, it is `h_u`.

    - **Vegetation Height (`h`):** The height of the vegetation.

    - **Flame Height (`h_f`):** The height of the flame.

    The midflame wind speed is calculated as the average wind speed between the top of the vegetation
    (`h`) and the top of the flame (`h + h_f`).

    **Data Types:**

    - The function accepts `input_wind_height`, `flame_height`, and `vegetation_height` as floats,
      lists, or numpy arrays. If they are lists or arrays, `fuel_cat` must be provided to select
      the appropriate value.

    - The function uses one-based indexing for `fuel_cat`.

    **Example Usage:**

    ```python
    # Example 1: Using scalar inputs
    wrf = Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height=10.0,
        flame_height=6.0,
        vegetation_height=2.0
    )

    # Example 2: Using list inputs with a fuel category
    input_wind_heights = [10.0, 15.0, 20.0]
    flame_heights = [5.0, 6.0, 7.0]
    vegetation_heights = [1.5, 2.0, 2.5]
    wrf = Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height=input_wind_heights,
        flame_height=flame_heights,
        vegetation_height=vegetation_heights,
        fuel_cat=2
    )

    # Example 3: Using pint list inputs with a fuel category
    input_wind_heights = firebench.Quantity([10.0, 15.0, 20.0])
    flame_heights = 3
    vegetation_heights = [1.5, 2.0, 2.5]
    wrf = Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height=input_wind_heights,
        flame_height=flame_heights,
        vegetation_height=vegetation_heights,
        fuel_cat=2
    )
    ```

    **Units Consistency:**

    - Ensure that all height inputs (`input_wind_height`, `flame_height`, and `vegetation_height`)
      are provided in consistent units (e.g., all in meters or all in feet).

    References
    ----------
    Baughman, R. G., & Albini, F. A. (1980).
    Estimating midflame windspeeds.
    In Proceedings, Sixth Conference on Fire and Forest Meteorology, Seattle, WA (pp. 88-92).

    Albini, F. A. (1979). Estimating windspeeds for predicting wildland fire behavior (Vol. 221).
    Intermountain Forest and Range Experiment Station, Forest Service, US Department of Agriculture.
    """  # pylint: disable=line-too-long
    # Extract scalar values using get_value_by_category
    vegetation_height_value = get_value_by_category(vegetation_height, fuel_cat)
    input_wind_height_value = get_value_by_category(input_wind_height, fuel_cat)
    flame_height_value = get_value_by_category(flame_height, fuel_cat)

    return __Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height_value,
        flame_height_value,
        vegetation_height_value,
        is_source_wind_height_above_veg,
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
    """Calculate the primitive of ln((z - d_0) / z_0) with respect to z."""  # pylint: disable=line-too-long
    return (z - d_0) * np.log((z - d_0) / z_0) - z
