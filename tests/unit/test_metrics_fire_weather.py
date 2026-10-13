import numpy as np
import pytest

from firebench.metrics import fire_weather

MPH = 1609.344 / 3600.0  # m/s


@pytest.mark.parametrize(
    "air_temperature, tabulated",
    [
        # Goff-Gratch values over water, which the formula follows within 0.2 % in this range
        (0.0, 6.11),
        (20.0, 23.37),
        (35.0, 56.24),
    ],
)
def test_saturation_vapor_pressure_follows_the_tabulated_values(air_temperature, tabulated):
    assert fire_weather.saturation_vapor_pressure(air_temperature) == pytest.approx(tabulated, rel=2e-3)


def test_vapor_pressure_deficit_is_the_share_of_saturation_the_air_lacks():
    saturation = fire_weather.saturation_vapor_pressure(30.0)

    assert fire_weather.vapor_pressure_deficit(30.0, 100.0) == pytest.approx(0.0, abs=1e-12)
    assert fire_weather.vapor_pressure_deficit(30.0, 0.0) == pytest.approx(saturation)
    assert fire_weather.vapor_pressure_deficit(30.0, 20.0) == pytest.approx(0.8 * saturation)


@pytest.mark.parametrize(
    "relative_humidity, expected",
    [
        # 20 degC is 68 degF; one value in each of the three humidity ranges of Simard (1968)
        (5.0, 0.03229 + 0.281073 * 5 - 0.000578 * 5 * 68),
        (30.0, 2.22749 + 0.160107 * 30 - 0.01478 * 68),
        (80.0, 21.0606 + 0.005565 * 80**2 - 0.00035 * 80 * 68 - 0.483199 * 80),
    ],
)
def test_equilibrium_moisture_content_uses_the_range_of_the_humidity(relative_humidity, expected):
    assert fire_weather.equilibrium_moisture_content(20.0, relative_humidity) == pytest.approx(expected)


def test_fosberg_index_of_a_hot_dry_windy_hour():
    # 90 degF, 10 %, 20 mph: moisture 2.498 %, damping 0.8436, index 0.8436 * sqrt(401) / 0.3002
    index = fire_weather.fosberg_fire_weather_index((90.0 - 32.0) / 1.8, 10.0, 20.0 * MPH)

    assert index == pytest.approx(56.27, abs=0.01)


def test_fosberg_index_grows_with_wind_and_falls_with_humidity():
    calm, windy = fire_weather.fosberg_fire_weather_index(30.0, 15.0, np.array([1.0, 10.0]))
    dry, moist = fire_weather.fosberg_fire_weather_index(30.0, np.array([10.0, 70.0]), 5.0)

    assert windy > calm
    assert dry > moist


def test_a_missing_input_gives_a_missing_value():
    values = fire_weather.fosberg_fire_weather_index(
        np.array([30.0, np.nan, 30.0]), np.array([20.0, 20.0, np.nan]), np.array([5.0, 5.0, 5.0])
    )
    deficit = fire_weather.vapor_pressure_deficit(np.array([np.nan, 30.0]), np.array([20.0, 20.0]))

    assert np.isfinite(values).tolist() == [True, False, False]
    assert np.isfinite(deficit).tolist() == [False, True]
