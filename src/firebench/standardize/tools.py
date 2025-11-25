import h5py
from ..tools.logging_config import logger
from ..tools.units import ureg
import re

VERSION_STD = "0.2"

VERSION_STD_COMPATIBILITY = {
    "0.1": [],
    "0.2": [],
}

VALIDATION_SCHEME_1 = ["0.1", "0.2"]


ISO8601_REGEX = re.compile(
    r"^\d{4}-\d{2}-\d{2}T"  # Date + 'T'
    r"\d{2}:\d{2}"  # HH:MM (always present)
    r"(?:\:\d{2}(?:\.\d+)?)?"  # optional :SS[.ffffff]
    r"(?:Z|[+-]\d{2}:\d{2})?$"  # optional timezone
)


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


def is_iso8601(s: str) -> bool:
    return bool(ISO8601_REGEX.match(s))


def validate_h5_std(file: h5py.File):
    """
    Validate that the mandatory structure in the h5 file is compliant with the standard
    """
    if "FireBench_io_version" not in file.attrs:
        raise ValueError(f"Attribute `FireBench_io_version` not found.")

    if file.attrs["FireBench_io_version"] in VALIDATION_SCHEME_1:
        # check creation date
        if "created_on" not in file.attrs:
            raise ValueError(f"Attribute `created_on` not found.")

        if not is_iso8601(file.attrs["created_on"]):
            raise ValueError(f"Attribute `created_on` not compliant with ISO8601.")

        # check authors
        if "created_by" not in file.attrs:
            raise ValueError(f"Attribute `created_by` not found.")


def validate_h5_requirement(file: h5py.File, required: dict[str, list[str]]):
    """
    Check if all datasets and associated attributs are present in the file.
    Return False and the name of the first missing item if either the dataset or an attribute is missing
    """
    for dset_path, attrs in required.items():
        if dset_path not in file:
            return False, f"dataset `{dset_path}`"

        dset = file[dset_path]

        for attr_name in attrs:
            if attr_name not in dset.attrs:
                return False, f"attr `{attr_name}` of dataset `{dset_path}`"

    return True, None


def read_quantity_from_fb_dataset(dataset_path: str, file_object: h5py.File | h5py.Group | h5py.Dataset):
    """
    Read a dataset from an HDF5 file, group, or dataset node and return it as a Pint Quantity
    according to the FireBench I/O standard.

    This function expects the dataset to comply with the FireBench standard I/O format
    (version >= 0.1), meaning it must define a string `units` attribute specifying the
    physical units of the stored values. The full dataset is loaded into memory and
    wrapped into a `pint.Quantity` using the global `ureg` registry.

    Parameters
    ----------
    dataset_path : str
        Path to the target dataset relative to `file_object`. For an `h5py.File`,
        this is the absolute or group-relative path (e.g., "/2D_raster/0001/temperature").
    file_object : h5py.File | h5py.Group | h5py.Dataset
        HDF5 file, group, or dataset object from which the dataset will be read.
        Must support item access via `__getitem__` and store datasets with `.attrs`.

    Returns
    -------
    pint.Quantity
        The dataset values loaded into memory, associated with the units taken from
        the dataset's `units` attribute.

    Raises
    ------
    KeyError
        If `dataset_path` does not exist in `file_object`.
    ValueError
        If the dataset has no `units` attribute or it is not a non-empty string.

    Notes
    -----
    - The function reads the **entire dataset** into memory; for very large datasets,
    consider reading subsets instead.
    - Compliant with FireBench I/O standard >= 0.1.
    """  # pylint: disable=line-too-long
    ds = file_object[dataset_path]

    units = ds.attrs.get("units", None)
    if not isinstance(units, str) or not units.strip():
        raise ValueError(
            f"Dataset '{dataset_path}' is missing a valid `units` attribute required by FireBench I/O standard."
        )

    return ureg.Quantity(ds[()], ds.attrs["units"])


def merge_authors(authors_1:str, authors_2:str):
    list_authors_1 = [a.strip() for a in authors_1.split(";") if a.strip()]
    list_authors_2 = [a.strip() for a in authors_2.split(";") if a.strip()]
    n1, n2 = len(list_authors_1), len(list_authors_2)
    merged_authors: list[str] = []
    seen = set()

    max_len = max(n1, n2)
    for i in range(max_len):
        if i < n1:
            a1 = list_authors_1[i]
            if a1 and a1 not in seen:
                merged_authors.append(a1)
                seen.add(a1)
        if i < n2:
            a2 = list_authors_2[i]
            if a2 and a2 not in seen:
                merged_authors.append(a2)
                seen.add(a2)

    if not merged_authors:
        return ""

    return ";".join(merged_authors) + ";"