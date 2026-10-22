"""
RRFS 3 km CONUS grid geometry.

RRFS runs on a North American domain and gives a CONUS subset on HRRR's grid: a 1799 x 1059, 3 km
Lambert conformal conic grid on a spherical earth whose messages give HRRR's parameters exactly
(first point 21.138123, 237.280472; LoV 262.5, which is wrapped to -97.5). Its 10 m winds are
grid-relative and are rotated to earth-relative components.
"""

from ..hrrr.grid import HRRR_PARAMETERS
from ..lambert import LambertGrid

RRFS_PARAMETERS = HRRR_PARAMETERS
# Angles of a message may differ from RRFS_PARAMETERS by this much (about 10 m): its messages give
# them to the microdegree.
TOLERANCE_DEG = 1e-4


class RRFSGrid(LambertGrid):
    """RRFS 3 km CONUS Lambert conformal grid with lat/lon <-> grid index conversions (row 0 = south)."""

    def __init__(self):
        super().__init__(RRFS_PARAMETERS)


_GRID = RRFSGrid()


def earth_winds(u_grid, v_grid, lon):
    """Rotate RRFS grid-relative winds to earth-relative (eastward, northward) components."""
    return _GRID.rotate_winds_to_earth(u_grid, v_grid, lon)
