"""
HRRR CONUS grid geometry.

The HRRR CONUS grid is a 1799 x 1059, 3 km Lambert conformal conic grid on a spherical earth
(parameters from the GRIB2 grid definition of the operational files). The tangent spherical LCC
projection is implemented directly to avoid a pyproj dependency. Ported from spear
``backends/hrrr/grid``.
"""

import math

import numpy as np

EARTH_RADIUS = 6371229.0  # m
NX = 1799
NY = 1059
DX = 3000.0  # m
DY = 3000.0  # m
LAT_STD = 38.5  # standard parallels (lat_1 = lat_2) and projection origin latitude
LON_0 = -97.5
LAT_FIRST = 21.138123  # grid point (j=0, i=0), south-west corner
LON_FIRST = -122.719528

# PROJ4 description of the HRRR projection (origin at LAT_STD/LON_0)
PROJ4 = (
    f"+proj=lcc +lat_1={LAT_STD} +lat_2={LAT_STD} +lat_0={LAT_STD} "
    f"+lon_0={LON_0} +R={EARTH_RADIUS} +units=m +no_defs"
)


class HRRRGrid:
    """HRRR CONUS Lambert conformal grid with lat/lon <-> grid index conversions (row 0 = south)."""

    nx = NX
    ny = NY
    dx = DX
    dy = DY
    proj4 = PROJ4

    def __init__(self):
        # Tangent cone (lat_1 == lat_2): n = sin(lat_std)
        lat_std = math.radians(LAT_STD)
        self._n = math.sin(lat_std)
        self._rf = (
            EARTH_RADIUS * math.cos(lat_std) * math.tan(0.25 * math.pi + 0.5 * lat_std) ** self._n / self._n
        )
        self._rho_0 = self._rf / math.tan(0.25 * math.pi + 0.5 * lat_std) ** self._n
        self._x_0, self._y_0 = self._project(LAT_FIRST, LON_FIRST)

    def _project(self, lat: float, lon: float) -> tuple[float, float]:
        """Spherical LCC forward projection, (lat, lon) degrees -> (x, y) meters."""
        rho = self._rf / math.tan(0.25 * math.pi + 0.5 * math.radians(lat)) ** self._n
        theta = self._n * math.radians(lon - LON_0)
        return rho * math.sin(theta), self._rho_0 - rho * math.cos(theta)

    def xy_from_latlon(self, lat: float, lon: float) -> tuple[float, float]:
        """Projected coordinates in meters relative to the grid south-west corner."""
        x, y = self._project(lat, lon)
        return x - self._x_0, y - self._y_0

    def ij_from_latlon(self, lat: float, lon: float) -> tuple[int, int]:
        """Closest HRRR cell (i, j) to a (lat, lon) point."""
        x, y = self.xy_from_latlon(lat, lon)
        return round(x / DX), round(y / DY)

    def ij_arrays_from_latlon(self, lat, lon) -> tuple[np.ndarray, np.ndarray]:
        """Fractional grid indices (i, j) of (lat, lon) arrays in degrees (vectorized projection)."""
        rho = (
            self._rf / np.tan(0.25 * np.pi + 0.5 * np.radians(np.asarray(lat, dtype=np.float64))) ** self._n
        )
        theta = self._n * np.radians(np.asarray(lon, dtype=np.float64) - LON_0)
        x = rho * np.sin(theta) - self._x_0
        y = self._rho_0 - rho * np.cos(theta) - self._y_0
        return x / DX, y / DY

    def latlon_from_ij(self, i: float, j: float) -> tuple[float, float]:
        """Spherical LCC inverse projection of cell (i, j) -> (lat, lon) degrees."""
        x = self._x_0 + i * DX
        y = self._y_0 + j * DY
        rho = math.hypot(x, self._rho_0 - y)
        theta = math.atan2(x, self._rho_0 - y)
        lat = 2.0 * math.atan((self._rf / rho) ** (1.0 / self._n)) - 0.5 * math.pi
        lon = LON_0 + math.degrees(theta / self._n)
        return math.degrees(lat), lon

    @staticmethod
    def contains(i, j) -> np.ndarray:
        """Whether (rounded) grid indices fall on the grid."""
        i = np.rint(np.asarray(i))
        j = np.rint(np.asarray(j))
        return (i >= 0) & (i < NX) & (j >= 0) & (j < NY)


def wind_rotation_angle(lon) -> np.ndarray:
    """Grid-to-earth wind rotation angle (radians): ``sin(lat_std) * (lon - lon_0)``."""
    return math.sin(math.radians(LAT_STD)) * np.radians(np.asarray(lon, dtype=np.float64) - LON_0)


def rotate_winds_to_earth(u_grid, v_grid, lon) -> tuple[np.ndarray, np.ndarray]:
    """
    Rotate HRRR grid-relative winds to earth-relative (eastward, northward) components.

    ``lon`` (degrees) must broadcast against the wind arrays. Standard NCEP rotation for Lambert
    conformal grids (HRRR FAQ): ``u_e = cos(a) u + sin(a) v``, ``v_e = -sin(a) u + cos(a) v`` with
    ``a = sin(lat_std) * (lon - lon_0)``.
    """
    angle = wind_rotation_angle(lon)
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    u_earth = cos_a * u_grid + sin_a * v_grid
    v_earth = -sin_a * u_grid + cos_a * v_grid
    return u_earth, v_earth
