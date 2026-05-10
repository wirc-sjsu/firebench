from typing import Union

import contourpy
import geopandas as gpd
import numpy as np
from scipy.ndimage import gaussian_filter
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.validation import make_valid


def array_to_geopolygons(
    field: np.ndarray,
    lon: np.ndarray,
    lat: np.ndarray,
    iso_value: float,
    original_crs: Union[str, dict] = "EPSG:4326",
    smooth_sigma: float = 0,
) -> gpd.GeoDataFrame:
    """
    Convert an array field into geospatial polygons at a given iso-value, preserving holes.

    Parameters
    ----------
    field : np.ndarray
        2D array of physical values (e.g., level-set or arrival time).
    lon : np.ndarray
        2D array of longitudes matching `field`.
    lat : np.ndarray
        2D array of latitudes matching `field`.
    iso_value : float
        Value at which to extract the contour.
    original_crs : str or dict, optional
        CRS of the input coordinate grid.
        If not specified, defaults to "EPSG:4326" (WGS84),
        which is suitable for most WRF output over the continental United States and supports area-preserving polygon construction.
    smooth_sigma : float, optional
        Standard deviation for optional Gaussian smoothing.

    Returns
    -------
    geopandas.GeoDataFrame
        GeoDataFrame with valid polygons (including holes) representing the iso-contour.
    """  # pylint: disable=line-too-long
    if not lon.shape == lat.shape == field.shape:
        raise ValueError("Input arrays (lon, lat, field) must have the same shape.")

    if smooth_sigma > 0:
        field = gaussian_filter(field, sigma=smooth_sigma)

    final_polygons = []
    masked_field = np.ma.masked_invalid(field)
    valid_field = masked_field.compressed()
    if valid_field.size == 0:
        return gpd.GeoDataFrame(geometry=final_polygons, crs=original_crs).assign(iso_value=iso_value)

    # Filled contours preserve polygon topology: each returned block is one
    # exterior ring followed by any holes inside that exterior.
    epsilon = max(1.0, abs(iso_value)) * 1e-12
    lower_level = min(float(valid_field.min()), float(iso_value)) - epsilon
    contour_generator = contourpy.contour_generator(
        x=lon,
        y=lat,
        z=masked_field,
        fill_type=contourpy.FillType.OuterOffset,
        corner_mask=True,
    )
    points_by_polygon, offsets_by_polygon = contour_generator.filled(lower_level, iso_value)

    for points, offsets in zip(points_by_polygon, offsets_by_polygon):
        if points is None or offsets is None or len(offsets) < 2:
            continue

        rings = [points[offsets[i] : offsets[i + 1]] for i in range(len(offsets) - 1)]
        if not rings or len(rings[0]) < 4:
            continue

        exterior = rings[0]
        holes = [ring for ring in rings[1:] if len(ring) >= 4]
        polygon = Polygon(exterior, holes=holes)
        final_polygons.extend(_valid_polygon_parts(polygon))

    return gpd.GeoDataFrame(geometry=final_polygons, crs=original_crs).assign(iso_value=iso_value)


def _valid_polygon_parts(geometry):
    """Return valid non-empty Polygon parts from a Shapely geometry."""
    if not geometry.is_valid:
        geometry = make_valid(geometry)

    if geometry.is_empty:
        return []

    if isinstance(geometry, Polygon):
        return [geometry] if geometry.area > 0 else []

    if isinstance(geometry, MultiPolygon):
        return [polygon for polygon in geometry.geoms if polygon.area > 0]

    if isinstance(geometry, GeometryCollection):
        polygons = []
        for part in geometry.geoms:
            polygons.extend(_valid_polygon_parts(part))
        return polygons

    return []
