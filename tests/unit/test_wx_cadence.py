from datetime import datetime, timedelta, timezone

import h5py
import numpy as np
import pytest

from firebench import standardize as fs
from firebench.benchmarks import wx_cadence

UTC = timezone.utc
CYCLE = datetime(2021, 8, 20, 0, tzinfo=UTC)


def _mae(model, obs):
    return float(np.mean(np.abs(model - obs)))


def _add_station(
    h5, name, minutes, values, *, variable="air_temperature", units="degC", height=2.0, trusted=True
):
    station = h5.require_group(f"time_series/station_{name}")
    time = station.create_dataset("time", data=np.asarray(minutes, dtype=float))
    time.attrs["time_origin"] = CYCLE.isoformat()
    time.attrs["time_units"] = "min"
    data = station.create_dataset(variable, data=np.asarray(values, dtype=float))
    data.attrs["units"] = units
    data.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = height
    data.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
    data.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = int(fs.SH_TRUST_HIGHEST if trusted else 0)


def _hourly_model(h5, name, hours, values, **kwargs):
    _add_station(h5, name, [60 * hour for hour in hours], values, **kwargs)


def _run(
    tmp_path,
    build_obs,
    build_model,
    *,
    lead=(1, 3),
    cadence=1,
    tolerance_s=600,
    variable="air_temperature",
    units="degC",
    min_coverage=0.5,
    ctx=None,
):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"
    with h5py.File(obs_path, "w") as obs_h5:
        build_obs(obs_h5)
    with h5py.File(model_path, "w") as model_h5:
        build_model(model_h5)
    lead_window = (CYCLE + timedelta(hours=lead[0]), CYCLE + timedelta(hours=lead[1]))
    ctx = {} if ctx is None else ctx
    with h5py.File(model_path, "r") as model_h5, h5py.File(obs_path, "r") as obs_h5:
        return wx_cadence.bench_wx_cadence_index(
            model_h5,
            obs_h5,
            ctx,
            kpi_name_custom="KPI",
            lead_window=lead_window,
            period=wx_cadence.expand_window(lead_window, tolerance_s),
            wx_variable_name=variable,
            common_unit=units,
            metric_func=_mae,
            stat_func=np.nanmean,
            value_norm_param_m=5,
            station_set=fs.WeatherStationSet.TSO,
            cadence_hours=cadence,
            obs_tolerance_s=tolerance_s,
            min_coverage=min_coverage,
        )


def test_mandatory_timestamps_are_utc_top_of_hour_marks_inside_the_window():
    pacific = timezone(timedelta(hours=-7))
    window = (datetime(2021, 8, 19, 17, 10, tzinfo=pacific), datetime(2021, 8, 20, 3, 0, tzinfo=UTC))

    marks = wx_cadence.mandatory_timestamps(window, 1)

    assert marks[0] == np.datetime64("2021-08-20T01:00:00")
    assert marks[-1] == np.datetime64("2021-08-20T03:00:00")
    assert marks.size == 3


def test_three_hourly_marks_are_anchored_to_utc_midnight():
    marks = wx_cadence.mandatory_timestamps((CYCLE + timedelta(hours=1), CYCLE + timedelta(hours=12)), 3)

    assert [str(mark)[11:13] for mark in marks] == ["03", "06", "09", "12"]


def test_analysis_window_has_a_single_mark():
    assert wx_cadence.mandatory_timestamps((CYCLE, CYCLE), 1).tolist() == [CYCLE.replace(tzinfo=None)]


def test_match_nearest_prefers_the_closest_finite_sample_and_the_earlier_on_ties():
    base = np.datetime64("2021-08-20T00:00:00")
    times = base + np.array([-300, 240, 300, 3000, 3900], dtype="timedelta64[s]")
    values = np.array([1.0, np.nan, 3.0, 4.0, 5.0])
    targets = base + np.array([0, 3600], dtype="timedelta64[s]")

    index = wx_cadence.match_nearest(times, targets, 600, values)

    # t=0: +240 s is closest but NaN; -300 s and +300 s tie -> the earlier one
    # t=3600: -600 s (at 3000) and +300 s (at 3900) -> the closer one
    assert index.tolist() == [0, 4]


def test_match_nearest_returns_minus_one_outside_the_tolerance():
    base = np.datetime64("2021-08-20T00:00:00")

    index = wx_cadence.match_nearest(
        base + np.array([36 * 60], dtype="timedelta64[s]"), np.array([base]), 600
    )

    assert index.tolist() == [-1]


@pytest.mark.parametrize("tolerance_s", (1800, 3600, -1))
def test_tolerance_must_be_below_half_the_cadence(tolerance_s):
    with pytest.raises(ValueError, match="half the 1 h cadence|below half"):
        wx_cadence.check_tolerance(tolerance_s, 1)


def test_exact_hour_station_is_scored_on_every_mark(tmp_path):
    result = _run(
        tmp_path,
        lambda h5: _add_station(h5, "A", [60, 120, 180], [10.0, 11.0, 12.0]),
        lambda h5: _hourly_model(h5, "A", [1, 2, 3], [11.0, 12.0, 13.0]),
    )

    assert result["KPI"] == pytest.approx(1.0)


def test_station_reporting_at_51_minutes_is_matched_to_the_next_hour(tmp_path):
    result = _run(
        tmp_path,
        lambda h5: _add_station(h5, "A", [51, 111, 171], [10.0, 11.0, 12.0]),
        lambda h5: _hourly_model(h5, "A", [1, 2, 3], [10.0, 11.0, 12.0]),
    )

    assert result["KPI"] == pytest.approx(0.0)


