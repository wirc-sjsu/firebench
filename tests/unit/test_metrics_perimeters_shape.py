import warnings

import firebench.metrics.perimeter as fbp
import numpy as np
import pytest
from shapely.geometry import Polygon
import geopandas as gpd


# jaccard_polygon
# ---------------
@pytest.mark.parametrize(
    "offset_x, expect_index",
    [
        (0, 1),  # Complete overlap
        (3, 0),  # No overlap
        (0.5, 0.332939),  # Half overlap
    ],
)
def test_jaccard_polygon_basic(offset_x, expect_index):
    # Build two identical squares (perfect overlap)
    poly1 = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    gdf1 = gpd.GeoDataFrame(geometry=[poly1], crs="EPSG:4326")

    poly2 = Polygon([(offset_x, 0), (offset_x, 1), (1 + offset_x, 1), (1 + offset_x, 0)])
    gdf2 = gpd.GeoDataFrame(geometry=[poly2], crs="EPSG:4326")

    score = fbp.jaccard_polygon(gdf1, gdf2)
    assert score == pytest.approx(expect_index, abs=1e-6)


def test_jaccard_polygon_not_valid_proj():
    # Build two identical squares (perfect overlap)
    poly1 = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    gdf1 = gpd.GeoDataFrame(geometry=[poly1], crs="EPSG:4326")

    with pytest.raises(ValueError, match="Invalid projection"):
        fbp.jaccard_polygon(gdf1, gdf1, projection="EPSG:4326")


# sorensen_dice_polygon
# ---------------------
@pytest.mark.parametrize(
    "offset_x, expect_index",
    [
        (0, 1),  # Complete overlap
        (3, 0),  # No overlap
        (0.5, 0.499556),  # Half overlap
    ],
)
def test_sorensen_dice_polygon_basic(offset_x, expect_index):
    # Build two identical squares (perfect overlap)
    poly1 = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    gdf1 = gpd.GeoDataFrame(geometry=[poly1], crs="EPSG:4326")

    poly2 = Polygon([(offset_x, 0), (offset_x, 1), (1 + offset_x, 1), (1 + offset_x, 0)])
    gdf2 = gpd.GeoDataFrame(geometry=[poly2], crs="EPSG:4326")

    score = fbp.sorensen_dice_polygon(gdf1, gdf2)
    assert score == pytest.approx(expect_index, abs=1e-6)


def test_sorensen_dice_polygon_not_valid_proj():
    # Build two identical squares (perfect overlap)
    poly1 = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    gdf1 = gpd.GeoDataFrame(geometry=[poly1], crs="EPSG:4326")

    with pytest.raises(ValueError, match="Invalid projection"):
        fbp.sorensen_dice_polygon(gdf1, gdf1, projection="EPSG:4326")


# jaccard_binary
# ---------------
@pytest.mark.parametrize(
    "offset_x, expect_index",
    [
        (0, 1),  # Complete overlap
        (5, 0),  # No overlap
        (2, 1.0 / 3.0),  # Half overlap
    ],
)
def test_jaccard_binary_basic(offset_x, expect_index):
    # Build two identical squares (perfect overlap)
    array1 = np.zeros((10, 10))
    array2 = np.zeros((10, 10))
    array1[1:5, 1:5] = 1
    array2[1 + offset_x : 5 + offset_x, 1:5] = 1

    score = fbp.jaccard_binary(array1, array2)
    assert score == pytest.approx(expect_index, abs=1e-6)


def test_jaccard_binary_shape_mismatch():
    # Build two identical squares (perfect overlap)
    array1 = np.zeros((10, 10))
    array2 = np.zeros((8, 10))
    with pytest.raises(ValueError, match="Input masks must have the same shape"):
        fbp.jaccard_binary(array1, array2)


def test_jaccard_binary_no_surface():
    # Build two identical squares (perfect overlap)
    array1 = np.zeros((10, 10))
    score = fbp.jaccard_binary(array1, array1)
    assert score == pytest.approx(1.0, abs=1e-6)


# sorensen_dice_binary
# ---------------
@pytest.mark.parametrize(
    "offset_x, expect_index",
    [
        (0, 1),  # Complete overlap
        (5, 0),  # No overlap
        (2, 1.0 / 2.0),  # Half overlap
    ],
)
def test_sorensen_dice_binary_basic(offset_x, expect_index):
    # Build two identical squares (perfect overlap)
    array1 = np.zeros((10, 10))
    array2 = np.zeros((10, 10))
    array1[1:5, 1:5] = 1
    array2[1 + offset_x : 5 + offset_x, 1:5] = 1

    score = fbp.sorensen_dice_binary(array1, array2)
    assert score == pytest.approx(expect_index, abs=1e-6)


def test_sorensen_dice_binary_shape_mismatch():
    # Build two identical squares (perfect overlap)
    array1 = np.zeros((10, 10))
    array2 = np.zeros((8, 10))
    with pytest.raises(ValueError, match="Input masks must have the same shape"):
        fbp.sorensen_dice_binary(array1, array2)


def test_sorensen_dice_binary_no_surface():
    # Build two identical squares (perfect overlap)
    array1 = np.zeros((10, 10))
    score = fbp.sorensen_dice_binary(array1, array1)
    assert score == pytest.approx(1.0, abs=1e-6)
