from typing import Tuple, Any, Callable
import numpy as np
from ..tools.logging_config import logger

CTXKey = Tuple[str, str, str]
ComputeFn = Callable[..., Any]


class CtxKeyError(KeyError):
    """Raised when a context key is not declared in CTX_SPEC."""


class CtxValueError(RuntimeError):
    """Raised when a cached value is missing/invalid in a way that suggests misuse."""


def ctx_get_or_compute(
    ctx_spec: dict[CTXKey, str],
    ctx: dict[CTXKey, Any],
    key: CTXKey,
    compute: ComputeFn,
    *args: Any,
    **kwargs: Any,
) -> Any:
    if key not in ctx_spec.keys():
        raise CtxKeyError(
            f"Context key {key!r} is not declared in CTX_SPEC. "
            "Declare it in CTX_SPEC to make cache usage explicit."
        )

    if key in ctx:
        logger.debug("CTXKey %s found in CTX dict", key)
        return ctx[key]

    logger.debug("Add field %s to CTX dict", key)
    value = compute(*args, **kwargs)
    ctx[key] = value

    return value
