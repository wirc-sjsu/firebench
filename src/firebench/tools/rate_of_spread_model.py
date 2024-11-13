from .logging_config import logger
from .input_info import ParameterType


class RateOfSpreadModel:
    """
    A base class for fire spread rate models.

    This class provides common functionalities and attributes for different fire spread rate models.
    """  # pylint: disable=line-too-long

    # metada dict containing information about inputs and outputs (std_name, units, range)
    metadata = {}

    @staticmethod
    def compute_ros(input_dict: dict[str, float | int | list[float] | list[int]], **opt) -> float:
        """
        Compute the rate of spread of fire using the specific model.

        This method should be overridden by subclasses.

        Parameters
        ----------
        input_dict : dict[str, float | int | list[float] | list[int]]
            Dictionary containing the input data for various fuel properties.

        Optional Parameters
        -------------------
        **opt : dict
            Optional parameters for the fire spread rate model.

        Returns
        -------
        float
            The computed rate of spread of fire [m/s].
        """  # pylint: disable=line-too-long
        raise NotImplementedError("Subclasses should implement this method")

    @staticmethod
    def prepare_fuel_properties(input_dict, metadata, fuel_cat=None):
        """
        Prepare the fuel properties dictionary for the rate of spread computation.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
        metadata : dict
            Dictionary containing metadata for the variables (e.g., std_name, default values).
        fuel_cat : int, optional
            The fuel category index (one-based). If provided, the function will extract the property of the specified fuel category.

        Returns
        -------
        dict
            The fuel properties dictionary prepared for the rate of spread computation.
        """  # pylint: disable=line-too-long
        fuel_properties_dict = {}

        for var, var_info in metadata.items():
            if var_info.get("type") == ParameterType.output:
                continue

            key = var_info["std_name"]
            # Get value from input dict
            try:
                value = input_dict[key]
            except KeyError as exc:
                if var_info.get("type") == ParameterType.optional:
                    logger.info("%s not found in input. Using default value.", key)
                    fuel_properties_dict[var] = var_info["default"]
                    continue
                raise KeyError(f"Mandatory key '{key}' not found in input_dict.") from exc

            # Check if fuel model variables need to be extracted
            if var_info.get("is_fuel_model_variable", False) and fuel_cat is not None:
                # Get the property of the fuel category
                fuel_properties_dict[var] = value[fuel_cat - 1]
            else:
                # Use the value directly
                fuel_properties_dict[var] = value

        return fuel_properties_dict
