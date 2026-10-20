"""
GFS 0.25 degree global grid geometry.

A regular latitude-longitude grid of 1440 x 721 points: the first point is at 90N 0E, longitudes
increase eastward (0 to 359.75) and latitudes decrease southward (``jScansPositively = 0``). Winds
are earth-relative on this grid, so they need no rotation.
"""

import numpy as np

NX = 1440
NY = 721
DLON = 0.25  # degrees
DLAT = 0.25
LAT_FIRST = 90.0  # grid point (j=0, i=0), north-west corner
LON_FIRST = 0.0


class GFSGrid:
    """GFS 0.25 degree grid with lat/lon -> grid index conversions (row 0 = north, wraps in longitude)."""

    nx = NX
    ny = NY

    @staticmethod
    def ij_arrays_from_latlon(lat, lon) -> tuple[np.ndarray, np.ndarray]:
        """Fractional grid indices (i, j) of (lat, lon) arrays in degrees; ``i`` is in [0, NX)."""
        i = np.mod(np.asarray(lon, dtype=np.float64) - LON_FIRST, 360.0) / DLON
        j = (LAT_FIRST - np.asarray(lat, dtype=np.float64)) / DLAT
        return i, j

    @staticmethod
    def contains(i, j) -> np.ndarray:
        """Whether (rounded) grid indices fall on the grid; the grid wraps around in longitude."""
        j = np.rint(np.asarray(j))
        return np.isfinite(np.asarray(i, dtype=np.float64)) & (j >= 0) & (j < NY)


def earth_winds(u_grid, v_grid, lon) -> tuple[np.ndarray, np.ndarray]:  # pylint: disable=unused-argument
    """GFS winds on its latitude-longitude grid are already earth-relative."""
    return np.asarray(u_grid, dtype=np.float64), np.asarray(v_grid, dtype=np.float64)
