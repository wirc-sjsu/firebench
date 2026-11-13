from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np
import pytest
from click.testing import CliRunner

from firebench import standardize as fs
from firebench.acquisition.hrrr import forecast as hrrr_forecast
from firebench.adapters import hrrr_weather
from firebench.cli import main
from firebench.standardize.files import new_std_file
from firebench.workflows import wx_stitch
from firebench.workflows.wx_stitch import StitchError, stitch_plan, stitch_station_files

UTC = timezone.utc
START = datetime(2021, 8, 20, 3, 45, tzinfo=UTC)
END = datetime(2021, 8, 22, 4, 15, tzinfo=UTC)


def _hours(plan):
    return [
        segment.cycle + timedelta(hours=lead)
        for segment in plan.segments
        for lead in range(segment.first_lead, segment.last_lead + 1)
    ]


# --- The plan -------------------------------------------------------------------------------------


def test_the_freshest_rule_takes_each_hour_from_the_latest_cycle():
    plan = stitch_plan("HRRR", START, END, [0, 6, 12, 18], [1, 6])

    assert len(plan.segments) == 9
    first, last = plan.segments[0], plan.segments[-1]
    assert (first.cycle, first.first_lead, first.last_lead) == (datetime(2021, 8, 20, tzinfo=UTC), 3, 6)
    assert (last.cycle, last.first_lead, last.last_lead) == (datetime(2021, 8, 22, tzinfo=UTC), 1, 5)
    hours = _hours(plan)
    # Every hour from the one before the start to the one after the end, each once.
    assert hours[0] == datetime(2021, 8, 20, 3, tzinfo=UTC) and hours[-1] == datetime(
        2021, 8, 22, 5, tzinfo=UTC
    )
    assert all(later - earlier == timedelta(hours=1) for earlier, later in zip(hours, hours[1:]))
    # f00 for the terrain and the leads used; HRRR's measured sizes.
    assert first.forecast_hours == (0, 3, 4, 5, 6)
    leads = sum(segment.last_lead - segment.first_lead + 1 for segment in plan.segments)
    assert plan.download_mb == round(9 * 11.6 + leads * 9.4, 1)


def test_the_day_ahead_rule_takes_leads_25_to_48_of_the_00z_cycle():
    plan = stitch_plan("HRRR", START, END, [0], [25, 48])

    assert [(s.cycle.day, s.first_lead, s.last_lead) for s in plan.segments] == [
        (19, 27, 48),
        (20, 25, 48),
        (21, 25, 29),
    ]
    assert plan.as_dict()["rule"] == {"cycle_hours": [0], "leads": [25, 48]}


def test_a_rule_whose_leads_do_not_reach_the_next_cycle_is_refused():
    with pytest.raises(StitchError, match="the leads must span the time between two cycles"):
        stitch_plan("HRRR", START, END, [0], [1, 6])


def test_a_cycle_the_archive_does_not_hold_is_refused_with_firebench_reason():
    with pytest.raises(StitchError, match="older than the first cycle of its archive"):
        stitch_plan("NAM", START, END, [0, 6, 12, 18], [1, 6])


def test_a_lead_beyond_the_cycle_horizon_is_refused():
    # HRRR's 03Z cycles reach 18 h.
    with pytest.raises(StitchError, match="reaches 18 h"):
        stitch_plan("HRRR", START, END, [3], [20, 43])


def test_a_period_without_time_zone_or_ending_first_is_refused():
    with pytest.raises(StitchError, match="no time zone"):
        stitch_plan("HRRR", START.replace(tzinfo=None), END, [0], [25, 48])
    with pytest.raises(StitchError, match="before it starts"):
        stitch_plan("HRRR", END, START, [0], [25, 48])


# --- The stitch -----------------------------------------------------------------------------------

STATION = "station_AAA"
OBS_ORIGIN = datetime(2021, 8, 20, tzinfo=UTC)


def _obs_file(path: Path, minutes: np.ndarray) -> Path:
    with new_std_file(str(path), "tests", overwrite=True) as h5:
        group = h5.create_group(f"time_series/{STATION}")
        group.attrs["position_lat"], group.attrs["position_lon"] = 38.7, -120.5
        time = group.create_dataset("time", data=minutes.astype(float))
        time.attrs["time_origin"] = OBS_ORIGIN.isoformat()
        time.attrs["time_units"] = "min"
        for variable, units in (
            ("air_temperature", "K"),
            ("wind_direction", "degree"),
            ("fuel_moisture_content_10h", "percent"),
        ):
            data = group.create_dataset(variable, data=np.ones(minutes.size))
            data.attrs["units"] = units
    return path


