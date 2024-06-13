from typing import Dict, List, Tuple

import numpy as np
from pint import Quantity, Unit
from SALib.sample import sobol


def sobol_seq(
    N: int,
    variables_info: Dict[str, Tuple[Unit, List[float]]],
    scramble: bool = True,
    seed: int = 0,
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
        If True, applies scrambling to the Sobol sequence for better uniformity. Defaults to True.
    seed : int, optional
        Seed for the random number generator for reproducibility. Defaults to 0.

    Returns
    -------
    dict
        A dictionary where each key is a variable name, and the value is a `pint.Quantity` array with the
        specified unit and range.
    sobol_problem : dict
        A dictionary defining the Sobol problem with keys 'num_vars', 'names', and 'bounds'.
    N_sobol : int
        The number of points in the generated Sobol sequence.
    """  # pylint: disable=line-too-long
    sobol_problem = {
        "num_vars": len(variables_info),
        "names": [k.value for k in variables_info.keys()],  # Replace with your variable names
        "bounds": [variables_info[k][1] for k in variables_info.keys()],
    }
    sobol_seq = sobol.sample(sobol_problem, N, calc_second_order=True, scramble=scramble, seed=seed)
    N_sobol = np.size(sobol_seq, 0)
    output_dict = {}

    for k, (var_name, var_info) in enumerate(variables_info.items()):
        output_dict[var_name] = Quantity(sobol_seq[:, k], var_info[0])

    return output_dict, sobol_problem, N_sobol


def merge_dictionaries(dict1: dict, dict2: dict) -> dict:
    """
    Merge two dictionaries and check for key conflicts.

    Parameters
    ----------
    dict1 : dict
        The first dictionary.
    dict2 : dict
        The second dictionary.

    Returns
    -------
    dict
        The merged dictionary.

    Raises
    ------
    KeyError
        If there is a key conflict between the dictionaries.
    """  # pylint: disable=line-too-long
    # Check for key conflicts
    conflicts = set(dict1.keys()) & set(dict2.keys())
    if conflicts:
        raise KeyError(f"Key conflicts detected: {conflicts}")

    return {**dict1, **dict2}
