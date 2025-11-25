import h5py
from ..tools.logging_config import logger
from ..tools.units import ureg
import re
import numpy as np

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

IGNORE_ATTRIBUTES = {
    "/": {"created_on", "created_by", "FireBench_io_version"},
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


def merge_authors(authors_1: str, authors_2: str):
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


def collect_conflicts(file1, file2, path: str = "/", conflicts: list | None = None):
    """
    Recursively collect conflicts between two HDF5 trees.

    A *conflict* is defined as one of:
      - Same path exists in both files but with different node types
        (group vs dataset).
      - Same dataset path exists in both files but has different
        shape or dtype.
      - Same attribute key exists in both objects but has different value.

    Parameters
    ----------
    file1, file2 :
        Open h5py.File or h5py.Group objects that share the same logical layout.
    path : str, optional
        Current absolute HDF5 path to compare (default is root "/").
    conflicts : list, optional
        List that will be extended with conflict dicts. If None, a new
        list is created and returned.

    Returns
    -------
    list
        The list of collected conflict dicts. Each conflict has keys:
        - "path" : str, the HDF5 path where the conflict occurs
        - "kind" : str, one of {"node_type", "dataset_mismatch", "attr_mismatch"}
        - "detail" : str, human-readable description
    """
    if conflicts is None:
        conflicts = []

    obj1 = file1[path]
    obj2 = file2[path]

    # Helper: compare attributes of two objects at same path
    def _compare_attrs(o1, o2, obj_path: str):
        ignore_set = IGNORE_ATTRIBUTES.get(obj_path, set())

        keys1 = set(o1.attrs.keys()) - ignore_set
        keys2 = set(o2.attrs.keys()) - ignore_set
        common = keys1 & keys2

        for key in common:
            v1 = o1.attrs[key]
            v2 = o2.attrs[key]

            # Use np.array_equal to handle scalars, strings, arrays, etc.
            if not np.array_equal(v1, v2):
                conflicts.append(
                    {
                        "path": obj_path,
                        "kind": "attr_mismatch",
                        "detail": f"Attribute '{key}' differs: {v1!r} vs {v2!r}",
                    }
                )

    is_group1 = isinstance(obj1, h5py.Group)
    is_group2 = isinstance(obj2, h5py.Group)
    is_dset1 = isinstance(obj1, h5py.Dataset)
    is_dset2 = isinstance(obj2, h5py.Dataset)

    # 1) Different node types at the same path: group vs dataset
    if (is_group1 and is_dset2) or (is_dset1 and is_group2):
        conflicts.append(
            {
                "path": path,
                "kind": "node_type",
                "detail": f"Different node types at {path}: "
                f"{type(obj1).__name__} vs {type(obj2).__name__}",
            }
        )
        return conflicts

    # 2) Both datasets: check shape/dtype + attributes
    if is_dset1 and is_dset2:
        if obj1.shape != obj2.shape or obj1.dtype != obj2.dtype:
            conflicts.append(
                {
                    "path": path,
                    "kind": "dataset_mismatch",
                    "detail": (
                        f"Dataset mismatch at {path}: "
                        f"shape/dtype {obj1.shape}, {obj1.dtype} vs "
                        f"{obj2.shape}, {obj2.dtype}"
                    ),
                }
            )

        _compare_attrs(obj1, obj2, path)
        return conflicts

    # 3) Both groups: compare attributes + recurse on common children
    if is_group1 and is_group2:
        _compare_attrs(obj1, obj2, path)

        keys1 = set(obj1.keys())
        keys2 = set(obj2.keys())
        common_keys = keys1 & keys2

        # Only common children can conflict. Extra children are fine.
        for name in common_keys:
            if path == "/":
                child_path = f"/{name}"
            else:
                child_path = f"{path.rstrip('/')}/{name}"

            collect_conflicts(file1, file2, path=child_path, conflicts=conflicts)

        return conflicts

    # Should not really reach here, but in case of exotic types:
    conflicts.append(
        {
            "path": path,
            "kind": "node_type",
            "detail": f"Unsupported node type combination at {path}: "
            f"{type(obj1).__name__} vs {type(obj2).__name__}",
        }
    )
    return conflicts


def merge_trees(
    file1: h5py.File,
    file2: h5py.File,
    merged_file: h5py.File,
    conflict_solver: dict | None = None,
) -> None:
    """
    Recursively fill `merged_file` with content from `file1` and `file2`.

    Order:
    ------
    1. Copy the full tree from file1 into merged_file.
    2. Merge the full tree from file2 into merged_file:
       - If a path does not exist in merged_file, copy it.
       - If a dataset already exists:
           * If a conflict solver is provided for this path, use it to
             combine existing and incoming data.
           * Otherwise, keep the existing data (we assume they are compatible
             because conflicts were checked earlier).
       - Group attributes:
           * Add attributes that don't exist yet in merged_file.
           * Attributes listed in IGNORE_ATTRIBUTES are skipped.
    """

    # 1) copy everything from file1 (no conflicts, merged_file is new/empty)
    _merge_from_source(
        src=file1,
        dst=merged_file,
        path="/",
        conflict_solver={},  # nothing to resolve, just copy
        overwrite_existing=False,
    )

    # 2) merge from file2, now conflict_solver may apply
    _merge_from_source(
        src=file2,
        dst=merged_file,
        path="/",
        conflict_solver={},
        overwrite_existing=True,
    )


def _merge_from_source(
    src: h5py.Group,
    dst: h5py.Group,
    path: str,
    conflict_solver: dict,
    overwrite_existing: bool,
) -> None:
    """
    Recursive helper.

    Parameters
    ----------
    src : h5py.Group or h5py.File
        Source root/node.
    dst : h5py.Group or h5py.File
        Destination root/node.
    path : str
        Absolute HDF5 path in src (and corresponding path in dst).
    conflict_solver : dict
        Mapping path -> solver(existing_data, incoming_data) -> resolved_data.
    overwrite_existing : bool
        If False, never touch existing objects (used for file1).
        If True, apply conflict_solver or keep existing by default (used for file2).
    """
    src_obj = src[path]
    dst_obj = dst[path]  # must exist; for root "/" this is the file itself

    # Copy/merge attributes for this object (group or dataset)
    _copy_attributes(src_obj, dst_obj, path)

    if isinstance(src_obj, h5py.Dataset):
        # Nothing more to recurse into
        return

    if not isinstance(src_obj, h5py.Group):
        # ignore exotic node types for now (SoftLink, ExternalLink, etc.)
        return

    # src_obj is a Group: iterate over its children
    for name, child in src_obj.items():
        if path == "/":
            child_path = f"/{name}"
        else:
            child_path = f"{path.rstrip('/')}/{name}"

        if name not in dst_obj:
            # Child does not exist yet in dst: copy entire subtree
            _copy_entire_object(src_obj, dst_obj, name)
        else:
            # TODO: allow for conflict solver
            raise ValueError("Conflict detected. Merge stopped")


def _copy_entire_object(src_parent: h5py.Group, dst_parent: h5py.Group, name: str) -> None:
    """
    Copy a group or dataset `name` from src_parent to dst_parent, including
    all attributes and children (for groups).
    """
    obj = src_parent[name]

    if isinstance(obj, h5py.Dataset):
        # Create dataset with same data and attrs
        dset = dst_parent.create_dataset(name, data=obj[...], dtype=obj.dtype)
        _copy_attributes(obj, dset, _build_child_path(dst_parent.name, name))

    elif isinstance(obj, h5py.Group):
        # Create group and copy attributes
        grp = dst_parent.create_group(name)
        _copy_attributes(obj, grp, _build_child_path(dst_parent.name, name))

        # Recurse to copy all children
        for child_name in obj.keys():
            _copy_entire_object(obj, grp, child_name)

    else:
        # Exotic object types (SoftLink, ExternalLink, etc.): skip or handle if needed
        # For now, we skip them to keep the implementation simple.
        pass


def _copy_attributes(
    src_obj: h5py.Dataset | h5py.Group, dst_obj: h5py.Dataset | h5py.Group, path: str
) -> None:
    """
    Copy attributes from src_obj to dst_obj, skipping attributes that:
      - are in IGNORE_ATTRIBUTES for this path, or
      - already exist in dst_obj.
    """
    ignore_set = IGNORE_ATTRIBUTES.get(path, set())

    for key, value in src_obj.attrs.items():
        if key in ignore_set:
            continue
        if key in dst_obj.attrs:
            # Keep existing attr value
            continue
        dst_obj.attrs[key] = value


def _build_child_path(parent_path: str, name: str) -> str:
    """
    Utility to build a proper HDF5 path for a child object.
    """
    if parent_path == "/":
        return f"/{name}"
    return f"{parent_path.rstrip('/')}/{name}"
