from pathlib import Path

import h5py
import hdf5plugin
import numpy as np
import rasterio
from pyproj import CRS, Transformer

from ..tools import StandardVariableNames as svn
from .tools import check_std_version, import_tif
from ..tools.logging_config import logger
from .std_file_info import SPATIAL_2D


def standardize_landfire_from_geotiff(
    geotiff_path: str,
    h5file: h5py.File,
    variable_name: str,
    variable_units: str,
    group_name: str | None = None,
    projection: str = None,
    overwrite: bool = False,
    invert_y: bool = False,
    fill_value: float = None,
    compression_lvl: int = 3,
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
    logger.debug("Standardize LANDFIRE dataset from file %s ", geotiff_path)
    check_std_version(h5file)
    lat, lon, landfire_data, crs, nodata = import_tif(geotiff_path, projection, invert_y)

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
    g.attrs["data_source"] = f"LANDFIRE {geotiff_path}"
    g.attrs["crs"] = str(crs)

    # Lat/Lon as 2-D arrays
    dlat = g.create_dataset(
        "position_lat", data=lat, dtype=np.float64, **hdf5plugin.Zstd(clevel=compression_lvl)
    )
    dlat.attrs["units"] = "degrees"

    dlat = g.create_dataset(
        "position_lon", data=lon, dtype=np.float64, **hdf5plugin.Zstd(clevel=compression_lvl)
    )
    dlat.attrs["units"] = "degrees"

    ddata = g.create_dataset(
        variable_name, data=landfire_data, dtype=np.uint16, **hdf5plugin.Zstd(clevel=compression_lvl)
    )
    ddata.attrs["units"] = variable_units
    if fill_value is None:
        ddata.attrs["_FillValue"] = nodata
    else:
        ddata.attrs["_FillValue"] = fill_value
