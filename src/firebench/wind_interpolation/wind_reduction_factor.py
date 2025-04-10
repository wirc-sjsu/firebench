import numpy as np

from ..tools import get_value_by_category


def apply_wind_reduction_factor(
    wind_speed: float | list | np.ndarray,
    wind_reduction_factor: float | list | np.ndarray,
    fuel_cat: int = 0,
):
    """
    Calculate the wind speed at a different height by applying a wind reduction factor.

    This function computes the wind speed at a new height by multiplying the input wind speed
    by a wind reduction factor. It handles various types of inputs for the wind speed and wind
    reduction factor, including floats, lists, NumPy arrays, and `pint.Quantity`. If the inputs
    are lists or arrays, the function uses ``fuel_cat`` to select the appropriate value.

    Parameters
    ----------
    wind_speed : float, list, or np.ndarray
        The wind speed at the initial height. If a list or array, ``fuel_cat`` is used to select
        the appropriate value.

    wind_reduction_factor : float, list, or np.ndarray
        The wind reduction factor to apply. If a list or array, ``fuel_cat`` is used to select
        the appropriate value.

    fuel_cat : int, optional
        The fuel category index used to select values from list or array inputs.
        Uses one-based indexing (i.e., the first category is ``fuel_cat=1``).
        Required if any of the inputs are lists or arrays.

    Returns
    -------
    float
        The wind speed at the new height, calculated by applying the wind reduction factor.

    Raises
    ------
    ValueError
        If ``fuel_cat`` is not provided when required, or if inputs are invalid.

    IndexError
        If ``fuel_cat`` is out of bounds for the provided list or array inputs.

    Notes
    -----
    **One-Based Indexing**

    ``fuel_cat`` uses one-based indexing to align with natural fuel category numbering
    (i.e., the first fuel category is ``fuel_cat=1``).

    **Data Types**

    The function accepts ``wind_speed`` and ``wind_reduction_factor`` as floats, lists, or
    NumPy arrays. Ensure that your inputs are of the correct type.

    **Units Consistency**

    Make sure that the units of ``wind_speed`` are consistent with your application.
    The wind reduction factor is dimensionless.

    Examples
    --------
    **Example 1: Using scalar inputs**

    .. code-block:: python

        new_wind_speed = apply_wind_reduction_factor(
            wind_speed=10.0,
            wind_reduction_factor=0.8
        )
        # Result: new_wind_speed = 8.0

    **Example 2: Using list inputs with a fuel category**

    .. code-block:: python

        wind_speeds = [10.0, 12.0, 15.0]
        wind_reduction_factors = [0.7, 0.8, 0.9]
        new_wind_speed = apply_wind_reduction_factor(
            wind_speed=wind_speeds,
            wind_reduction_factor=wind_reduction_factors,
            fuel_cat=2
        )
        # Result: new_wind_speed = 12.0 * 0.8 = 9.6

    **Example 3: Using NumPy arrays**

    .. code-block:: python

        import numpy as np
        wind_speeds = np.array([10.0, 12.0, 15.0])
        wind_reduction_factors = np.array([0.7, 0.8, 0.9])
        new_wind_speed = apply_wind_reduction_factor(
            wind_speed=wind_speeds,
            wind_reduction_factor=wind_reduction_factors,
            fuel_cat=3
        )
        # Result: new_wind_speed = 15.0 * 0.9 = 13.5

    """  # pylint: disable=line-too-long
    wind_speed_value = get_value_by_category(wind_speed, fuel_cat)
    wind_reduction_factor_value = get_value_by_category(wind_reduction_factor, fuel_cat)

    return wind_speed_value * wind_reduction_factor_value


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
        The flame height (``H_i``) in feet [ft]. If a list or array, ``fuel_cat`` is used to select the appropriate value.

    vegetation_height : float, list, or np.ndarray
        The vegetation height (``H_v``) in feet [ft]. If a list or array, ``fuel_cat`` is used to select the appropriate value.

    fuel_cat : int, optional
        The fuel category index used to select values from list or array inputs. Uses one-based indexing (i.e., the first category is ``fuel_cat=1``). Required if any of the inputs are lists or arrays.

    Returns
    -------
    float
        The wind reduction factor between the 20-foot wind and the average wind speed at the midflame height.

    Raises
    ------
    ValueError
        If ``fuel_cat`` is not provided when required, or if inputs are invalid.

    IndexError
        If ``fuel_cat`` is out of bounds for the provided list or array inputs.

    Notes
    -----
    The wind reduction factor is computed using the formula from Baughman and Albini (1980):

    .. math::

        \text{Wind Reduction Factor} = \frac{\left(1 + 0.36 \frac{H_v}{H_i}\right)
        \left( \ln\left( \frac{0.36 + \frac{H_i}{H_v}}{0.13} \right) - 1 \right)}
        {\ln\left( \frac{20 + 0.36 H_v}{0.13 H_v} \right)}

    where:

    - ``H_v`` is the vegetation height.
    - ``H_i`` is the flame height.

    **Reference Heights**

    - **20-foot Wind Height**: Wind speed measured 20 feet above the vegetation surface.
    - **Flame Height**: The height of the flame.

    Examples
    --------
    **Example 1: Using scalar inputs**

    .. code-block:: python

        wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
            flame_height=6.0,
            vegetation_height=2.0
        )

    **Example 2: Using list inputs with a fuel category**

    .. code-block:: python

        flame_heights = [5.0, 6.0, 7.0]
        vegetation_heights = [1.5, 2.0, 2.5]
        wrf = Baughman_20ft_wind_reduction_factor_unsheltered(
            flame_height=flame_heights,
            vegetation_height=vegetation_heights,
            fuel_cat=2
        )

    **Important Considerations**

    - **One-Based Indexing**: Note that ``fuel_cat`` uses one-based indexing to align with natural fuel category numbering (i.e., the first fuel category is ``fuel_cat = 1``).
    - **Data Types**: The function accepts ``flame_height`` and ``vegetation_height`` as floats, lists, or NumPy arrays. Ensure that your inputs are of the correct type.
    - **Units Consistency**: Make sure that the units of ``flame_height`` and ``vegetation_height`` are in feet [ft].

    References
    ----------
    Baughman, R. G., & Albini, F. A. (1980). *Estimating midflame wind speeds*.
    In *Proceedings, Sixth Conference on Fire and Forest Meteorology*, Seattle, WA (pp. 88–92).
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
    Calculate the wind reduction factor in unsheltered land based on Baughman and Albini (1980) and Albini (1979).

    This function computes the wind reduction factor for converting a wind speed measured at a given height
    to the average wind speed between the top of the vegetation layer and the top of the flame. The calculation
    generalizes the method presented in Baughman and Albini (1980) and Albini (1979).

    Parameters
    ----------
    input_wind_height : float, list, or np.ndarray
        The height at which the wind speed is provided (``h_u``).
        If a list or array, ``fuel_cat`` is used to select the appropriate value.

    flame_height : float, list, or np.ndarray
        The flame height (``h_f``). If a list or array, ``fuel_cat`` is used to select the appropriate value.

    vegetation_height : float, list, or np.ndarray
        The vegetation height (``h``). If a list or array, ``fuel_cat`` is used to select the appropriate value.

    fuel_cat : int, optional
        The fuel category index used to select values from list or array inputs. Uses one-based indexing (i.e., the first category is ``fuel_cat=1``). Required if any of the inputs are lists or arrays.

    is_source_wind_height_above_veg : bool, optional
        If ``True``, the input wind height is assumed to be above the vegetation top (i.e., at ``h + h_u``). If ``False`` (default), it is assumed to be from the ground level (i.e., at ``h_u``).

    Returns
    -------
    float
        The wind reduction factor between the input wind height and the average wind at the midflame height.

    Raises
    ------
    ValueError
        If ``fuel_cat`` is not provided when required, or if inputs are invalid.

    IndexError
        If ``fuel_cat`` is out of bounds for the provided list or array inputs.

    Notes
    -----
    The wind reduction factor is computed using a generalization of the logarithmic wind profile theory
    as described by Baughman and Albini (1980) and Albini (1979).

    **Reference Heights**

    - **Input Wind Height** (``h_u``): The height where wind is measured. If ``is_source_wind_height_above_veg`` is ``True``,
      it is interpreted as ``h + h_u``; otherwise, it is just ``h_u``.

    - **Vegetation Height** (``h``): The height of the vegetation.

    - **Flame Height** (``h_f``): The height of the flame.

    Examples
    --------
    **Example 1: Using scalar inputs**

    .. code-block:: python

        wrf = Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=10.0,
            flame_height=6.0,
            vegetation_height=2.0
        )

    **Example 2: Using list inputs with a fuel category**

    .. code-block:: python

        input_wind_heights = [10.0, 15.0, 20.0]
        flame_heights = [5.0, 6.0, 7.0]
        vegetation_heights = [1.5, 2.0, 2.5]
        wrf = Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=input_wind_heights,
            flame_height=flame_heights,
            vegetation_height=vegetation_heights,
            fuel_cat=2
        )

    **Example 3: Using pint Quantity list inputs**

    .. code-block:: python

        input_wind_heights = firebench.Quantity([10.0, 15.0, 20.0])
        flame_heights = 3
        vegetation_heights = [1.5, 2.0, 2.5]
        wrf = Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=input_wind_heights,
            flame_height=flame_heights,
            vegetation_height=vegetation_heights,
            fuel_cat=2
        )

    **Important Considerations**

    - **One-Based Indexing**: Note that ``fuel_cat`` uses one-based indexing to align with natural fuel category numbering (i.e., the first fuel category is ``fuel_cat = 1``).
    - **Data Types**: The function accepts ``input_wind_height``, ``flame_height``, and ``vegetation_height`` as floats, lists, or NumPy arrays. Ensure that your inputs are of the correct type.
    - **Units Consistency**: All height inputs should use consistent units (e.g., all in meters or all in feet).

    References
    ----------
    Baughman, R. G., & Albini, F. A. (1980). *Estimating midflame wind speeds*.
    In *Proceedings, Sixth Conference on Fire and Forest Meteorology*, Seattle, WA (pp. 88–92).

    Albini, F. A. (1979). *Estimating windspeeds for predicting wildland fire behavior* (Vol. 221).
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
