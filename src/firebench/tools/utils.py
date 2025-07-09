import hashlib

import numpy as np
from pint import Quantity
from .logging_config import logger


def is_scalar_quantity(x: any):
    """
    Determine if the input is a scalar or a pint.Quantity with a scalar magnitude.

    Parameters
    ----------
    x : Any
        The value to check. Can be a scalar, array-like, or a pint.Quantity object.

    Returns
    -------
    bool
        True if the input or its magnitude is scalar, False otherwise.
    """  # pylint: disable=line-too-long
    if isinstance(x, Quantity):
        magnitude = x.magnitude
    else:
        magnitude = x
    return np.isscalar(magnitude)


def get_value_by_category(x: any, category_index: int):
    """
    Retrieve a value from `x` based on the specified category index.

    Parameters
    ----------
    x : scalar or array-like
        The input value, which can be a scalar or an array-like object
        (e.g., list, NumPy array, or pint.Quantity).
    category_index : int
        The one-based category index to select from `x` if `x` is array-like.
        If `x` is scalar, this parameter is ignored.

    Returns
    -------
    value
        The scalar value from `x`: either `x` itself if scalar, or `x[category_index - 1]`
        if array-like.

    Raises
    ------
    ValueError
        If `category_index` is less than 1.
    IndexError
        If `category_index` is out of bounds for `x`.

    Notes
    -----
    - If `x` is scalar, `category_index` is ignored.
    - The `category_index` is one-based; to select the first element, use `category_index=1`.
    """  # pylint: disable=line-too-long
    if is_scalar_quantity(x):
        return x

    if category_index < 1:
        raise ValueError("category_index must be an integer greater than or equal to 1.")
    try:
        return x[category_index - 1]
    except IndexError as exc:
        raise IndexError(f"One-based index {category_index} not found in {x}.") from exc


def calculate_sha256(file_path):
    """
    Calculate the SHA-256 hash of a file's contents.

    Parameters:
    -----------
    file_path : str
        The path to the file for which the SHA-256 hash is to be calculated.

    Returns:
    --------
    str
        The SHA-256 hash as a hexadecimal string if the file is successfully processed, and an empty string if not.
    """  # pylint: disable=line-too-long
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as file:
            # Read the file in chunks to handle large files efficiently
            for byte_block in iter(lambda: file.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except FileNotFoundError:
        logger.error("File not found: '%s'. Unable to calculate SHA-256 hash.", file_path)
    except PermissionError:
        logger.error(
            "Permission denied when accessing file: '%s'. Unable to calculate SHA-256 hash.", file_path
        )
    except OSError as e:
        logger.error("OS error occurred while processing file '%s': %s", file_path, e)
    return ""
