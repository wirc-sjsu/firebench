import h5py
from ..tools.logging_config import logger

VERSION_STD = "0.1"

VERSION_STD_COMPATIBILITY = {
    "0.1": [],
}


def check_std_version(file: h5py.File):
    """
    Determine whether the standard version of a file should be updated to the latest.

    This function inspects the `FireBench_io_version` attribute stored in the given HDF5 file.
    It compares the file's version with the current standard version defined in `VERSION_STD`.
    The return value indicates whether the caller should update the file's standard version.

    The logic is as follows:
    - If the attribute is missing, the file is treated as new and should be updated.
    - If the attribute matches the current standard version, the file is already up to date and may be updated.
    - If the attribute is in the compatibility list for the current version, the file is considered valid
      but should not be updated; a warning is logged instead.
    - If the attribute is not compatible with the current version, a `ValueError` is raised.

    Parameters
    ----------
    file : h5py.File
        An open HDF5 file object to be checked. The file is expected to potentially have a
        `FireBench_io_version` attribute at the root.

    Returns
    -------
    bool
        True if the file should be updated to the latest standard version.
        False if the file has a compatible version and should not be updated.

    Raises
    ------
    ValueError
        If the file contains a `FireBench_io_version` attribute that is incompatible with the
        current standard version.
    """  # pylint: disable=line-too-long
    if "FireBench_io_version" not in file.attrs:
        return True

    file_version = file.attrs["FireBench_io_version"]

    if file_version == VERSION_STD:
        return True

    if file_version in VERSION_STD_COMPATIBILITY[VERSION_STD]:
        logger.warning(
            "FireBench_io_version differs but is compatible: file=%s, current=%s", file_version, VERSION_STD
        )
        return False

    raise ValueError(f"Standard version {file_version} not compatible with {VERSION_STD}")
