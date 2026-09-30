"""End-to-end `firebench wx` workflow, offline: saved Synoptic JSON, faked HRRR downloads."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import hdf5plugin  # noqa: F401
import numpy as np
import pytest
from click.testing import CliRunner

from firebench.acquisition.hrrr import forecast as hrrr_forecast
from firebench.acquisition.hrrr.grid import HRRRGrid
from firebench.cli import main
from firebench.tools.logging_config import configure_logging
from firebench.workflows.wx_forecast import WxForecastWorkflow
from firebench.workflows.wx_setup import load_setup

UTC = timezone.utc
CYCLE = datetime(2021, 8, 20, 0, tzinfo=UTC)
STATIONS = {"AAA01": (38.70, -120.30), "BBB02": (38.75, -120.20), "CCC03": (38.65, -120.10)}


def _synoptic_payload(seed: int = 3) -> dict:
    rng = np.random.default_rng(seed)
    times = [CYCLE - timedelta(hours=1) + timedelta(minutes=10 * step) for step in range(31)]
    hours = np.array([(time - CYCLE).total_seconds() / 3600 for time in times])
    stations = []
    for index, (stid, (lat, lon)) in enumerate(STATIONS.items()):
        stations.append(
            {
                "STID": stid,
                "NAME": f"Station {stid}",
                "ID": str(index + 1),
                "MNET_ID": "2",
                "STATE": "CA",
                "TIMEZONE": "America/Los_Angeles",
                "LATITUDE": str(lat),
                "LONGITUDE": str(lon),
                "ELEVATION": "4921",
                "UNITS": {"position": "m", "elevation": "ft"},
                "PROVIDERS": [{"name": "Test provider"}],
                "SENSOR_VARIABLES": {
                    "air_temp": {"air_temp_set_1": {"position": "2.0"}},
                    "relative_humidity": {"relative_humidity_set_1": {"position": "2.0"}},
                    "wind_speed": {"wind_speed_set_1": {"position": "6.1"}},
                    "wind_direction": {"wind_direction_set_1": {"position": "6.1"}},
                    "fuel_moisture": {"fuel_moisture_set_1": {"position": "0.3"}},
                },
                "OBSERVATIONS": {
                    "date_time": [time.strftime("%Y-%m-%dT%H:%M:%SZ") for time in times],
                    "air_temp_set_1": (20 - hours + rng.normal(0, 0.2, hours.size)).round(2).tolist(),
                    "relative_humidity_set_1": (30 + 2 * hours + rng.normal(0, 0.5, hours.size))
                    .round(1)
                    .tolist(),
                    "wind_speed_set_1": (3 + rng.normal(0, 0.3, hours.size)).clip(0.5).round(2).tolist(),
                    "wind_direction_set_1": (250 + rng.normal(0, 10, hours.size)).round(0).tolist(),
                    "fuel_moisture_set_1": (6 + 0.1 * hours + rng.normal(0, 0.05, hours.size))
                    .round(2)
                    .tolist(),
                },
            }
        )
    return {"STATION": stations}


class _Field:
    def __init__(self, value: float) -> None:
        self.value = value

    def __getitem__(self, index):
        _, i = index
        return np.full(np.shape(i), self.value, dtype=float)


def _fake_read(path):
    fxx = int(re.search(r"wrfsfcf(\d+)", Path(path).name).group(1))
    fields = {
        "TMP:2 m above ground": _Field(273.15 + 21 - fxx),
        "RH:2 m above ground": _Field(31 + 2 * fxx),
        "UGRD:10 m above ground": _Field(3.0),
        "VGRD:10 m above ground": _Field(1.0),
        "SFCR:surface": _Field(0.1),
    }
    if fxx == 0:
        fields["HGT:surface"] = _Field(1500.0)
    return fields


@pytest.fixture(autouse=True)
def reset_firebench_logger():
    # `firebench wx` commands attach console handlers to the CliRunner streams
    configure_logging(2, use_console=False)
    yield
    configure_logging(2, use_console=False)


@pytest.fixture
def fake_hrrr(monkeypatch, tmp_path):
    calls = []

    def fake_fetch_file(cycle, fxx, fields=None, cache_root=None, **kwargs):
        calls.append(fxx)
        path = tmp_path / "cache" / f"hrrr.t{cycle:%H}z.wrfsfcf{fxx:02d}.fb.grib2"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"grib")
        return path

    monkeypatch.setattr(hrrr_forecast, "fetch_file", fake_fetch_file)
    return calls


def _write_setup(tmp_path) -> Path:
    source = tmp_path / "synoptic_saved.json"
    source.write_text(json.dumps(_synoptic_payload()))
    setup = tmp_path / "setup.yml"
    setup.write_text("""
