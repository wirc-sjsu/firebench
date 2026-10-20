import math

import numpy as np
import pytest

from firebench.acquisition.hrrr.grid import HRRR_PARAMETERS, HRRRGrid
from firebench.acquisition.lambert import LambertGrid, LambertParameters, wrap_longitude

# The NAM CONUS nest as its GRIB2 messages give it: HRRR's grid, LoV and longitudes in 0..360, the
# first point rounded to the millidegree (checked on nam.20260828 t00z).
NAM_MESSAGE = {
    "gridType": "lambert",
    "iScansNegatively": 0,
    "jScansPositively": 1,
    "jPointsAreConsecutive": 0,
    "radius": 6371229,
    "shapeOfTheEarth": 6,
    "Nx": 1799,
    "Ny": 1059,
    "DxInMetres": 3000.0,
    "DyInMetres": 3000.0,
    "Latin1InDegrees": 38.5,
    "Latin2InDegrees": 38.5,
    "LoVInDegrees": 262.5,
    "latitudeOfFirstGridPoint": 21138000,
    "longitudeOfFirstGridPoint": 237280000,
}


class _FakeEccodes:
    """The two eccodes calls ``from_message`` makes, on a dict standing for a message."""

    @staticmethod
    def codes_get(gid, key):
        if key not in gid:
            raise RuntimeError(f"Key/value not found: {key}")
        return gid[key]


def test_longitudes_are_wrapped_to_minus_180_180_only_where_outside():
    assert wrap_longitude(262.5) == -97.5
    assert wrap_longitude(-122.72) == -122.72
    assert wrap_longitude(-380.5) == -20.5
    assert np.array_equal(wrap_longitude(np.array([190.0, -10.0])), [-170.0, -10.0])


def test_parameters_of_a_message_wrap_lov_and_keep_the_precision_of_the_file():
    parameters = LambertParameters.from_message(_FakeEccodes, NAM_MESSAGE)

    assert parameters.lon_0 == -97.5
    assert (parameters.lat_first, parameters.lon_first) == (21.138, -122.72)
    assert (parameters.nx, parameters.ny, parameters.radius) == (1799, 1059, 6371229.0)


def test_a_grid_given_with_lov_in_0_360_rotates_winds_as_the_same_grid_in_minus_180_180():
    # Unwrapped, the angle at 118 W would be off by 360 sin(38.5) degrees, about 224.
    parameters = LambertParameters.from_message(_FakeEccodes, NAM_MESSAGE)
    nam = LambertGrid(parameters)
    hrrr = HRRRGrid()
    lon = np.array([-118.2, -120.0, -75.0])
    u, v = np.array([3.0, -2.0, 1.0]), np.array([1.0, 4.0, -2.0])

    assert np.allclose(nam.rotate_winds_to_earth(u, v, lon), hrrr.rotate_winds_to_earth(u, v, lon))
    assert np.allclose(nam.rotate_winds_to_earth(u, v, lon + 360.0), hrrr.rotate_winds_to_earth(u, v, lon))


def test_the_nam_nest_differs_from_hrrr_only_by_the_rounding_of_its_first_point():
    parameters = LambertParameters.from_message(_FakeEccodes, NAM_MESSAGE)

    assert "lat_first" in parameters.mismatch(HRRR_PARAMETERS)
    assert parameters.mismatch(HRRR_PARAMETERS, tolerance_deg=1e-3) is None
    i, j = LambertGrid(parameters).ij_arrays_from_latlon([44.85], [-118.2])
    hrrr_i, hrrr_j = HRRRGrid().ij_arrays_from_latlon([44.85], [-118.2])
    # 0.0005 degrees of longitude is about 50 m, a sixtieth of a cell.
    assert abs(i[0] - hrrr_i[0]) < 0.02 and abs(j[0] - hrrr_j[0]) < 0.02


def test_a_message_on_another_grid_type_scan_order_or_earth_is_refused():
    with pytest.raises(ValueError, match="expected a Lambert conformal grid"):
        LambertParameters.from_message(_FakeEccodes, {**NAM_MESSAGE, "gridType": "regular_ll"})
    with pytest.raises(ValueError, match="expected \\(0, 1, 0\\)"):
        LambertParameters.from_message(_FakeEccodes, {**NAM_MESSAGE, "jScansPositively": 0})
    ellipsoid = {key: value for key, value in NAM_MESSAGE.items() if key != "radius"}
    with pytest.raises(ValueError, match="is not a sphere"):
        LambertParameters.from_message(_FakeEccodes, {**ellipsoid, "shapeOfTheEarth": 7})


def test_a_mismatch_names_every_parameter_that_differs():
    parameters = LambertParameters.from_message(
        _FakeEccodes, {**NAM_MESSAGE, "Nx": 1800, "DxInMetres": 2500.0}
    )

    problem = parameters.mismatch(HRRR_PARAMETERS, tolerance_deg=1e-3)

    assert "nx 1800 (expected 1799)" in problem and "dx 2500.0" in problem


def test_the_hrrr_grid_is_the_shared_lambert_grid_with_hrrr_parameters():
    shared = LambertGrid(HRRR_PARAMETERS)
    hrrr = HRRRGrid()
    lat, lon = np.array([38.7, 21.138123, 47.8]), np.array([-120.3, -122.719528, -70.0])

    assert all(
        np.array_equal(a, b)
        for a, b in zip(shared.ij_arrays_from_latlon(lat, lon), hrrr.ij_arrays_from_latlon(lat, lon))
    )
    assert hrrr.ij_from_latlon(21.138123, -122.719528) == (0, 0)
    assert hrrr.cone_constant == pytest.approx(math.sin(math.radians(38.5)))


def test_a_secant_cone_has_snyders_constant_and_round_trips():
    # Snyder, Map Projections: A Working Manual, p. 296: standard parallels 33 and 45 N, n = 0.6304777.
    secant = LambertGrid(
        LambertParameters(
            nx=1000,
            ny=800,
            dx=5000.0,
            dy=5000.0,
            lat_1=33.0,
            lat_2=45.0,
            lon_0=-96.0,
            lat_first=20.0,
            lon_first=-120.0,
            radius=6371229.0,
        )
    )

    assert secant.cone_constant == pytest.approx(0.6304777, abs=1e-7)
    assert secant.ij_from_latlon(20.0, -120.0) == (0, 0)
    lat, lon = secant.latlon_from_ij(412.5, 377.25)
    i, j = secant.ij_arrays_from_latlon([lat], [lon])
    assert (i[0], j[0]) == pytest.approx((412.5, 377.25))
    assert float(secant.wind_rotation_angle(-96.0)) == 0.0
