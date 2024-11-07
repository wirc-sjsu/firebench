from enum import Enum


class ParameterType(Enum):
    """
    List of parameter types for metadata dictionaries of models in FireBench.
    """

    input = "input"
    output = "output"
    optional = "optional"
