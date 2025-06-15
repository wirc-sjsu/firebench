from typing import Union
import geopandas as gpd
from geopandas import GeoDataFrame

# Equal-area projection list
LIST_VALID_PROJ = [
    "EPSG:5070",   # USA Contiguous Albers Equal Area
    "EPSG:3035",   # Europe LAEA (ETRS89)
    "EPSG:102001", # Canada Albers Equal Area
    "EPSG:6933",   # World Cylindrical Equal Area
]

def jaccard_polygon(
    polygon1: GeoDataFrame,
    polygon2: GeoDataFrame,
    projection: str = "EPSG:5070"
) -> float:
    """
    Compute the Intersection over Union (IoU), also known as the Jaccard Index, between two fire perimeters.

    The perimeters are assumed to be geospatial polygons (e.g., shapefiles or KMZ imports via GeoPandas).
    Internally, both input geometries are reprojected to an equal-area projection before computing the metric.

    Geometries of different types may be dropped during overlay; to ensure all area-bearing geometries are retained, keep_geom_type=False is used in both intersection and union operations.
    
    Parameters
    ----------
    polygon1 : geopandas.GeoDataFrame
        First perimeter geometry, must be a valid polygon or multipolygon layer.
    polygon2 : geopandas.GeoDataFrame
        Second perimeter geometry to compare against `polygon1`.
    projection : str, optional
        EPSG code string of an equal-area CRS used for area calculation. Default is "EPSG:5070".

        Recommended projections:
            - USA (CONUS): "EPSG:5070"
            - Europe: "EPSG:3035"
            - Canada: "EPSG:102001"
            - Global: "EPSG:6933"

    Returns
    -------
    float
        Jaccard index (IoU) between the two geometries. A value in [0, 1], where:
            - 1.0 indicates perfect overlap,
            - 0.0 indicates no overlap.

    Raises
    ------
    ValueError
        If the projection string is not in the allowed list of equal-area projections.

    Notes
    -----
    It is strongly recommended to use only valid, topologically correct polygons.
    """

    if projection not in LIST_VALID_PROJ:
        raise ValueError(
            f"Invalid projection '{projection}'. Use one of the following area-preserving projections: {LIST_VALID_PROJ}"
        )

    # Reproject to equal-area projection
    polygon1 = polygon1.to_crs(projection)
    polygon2 = polygon2.to_crs(projection)

    # Calculate the intersection and union
    intersection = gpd.overlay(polygon1, polygon2, how='intersection', keep_geom_type=False)
    union = gpd.overlay(polygon1, polygon2, how='union', keep_geom_type=False)

    # Compute and return IoU
    return intersection.area.sum() / union.area.sum()
