from importlib.metadata import version, PackageNotFoundError
from . import ros_models, tools, wind_interpolation, stats, metrics, sensors, standardize, signing
from .tools.logging_config import logger
from .tools.namespace import StandardVariableNames as svn
from .tools.units import ureg
from .signing.signing import verify_output_dict, write_case_results

Quantity = ureg.Quantity

try:
    __version__ = version("firebench")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["__version__"]
