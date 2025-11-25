from pathlib import Path

import h5py
import numpy as np
import rasterio
from pyproj import CRS, Transformer

from ..tools import StandardVariableNames as svn
from .tools import check_std_version
from ..tools.logging_config import logger


def standardize_mtbs_from_geotiff(
    geotiff_path: str,
    h5file: h5py.File,
    group_name: str | None = None,
    projection: str = None,
    overwrite: bool = False,
    invert_y: bool = False,
):
    """
    Convert a MTBS GeoTIFF to Firebench HDF5 standard file.

    Use source data projection as default. Can be reprojected by specifying the CRS in projection.

    Parameters
    ----------
    geotiff_path : str
        Path to the MTBS GeoTIFF (ending with *_dnbr6.tif).
    h5file :  h5py.File
        target HDF5 file
    group_name : str | None
        HDF5 group path. If None, auto-derive from filename, e.g. '2D_raster/<group_name>'.
    overwrite: bool
        Overwrite the group in the HDF5 file. Default: False
    invert_y: bool
        Invert y axis in data

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """  # pylint: disable=line-too-long
    logger.debug("Standardize MTBS dataset from file %s ", geotiff_path)
    check_std_version(h5file)
    with rasterio.open(geotiff_path) as src:
        data = src.read(1)
        severity_raw = {"data": data, "transform": src.transform, "crs": src.crs, "nodata": src.nodata}
        logger.info(f"Loaded {geotiff_path}: shape={data.shape}, CRS={src.crs}")

    rows, cols = data.shape

    # Build pixel center coordinates (projected)
    # col indices (x-direction), row indices (y-direction)
    jj = np.arange(cols)
    ii = np.arange(rows)
    # vectorized center coordinates from affine:
    # x = a*col + b*row + c ; y = d*col + e*row + f
    x = (
        severity_raw["transform"].a * jj[None, :]
        + severity_raw["transform"].b * ii[:, None]
        + severity_raw["transform"].c
    )
    y = (
        severity_raw["transform"].d * jj[None, :]
        + severity_raw["transform"].e * ii[:, None]
        + severity_raw["transform"].f
    )

    # Reproject to geographic lat/lon
    if projection is None:
        projection = severity_raw["crs"]
    tgt_crs = CRS(projection)

    # always_xy=True -> transformer expects/returns (x, y) = (lon, lat) ordering for geographic CRS
    transformer = Transformer.from_crs(severity_raw["crs"], tgt_crs, always_xy=True)
    lon, lat = transformer.transform(x, y)  # lon, lat are 2-D arrays aligned with `data`

    if invert_y:
        lat = lat[::-1, :]
        lon = lon[::-1, :]
        severity_raw["data"] = severity_raw["data"][::-1, :]

    if group_name is None:
        group_name = Path(geotiff_path).stem

    group_name = f"/2D_raster/{group_name}"
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
    g.attrs["data_source"] = f"MTBS {geotiff_path}"
    g.attrs["crs"] = str(tgt_crs)

    # Lat/Lon as 2-D arrays
    dlat = g.create_dataset("position_lat", data=lat, dtype=np.float64)
    dlat.attrs["units"] = "degrees"

    dlat = g.create_dataset("position_lon", data=lon, dtype=np.float64)
    dlat.attrs["units"] = "degrees"

    ddata = g.create_dataset(svn.FIRE_BURN_SEVERITY.value, data=severity_raw["data"], dtype=np.uint8)
    ddata.attrs["units"] = "dimensionless"
    ddata.attrs["_FillValue"] = 0
