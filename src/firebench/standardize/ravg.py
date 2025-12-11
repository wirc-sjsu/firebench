import h5py
import numpy as np
from .tools import check_std_version, import_tif_with_rect_box
from ..tools.logging_config import logger
from ..tools import StandardVariableNames as svn
from pathlib import Path
from .std_file_info import SPATIAL_2D


def standardize_ravg_cc_from_geotiff(
    geotiff_path: Path,
    h5file: h5py.File,
    lower_left_corner: tuple[float, float],
    upper_right_corner: tuple[float, float],
    group_name: str | None = None,
    projection: str = None,
    overwrite: bool = False,
    invert_y: bool = False,
):
    """
    Convert a RAVG GeoTIFF to FireBench HDF5 Standard for Canopy Cover Loss
    Use CONUS tif file and define bounding box for data import.

    Use source data projection as default. Can be reprojected by specifying the CRS in projection.

    Parameters
    ----------
    geotiff_path : Path
        Path to the RAVG Canopy Cover Loss GeoTIFF (ending with *_cc5.tif).
    h5file : h5py.File
        target HDF5 file
    group_name : str | None
        HDF5 group path. If None, auto-derive from filename, e.g. 'spatial_2d/<group_name>'.
    overwrite: bool
        Overwrite the group in the HDF5 file. Default: False
    invert_y: bool
        Invert y axis in data

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """
    _standardize_ravg_from_geotiff(
        geotiff_path,
        h5file,
        lower_left_corner,
        upper_right_corner,
        svn.RAVG_CANOPY_COVER_LOSS.value,
        group_name,
        projection,
        overwrite,
        invert_y,
    )


def standardize_ravg_cbi_from_geotiff(
    geotiff_path: Path,
    h5file: h5py.File,
    lower_left_corner: tuple[float, float],
    upper_right_corner: tuple[float, float],
    group_name: str | None = None,
    projection: str = None,
    overwrite: bool = False,
    invert_y: bool = False,
):
    """
    Convert a RAVG GeoTIFF to FireBench HDF5 Standard for Composite Burn Index Severity
    Use CONUS tif file and define bounding box for data import.

    Use source data projection as default. Can be reprojected by specifying the CRS in projection.

    Parameters
    ----------
    geotiff_path : Path
        Path to the RAVG Composite Burn Index Severity GeoTIFF (ending with *_cbi4.tif).
    h5file : h5py.File
        target HDF5 file
    group_name : str | None
        HDF5 group path. If None, auto-derive from filename, e.g. 'spatial_2d/<group_name>'.
    overwrite: bool
        Overwrite the group in the HDF5 file. Default: False
    invert_y: bool
        Invert y axis in data

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """
    _standardize_ravg_from_geotiff(
        geotiff_path,
        h5file,
        lower_left_corner,
        upper_right_corner,
        svn.RAVG_COMPOSITE_BURN_INDEX_SEVERITY.value,
        group_name,
        projection,
        overwrite,
        invert_y,
    )


def standardize_ravg_ba_from_geotiff(
    geotiff_path: Path,
    h5file: h5py.File,
    lower_left_corner: tuple[float, float],
    upper_right_corner: tuple[float, float],
    group_name: str | None = None,
    projection: str = None,
    overwrite: bool = False,
    invert_y: bool = False,
):
    """
    Convert a RAVG GeoTIFF to FireBench HDF5 Standard for Live Basal Area loss
    Use CONUS tif file and define bounding box for data import.

    Use source data projection as default. Can be reprojected by specifying the CRS in projection.

    Parameters
    ----------
    geotiff_path : Path
        Path to the RAVG Live Basal Area loss GeoTIFF (ending with *_ba7.tif).
    h5file : h5py.File
        target HDF5 file
    group_name : str | None
        HDF5 group path. If None, auto-derive from filename, e.g. 'spatial_2d/<group_name>'.
    overwrite: bool
        Overwrite the group in the HDF5 file. Default: False
    invert_y: bool
        Invert y axis in data

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """
    _standardize_ravg_from_geotiff(
        geotiff_path,
        h5file,
        lower_left_corner,
        upper_right_corner,
        svn.RAVG_LIVE_BASAL_AREA_LOSS.value,
        group_name,
        projection,
        overwrite,
        invert_y,
    )


def _standardize_ravg_from_geotiff(
    geotiff_path: Path,
    h5file: h5py.File,
    lower_left_corner: tuple[float, float],
    upper_right_corner: tuple[float, float],
    ravg_variable: str,
    group_name: str | None = None,
    projection: str = None,
    overwrite: bool = False,
    invert_y: bool = False,
):
    """
    Convert a RAVG GeoTIFF to FireBench HDF5 Standard.
    Use CONUS tif file and define bounding box for data import.

    Use source data projection as default. Can be reprojected by specifying the CRS in projection.

    Parameters
    ----------
    geotiff_path : Path
        Path to the RAVG Composite Burn Index Severity GeoTIFF (ending with *_cc5.tif).
    h5file : h5py.File
        target HDF5 file
    group_name : str | None
        HDF5 group path. If None, auto-derive from filename, e.g. 'spatial_2d/<group_name>'.
    overwrite: bool
        Overwrite the group in the HDF5 file. Default: False
    invert_y: bool
        Invert y axis in data

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """
    logger.debug("Standardize RAVG %s dataset from file %s ", ravg_variable, geotiff_path)
    check_std_version(h5file)

    lat, lon, ravg_data, crs = import_tif_with_rect_box(
        geotiff_path, lower_left_corner, upper_right_corner, projection, invert_y
    )

    if group_name is None:
        group_name = Path(geotiff_path).stem

    group_name = f"/{SPATIAL_2D}/{group_name}"
    if group_name in h5file.keys():
        if overwrite:
            del h5file[group_name]
        else:
            logger.warning(
                "group name %s already exists in file %s. Group not updated. Set `overwrite` to True to update the dataset.",
                group_name,
                geotiff_path,
            )
            return

    g = h5file.create_group(group_name)
    g.attrs["data_source"] = f"RAVG {geotiff_path}"
    g.attrs["crs"] = str(crs)

    dlat = g.create_dataset("position_lat", data=lat, dtype=np.float64)
    dlat.attrs["units"] = "degrees"

    dlat = g.create_dataset("position_lon", data=lon, dtype=np.float64)
    dlat.attrs["units"] = "degrees"

    ddata = g.create_dataset(ravg_variable, data=ravg_data, dtype=np.uint8)
    ddata.attrs["units"] = "dimensionless"
    ddata.attrs["_FillValue"] = 0
