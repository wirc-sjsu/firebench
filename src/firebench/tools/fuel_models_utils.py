import numpy as np
from pint import Quantity
from pint.errors import DimensionalityError


def find_closest_fuel_class_by_properties(
    fuel_model_dict: dict[str, Quantity],
    properties_to_test: dict[str, Quantity],
    weights: dict[str, float] = None,
) -> int:
    """
    Find the fuel class index that has the closest properties to the given set of properties.

    This function compares a set of fuel classes defined in `fuel_model_dict` with a target set of properties
    provided in `properties_to_test`. It calculates a weighted Euclidean distance between the properties of each
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
    """
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
                (fuel_model_converted[prop_key][class_index].magnitude - target_magnitude) ** 2
            )

    # Return the one-based index of the fuel class with the minimum total distance
    closest_index = np.argmin(np.sum(distances, axis=0)) + 1  # Return 1-based index
    return closest_index
