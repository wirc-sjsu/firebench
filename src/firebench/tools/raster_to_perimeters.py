from typing import Union

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter
from shapely.geometry import Polygon


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

    fig, ax = plt.subplots()
    cs = ax.contour(lon, lat, field, levels=[iso_value])
    plt.close(fig)

    rings = [seg.tolist() for seg in cs.allsegs[0]]
    polys = [Polygon(ring) for ring in rings if Polygon(ring).is_valid and Polygon(ring).area > 0]
    sorted_indices = sorted(range(len(polys)), key=lambda i: polys[i].area, reverse=True)

    used_as_hole = set()
    final_polygons = []

    for i in sorted_indices:
        if i in used_as_hole:
            continue
        outer = polys[i]
        hole_list = []
        for j in sorted_indices:
            if i == j or j in used_as_hole:
                continue
            inner = polys[j]
            if inner.within(outer):
                # make sure inner is not already inside another hole
                conflict = False
                for h in hole_list:
                    if inner.within(Polygon(h)):
                        conflict = True
                        break
                if not conflict:
                    hole_list.append(rings[j])
                    used_as_hole.add(j)
        final_poly = Polygon(rings[i], holes=hole_list)
        if final_poly.is_valid:
            final_polygons.append(final_poly)

    return gpd.GeoDataFrame(geometry=final_polygons, crs=original_crs).assign(iso_value=iso_value)
