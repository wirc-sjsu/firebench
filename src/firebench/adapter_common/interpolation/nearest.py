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
    nearest_i = -1
    nearest_j = -1
    min_squared_distance = 1e9

    half_min_cell_size = min(0.5 * grid_dlat, 0.5 * grid_dlon)
    found = False

    for j in range(ny):
        for i in range(nx):
            squared_distance = (grid_lat[j, i] - target_lat) ** 2 + (grid_lon[j, i] - target_lon) ** 2

            if squared_distance <= min_squared_distance:
                nearest_i = i
                nearest_j = j
                min_squared_distance = squared_distance

            if min_squared_distance < half_min_cell_size:
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
