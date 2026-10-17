import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

import firebench.standardize as fs

# 40 x 40 cells of 30 m in CONUS Albers, as LANDFIRE ships its mosaics: int16, no data 32767
ORIGIN = (-2100000.0, 2000000.0)
SIZE = 40
CELL = 30.0


@pytest.fixture
def mosaic(tmp_path):
    grid = (np.arange(SIZE * SIZE, dtype=np.int16).reshape(SIZE, SIZE) % 50) * 10
    grid[0, 0] = 32767
    grid[0, 1] = -9999
    profile = {
        "driver": "GTiff",
        "height": SIZE,
        "width": SIZE,
        "count": 1,
        "dtype": "int16",
        "crs": "EPSG:5070",
        "nodata": 32767,
        "transform": from_origin(*ORIGIN, CELL, CELL),
    }
    path = tmp_path / "LF2025_CH_CONUS.tif"
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(grid, 1)
    return path, grid


def _corners(rows, columns):
    """Geographic corners (lat, lon) of a block of cells, a little inside its edges."""
    to_geo = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    x_min = ORIGIN[0] + columns[0] * CELL + 1
    x_max = ORIGIN[0] + columns[1] * CELL - 1
    y_max = ORIGIN[1] - rows[0] * CELL - 1
    y_min = ORIGIN[1] - rows[1] * CELL + 1
    lon_ll, lat_ll = to_geo.transform(x_min, y_min)
    lon_ur, lat_ur = to_geo.transform(x_max, y_max)
    return (lat_ll, lon_ll), (lat_ur, lon_ur)


def test_a_canopy_product_is_cut_to_the_box_into_its_group(mosaic, tmp_path):
    path, grid = mosaic
    h5 = fs.new_std_file(str(tmp_path / "out.h5"), "FireBench tests")
    lower_left, upper_right = _corners((10, 20), (5, 25))

    written = fs.standardize_landfire_canopy(str(path), h5, "ch", lower_left, upper_right)

    assert written == "/spatial_2d/landfire_ch"
    group = h5[written]
    data = group["canopy_height"]
    assert data.attrs["units"] == "dm"
    assert data.attrs["_FillValue"] == 32767
    assert data.dtype == np.uint16
    assert group.attrs["landfire_product"] == "ch"
    assert group.attrs["license"] == "/DATA_LICENSES/LANDFIRE.txt"
    # The box, reprojected to Albers, holds the block and a few cells of its edges, never the grid.
    assert 10 * 20 <= data.size < SIZE * SIZE
    assert set(np.unique(data[:])) <= set(np.unique(grid[grid >= 0]))
    assert group["position_lat"].shape == data.shape
    h5.close()


def test_a_negative_value_is_stored_as_the_fill_value(mosaic, tmp_path):
    path, _grid = mosaic
    h5 = fs.new_std_file(str(tmp_path / "out.h5"), "FireBench tests")
    lower_left, upper_right = _corners((0, 5), (0, 5))

    fs.standardize_landfire_canopy(str(path), h5, "cbd", lower_left, upper_right)

    data = h5["/spatial_2d/landfire_cbd/canopy_density_bulk"]
    assert data.attrs["units"] == "dag / m^3"
    values = data[:]
    assert not (values == np.uint16(-9999 & 0xFFFF)).any()
    assert (values == 32767).sum() >= 2
    h5.close()


def test_every_canopy_product_has_its_variable(mosaic, tmp_path):
    path, _grid = mosaic
    h5 = fs.new_std_file(str(tmp_path / "out.h5"), "FireBench tests")
    lower_left, upper_right = _corners((10, 20), (10, 20))

    for product, (variable, units, group) in fs.LANDFIRE_CANOPY_PRODUCTS.items():
        written = fs.standardize_landfire_canopy(str(path), h5, product, lower_left, upper_right)
        assert written == f"/spatial_2d/{group}"
        assert h5[written][variable].attrs["units"] == units
    h5.close()


def test_an_unknown_product_is_refused(mosaic, tmp_path):
    path, _grid = mosaic
    h5 = fs.new_std_file(str(tmp_path / "out.h5"), "FireBench tests")
    lower_left, upper_right = _corners((10, 20), (10, 20))

    with pytest.raises(ValueError, match="Unknown LANDFIRE canopy product"):
        fs.standardize_landfire_canopy(str(path), h5, "evc", lower_left, upper_right)
    h5.close()


def test_one_corner_alone_is_refused(mosaic, tmp_path):
    path, _grid = mosaic
    h5 = fs.new_std_file(str(tmp_path / "out.h5"), "FireBench tests")

    with pytest.raises(ValueError, match="both corners"):
        fs.standardize_landfire_from_geotiff(
            str(path), h5, "canopy_height", "dm", lower_left_corner=(38.5, -120.5)
        )
    h5.close()
