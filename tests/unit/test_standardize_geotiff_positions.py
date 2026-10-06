import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

import firebench.standardize as fs
from firebench.standardize.tools import import_tif

# 4 x 3 cells of a quarter of a degree, from 121 W and 39.5 N
GRID = np.arange(1, 13, dtype=np.uint8).reshape(3, 4)
CENTER_LAT = [39.375, 39.125, 38.875]
CENTER_LON = [-120.875, -120.625, -120.375, -120.125]


@pytest.fixture
def geotiff_path(tmp_path):
    profile = {
        "driver": "GTiff",
        "height": GRID.shape[0],
        "width": GRID.shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": "EPSG:4326",
        "transform": from_origin(-121.0, 39.5, 0.25, 0.25),
    }
    path = tmp_path / "grid.tif"
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(GRID, 1)
    return path


def _assert_positions_are_cell_centers(lat, lon, center_lat=CENTER_LAT):
    np.testing.assert_allclose(lat, np.tile(np.array(center_lat)[:, None], (1, 4)), atol=1e-12)
    np.testing.assert_allclose(lon, np.tile(CENTER_LON, (3, 1)), atol=1e-12)


def test_import_tif_gives_the_cell_centers(geotiff_path):
    lat, lon, data, _crs, _nodata = import_tif(geotiff_path)

    np.testing.assert_array_equal(data, GRID)
    _assert_positions_are_cell_centers(lat, lon)


def test_import_tif_inverted_keeps_each_position_with_its_cell(geotiff_path):
    lat, lon, data, _crs, _nodata = import_tif(geotiff_path, invert_y=True)

    np.testing.assert_array_equal(data, GRID[::-1])
    _assert_positions_are_cell_centers(lat, lon, CENTER_LAT[::-1])


def test_import_tif_with_rect_box_gives_the_cell_centers_of_the_window(geotiff_path):
    lat, lon, data, _crs, _nodata = fs.import_tif_with_rect_box(
        geotiff_path, (38.75, -120.75), (39.25, -120.25), "EPSG:4326"
    )

    np.testing.assert_array_equal(data, GRID[1:3, 1:3])
    np.testing.assert_allclose(lat[:, 0], CENTER_LAT[1:3], atol=1e-12)
    np.testing.assert_allclose(lon[0, :], CENTER_LON[1:3], atol=1e-12)


def test_mtbs_positions_are_the_cell_centers(geotiff_path, tmp_path):
    h5 = fs.new_std_file(str(tmp_path / "mtbs.h5"), "FireBench tests")

    fs.standardize_mtbs_from_geotiff(str(geotiff_path), h5, "mtbs")

    group = h5["spatial_2d/mtbs"]
    _assert_positions_are_cell_centers(group["position_lat"][:], group["position_lon"][:])
    h5.close()


def test_landfire_positions_are_the_cell_centers(geotiff_path, tmp_path):
    h5 = fs.new_std_file(str(tmp_path / "landfire.h5"), "FireBench tests")

    fs.standardize_landfire_from_geotiff(
        str(geotiff_path), h5, "canopy_height", "m", "landfire", fill_value=0
    )

    group = h5["spatial_2d/landfire"]
    _assert_positions_are_cell_centers(group["position_lat"][:], group["position_lon"][:])
    h5.close()
