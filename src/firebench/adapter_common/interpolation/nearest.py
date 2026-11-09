import numpy as np
from numba import njit
from scipy.interpolate import NearestNDInterpolator


@njit(fastmath=True)
def find_nearest_grid_point(
    nx: int,
    ny: int,
    target_lat: float,
    target_lon: float,
    grid_lat: np.ndarray,
    grid_lon: np.ndarray,
    grid_dlat: float,
    grid_dlon: float,
):
    """Find the nearest point on a regular latitude/longitude grid.

    Distances use a local planar approximation, scaling longitude differences
    by cos(target_lat). The early exit requires a regular grid whose angular
    spacings match grid_dlat and grid_dlon; longitude differences are not wrapped.

    Parameters
    ----------
    nx, ny : int
        Number of grid columns and rows, respectively.
    target_lat, target_lon : float
        Target coordinates in degrees.
    grid_lat, grid_lon : np.ndarray
        Grid coordinates in degrees, with shape (ny, nx).
    grid_dlat, grid_dlon : float
        Latitude and longitude spacings in degrees; either sign is accepted.

    Returns
    -------
    tuple[int, int]
        Column and row indices (i, j), or (-1, -1) for an empty grid.
    """

    nearest_i = -1
    nearest_j = -1
    min_squared_distance = 1e9

    dlon_correction = abs(np.cos(np.deg2rad(target_lat)))
    # Within half the smallest cell spacing, no other regular-grid point is closer.
    half_min_cell_size_squared = (0.5 * min(abs(grid_dlat), abs(grid_dlon) * dlon_correction)) ** 2
    found = False

    for j in range(ny):
        for i in range(nx):
            squared_distance = (grid_lat[j, i] - target_lat) ** 2 + (
                (grid_lon[j, i] - target_lon) * dlon_correction
            ) ** 2

            if squared_distance <= min_squared_distance:
                nearest_i = i
                nearest_j = j
                min_squared_distance = squared_distance

            if min_squared_distance < half_min_cell_size_squared:
                found = True
                break

        if found:
            break

    return nearest_i, nearest_j


def nearest_2d(
    data_src: np.ndarray,
    x_src: np.ndarray,
    y_src: np.ndarray,
    x_tgt: np.ndarray,
    y_tgt: np.ndarray,
):
    interp = NearestNDInterpolator(list(zip(x_src.ravel(), y_src.ravel())), data_src.ravel())
    return interp(x_tgt, y_tgt)
