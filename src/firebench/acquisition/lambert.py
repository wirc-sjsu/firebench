"""
Lambert conformal conic grids of NCEP's limited-area forecasts (HRRR, NAM, and the like).

A grid is described by the parameters of its GRIB2 grid definition (template 3.30): size, spacing,
standard parallels, orientation longitude (LoV), first grid point, and the radius of a spherical
earth. The projection is implemented directly, for a tangent or a secant cone, to avoid a pyproj
dependency. A model declares the parameters it expects, and the parameters of every message it reads
are compared with them (``LambertParameters.from_message``, ``mismatch``), so a change of layout is
an error rather than wrong values.

Longitudes are taken in -180..180. GRIB gives LoV and the first longitude in 0..360 (262.5 for the
NAM CONUS nest), and a wind rotation computed with an unwrapped LoV would be off by 360 n degrees.
"""

import math
from dataclasses import dataclass

import numpy as np


def wrap_longitude(lon):
    """Longitude (or longitude difference) in degrees, brought to -180..180 where it is outside."""
    lon = np.asarray(lon, dtype=np.float64)
    wrapped = np.where(lon > 180.0, lon - 360.0, lon)
    wrapped = np.where(wrapped < -180.0, wrapped + 360.0, wrapped)
    return wrapped if wrapped.ndim else float(wrapped)


@dataclass(frozen=True)
class LambertParameters:  # pylint: disable=too-many-instance-attributes
    """Grid definition of a Lambert conformal grid scanning from its south-west corner (row 0 = south)."""

    nx: int
    ny: int
    dx: float  # m
    dy: float  # m
    lat_1: float  # standard parallels, degrees
    lat_2: float
    lon_0: float  # orientation longitude (LoV), degrees in -180..180
    lat_first: float  # grid point (j=0, i=0), degrees
    lon_first: float
    radius: float  # spherical earth, m

    @classmethod
    def from_message(cls, eccodes, gid) -> "LambertParameters":
        """Parameters of one GRIB2 message; refuses another grid type, scan order, or earth shape."""
        grid_type = eccodes.codes_get(gid, "gridType")
        if grid_type != "lambert":
            raise ValueError(f"grid type is {grid_type!r}, expected a Lambert conformal grid")
        scan = tuple(
            eccodes.codes_get(gid, key)
            for key in ("iScansNegatively", "jScansPositively", "jPointsAreConsecutive")
        )
        if scan != (0, 1, 0):
            raise ValueError(
                f"grid scans with (iScansNegatively, jScansPositively, jPointsAreConsecutive) = {scan}, "
                "expected (0, 1, 0)"
            )
        try:
            radius = float(eccodes.codes_get(gid, "radius"))
        except Exception as error:  # pylint: disable=broad-exception-caught
            # eccodes raises its own KeyValueNotFoundError for an ellipsoidal earth
            raise ValueError(
                f"earth shape {eccodes.codes_get(gid, 'shapeOfTheEarth')} is not a sphere"
            ) from error
        return cls(
            nx=int(eccodes.codes_get(gid, "Nx")),
            ny=int(eccodes.codes_get(gid, "Ny")),
            dx=float(eccodes.codes_get(gid, "DxInMetres")),
            dy=float(eccodes.codes_get(gid, "DyInMetres")),
            lat_1=float(eccodes.codes_get(gid, "Latin1InDegrees")),
            lat_2=float(eccodes.codes_get(gid, "Latin2InDegrees")),
            lon_0=wrap_longitude(float(eccodes.codes_get(gid, "LoVInDegrees"))),
            # The integer keys, in millionths of a degree, carry the precision the file was written with.
            lat_first=eccodes.codes_get(gid, "latitudeOfFirstGridPoint") / 1e6,
            lon_first=wrap_longitude(eccodes.codes_get(gid, "longitudeOfFirstGridPoint") / 1e6),
            radius=radius,
        )

    def mismatch(self, expected: "LambertParameters", tolerance_deg: float = 1e-4) -> str | None:
        """What differs from ``expected``, or ``None``: sizes exactly, spacings to the millimetre,
        angles to ``tolerance_deg``, the earth radius to the metre."""
        differences = []
        for name in ("nx", "ny"):
            if getattr(self, name) != getattr(expected, name):
                differences.append(f"{name} {getattr(self, name)} (expected {getattr(expected, name)})")
        for name, tolerance in (
            ("dx", 1e-3),
            ("dy", 1e-3),
            ("lat_1", tolerance_deg),
            ("lat_2", tolerance_deg),
            ("lat_first", tolerance_deg),
            ("radius", 1.0),
        ):
            if abs(getattr(self, name) - getattr(expected, name)) > tolerance:
                differences.append(f"{name} {getattr(self, name)} (expected {getattr(expected, name)})")
        for name in ("lon_0", "lon_first"):
            if abs(wrap_longitude(getattr(self, name) - getattr(expected, name))) > tolerance_deg:
                differences.append(f"{name} {getattr(self, name)} (expected {getattr(expected, name)})")
        return "; ".join(differences) or None


