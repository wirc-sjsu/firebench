from pathlib import Path

import h5py
import hdf5plugin
import numpy as np
import rasterio

from .tools import check_std_version, import_tif, import_tif_with_rect_box
from ..tools.logging_config import logger
from .std_file_info import SPATIAL_2D

# The canopy products of LANDFIRE a dataset may hold: variable, units of the stored integers, and the
# group they are written to. LANDFIRE stores heights in m x 10 and bulk density in kg m-3 x 100.
LANDFIRE_CANOPY_PRODUCTS = {
    "cc": ("canopy_cover", "percent", "landfire_cc"),
    "ch": ("canopy_height", "dm", "landfire_ch"),
    "cbh": ("canopy_height_bottom", "dm", "landfire_cbh"),
    "cbd": ("canopy_density_bulk", "dag / m^3", "landfire_cbd"),
}
LANDFIRE_FILL_VALUE = 32767


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
    lower_left_corner: tuple[float, float] | None = None,
    upper_right_corner: tuple[float, float] | None = None,
):
    """
    Convert a LANDFIRE GeoTIFF to Firebench HDF5 standard file.

    Use source data projection as default. Can be reprojected by specifying the CRS in projection.

    Parameters
    ----------
    geotiff_path : str
        Path to the LANDFIRE GeoTIFF.
    h5file :  h5py.File
        target HDF5 file
    group_name : str | None
        HDF5 group path. If None, auto-derive from filename, e.g. '2D_raster/<group_name>'.
    overwrite: bool
        Overwrite the group in the HDF5 file. Default: False
    invert_y: bool
        Invert y axis in data
    lower_left_corner, upper_right_corner : tuple[float, float] | None
        Corners (latitude, longitude) of the box to read in the CRS ``projection``, both or neither. Given, only the
        window of the GeoTIFF that covers the box is read, so a national mosaic can be cut to a fire.
        Left out, the whole GeoTIFF is read.

    A negative value of the GeoTIFF (LANDFIRE's -9999 fill) is stored as the fill value: the data are
    written as unsigned integers.

    Returns
    -------
     h5py.File
        The actual HDF5 group written (with suffix if collision).
    """  # pylint: disable=line-too-long
    logger.debug("Standardize LANDFIRE dataset from file %s ", geotiff_path)
    check_std_version(h5file)
    if (lower_left_corner is None) != (upper_right_corner is None):
        raise ValueError("Give both corners of the box to read, or neither.")
    if lower_left_corner is None:
        lat, lon, landfire_data, crs, nodata = import_tif(geotiff_path, projection, invert_y)
    else:
        lat, lon, landfire_data, crs, nodata = import_tif_with_rect_box(
            Path(geotiff_path), lower_left_corner, upper_right_corner, projection, invert_y
        )
    fill = nodata if fill_value is None else fill_value
    if fill is not None and np.issubdtype(landfire_data.dtype, np.signedinteger):
        landfire_data = np.where(landfire_data < 0, fill, landfire_data)

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
    g.attrs["license"] = "/DATA_LICENSES/LANDFIRE.txt"
    g.attrs["data_use_restrictions"] = "No restrictions on public use"
    g.attrs["public_access_level"] = "Public"
    g.attrs["redistribution_allowed"] = True

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


def standardize_landfire_canopy(
    geotiff_path: str,
    h5file: h5py.File,
    product: str,
    lower_left_corner: tuple[float, float],
    upper_right_corner: tuple[float, float],
    projection: str = "EPSG:4326",
    overwrite: bool = False,
    invert_y: bool = False,
    compression_lvl: int = 3,
):
    """
    Cut a LANDFIRE canopy product of a national mosaic to a box, into its standard group.

    Parameters
    ----------
    geotiff_path : str
        Path to the LANDFIRE GeoTIFF of the product, e.g. ``LF2025_CH_CONUS.tif``.
    h5file : h5py.File
        Target HDF5 file.
    product : str
        One of ``cc`` (canopy cover), ``ch`` (canopy height), ``cbh`` (canopy base height), and ``cbd``
        (canopy bulk density). It gives the variable, its units, and the group,
        ``/spatial_2d/landfire_<product>`` (``LANDFIRE_CANOPY_PRODUCTS``).
    lower_left_corner, upper_right_corner : tuple[float, float]
        Geographic corners (latitude, longitude) of the box.
    projection : str
        CRS of the stored positions and of the corners, geographic by default. FireBench reads the
        corners in this CRS.

    The values are LANDFIRE's integers, with the units of ``LANDFIRE_CANOPY_PRODUCTS``. The fill value
    is the GeoTIFF's no-data value, 32767 when it has none.

    Returns
    -------
    str | None
        The path of the group written, or None when the group exists and ``overwrite`` is False.
    """
    if product not in LANDFIRE_CANOPY_PRODUCTS:
        raise ValueError(
            f"Unknown LANDFIRE canopy product `{product}`; expected one of "
            f"{', '.join(LANDFIRE_CANOPY_PRODUCTS)}."
        )
    variable, units, group = LANDFIRE_CANOPY_PRODUCTS[product]
    path = f"/{SPATIAL_2D}/{group}"
    if path in h5file and not overwrite:
        logger.warning("group %s already exists. Set `overwrite` to True to update it.", path)
        return None
    with rasterio.open(geotiff_path) as src:
        nodata = src.nodata
    standardize_landfire_from_geotiff(
        geotiff_path,
        h5file,
        variable,
        units,
        group_name=group,
        projection=projection,
        overwrite=overwrite,
        invert_y=invert_y,
        fill_value=LANDFIRE_FILL_VALUE if nodata is None else nodata,
        compression_lvl=compression_lvl,
        lower_left_corner=lower_left_corner,
        upper_right_corner=upper_right_corner,
    )
    if path not in h5file:
        return None
    if h5file[path][variable].size == 0:
        del h5file[path]
        raise ValueError("The box does not cross the LANDFIRE grid.")
    h5file[path].attrs["landfire_product"] = product
    return path
