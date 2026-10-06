import json
from pathlib import Path
import h5py
import hdf5plugin
import numpy as np
import rasterio
from pyproj import CRS
from .tools import check_std_version, import_tif_with_rect_box
from ..tools.logging_config import logger
from ..tools import StandardVariableNames as svn
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
    compression_lvl: int = 3,
    exclude_boxes: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
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
    exclude_boxes: list[tuple[tuple[float, float], tuple[float, float]]] | None
        Boxes to blank out, each as ((lat_min, lon_min), (lat_max, lon_max)). A bound may be infinite.
        A cell whose position (`position_lat`, `position_lon`) is strictly inside a box is set to the
        fill value, 0. The output coordinates must be geographic. The boxes are stored as JSON in the
        group attribute `excluded_boxes`, with null for an infinite bound.

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """  # pylint: disable=line-too-long
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
        compression_lvl,
        fill_value=0,
        exclude_boxes=exclude_boxes,
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
    compression_lvl: int = 3,
    exclude_boxes: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
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
    exclude_boxes: list[tuple[tuple[float, float], tuple[float, float]]] | None
        Boxes to blank out, each as ((lat_min, lon_min), (lat_max, lon_max)). A bound may be infinite.
        A cell whose position (`position_lat`, `position_lon`) is strictly inside a box is set to the
        fill value, 0. The output coordinates must be geographic. The boxes are stored as JSON in the
        group attribute `excluded_boxes`, with null for an infinite bound.

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """  # pylint: disable=line-too-long
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
        compression_lvl,
        fill_value=0,
        exclude_boxes=exclude_boxes,
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
    compression_lvl: int = 3,
    exclude_boxes: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
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
    exclude_boxes: list[tuple[tuple[float, float], tuple[float, float]]] | None
        Boxes to blank out, each as ((lat_min, lon_min), (lat_max, lon_max)). A bound may be infinite.
        A cell whose position (`position_lat`, `position_lon`) is strictly inside a box is set to the
        fill value, 0. The output coordinates must be geographic. The boxes are stored as JSON in the
        group attribute `excluded_boxes`, with null for an infinite bound.

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """  # pylint: disable=line-too-long
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
        compression_lvl,
        fill_value=0,
        exclude_boxes=exclude_boxes,
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
    compression_lvl: int = 3,
    fill_value=None,
    exclude_boxes: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
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
    exclude_boxes: list[tuple[tuple[float, float], tuple[float, float]]] | None
        Boxes to blank out, each as ((lat_min, lon_min), (lat_max, lon_max)). A bound may be infinite.
        A cell whose position (`position_lat`, `position_lon`) is strictly inside a box is set to the
        fill value, 0. The output coordinates must be geographic. The boxes are stored as JSON in the
        group attribute `excluded_boxes`, with null for an infinite bound.

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """  # pylint: disable=line-too-long
    logger.debug("Standardize RAVG %s dataset from file %s ", ravg_variable, geotiff_path)
    check_std_version(h5file)
    boxes = _checked_boxes(geotiff_path, projection, exclude_boxes) if exclude_boxes else []

    lat, lon, ravg_data, crs, nodata = import_tif_with_rect_box(
        geotiff_path, lower_left_corner, upper_right_corner, projection, invert_y
    )
    for (lat_min, lon_min), (lat_max, lon_max) in boxes:
        inside = (lat > lat_min) & (lat < lat_max) & (lon > lon_min) & (lon < lon_max)
        ravg_data[inside] = 0 if fill_value is None else fill_value

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
    if boxes:
        g.attrs["excluded_boxes"] = json.dumps(
            [[[None if np.isinf(bound) else bound for bound in corner] for corner in box] for box in boxes],
            allow_nan=False,
        )

    dlat = g.create_dataset(
        "position_lat", data=lat, dtype=np.float64, **hdf5plugin.Zstd(clevel=compression_lvl)
    )
    dlat.attrs["units"] = "degrees"

    dlat = g.create_dataset(
        "position_lon", data=lon, dtype=np.float64, **hdf5plugin.Zstd(clevel=compression_lvl)
    )
    dlat.attrs["units"] = "degrees"

    ddata = g.create_dataset(
        ravg_variable, data=ravg_data, dtype=np.uint8, **hdf5plugin.Zstd(clevel=compression_lvl)
    )
    ddata.attrs["units"] = "dimensionless"
    if nodata is not None:
        ddata.attrs["_FillValue"] = nodata
    if fill_value is not None:
        ddata.attrs["_FillValue"] = fill_value


def _checked_boxes(geotiff_path: Path, projection: str | None, exclude_boxes: list) -> list:
    """Check that the boxes are well formed and that the output coordinates are geographic."""
    if projection is None:
        with rasterio.open(geotiff_path) as src:
            projection = src.crs
    if not CRS(projection).is_geographic:
        raise ValueError(
            f"exclude_boxes are geographic, but the output coordinates are in {CRS(projection).name}. "
            "Set `projection` to a geographic CRS, for example EPSG:4326."
        )

    boxes = []
    for item in exclude_boxes:
        try:
            (lat_min, lon_min), (lat_max, lon_max) = item
            boxes.append(((float(lat_min), float(lon_min)), (float(lat_max), float(lon_max))))
            valid = lat_min < lat_max and lon_min < lon_max
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ValueError(
                f"exclude box {item!r} must be ((lat_min, lon_min), (lat_max, lon_max)), with min < max"
            )
    return boxes
