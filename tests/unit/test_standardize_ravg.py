import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

import firebench.standardize as fs
from firebench.tools import StandardVariableNames as svn

# 8 x 6 cells of a quarter of a degree, from 121 W and 39.5 N; values 1 to 48, so 0 only comes from blanking
GRID = np.arange(1, 49, dtype=np.uint8).reshape(6, 8)
LOWER_LEFT = (38.5, -120.5)
UPPER_RIGHT = (39.25, -119.75)
# the 3 x 3 cells the corners cut out, and their stored positions
CUT = GRID[1:4, 2:5]
CUT_LAT = [39.25, 39.0, 38.75]
CUT_LON = [-120.5, -120.25, -120.0]
VARIABLE = svn.RAVG_CANOPY_COVER_LOSS.value


def _write_geotiff(path, crs="EPSG:4326"):
    profile = {
        "driver": "GTiff",
        "height": GRID.shape[0],
        "width": GRID.shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": crs,
        "transform": from_origin(-121.0, 39.5, 0.25, 0.25),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(GRID, 1)
    return path


@pytest.fixture
def inputs(tmp_path):
    h5 = fs.new_std_file(str(tmp_path / "ravg.h5"), "FireBench tests")
    yield _write_geotiff(tmp_path / "ravg_cc5.tif"), h5
    h5.close()


def _standardize(inputs, function=fs.standardize_ravg_cc_from_geotiff, projection="EPSG:4326", **arguments):
    geotiff_path, h5 = inputs
    function(geotiff_path, h5, LOWER_LEFT, UPPER_RIGHT, "ravg", projection, overwrite=True, **arguments)
    return h5["spatial_2d/ravg"]


def test_without_boxes_the_grid_is_cut_to_the_corners(inputs):
    group = _standardize(inputs)

    assert set(group) == {"position_lat", "position_lon", VARIABLE}
    assert set(group.attrs) == {"data_source", "crs"}
    assert group.attrs["crs"] == "EPSG:4326"
    np.testing.assert_array_equal(group[VARIABLE][:], CUT)
    assert group[VARIABLE].dtype == np.uint8
    assert group[VARIABLE].attrs["units"] == "dimensionless"
    assert group[VARIABLE].attrs["_FillValue"] == 0
    np.testing.assert_allclose(group["position_lat"][:, 0], CUT_LAT, atol=1e-12)
    np.testing.assert_allclose(group["position_lon"][0, :], CUT_LON, atol=1e-12)
    assert group["position_lat"].dtype == np.float64
    assert group["position_lat"].attrs["units"] == "degrees"
    assert group["position_lon"].attrs["units"] == "degrees"


@pytest.mark.parametrize(
    "function,variable",
    [
        (fs.standardize_ravg_cc_from_geotiff, svn.RAVG_CANOPY_COVER_LOSS.value),
        (fs.standardize_ravg_cbi_from_geotiff, svn.RAVG_COMPOSITE_BURN_INDEX_SEVERITY.value),
        (fs.standardize_ravg_ba_from_geotiff, svn.RAVG_LIVE_BASAL_AREA_LOSS.value),
    ],
)
def test_one_box_blanks_the_cells_inside_and_no_other(inputs, function, variable):
    box = ((38.9, -120.3), (39.1, -120.1))

    group = _standardize(inputs, function, exclude_boxes=[box])

    expected = CUT.copy()
    expected[1, 1] = 0
    np.testing.assert_array_equal(group[variable][:], expected)
    assert json.loads(group.attrs["excluded_boxes"]) == [[[38.9, -120.3], [39.1, -120.1]]]
    np.testing.assert_allclose(group["position_lat"][:, 0], CUT_LAT, atol=1e-12)
    np.testing.assert_allclose(group["position_lon"][0, :], CUT_LON, atol=1e-12)


def test_cell_on_the_edge_of_a_box_is_not_blanked(inputs):
    stored = _standardize(inputs)
    lat_edge = float(stored["position_lat"][1, 0])
    lon_edge = float(stored["position_lon"][0, 1])

    # the box starts exactly on the middle row and the middle column
    group = _standardize(inputs, exclude_boxes=[((lat_edge, lon_edge), (40.0, -119.0))])

    expected = CUT.copy()
    expected[0, 2] = 0
    np.testing.assert_array_equal(group[VARIABLE][:], expected)


def test_infinite_bound_blanks_to_the_edge_of_the_grid(inputs):
    group = _standardize(inputs, exclude_boxes=[((38.9, -120.3), (np.inf, np.inf))])

    expected = CUT.copy()
    expected[:2, 1:] = 0
    np.testing.assert_array_equal(group[VARIABLE][:], expected)
    assert group.attrs["excluded_boxes"] == "[[[38.9, -120.3], [null, null]]]"


def test_several_boxes_are_all_blanked(inputs):
    boxes = [((39.1, -np.inf), (np.inf, -120.4)), ((-np.inf, -120.1), (38.9, np.inf))]

    group = _standardize(inputs, exclude_boxes=boxes, invert_y=True)

    expected = CUT[::-1].copy()
    expected[2, 0] = 0
    expected[0, 2] = 0
    np.testing.assert_array_equal(group[VARIABLE][:], expected)
    assert json.loads(group.attrs["excluded_boxes"]) == [
        [[39.1, None], [None, -120.4]],
        [[None, -120.1], [38.9, None]],
    ]


def test_empty_list_of_boxes_writes_what_no_box_writes(inputs):
    group = _standardize(inputs, exclude_boxes=[])

    np.testing.assert_array_equal(group[VARIABLE][:], CUT)
    assert "excluded_boxes" not in group.attrs


def test_projected_output_with_boxes_is_refused(inputs, tmp_path):
    geotiff_path, h5 = inputs
    box = ((38.9, -120.3), (39.1, -120.1))

    with pytest.raises(ValueError, match="exclude_boxes are geographic"):
        _standardize(inputs, projection="EPSG:3310", exclude_boxes=[box])
    # without `projection` the output is in the projection of the GeoTIFF
    projected = _write_geotiff(tmp_path / "projected.tif", crs="EPSG:32610")
    with pytest.raises(ValueError, match="exclude_boxes are geographic"):
        _standardize((projected, h5), projection=None, exclude_boxes=[box])

    assert "spatial_2d" not in h5
    assert _standardize((geotiff_path, h5), projection=None, exclude_boxes=[box])[VARIABLE][1, 1] == 0


@pytest.mark.parametrize(
    "box",
    [
        ((39.1, -120.3), (38.9, -120.1)),
        ((38.9, -120.1), (39.1, -120.3)),
        ((38.9, np.nan), (39.1, -120.1)),
        (38.9, -120.3, 39.1, -120.1),
        ((38.9, -120.3),),
    ],
)
def test_malformed_box_is_refused(inputs, box):
    with pytest.raises(ValueError, match="must be .*lat_min, lon_min.*, with min < max"):
        _standardize(inputs, exclude_boxes=[box])

    assert "spatial_2d" not in inputs[1]