def _segment_file(path: Path, cycle: datetime, values: dict, height=2.0) -> Path:
    """A station file of one cycle: ``values`` maps a variable to its value at each forecast hour."""
    hours = len(next(iter(values.values())))
    with new_std_file(str(path), "tests", overwrite=True) as h5:
        h5.attrs["hrrr_version"] = "4"
        group = h5.create_group(f"time_series/{STATION}")
        group.attrs["position_lat"], group.attrs["position_lon"] = 38.7, -120.5
        group.attrs["terrain_height_difference"] = 12.0
        time = group.create_dataset("time", data=3600.0 * np.arange(hours))
        time.attrs["time_origin"] = cycle.isoformat()
        time.attrs["time_units"] = "s"
        for variable, series in values.items():
            data = group.create_dataset(variable, data=np.asarray(series, dtype=float))
            data.attrs["units"] = "K" if variable == "air_temperature" else "degree"
            data.attrs["sensor_height"] = height
            data.attrs["sensor_height_units"] = "m"
    return path


@pytest.fixture
def small_plan():
    # 01:00 to 11:00: the 00Z cycle gives 01-06, the 06Z cycle 07-12.
    return stitch_plan(
        "HRRR",
        datetime(2021, 8, 20, 1, tzinfo=UTC),
        datetime(2021, 8, 20, 11, tzinfo=UTC),
        [0, 6, 12, 18],
        [1, 6],
    )


def _segments(tmp_path, small_plan, **changes):
    c00, c06 = (segment.cycle for segment in small_plan.segments)
    temperature_00 = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]  # f00..f06: one degree an hour
    temperature_06 = [100.0, 7.0, 8.0, 9.0, 10.0, 11.0]  # f00 is not used
    direction_00 = [0.0, 0.0, 0.0, 0.0, 0.0, 340.0, 350.0]
    direction_06 = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    return {
        "2021082000": _segment_file(
            tmp_path / "a.h5", c00, {"air_temperature": temperature_00, "wind_direction": direction_00}
        ),
        "2021082006": _segment_file(
            tmp_path / "b.h5",
            c06,
            {"air_temperature": temperature_06, "wind_direction": direction_06},
            **changes,
        ),
    }


def test_the_series_is_joined_and_brought_to_the_observation_times_of_the_period(tmp_path, small_plan):
    # Observations every 30 min from 00:00 to 12:00: the period keeps 01:00 to 11:00.
    obs = _obs_file(tmp_path / "obs.h5", np.arange(0, 721, 30))
    out = tmp_path / "stitched.h5"

    summary = stitch_station_files(small_plan, _segments(tmp_path, small_plan), obs, out, name="HRRR test")

    assert summary["stations"] == 1 and summary["samples"] == 21
    assert summary["not_forecast"] == {"fuel_moisture_content_10h": 1}
    with h5py.File(out, "r") as h5:
        fs.validate_h5_std(h5)
        group = h5[f"time_series/{STATION}"]
        np.testing.assert_array_equal(group["time"][:], np.arange(60, 661, 30))
        # Linear between the hourly values: 00Z gives 1..6, 06Z gives 7..11.
        np.testing.assert_allclose(group["air_temperature"][:], np.arange(1.0, 11.01, 0.5))
        # 350 at 06:00 and 10 at 07:00 (from the next cycle): 0 between, not 180.
        direction = group["wind_direction"][:]
        assert direction[11] == pytest.approx(0.0, abs=1e-9) or direction[11] == pytest.approx(360.0)
        assert group["air_temperature"].attrs["sensor_height"] == 2.0
        assert group.attrs["terrain_height_difference"] == 12.0
        assert np.all(np.isnan(group["fuel_moisture_content_10h"][:]))
        assert "does not forecast" in group["fuel_moisture_content_10h"].attrs[wx_stitch.NOT_FORECAST]
        assert h5.attrs["model_name"] == "HRRR test"
        assert "linear in time" in h5.attrs["time_interpolation"]
        assert '"leads": [1, 6]' in h5.attrs["stitch_plan"]
        assert '"2021082006": "4"' in h5.attrs["stitch_model_versions"]


def test_cycles_that_declare_other_heights_are_refused(tmp_path, small_plan):
    obs = _obs_file(tmp_path / "obs.h5", np.arange(0, 721, 30))
    with pytest.raises(StitchError, match="another height or unit"):
        stitch_station_files(
            small_plan, _segments(tmp_path, small_plan, height=6.1), obs, tmp_path / "out.h5"
        )
    assert not (tmp_path / "out.h5").exists()


def test_a_missing_segment_or_hour_is_refused(tmp_path, small_plan):
    obs = _obs_file(tmp_path / "obs.h5", np.arange(0, 721, 30))
    files = _segments(tmp_path, small_plan)
    with pytest.raises(StitchError, match="no station file for cycle 2021082006"):
        stitch_station_files(small_plan, {"2021082000": files["2021082000"]}, obs, tmp_path / "out.h5")

    c06 = small_plan.segments[1].cycle
    files["2021082006"] = _segment_file(
        tmp_path / "short.h5", c06, {"air_temperature": [0.0, 7.0, 8.0], "wind_direction": [0.0] * 3}
    )
    with pytest.raises(StitchError, match="not the 11 consecutive hours"):
        stitch_station_files(small_plan, files, obs, tmp_path / "out.h5")


# --- The download ---------------------------------------------------------------------------------


