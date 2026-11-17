"""Behavioral checks for raw NFMDB conversion and temporal FMC scoring."""

import csv
from datetime import datetime

import h5py
import numpy as np
import pytest

from firebench.standardize import new_std_file, standardize_nfmdb_csv
from firebench.benchmarks.fmc import compare_fmc_series, run_fmc_benchmark


@pytest.fixture
def fmc_csv(tmp_path):
    path = tmp_path / "observations.csv"

    def write(rows):
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                "STID DATE FUEL_TYPE FUEL_VARIATION PERCENT NAME GACC GROUP LAT LON ELE".split()
            )
            for fuel, date, value, variation in rows:
                writer.writerow(
                    ["2", date, fuel, variation, value, "Station", "NOCC", "Tahoe", 39, -120, 7600]
                )
        return path

    return write


def test_raw_grouping_and_noon(fmc_csv, tmp_path):
    source = fmc_csv(
        [
            ("Pine", "2024-03-01", 100, "None"),
            ("Pine", "2024-03-15", "", "None"),
            ("Pine", "2024-03-15", 0, "None"),
            ("10-Hour", "2024-03-01", 10, "None"),
        ]
    )
    with new_std_file(str(tmp_path / "raw.h5"), "test") as handle:
        with pytest.raises(ValueError, match="timezone"):
            standardize_nfmdb_csv(source, handle)
        assert "time_series" not in handle
        standardize_nfmdb_csv(source, handle, timezone="America/Los_Angeles")
        groups = handle["time_series"]
        assert len(groups) == 2
        pine = groups["station_2_Pine"]
        assert pine["time"].attrs["time_origin"] == "2024-03-01T20:00:00+00:00"
        assert pine["time"][1] == (14 * 24 - 1) * 3600  # DST changed between visits
        np.testing.assert_equal(pine["fuel_moisture_content"][:], [100, np.nan, 0])
        assert pine["fuel_moisture_content_time_assumed"][:].all()
        assert groups["station_2_10-Hour"]["fuel_moisture_content_10h_date_only"][0]
        with pytest.raises(ValueError, match="already exists"):
            standardize_nfmdb_csv(source, handle, timezone="America/Los_Angeles")


def test_shared_timestamps(fmc_csv, tmp_path):
    source = fmc_csv([(fuel, "2024-01-01T12:00:00Z", 12, "None") for fuel in ("1-Hour", "10-Hour")])
    with new_std_file(str(tmp_path / "shared.h5"), "test") as handle:
        standardize_nfmdb_csv(source, handle)
        assert list(handle["time_series"]) == ["station_2"]
        assert "fuel_moisture_content_1h" in handle["time_series/station_2"]


def test_fortnightly_events_and_gaps():
    obs = [(0, 100, True, True), (14 * 86400, 120, True, True), (29 * 86400, 90, True, True)]
    model = [(-60, 110, False, False), (60, 200, False, False), (14 * 86400 + 3600, 100, False, False)]
    values, detail = compare_fmc_series(obs, model, live=True, mode="events")
    assert values == pytest.approx({"MAE": 15, "RMSE": np.sqrt(250), "Bias": -5})
    assert detail["time_offsets_seconds"] == [-60, 3600]
    assert detail["unmatched_count"] == 1
    assert detail["assumed_time_count"] == 2


def test_bins_duplicates_and_precision():
    obs = [(0, 10, False, False), (0, 20, False, False), (1800, 30, False, False)]
    mod = [(0, 15, False, False), (2000, 25, False, False)]
    values, detail = compare_fmc_series(obs, mod, live=False, mode="native")
    assert values["MAE"] == 0
    assert detail["matched_count"] == 1
    assert compare_fmc_series(obs, mod, live=False, mode="hourly")[0]["MAE"] == 0
    dates = [(0, 10, True, False)]
    assert not compare_fmc_series(dates, mod, live=False, mode="hourly")[0]
    assert compare_fmc_series(dates, mod, live=False, mode="daily")[0]["MAE"] == 10


def test_benchmark_pdf_and_units(fmc_csv, tmp_path):
    source = fmc_csv([("Pine", "2024-01-01", 100, "None"), ("Pine", "2024-01-15", 120, "None")])
    obs, model = tmp_path / "obs.h5", tmp_path / "model.h5"
    for path in (obs, model):
        with new_std_file(str(path), "test") as handle:
            standardize_nfmdb_csv(source, handle, timezone="America/Los_Angeles")
    with h5py.File(model, "a") as handle:
        ds = handle["time_series/station_2/fuel_moisture_content"]
        ds[:] = (ds[:] + 10) / 100
        ds.attrs["units"] = "dimensionless"
    result = run_fmc_benchmark(
        model,
        obs,
        mae_half_score_pp=10,
        output_json=tmp_path / "results.json",
        score_card_report=tmp_path / "card.pdf",
    )
    assert result["score_card"]["Score Total"] == pytest.approx(50)
    assert (tmp_path / "card.pdf").read_bytes().startswith(b"%PDF")
    assert "NaN" not in (tmp_path / "results.json").read_text()
    with pytest.raises(FileExistsError):
        run_fmc_benchmark(
            model,
            obs,
            mae_half_score_pp=10,
            output_json=tmp_path / "results.json",
            score_card_report=tmp_path / "card.pdf",
        )


@pytest.mark.parametrize("scale", [0, -1, float("nan"), float("inf")])
def test_bad_scale(scale, tmp_path):
    with pytest.raises(ValueError, match="scale"):
        run_fmc_benchmark(tmp_path / "missing", tmp_path / "missing", mae_half_score_pp=scale)


def test_invalid_input_is_non_mutating(fmc_csv, tmp_path):
    path = tmp_path / "invalid.h5"
    with new_std_file(str(path), "test") as handle:
        source = fmc_csv([("Pine", "not-a-date", 100, "None")])
        with pytest.raises(ValueError, match="row 2"):
            standardize_nfmdb_csv(source, handle)
        assert "time_series" not in handle
        source.write_text("STID,DATE\n2,2024-01-01\n")
        with pytest.raises(ValueError, match="missing required columns"):
            standardize_nfmdb_csv(source, handle)
        source = fmc_csv([("Pine", "2024-01-01", 100, "None")])
        source.write_text(source.read_text().rstrip() + ",extra\n")
        with pytest.raises(ValueError, match="number of fields"):
            standardize_nfmdb_csv(source, handle, timezone="America/Los_Angeles")
        assert "time_series" not in handle


def test_name_collision_before_writing(fmc_csv, tmp_path):
    source = fmc_csv([("Pine_A", "2024-01-01", 100, "B"), ("Pine", "2024-01-02", 100, "A_B")])
    with new_std_file(str(tmp_path / "collision.h5"), "test") as handle:
        with pytest.raises(ValueError, match="collision"):
            standardize_nfmdb_csv(source, handle, timezone="America/Los_Angeles")
        assert "time_series" not in handle


def test_unavailable_total(fmc_csv, tmp_path):
    source = fmc_csv([("10-Hour", "2024-01-01", 10, "None")])
    obs, model = tmp_path / "obs.h5", tmp_path / "model.h5"
    with new_std_file(str(obs), "test") as handle:
        standardize_nfmdb_csv(source, handle)
    with new_std_file(str(model), "test"):
        pass
    result = run_fmc_benchmark(
        model,
        obs,
        mae_half_score_pp=10,
        output_json=tmp_path / "empty.json",
        score_card_report=tmp_path / "empty.pdf",
    )
    assert "Score Total" not in result["score_card"]
    assert result["ignored_reasons"]
