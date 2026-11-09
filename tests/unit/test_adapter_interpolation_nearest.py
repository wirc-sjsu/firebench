import numpy as np
import pytest

from firebench.adapter_common.interpolation.nearest import find_nearest_grid_point

LAT0 = 40.0
LON0 = -120.0
DLAT = 0.1
DLON = 0.1
NY = 5
NX = 5

# Initial unit tests created with Claude AI.


@pytest.fixture(name="grid")
def fixture_grid():
    """Regular lat/lon grid in degrees: latitude varies along j (axis 0), longitude along i (axis 1)."""
    lat_1d = LAT0 + DLAT * np.arange(NY)
    lon_1d = LON0 + DLON * np.arange(NX)
    grid_lon, grid_lat = np.meshgrid(lon_1d, lat_1d)
    return grid_lat, grid_lon


def _find(grid, target_lat, target_lon):
    grid_lat, grid_lon = grid
    ny, nx = grid_lat.shape
    return find_nearest_grid_point(nx, ny, target_lat, target_lon, grid_lat, grid_lon, DLAT, DLON)


def test_target_in_middle_of_grid(grid):
    # slightly offset from the center point (j=2, i=2)
    i, j = _find(grid, LAT0 + 2 * DLAT + 0.01, LON0 + 2 * DLON - 0.01)
    assert (i, j) == (2, 2)


def test_target_at_exact_grid_point(grid):
    i, j = _find(grid, LAT0 + 3 * DLAT, LON0 + 1 * DLON)
    assert (i, j) == (1, 3)


def test_target_outside_grid_far_away(grid):
    # north-east of the grid: nearest point is the north-east corner
    i, j = _find(grid, LAT0 + 10.0, LON0 + 10.0)
    assert (i, j) == (NX - 1, NY - 1)


def test_target_outside_grid_other_corner(grid):
    # south-west of the grid: nearest point is the south-west corner
    i, j = _find(grid, LAT0 - 10.0, LON0 - 10.0)
    assert (i, j) == (0, 0)


def test_target_outside_grid_close_to_edge(grid):
    # just outside the south-west corner, within half a cell of it
    i, j = _find(grid, LAT0 - 0.02, LON0 - 0.02)
    assert (i, j) == (0, 0)


def test_target_inside_snaps_to_grid_edge(grid):
    # inside the grid but closest to the south-east edge point (j=0, i=NX-1)
    i, j = _find(grid, LAT0 + 0.01, LON0 + (NX - 1) * DLON - 0.01)
    assert (i, j) == (NX - 1, 0)


@pytest.mark.parametrize("latitude", [0.0, 80.0, -80.0])
@pytest.mark.parametrize("dlat, dlon", [(0.1, 0.1), (0.2, 1.0), (1.0, 0.2), (-0.1, -0.1)])
@pytest.mark.parametrize("axis", ["latitude", "longitude"])
def test_two_point_grid_picks_closest_point(latitude, dlat, dlon, axis):
    # The first point must not trigger an early exit when the second is closer.
    # Include both axes, unequal spacings, descending coordinates and both hemispheres.
    if axis == "longitude":
        grid_lat = np.array([[latitude, latitude]])
        grid_lon = np.array([[0.0, dlon]])
        target_lat, target_lon = latitude, 0.9 * dlon
        expected = (1, 0)
    else:
        grid_lat = np.array([[latitude], [latitude + dlat]])
        grid_lon = np.array([[0.0], [0.0]])
        target_lat, target_lon = latitude + 0.9 * dlat, 0.0
        expected = (0, 1)

    ny, nx = grid_lat.shape
    assert (
        find_nearest_grid_point(nx, ny, target_lat, target_lon, grid_lat, grid_lon, dlat, dlon) == expected
    )
