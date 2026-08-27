from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .c001_caldor import run_caldor_benchmark
    from .registry import AVAIL_BENCHMARKS

__all__ = ["AVAIL_BENCHMARKS", "run_caldor_benchmark"]


def __getattr__(name):
    if name == "AVAIL_BENCHMARKS":
        value = import_module(".registry", __name__).AVAIL_BENCHMARKS
    elif name == "run_caldor_benchmark":
        value = import_module(".c001_caldor", __name__).run_caldor_benchmark
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    globals()[name] = value
    return value


def __dir__():
    return sorted({*globals(), *__all__})
