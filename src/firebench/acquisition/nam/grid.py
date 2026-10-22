"""
NAM CONUS nest grid geometry.

The nest is a 1799 x 1059, 3 km Lambert conformal conic grid on a spherical earth, one of the shared
Lambert grids of ``firebench.acquisition.lambert``. Its parameters are HRRR's, but its messages give
the first point to the millidegree (21.138, -122.72) and LoV in 0..360 (262.5): the parameters here
are those the messages give, so the projection matches the file's own grid points. Its 10 m winds
are grid-relative and are rotated to earth-relative components.
"""

from ..lambert import LambertGrid, LambertParameters

NX = 1799
NY = 1059

NAM_PARAMETERS = LambertParameters(
    nx=NX,
    ny=NY,
    dx=3000.0,
    dy=3000.0,
    lat_1=38.5,
    lat_2=38.5,
    lon_0=-97.5,
    lat_first=21.138,  # grid point (j=0, i=0), south-west corner
    lon_first=-122.72,
    radius=6371229.0,
)
# Angles of a message may differ from NAM_PARAMETERS by this much (about 100 m, a thirtieth of a
# cell), so the same grid given with HRRR's precision (21.138123) is still accepted.
TOLERANCE_DEG = 1e-3


class NAMGrid(LambertGrid):
    """NAM CONUS nest Lambert conformal grid with lat/lon <-> grid index conversions (row 0 = south)."""

    def __init__(self):
        super().__init__(NAM_PARAMETERS)


_GRID = NAMGrid()


def earth_winds(u_grid, v_grid, lon):
    """Rotate NAM grid-relative winds to earth-relative (eastward, northward) components."""
    return _GRID.rotate_winds_to_earth(u_grid, v_grid, lon)
