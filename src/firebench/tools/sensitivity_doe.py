from typing import Dict, List, Tuple

from pint import Quantity, Unit
from scipy.stats.qmc import Sobol


def sobol_seq(
    N: float, variables_info: Dict[str, Tuple[Unit, List[float]]], scramble: bool = False, seed: int = None
) -> Dict[str, Quantity]:
    """
    Generate a Sobol sequence for the given variables with specified units and ranges.

    This function generates a Sobol sequence and scales it to the ranges specified for each variable. The result
    is a dictionary where each variable's values are given as a `pint.Quantity` with the appropriate unit.

    Parameters
    ----------
    N : int
        The number of points in the Sobol sequence.
    variables_info : dict
        A dictionary where each key is the name of a variable, and the value is a tuple containing a `pint.Unit`
        and a list of two floats representing the range of the variable.
    scramble : bool, optional
        If True, applies scrambling to the Sobol sequence for better uniformity. Defaults to False.
    seed : int, optional
        Seed for the random number generator for reproducibility. Defaults to None.

    Returns
    -------
    dict
        A dictionary where each key is a variable name, and the value is a `pint.Quantity` array with the
        specified unit and range.

    Raises
    ------
    ValueError
        If the length of the range list is not equal to 2 or if the upper range value is less than or equal to the lower range value.
    """  # pylint: disable=line-too-long
    nb_variable = len(variables_info.keys())
    raw_sequence = Sobol(d=nb_variable, scramble=scramble, seed=seed).random(N)
    output_dict = {}

    for k, (var_name, var_info) in enumerate(variables_info.items()):
        var_unit, var_range = var_info

        if len(var_range) != 2:
            raise ValueError(f"Range for variable '{var_name}' must have exactly 2 elements.")
        if var_range[1] <= var_range[0]:
            raise ValueError(
                f"Upper range value must be greater than lower range value for variable '{var_name}'."
            )

        output_dict[var_name] = Quantity(
            (var_range[1] - var_range[0]) * raw_sequence[:, k] + var_range[0], var_unit
        )

    return output_dict
