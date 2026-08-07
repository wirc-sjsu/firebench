from importlib import import_module
from importlib.metadata import version, PackageNotFoundError

_SUBMODULES = {
    "adapter_common",
    "ros_models",
    "tools",
    "wind_interpolation",
    "stats",
    "metrics",
    "sensors",
    "standardize",
    "signing",
}

try:
    __version__ = version("firebench")
except PackageNotFoundError:
    __version__ = "unknown"


def __getattr__(name):
    if name in _SUBMODULES:
        value = import_module(f".{name}", __name__)
    elif name == "logger":
        value = import_module(".tools.logging_config", __name__).logger
    elif name == "svn":
        value = import_module(".tools.namespace", __name__).StandardVariableNames
    elif name in {"ureg", "Quantity"}:
        unit_registry = import_module(".tools.units", __name__).ureg
        value = unit_registry if name == "ureg" else unit_registry.Quantity
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    globals()[name] = value
    return value


def __dir__():
    return sorted({*globals(), *_SUBMODULES, "logger", "svn", "ureg", "Quantity"})


__all__ = ["__version__"]
