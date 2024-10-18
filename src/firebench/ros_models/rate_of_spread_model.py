class RateOfSpreadModel:
    """
    A base class for fire spread rate models.

    This class provides common functionalities and attributes for different fire spread rate models.
    """  # pylint: disable=line-too-long

    # metada dict containing information about inputs and outputs (std_name, units, range)
    metadata = {}

    @staticmethod
    def compute_ros(input_dict: dict[str, list[float]], **opt) -> float:
        """
        Compute the rate of spread of fire using the specific model.

        This method should be overridden by subclasses.

        Parameters
        ----------
        input_dict : dict[str, list[float]]
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
