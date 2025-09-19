from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import rasterio
from pyproj import CRS, Transformer

from ..tools import StandardVariableNames as svn
from ..tools import current_datetime_iso8601, datetime_to_iso8601
from .tools import VERSION_STD, check_std_version
from ..tools.logging_config import logger


def convert_mtbs_geotiff(
    path: str,
    dst: str,
    group_name: str | None = None,
    authors: str = "",
    std_file_description: str = "auto",
    overwrite: bool = False,
):
    """
    Convert a MTBS GeoTIFF to Firebench HDF5 standard file.

    Parameters
    ----------
    path : str
        Path to the MTBS GeoTIFF (ending with *_dnbr6.tif).
    dst : str
        Path to target HDF5 file (created or appended).
    group_name : str | None
        HDF5 group path. If None, auto-derive from filename, e.g. '2D_raster/<basename>'.
    authors: str
        Add the names of the authors in the standard file in the file attribute `created_by`.
    std_file_description: str
        Add custom description of the mtbs group. If description is "auto" the description will be "\n- Burn severity from MTBS".
    overwrite: bool
        Overwrite the group in the HDF5 file. Default: False

    Returns
    -------
    str
        The actual HDF5 group written (with suffix if collision).
    """  # pylint: disable=line-too-long
    with rasterio.open(path) as src:
        data = src.read(1)
        severity_raw = {"data": data, "transform": src.transform, "crs": src.crs, "nodata": src.nodata}
        logger.info(f"Loaded {path}: shape={data.shape}, CRS={src.crs}")

    rows, cols = data.shape

    # Build pixel center coordinates (projected)
    # col indices (x-direction), row indices (y-direction)
    jj = np.arange(cols)
    ii = np.arange(rows)
    # vectorized center coordinates from affine:
    # x = a*col + b*row + c ; y = d*col + e*row + f
    # Use broadcasting to form 2-D arrays without Python loops.
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
    # Choose your target CRS:
    #   - WGS84 geographic:
    epsg_code = 4269
    tgt_crs = CRS.from_epsg(epsg_code)  # lon/lat
    #   - OR NAD83 geographic:
    # tgt_crs = CRS.from_epsg(4269) # lon/lat

    # always_xy=True -> transformer expects/returns (x, y) = (lon, lat) ordering for geographic CRS
    transformer = Transformer.from_crs(severity_raw["crs"], tgt_crs, always_xy=True)
    lon, lat = transformer.transform(x, y)  # lon, lat are 2-D arrays aligned with `data`

    with h5py.File(dst, "a") as h5:

        if check_std_version(h5):
            h5.attrs["FireBench_io_version"] = VERSION_STD

        h5.attrs["created_on"] = current_datetime_iso8601(include_seconds=False)

        if "created_by" in h5.attrs.keys():
            if authors is not None:
                h5.attrs["created_by"] = h5.attrs["created_by"] + f", {authors}"
        else:
            h5.attrs["created_by"] = authors

        if std_file_description == "auto":
            std_file_description = "\n- Burn severity from MTBS"
        if "description" in h5.attrs.keys():
            h5.attrs["description"] = h5.attrs["description"] + "\n- Burn severity from MTBS"
        else:
            h5.attrs["description"] = "This file contains:\n- Burn severity from MTBS"

        group_name = f"/2D_raster/{group_name}"
        if group_name in h5.keys():
            if overwrite:
                del h5[group_name]
            else:
                logger.warning(
                    "group name %s already exists in file %s. Group not updated. Set `overwrite` to True to update the dataset.",
                    group_name,
                    path,
                )
                return

        g = h5.create_group(group_name)
        g.attrs["data_source"] = f"MTBS {path}"
        g.attrs["crs"] = f"EPSG:{epsg_code}"
        # TODO: add some useful metadata from _metadata.xml (fire_ignition_time, pre_fire_image_date, post_fire_image_date)

        # Lat/Lon as 2-D arrays
        dlat = g.create_dataset("latitude", data=lat, dtype=np.float64)
        dlat.attrs["units"] = "degrees"

        dlat = g.create_dataset("longitude", data=lon, dtype=np.float64)
        dlat.attrs["units"] = "degrees"

        ddata = g.create_dataset(svn.FIRE_BURN_SEVERITY.value, data=severity_raw["data"], dtype=np.uint8)
        ddata.attrs["units"] = "dimensionless"
        ddata.attrs["_FillValue"] = 0
