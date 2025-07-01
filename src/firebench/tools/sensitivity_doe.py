import numpy as np
from SALib.sample import sobol
from .units import ureg


def sobol_seq(
    N: int,
    variables_info: dict,
    scramble: bool = True,
    seed: int = 0,
):
    """
    Generate a Sobol sequence for the given variables with specified units and ranges.

    This function generates a Sobol sequence and scales it to the ranges specified for each variable. The result
    is a dictionary where each variable's values are given as a `pint.Quantity` with the appropriate unit.

    Parameters
    ----------
    N : int
        The number of points in the Sobol sequence.
    variables_info : dict
        A dictionary where each key is the name of a variable, and the value is a dictionary containing a `pint.Unit` (key: unit)
        and a list of two floats representing the range of the variable (key: range).
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
        "bounds": [variables_info[k]["range"] for k in variables_info.keys()],
    }
    sobol_sequence = sobol.sample(sobol_problem, N, calc_second_order=True, scramble=scramble, seed=seed)
    N_sobol = np.size(sobol_sequence, 0)
    output_dict = {}

    for k, (var_name, var_info) in enumerate(variables_info.items()):
        output_dict[var_name] = ureg.Quantity(sobol_sequence[:, k], var_info["unit"])

    return output_dict, sobol_problem, N_sobol


def merge_dictionaries(dict1: dict, dict2: dict, prefer: int = 0) -> dict:
    """
    Merge two dictionaries, resolving key conflicts by favoring one dictionary.

    Parameters
    ----------
    dict1 : dict
        The first dictionary.
    dict2 : dict
        The second dictionary.
    prefer : int, optional
        Which dictionary to prefer in case of key conflict (0: raise error if conflicts, 1:'dict1' or 2:'dict2'). Default is 0.

    Returns
    -------
    dict
        The merged dictionary with conflicts resolved based on the 'prefer' setting.

    Raises
    ------
    KeyError
        If there is a key conflict between the dictionaries and prefer is set to 0.
    """
    match prefer:
        case 1:
            return {**dict2, **dict1}  # dict1 overrides dict2
        case 2:
            return {**dict1, **dict2}  # dict2 overrides dict1
        case _:
            conflicts = set(dict1.keys()) & set(dict2.keys())
            if conflicts:
                raise KeyError(f"Key conflicts detected: {conflicts}")
            return {**dict2, **dict1} # merge without conflicts