def test_station_reporting_at_36_minutes_is_never_matched_and_excluded(tmp_path):
    ctx = {}

    result = _run(
        tmp_path,
        lambda h5: _add_station(h5, "A", [36, 96, 156], [10.0, 11.0, 12.0]),
        lambda h5: _hourly_model(h5, "A", [1, 2, 3], [10.0, 11.0, 12.0]),
        ctx=ctx,
    )

    assert result is None
    (exclusion,) = ctx["cadence_exclusions"].values()
    assert exclusion["matched_timestamps"] == 0
    assert exclusion["mandatory_timestamps"] == 3


def test_nan_observation_falls_back_to_the_next_nearest_finite_value(tmp_path):
    result = _run(
        tmp_path,
        lambda h5: _add_station(h5, "A", [60, 65, 120, 180], [np.nan, 10.0, 11.0, 12.0]),
        lambda h5: _hourly_model(h5, "A", [1, 2, 3], [10.0, 11.0, 12.0]),
    )

    assert result["KPI"] == pytest.approx(0.0)


def test_hourly_model_is_joined_to_ten_minute_observations(tmp_path):
    minutes = np.arange(0, 181, 10)

    result = _run(
        tmp_path,
        lambda h5: _add_station(h5, "A", minutes, minutes / 10.0),
        lambda h5: _hourly_model(h5, "A", [0, 1, 2, 3], [0.0, 7.0, 12.0, 20.0]),
    )

    # marks 1, 2, 3 h pair obs 6, 12, 18 with model 7, 12, 20
    assert result["KPI"] == pytest.approx((1.0 + 0.0 + 2.0) / 3)


def test_missing_model_mark_is_penalized(tmp_path):
    result = _run(
        tmp_path,
        lambda h5: _add_station(h5, "A", [60, 120, 180], [10.0, 11.0, 12.0]),
        lambda h5: _hourly_model(h5, "A", [1, 3], [10.0, 12.0]),
    )

    assert result["KPI"] == pytest.approx((11.0 - wx_cadence.PENALTY_VALUE) / 3)
    assert result["Score"] == pytest.approx(0.0, abs=1e-9)


def test_wind_direction_nan_is_penalized_as_the_opposite_direction(tmp_path):
    captured = {}

    def capture(model, obs):
        captured["model"] = model.copy()
        return 0.0

    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"
    with h5py.File(obs_path, "w") as h5:
        _add_station(
            h5, "A", [60, 120], [350.0, 10.0], variable="wind_direction", units="degree", height=6.1
        )
    with h5py.File(model_path, "w") as h5:
        _hourly_model(
            h5, "A", [1, 2], [np.nan, 20.0], variable="wind_direction", units="degree", height=6.1
        )
    window = (CYCLE + timedelta(hours=1), CYCLE + timedelta(hours=2))
    with h5py.File(model_path, "r") as model_h5, h5py.File(obs_path, "r") as obs_h5:
        wx_cadence.bench_wx_cadence_index(
            model_h5,
            obs_h5,
            {},
            kpi_name_custom="WD",
            lead_window=window,
            period=wx_cadence.expand_window(window, 600),
            wx_variable_name="wind_direction",
            common_unit="degree",
            metric_func=capture,
            stat_func=np.nanmean,
            value_norm_param_m=45,
            station_set=fs.WeatherStationSet.TSO,
            cadence_hours=1,
        )

    assert captured["model"].tolist() == pytest.approx([170.0, 20.0])


def test_coverage_floor_excludes_sparse_stations_but_keeps_others(tmp_path):
    ctx = {}

    def obs(h5):
        _add_station(h5, "DENSE", [60, 120, 180], [10.0, 11.0, 12.0])
        _add_station(h5, "SPARSE", [60, 150], [10.0, 99.0])

    def model(h5):
        _hourly_model(h5, "DENSE", [1, 2, 3], [11.0, 12.0, 13.0])
        _hourly_model(h5, "SPARSE", [1, 2, 3], [0.0, 0.0, 0.0])

    result = _run(tmp_path, obs, model, min_coverage=0.5, ctx=ctx)

    assert result["KPI"] == pytest.approx(1.0)
    assert [item["station"] for item in ctx["cadence_exclusions"].values()] == ["station_SPARSE"]


def test_analysis_window_matches_off_hour_observation_within_tolerance(tmp_path):
    result = _run(
        tmp_path,
        lambda h5: _add_station(h5, "A", [-8, 52], [15.0, 16.0]),
        lambda h5: _hourly_model(h5, "A", [0, 1], [14.0, 16.0]),
        lead=(0, 0),
    )

    assert result["KPI"] == pytest.approx(1.0)


def test_untrusted_station_is_not_scored_in_the_tso_set(tmp_path):
    result = _run(
        tmp_path,
        lambda h5: _add_station(h5, "A", [60, 120, 180], [10.0, 11.0, 12.0], trusted=False),
        lambda h5: _hourly_model(h5, "A", [1, 2, 3], [10.0, 11.0, 12.0]),
    )

    assert result is None


def test_absolute_time_encoding_is_supported(tmp_path):
    path = tmp_path / "abs.h5"
    with h5py.File(path, "w") as h5:
        station = h5.create_group("time_series/station_A")
        station.create_dataset("time", data=[b"2021-08-19T17:00:00-07:00", b"2021-08-20T01:00:00+00:00"])
    with h5py.File(path, "r") as h5:
        times = wx_cadence.station_times_utc(h5, "time_series/station_A")

    assert times.tolist() == [datetime(2021, 8, 20, 0), datetime(2021, 8, 20, 1)]
