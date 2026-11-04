import numpy as np
import pytest

from firebench.adapter_common.interpolation.nearest import find_nearest_grid_point

LAT0 = 40.0
LON0 = -120.0
DLAT = 0.1
DLON = 0.1
NY = 5
NX = 5

# Unit tests created with Claude AI:
# Add unit tests for find_nearest_grid_point function.
# Use regular latitude/longitude grid for all tests with coordinates and spacing in degree.
# - Add test for target in the middle of the grid.
# - Add test with target at exact grid point.
# - Add tests for target outside grid.
# - Add test target outside but close enough to grid edge.
# - Add test inside and snap to grid edge.
# - Add edge case: with grid latitude [[80, 80]], longitude [[0, 0.1]], target (80, 0.09), and both spacings 0.1.
# >>>>
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


def test_two_point_grid_high_latitude_picks_closest_longitude():
    # At 80 deg N longitude degrees are shrunk by cos(lat); the second point must still win
    # over the first one, which is only reached first in scan order.
    grid_lat = np.array([[80.0, 80.0]])
    grid_lon = np.array([[0.0, 0.1]])
    i, j = find_nearest_grid_point(2, 1, 80.0, 0.09, grid_lat, grid_lon, 0.1, 0.1)
    assert (i, j) == (1, 0)
# <<<<