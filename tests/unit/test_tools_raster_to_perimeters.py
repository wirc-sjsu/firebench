import warnings

import firebench.tools as ft
import numpy as np
import pytest


# array_to_geopolygons
# --------------------
def test_array_to_geopolygons():
    """
    Define a synthetic field with three circular regions:
    - a large outer circle
    - a smaller inner circle forming a hole
    - a third, smaller circle acting as an island inside the hole

    This tests that `array_to_geopolygons` correctly identifies nested contours and constructs
    valid polygons with holes and interior islands.

    Note:
    Area calculations in EPSG:4326 (degrees) are not physically meaningful, but are acceptable
    here for relative validation of the geometric extraction. The CRS warning is ignored intentionally
    because this is a geometry/topology test rather than a true area measurement test.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Geometry is in a geographic CRS*")
        N_x = 1000
        N_y = 1000

        lon2, lat2 = np.meshgrid(np.linspace(-10, 10, N_x),  np.linspace(-10, 10, N_y))

        r1 = 8
        r2 = 3
        r3 = 1

        r = np.sqrt((lon2) ** 2 + lat2**2)
        field = (r - r2) * (r - r1) * (r + r1) * (r + r2) * (r-r3)
        theoretical_area = np.pi*(r1**2 - r2**2 + r3**2)


        final_polygons = ft.array_to_geopolygons(field, lon2, lat2, 0, original_crs="EPSG:4326")
        polygon_area = sum(final_polygons.area) 
        print(polygon_area, theoretical_area)
        assert abs(polygon_area - theoretical_area) < 5e-3

def test_array_to_geopolygons_shape_mismatch():
    field = np.ones((10, 10))
    lon = np.ones((10, 10))
    lat = np.ones((8, 10))  # wrong shape
    with pytest.raises(ValueError, match="must have the same shape"):
        ft.array_to_geopolygons(field, lon, lat, 0)

def test_array_to_geopolygons_smoothing():
    N = 50
    lon, lat = np.meshgrid(np.linspace(-10, 10, N), np.linspace(-10, 10, N))
    field = (np.sqrt(lon**2 + lat**2) - 5)  # circular contour at 5

    # adding a sharp feature that will get smoothed
    field[N//2, N//2] = 100

    geopoly = ft.array_to_geopolygons(field, lon, lat, iso_value=0, smooth_sigma=1)

    assert not geopoly.empty
    assert geopoly.geometry.iloc[0].is_valid
