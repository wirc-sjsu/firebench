import firebench.sensors as fbs
import numpy as np
import pytest


### z_from_cl
@pytest.mark.parametrize(
    ("cl", "z_expected"),
    [
        (0.683, 1.0006418287624494),
        (0.955, 2.0046544617650968),
        (0.99731, 3.001107025793382),
    ],
)
def test_z_from_cl_known_values(cl: float, z_expected: float):
    assert fbs.z_from_cl(cl) == pytest.approx(z_expected, rel=1e-12, abs=0.0)


### CS506_cl
@pytest.mark.parametrize(
    "fmc, cl, age, expected_value",
    [
        (0, 68, None, 0.7557879912394126),
        (0, 95, None, 1.4895726282504427),
        (10, 68, None, 1.2132386175158991),
        (10, 95, None, 2.3911560611388682),
        (20, 68, None, 2.0585278182441895),
        (20, 95, None, 4.057125447997915),
        (30, 68, None, 2.4861447080243835),
        (30, 95, None, 4.89990996135014),
        (50, 68, None, 2.4861447080243835),
        (50, 95, None, 4.89990996135014),
    ],
)
def test_CS506_cl(fmc, cl, age, expected_value):
    result = fbs.CS506_cl(fmc, cl, age)
    assert np.isclose(
        result, expected_value, rtol=1e-5
    ), f"Failed for {fmc=}, {cl=}, {age=}. expected {expected_value}, got {result}"


def test_CS506_cl_array():
    fmc_input = np.array([10, 20, 30, 50])
    expected = np.array([1.2132386175158991, 2.0585278182441895, 2.4861447080243835, 2.4861447080243835])
    result = fbs.CS506_cl(fmc_input, 68)
    for i in range(4):
        assert np.isclose(
            result[i], expected[i], rtol=1e-5
        ), f"Failed for {fmc_input[i]=}, 68. expected {expected[i]}, got {result}"


### CS505_cl
@pytest.mark.parametrize(
    "fmc, cl, age, expected_value",
    [
        (0, 68, None, 1.2132386175158991),
        (0, 95, None, 2.3911560611388682),
        (10, 68, None, 1.8099133474417515),
        (10, 95, None, 3.567134451862902),
        (20, 68, None, 3.0231519649576506),
        (20, 95, None, 5.958290513001771),
        (30, 68, None, 3.6297712737156003),
        (30, 95, None, 7.153868543571204),
        (50, 68, None, 3.6297712737156003),
        (50, 95, None, 7.153868543571204),
    ],
)
def test_CS505_cl(fmc, cl, age, expected_value):
    result = fbs.CS505_cl(fmc, cl, age)
    assert np.isclose(
        result, expected_value, rtol=1e-5
    ), f"Failed for {fmc=}, {cl=}, {age=}. expected {expected_value}, got {result}"


def test_CS505_cl_array():
    fmc_input = np.array([10, 20, 30, 50])
    expected = np.array([1.8099133474417515, 3.0231519649576506, 3.6297712737156003, 3.6297712737156003])
    result = fbs.CS505_cl(fmc_input, 68)
    for i in range(4):
        assert np.isclose(
            result[i], expected[i], rtol=1e-5
        ), f"Failed for {fmc_input[i]=}, 68. expected {expected[i]}, got {result}"
