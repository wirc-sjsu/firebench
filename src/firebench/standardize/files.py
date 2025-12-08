import h5py
from ..tools.logging_config import logger
from .time import current_datetime_iso8601
from pathlib import Path
from .tools import VERSION_STD, validate_h5_std, merge_authors, collect_conflicts, merge_trees
from pathlib import Path
import shutil


def new_std_file(filepath: str, authors: str, overwrite: bool = False) -> h5py.File:
    """
    Create a new file using FireBench standard.
    Return the file object.
    Notes
    -----
    Do not forget to close the file once edited. This function opens the h5 file but do not close it.
    """
    new_file_path = Path(filepath)
    new_file_path.parent.mkdir(parents=True, exist_ok=True)
    if new_file_path.exists():
        if overwrite:
            logger.info("file %s  already exists and is being replaced.", filepath)
        else:
            logger.error(
                "file %s already exists. Use `overwrite=True` to overwrite the existing file.", filepath
            )
            raise FileExistsError()

    h5 = h5py.File(filepath, mode="w")
    h5.attrs["FireBench_io_version"] = VERSION_STD
    h5.attrs["created_on"] = current_datetime_iso8601(include_seconds=False)
    h5.attrs["created_by"] = authors

    return h5


def merge_two_std_files(
    filepath_1: str,
    filepath_2: str,
    filepath_target: str,
    merged_description: str = "",
    overwrite: bool = False,
):
    """
    Try to merge two std FireBench files

    Check if both files are std, then check for any group/dataset/attribut conflict

    Then merge the list of authors without duplicates. Keep order as much as possible (first authors from file1 then first author from file2 then second from file 1...)
    """
    logger.debug("Merge two std files")
    file1 = h5py.File(filepath_1, "r")
    validate_h5_std(file1)
    file2 = h5py.File(filepath_2, "r")
    validate_h5_std(file2)

    # Check for any conflicts
    conflicts = collect_conflicts(file1, file2)
    if conflicts:
        logger.critical("Try to merge files but conflicts have been found.")
        print(conflicts)
        raise ValueError("Try to merge files but conflicts have been found.")

    # Find both list of authors
    merged_authors = merge_authors(file1.attrs["created_by"], file2.attrs["created_by"])

    # Create the new file
    merged_file = new_std_file(filepath_target, authors=merged_authors, overwrite=overwrite)

    merge_trees(file1, file2, merged_file)

    merged_file.attrs["description"] = merged_description

    # fill the content of merged_file witht the content of both files

    file1.close()
    file2.close()
    merged_file.close()
    logger.info("Standard files merge successfull")


def merge_std_files(
    filespath: list[str], filepath_target: str, merged_description: str = "", overwrite: bool = False
):
    if not filespath:
        raise ValueError("filespath must contain at least one file")

    input_paths = [Path(p) for p in filespath]
    target_path = Path(filepath_target)

    for p in input_paths:
        if not p.is_file():
            raise FileNotFoundError(f"Input file not found: {p}")

    # Single file: just copy it to target (no merge needed)
    if len(input_paths) == 1:
        if target_path.exists() and not overwrite:
            raise FileExistsError(f"Target file already exists: {target_path}")
        # Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_paths[0], target_path)
        return

    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    current_path = input_paths[0]

    try:
        for i, next_path in enumerate(input_paths[1:], start=1):
            is_last = i == len(input_paths) - 1

            out_path = target_path if is_last else tmp_path

            # Always allow overwrite on intermediate/target files inside this routine
            merge_two_std_files(
                filepath_1=str(current_path),
                filepath_2=str(next_path),
                filepath_target=str(out_path),
                merged_description=merged_description,
                overwrite=True,
            )

            current_path = out_path

    finally:
        # Clean up temporary file if it exists
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                # If removal fails, we silently ignore; nothing critical.
                pass
