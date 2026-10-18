import io
import json
import urllib.error

import h5py
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from firebench.acquisition import copernicus_dem
from firebench.standardize import (
    ground_elevation,
    new_std_file,
    read_terrain_elevation,
    standardize_terrain_elevation,
    terrain_elevation_grid,
)
from firebench.standardize.elevation import COPERNICUS, LANDFIRE

BBOX = (-119.23, 40.775, -119.18, 40.805)


def _copernicus(path, value=1189.0):
    """A Copernicus-like tile: 1 by 1 degree, EPSG:4326, a slope of 1 m per 0.01 degree eastward."""
    size = 360
    cols = np.arange(size)
    data = (value + (cols / size) * 100.0)[None, :].repeat(size, axis=0).astype(np.float32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=size,
        height=size,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-120.0, 41.0, 1 / size, 1 / size),
        nodata=-32767.0,
    ) as dst:
        dst.write(data, 1)
    return path


def _landfire(path, value=1191, west_of=-119.2):
    """A LANDFIRE-like mosaic: EPSG:5070, 30 m, int16, -9999 east of `west_of` (outside its cover)."""
    from pyproj import Transformer  # pylint: disable=import-outside-toplevel

    to = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    x0, y0 = to.transform(-119.30, 40.83)
    width, height = 300, 300
    data = np.full((height, width), value, dtype=np.int16)
    back = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    xs = x0 + (np.arange(width) + 0.5) * 30
    for row in range(height):
        lon, _ = back.transform(xs, np.full(width, y0 - (row + 0.5) * 30))
        data[row, np.asarray(lon) > west_of] = -9999
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="int16",
        crs="EPSG:5070",
        transform=from_origin(x0, y0, 30, 30),
        nodata=-9999,
    ) as dst:
        dst.write(data, 1)
    return path


def test_landfire_is_used_where_it_has_a_value_and_copernicus_elsewhere(tmp_path):
    landfire = _landfire(tmp_path / "lf.tif")
    tile = _copernicus(tmp_path / "cop.tif")
    grid = terrain_elevation_grid(BBOX, landfire_path=landfire, copernicus=[tile])
    assert grid.step == pytest.approx(1 / 3600)
    assert grid.elevation.shape == (108, 180)
    west = grid.lon < -119.205
    east = grid.lon > -119.195
    assert (grid.source[:, west] == LANDFIRE).all() and np.allclose(grid.elevation[:, west], 1191)
    assert (grid.source[:, east] == COPERNICUS).all()
    # The Copernicus slope: 1189 m at -120, 100 m more a degree east.
    np.testing.assert_allclose(grid.elevation[:, -1], 1189 + (grid.lon[-1] + 120) * 100, atol=0.3)
    assert grid.landfire_file == "lf.tif" and grid.copernicus_tiles == {"cop": None}


def test_the_elevation_of_a_point_names_its_source(tmp_path):
    landfire = _landfire(tmp_path / "lf.tif")
    tile = _copernicus(tmp_path / "cop.tif")
    assert ground_elevation(40.79, -119.21, landfire_path=landfire, copernicus=[tile]) == (
        1191.0,
        "LANDFIRE",
    )
    value, source = ground_elevation(40.79, -119.19, landfire_path=landfire, copernicus=[tile])
    assert source == "Copernicus DEM GLO-30" and value == pytest.approx(1189 + 81, abs=0.3)
    assert ground_elevation(45.0, -100.0, copernicus=[tile]) is None


def test_a_box_no_source_covers_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no elevation in the box"):
        terrain_elevation_grid((-100.0, 45.0, -99.9, 45.1), copernicus=[_copernicus(tmp_path / "cop.tif")])


def test_a_large_box_is_sampled_on_a_coarser_grid(tmp_path, monkeypatch):
    monkeypatch.setattr("firebench.standardize.elevation.MAX_CELLS", 1000)
    grid = terrain_elevation_grid(BBOX, copernicus=[_copernicus(tmp_path / "cop.tif")])
    assert grid.elevation.size <= 1100 and grid.step > 1 / 3600


def test_the_grid_is_written_and_read_back(tmp_path):
    grid = terrain_elevation_grid(BBOX, copernicus=[_copernicus(tmp_path / "cop.tif")])
    with new_std_file(tmp_path / "terrain.h5", "tester") as h5:
        group = standardize_terrain_elevation(grid, h5)
        assert dict(h5["/spatial_2d"].attrs) == {}
        assert group["terrain_elevation"].attrs["units"] == "m"
        assert json.loads(group.attrs["sources"])["copernicus"]["cells"] == grid.elevation.size
        with pytest.raises(ValueError, match="already exists"):
            standardize_terrain_elevation(grid, h5)
    with h5py.File(tmp_path / "terrain.h5") as h5:
        back = read_terrain_elevation(h5)
    np.testing.assert_array_equal(back.elevation, grid.elevation)
    assert back.bbox == pytest.approx(BBOX)


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_tiles_of_a_box_are_named_and_fetched(tmp_path):
    assert copernicus_dem.tile_name(40.79, -119.2) == "Copernicus_DSM_COG_10_N40_00_W120_00_DEM"
    assert copernicus_dem.tile_name(-0.5, 0.5) == "Copernicus_DSM_COG_10_S01_00_E000_00_DEM"
    names = copernicus_dem.tiles_for_bbox((-120.5, 40.5, -119.5, 41.5))
    assert len(names) == 4 and names[0].endswith("N40_00_W121_00_DEM")
    asked = []

    def opener(request, timeout):
        asked.append(request.full_url)
        if "W121" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
        return _Response(b"tile")

    tiles = copernicus_dem.fetch_copernicus_dem((-120.5, 40.2, -119.5, 40.4), tmp_path, opener=opener)
    assert [tile.path is None for tile in tiles] == [True, False]
    assert tiles[1].bytes == 4 and tiles[1].sha256 and asked[1].startswith(copernicus_dem.BASE_URL)
    (tmp_path / "empty").mkdir()
    local = copernicus_dem.fetch_copernicus_dem(BBOX, tmp_path / "out", local_dir=tmp_path / "empty")
    assert local[0].path is None
