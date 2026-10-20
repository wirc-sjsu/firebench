"""
HRRR CONUS grid geometry.

The HRRR CONUS grid is a 1799 x 1059, 3 km Lambert conformal conic grid on a spherical earth
(parameters from the GRIB2 grid definition of the operational files), one of the shared Lambert
grids of ``firebench.acquisition.lambert``. Ported from spear ``backends/hrrr/grid``.
"""

import numpy as np

from ..lambert import LambertGrid, LambertParameters

EARTH_RADIUS = 6371229.0  # m
NX = 1799
NY = 1059
DX = 3000.0  # m
DY = 3000.0  # m
LAT_STD = 38.5  # standard parallels (lat_1 = lat_2) and projection origin latitude
LON_0 = -97.5
LAT_FIRST = 21.138123  # grid point (j=0, i=0), south-west corner
LON_FIRST = -122.719528

HRRR_PARAMETERS = LambertParameters(
    nx=NX,
    ny=NY,
    dx=DX,
    dy=DY,
    lat_1=LAT_STD,
    lat_2=LAT_STD,
    lon_0=LON_0,
    lat_first=LAT_FIRST,
    lon_first=LON_FIRST,
    radius=EARTH_RADIUS,
)

# PROJ4 description of the HRRR projection (origin at LAT_STD/LON_0)
PROJ4 = (
    f"+proj=lcc +lat_1={LAT_STD} +lat_2={LAT_STD} +lat_0={LAT_STD} "
    f"+lon_0={LON_0} +R={EARTH_RADIUS} +units=m +no_defs"
)


class HRRRGrid(LambertGrid):
    """HRRR CONUS Lambert conformal grid with lat/lon <-> grid index conversions (row 0 = south)."""

    def __init__(self):
        super().__init__(HRRR_PARAMETERS)
        self.proj4 = PROJ4


_GRID = HRRRGrid()


def wind_rotation_angle(lon) -> np.ndarray:
    """Grid-to-earth wind rotation angle (radians): ``sin(lat_std) * (lon - lon_0)``."""
    return _GRID.wind_rotation_angle(lon)


def rotate_winds_to_earth(u_grid, v_grid, lon) -> tuple[np.ndarray, np.ndarray]:
    """
    Rotate HRRR grid-relative winds to earth-relative (eastward, northward) components.

    ``lon`` (degrees) must broadcast against the wind arrays. Standard NCEP rotation for Lambert
    conformal grids (HRRR FAQ): ``u_e = cos(a) u + sin(a) v``, ``v_e = -sin(a) u + cos(a) v`` with
    ``a = sin(lat_std) * (lon - lon_0)``.
    """
    return _GRID.rotate_winds_to_earth(u_grid, v_grid, lon)