class LambertGrid:
    """A Lambert conformal grid with lat/lon <-> grid index conversions (row 0 = south)."""

    def __init__(self, parameters: LambertParameters):
        self.parameters = parameters
        self.nx = parameters.nx
        self.ny = parameters.ny
        self.dx = parameters.dx
        self.dy = parameters.dy
        self.proj4 = (
            f"+proj=lcc +lat_1={parameters.lat_1} +lat_2={parameters.lat_2} +lat_0={parameters.lat_1} "
            f"+lon_0={parameters.lon_0} +R={parameters.radius} +units=m +no_defs"
        )
        lat_1 = math.radians(parameters.lat_1)
        lat_2 = math.radians(parameters.lat_2)
        if abs(parameters.lat_1 - parameters.lat_2) < 1e-9:
            # Tangent cone (lat_1 == lat_2)
            self._n = math.sin(lat_1)
        else:
            self._n = math.log(math.cos(lat_1) / math.cos(lat_2)) / math.log(
                math.tan(0.25 * math.pi + 0.5 * lat_2) / math.tan(0.25 * math.pi + 0.5 * lat_1)
            )
        self._rf = (
            parameters.radius
            * math.cos(lat_1)
            * math.tan(0.25 * math.pi + 0.5 * lat_1) ** self._n
            / self._n
        )
        # Projection origin at lat_1: the grid is placed by its first point, so the origin cancels out.
        self._rho_0 = self._rf / math.tan(0.25 * math.pi + 0.5 * lat_1) ** self._n
        self._x_0, self._y_0 = self._project(parameters.lat_first, parameters.lon_first)

    @property
    def cone_constant(self) -> float:
        """``n`` of the projection: the wind rotation angle is ``n * (lon - lon_0)``."""
        return self._n

    def _project(self, lat: float, lon: float) -> tuple[float, float]:
        """Spherical LCC forward projection, (lat, lon) degrees -> (x, y) meters."""
        rho = self._rf / math.tan(0.25 * math.pi + 0.5 * math.radians(lat)) ** self._n
        theta = self._n * math.radians(wrap_longitude(lon - self.parameters.lon_0))
        return rho * math.sin(theta), self._rho_0 - rho * math.cos(theta)

    def xy_from_latlon(self, lat: float, lon: float) -> tuple[float, float]:
        """Projected coordinates in meters relative to the grid south-west corner."""
        x, y = self._project(lat, lon)
        return x - self._x_0, y - self._y_0

    def ij_from_latlon(self, lat: float, lon: float) -> tuple[int, int]:
        """Closest grid cell (i, j) to a (lat, lon) point."""
        x, y = self.xy_from_latlon(lat, lon)
        return round(x / self.dx), round(y / self.dy)

    def ij_arrays_from_latlon(self, lat, lon) -> tuple[np.ndarray, np.ndarray]:
        """Fractional grid indices (i, j) of (lat, lon) arrays in degrees (vectorized projection)."""
        rho = (
            self._rf / np.tan(0.25 * np.pi + 0.5 * np.radians(np.asarray(lat, dtype=np.float64))) ** self._n
        )
        theta = self._n * np.radians(
            wrap_longitude(np.asarray(lon, dtype=np.float64) - self.parameters.lon_0)
        )
        x = rho * np.sin(theta) - self._x_0
        y = self._rho_0 - rho * np.cos(theta) - self._y_0
        return x / self.dx, y / self.dy

    def latlon_from_ij(self, i: float, j: float) -> tuple[float, float]:
        """Spherical LCC inverse projection of cell (i, j) -> (lat, lon) degrees."""
        x = self._x_0 + i * self.dx
        y = self._y_0 + j * self.dy
        # A northern-hemisphere cone (n > 0), as every grid read here.
        rho = math.hypot(x, self._rho_0 - y)
        theta = math.atan2(x, self._rho_0 - y)
        lat = 2.0 * math.atan((self._rf / rho) ** (1.0 / self._n)) - 0.5 * math.pi
        lon = self.parameters.lon_0 + math.degrees(theta / self._n)
        return math.degrees(lat), float(wrap_longitude(lon))

    def contains(self, i, j) -> np.ndarray:
        """Whether (rounded) grid indices fall on the grid."""
        i = np.rint(np.asarray(i))
        j = np.rint(np.asarray(j))
        return (i >= 0) & (i < self.nx) & (j >= 0) & (j < self.ny)

    def wind_rotation_angle(self, lon) -> np.ndarray:
        """Grid-to-earth wind rotation angle (radians): ``n * (lon - lon_0)``."""
        return self._n * np.radians(
            wrap_longitude(np.asarray(lon, dtype=np.float64) - self.parameters.lon_0)
        )

    def rotate_winds_to_earth(self, u_grid, v_grid, lon) -> tuple[np.ndarray, np.ndarray]:
        """
        Rotate grid-relative winds to earth-relative (eastward, northward) components.

        ``lon`` (degrees) must broadcast against the wind arrays. Standard NCEP rotation for Lambert
        conformal grids: ``u_e = cos(a) u + sin(a) v``, ``v_e = -sin(a) u + cos(a) v`` with
        ``a = n * (lon - lon_0)``.
        """
        angle = self.wind_rotation_angle(lon)
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)
        return cos_a * u_grid + sin_a * v_grid, -sin_a * u_grid + cos_a * v_grid