name: offline_test
output_dir: run
domain: {bbox: [-120.5, 38.5, -120.0, 38.9]}
window: {start: 2021-08-20T00:00Z, end: 2021-08-20T03:00Z}
observations:
  synoptic_json: synoptic_saved.json
  context_hours: 1
model: {cycle_hours: [0], horizon_hours: 3, download_workers: 2}
benchmark: {lead_bins: [[1, 3]], informational_lead_bins: [[0, 0]]}
""")
    return setup


def test_workflow_produces_observations_model_scores_and_summary(tmp_path, fake_hrrr):
    setup = load_setup(_write_setup(tmp_path))

    result = WxForecastWorkflow(setup, read_fields=_fake_read).run()

    run_dir = tmp_path / "run"
    assert sorted(fake_hrrr) == [0, 1, 2, 3]
    with h5py.File(run_dir / "observations" / "obs.h5", "r") as obs:
        assert obs.attrs["data_tier"] == "provisional"
        assert obs.attrs["wx_qc_stage"] == "final"
        assert {name for name in obs["time_series"]} == {f"station_{stid}" for stid in STATIONS}
    with h5py.File(run_dir / "models" / "hrrr_2021082000.h5", "r") as model:
        assert model["time_series/station_AAA01/time"][:].tolist() == [0.0, 3600.0, 7200.0, 10800.0]

    scored = result.results["2021082000"]
    assert scored["excluded_kpis"] == [{"variable": "fuel_moisture_content_10h", "reason": "no model data"}]
    assert scored["data_tier"] == "provisional"
    assert scored["score_card"]["Scheme"]["Air Temp 1h F00 analysis"]["weight"] == 0
    assert scored["score_card"]["Score Air Temp 1h F01-03"] > 50
    # the fake HRRR is 1 degC warmer than the observations at every hour
    assert scored["benchmarks"]["WX-AT-MAE-MEAN-TSO-1H-F0103"][
        "Air temp MAE mean 1h F01-03 TSO"
    ] == pytest.approx(1.0, abs=0.2)
    assert (run_dir / "scores" / "HRRR_2021082000_scorecard.pdf").is_file()
    summary = (run_dir / "summary.md").read_text()
    assert "fuel_moisture_content_10h: no model data" in summary
    assert "| Total |" in summary


def test_second_run_downloads_nothing_and_skips_every_stage(tmp_path, fake_hrrr):
    setup_path = _write_setup(tmp_path)
    WxForecastWorkflow(load_setup(setup_path), read_fields=_fake_read).run()
    first_calls = list(fake_hrrr)
    model_file = tmp_path / "run" / "models" / "hrrr_2021082000.h5"
    first_mtime = model_file.stat().st_mtime_ns

    result = WxForecastWorkflow(load_setup(setup_path), read_fields=_fake_read).run()

    assert fake_hrrr == first_calls
    assert {record.status for record in result.records} == {"skipped"}
    assert model_file.stat().st_mtime_ns == first_mtime
    assert result.results["2021082000"]["score_card"]["Score Total"] > 0


def test_force_reruns_the_stages(tmp_path, fake_hrrr):
    setup_path = _write_setup(tmp_path)
    WxForecastWorkflow(load_setup(setup_path), read_fields=_fake_read).run()

    result = WxForecastWorkflow(load_setup(setup_path), force=True, read_fields=_fake_read).run()

    assert "skipped" not in {record.status for record in result.records}


def test_force_on_one_stage_reuses_the_other_stages(tmp_path, fake_hrrr):
    setup_path = _write_setup(tmp_path)
    WxForecastWorkflow(load_setup(setup_path), read_fields=_fake_read).run()
    downloads = list(fake_hrrr)

    result = WxForecastWorkflow(load_setup(setup_path), force=True, read_fields=_fake_read).run(("score",))

    assert fake_hrrr == downloads
    assert [(record.name, record.status) for record in result.records] == [
        ("obs", "skipped"),
        ("score 2021082000", "done"),
    ]


def test_cycle_with_hours_missing_from_the_archive_is_dropped(tmp_path, monkeypatch, fake_hrrr):
    original = hrrr_forecast.fetch_file

    def fetch_without_f02(cycle, fxx, *args, **kwargs):
        if fxx == 2:
            raise FileNotFoundError("HRRR file not available (HTTP 404)")
        return original(cycle, fxx, *args, **kwargs)

    monkeypatch.setattr(hrrr_forecast, "fetch_file", fetch_without_f02)

    result = WxForecastWorkflow(load_setup(_write_setup(tmp_path)), read_fields=_fake_read).run()

    assert result.dropped_cycles == [
        {"cycle": "2021-08-20T00:00:00+00:00", "reason": "forecast hours missing from the archive: [2]"}
    ]
    assert result.results == {}
    assert "Dropped cycles" in (tmp_path / "run" / "summary.md").read_text()


def test_extra_model_is_scored_against_the_same_observations(tmp_path, fake_hrrr):
    setup_path = _write_setup(tmp_path)
    workflow = WxForecastWorkflow(load_setup(setup_path), read_fields=_fake_read)
    workflow.run()
    other_model = tmp_path / "other.h5"
    other_model.write_bytes((tmp_path / "run" / "models" / "hrrr_2021082000.h5").read_bytes())

    result = CliRunner().invoke(
        main,
        [
            "wx",
            "score",
            str(setup_path),
            str(other_model),
            "--cycle",
            "2021-08-20T00:00Z",
            "--name",
            "Other",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Other 2021-08-20 00Z: total score" in result.output
    assert (tmp_path / "run" / "scores" / "Other_2021082000_rslt.json").is_file()


def test_cli_init_and_plan_work_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("FIREBENCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("FIREBENCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("SYNOPTIC_TOKEN", raising=False)
    setup = tmp_path / "caldor.yml"
    runner = CliRunner()

    init = runner.invoke(main, ["wx", "init", str(setup), "--case", "2021_Caldor", "--period", "H012"])
    plan = runner.invoke(main, ["wx", "plan", str(setup)])

    assert init.exit_code == 0, init.output
    assert plan.exit_code == 0, plan.output
    assert "Preset: 2021_Caldor H012" in plan.output
    assert "cycle 2021-08-20 00Z (HRRR v4): f00-f48, 49 files, 0 cached" in plan.output
    assert "No API key found for 'synoptic'" in plan.output
    assert "firebench keys set synoptic" in plan.output


def test_cli_run_reports_an_invalid_setup_without_traceback(tmp_path):
    setup = tmp_path / "bad.yml"
    setup.write_text("name: bad\nwindow: {start: 2021-08-20T00:00, end: 2021-08-19T00:00Z}\ntoken: abc\n")

    result = CliRunner().invoke(main, ["wx", "run", str(setup)])

    assert result.exit_code != 0
    assert "invalid setup" in result.output
    assert "unknown top-level key 'token'" in result.output
    assert "has no time zone" in result.output
    assert "Traceback" not in result.output