def _fake_read(path):
    fxx = int(Path(path).stem)
    return {
        hrrr_weather.TEMPERATURE: _Field(290.0 + fxx),
        hrrr_weather.HUMIDITY: _Field(40.0),
        hrrr_weather.WIND_U: _Field(0.0),
        hrrr_weather.WIND_V: _Field(5.0),
        hrrr_weather.ROUGHNESS: _Field(0.1),
        **({hrrr_weather.TERRAIN: _Field(1500.0)} if fxx == 0 else {}),
    }


class _Field:
    def __init__(self, value):
        self.value = value

    def __getitem__(self, index):
        return np.full(np.shape(index[1]), self.value, dtype=float)


def _adapter_obs(path: Path) -> Path:
    with h5py.File(path, "w") as h5:
        h5.attrs["FireBench_io_version"] = "1.0"
        h5.attrs["created_on"] = "2026-11-09T12:00:00+00:00"
        h5.attrs["created_by"] = "tests"
        group = h5.create_group(f"time_series/{STATION}")
        group.attrs["position_lat"], group.attrs["position_lon"] = 38.7, -120.5
        group.attrs["position_alt"], group.attrs["position_alt_units"] = 4921.26, "ft"
        time = group.create_dataset("time", data=[0.0, 60.0])
        time.attrs["time_origin"], time.attrs["time_units"] = OBS_ORIGIN.isoformat(), "min"
        for variable, height in (("air_temperature", 2.0), ("wind_speed", 6.1)):
            data = group.create_dataset(variable, data=[1.0, 2.0])
            data.attrs["units"] = hrrr_weather.VARIABLE_UNITS[variable]
            data.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = height
            data.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
            data.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = int(fs.SH_TRUST_HIGHEST)
    return path


def test_a_segment_downloads_f00_and_its_leads_then_deletes_them(tmp_path, monkeypatch, small_plan):
    asked = []

    def fake_fetch(cycle, fxx, fields=None, cache_root=None):
        asked.append(fxx)
        path = tmp_path / "cache" / f"{fxx}.grib2"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"grib")
        return path

    monkeypatch.setattr(hrrr_forecast, "fetch_file", fake_fetch)
    segment = small_plan.segments[1]  # 06Z, leads 1-5
    summary = wx_stitch.fetch_segment(
        "HRRR", segment, _adapter_obs(tmp_path / "obs.h5"), tmp_path / "seg.h5", read=_fake_read
    )

    assert sorted(asked) == [0, 1, 2, 3, 4, 5]
    assert summary["forecast_hours"] == [0, 1, 2, 3, 4, 5]
    assert not list((tmp_path / "cache").iterdir())
    with h5py.File(tmp_path / "seg.h5", "r") as h5:
        np.testing.assert_allclose(h5[f"time_series/{STATION}/air_temperature"][:], 290.0 + np.arange(6))


def test_a_segment_missing_from_the_archive_is_refused_and_cleaned(tmp_path, monkeypatch, small_plan):
    def fake_fetch(cycle, fxx, fields=None, cache_root=None):
        if fxx == 3:
            raise FileNotFoundError("not in the archive")
        path = tmp_path / f"{fxx}.grib2"
        path.write_bytes(b"grib")
        return path

    monkeypatch.setattr(hrrr_forecast, "fetch_file", fake_fetch)
    with pytest.raises(StitchError, match=r"lacks forecast hour\(s\) \[3\]"):
        wx_stitch.fetch_segment(
            "HRRR",
            small_plan.segments[1],
            _adapter_obs(tmp_path / "obs.h5"),
            tmp_path / "seg.h5",
            read=_fake_read,
        )
    assert not list(tmp_path.glob("*.grib2"))


# --- The command ----------------------------------------------------------------------------------


def test_the_command_prints_the_plan_of_a_caldor_period(tmp_path):
    obs = _obs_file(tmp_path / "obs.h5", np.arange(0, 60, 10))
    result = CliRunner().invoke(
        main,
        [
            "wx",
            "stitch",
            "HRRR",
            str(tmp_path / "out.h5"),
            "--obs-data",
            str(obs),
            "--case",
            "2021_Caldor",
            "--period",
            "P02",
            "--plan-only",
            "-v",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "HRRR over 2021-08-20 03:45Z to 2021-08-22 04:15Z: 9 cycles" in result.output
    assert "2021-08-22 00Z  leads 1-5 h" in result.output


def test_the_command_reports_a_refused_rule(tmp_path):
    obs = _obs_file(tmp_path / "obs.h5", np.arange(0, 60, 10))
    result = CliRunner().invoke(
        main,
        [
            "wx",
            "stitch",
            "HRRR",
            str(tmp_path / "out.h5"),
            "--obs-data",
            str(obs),
            "--start",
            "2021-08-20T03:00Z",
            "--end",
            "2021-08-21T03:00Z",
            "--cycle-hours",
            "0",
            "--leads",
            "1-6",
            "--plan-only",
        ],
    )
    assert result.exit_code != 0
    assert "the leads must span the time between two cycles" in result.output
