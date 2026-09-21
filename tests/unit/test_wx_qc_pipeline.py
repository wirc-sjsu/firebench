"""Focused tests for the auditable Synoptic weather-QC pipeline."""

import json

import h5py
import hdf5plugin  # noqa: F401
import numpy as np
import pytest

from firebench.tools.wx_qc.pipeline import (
    QCError,
    add_manual_action,
    decide_action,
    edit_action,
    finalize_manifest,
    process_synoptic_json,
    read_manifest,
)


def _station():
    return {
        "STID": "TEST1",
        "NAME": "Test station",
        "ID": 1,
        "MNET_ID": 1,
        "STATE": "CA",
        "TIMEZONE": "America/Los_Angeles",
        "LATITUDE": 38.0,
        "LONGITUDE": -120.0,
        "ELEVATION": 1000.0,
        "ELEV_DEM": 1000.0,
        "UNITS": {"elevation": "m"},
        "PROVIDERS": [{"name": "Test"}],
        "QC_FLAGGED": True,
        "SENSOR_VARIABLES": {
            "air_temperature": {"air_temp_set_1": {"position": "2.0"}},
            "wind": {"wind_speed_set_1": {"position": 10.0}},
        },
        "OBSERVATIONS": {
            "date_time": [
                "20210817000000",
                "20210817000100",
                "20210817000100",
                "20210817000200",
            ],
            "air_temp_set_1": [10.0, 80.0, 80.0, 12.0],
            "wind_speed_set_1": [0.0, 0.0, 0.0, 1.0],
        },
    }


def test_pipeline_creates_deterministic_actions_candidate_and_log(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"STATION": [_station()]}), encoding="utf-8")
    candidate = tmp_path / "candidate.h5"
    manifest_path = tmp_path / "qc.json"
    log_path = tmp_path / "qc.log"

    manifest = process_synoptic_json(source, None, candidate, manifest_path, log_path, overwrite=False)

    actions_by_code = {item["code"]: item for item in manifest["actions"]}
    assert actions_by_code["DUP"]["effect"]["count"] == 1
    assert actions_by_code["META"]["decision"]["status"] == "auto_accepted"
    assert actions_by_code["BOUND"]["effect"]["count"] == 1
    assert actions_by_code["SRCFLAG"]["decision"]["status"] == "pending"
    assert len({item["id"] for item in manifest["actions"]}) == len(manifest["actions"])
    assert "WXQC-DUP-" in log_path.read_text(encoding="utf-8")

    with h5py.File(candidate, "r") as output:
        station = output["time_series/station_TEST1"]
        assert len(station["time"]) == 3
        assert np.isnan(station["air_temperature"][:]).sum() == 1
        assert station["time"].attrs["time_origin"].endswith("+00:00")
        assert station.attrs["timezone"] == "America/Los_Angeles"
        assert output.attrs["wx_qc_stage"] == "candidate"

    second_candidate = tmp_path / "candidate2.h5"
    second_manifest = tmp_path / "qc2.json"
    process_synoptic_json(
        source,
        None,
        second_candidate,
        second_manifest,
        tmp_path / "qc2.log",
    )
    assert [item["id"] for item in read_manifest(second_manifest)["actions"]] == [
        item["id"] for item in manifest["actions"]
    ]


def test_manifest_rejects_action_content_that_no_longer_matches_its_id(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"STATION": [_station()]}), encoding="utf-8")
    manifest_path = tmp_path / "qc.json"
    process_synoptic_json(
        source,
        None,
        tmp_path / "candidate.h5",
        manifest_path,
        tmp_path / "qc.log",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["actions"][0]["selector"]["tampered"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(QCError, match="action ID does not match"):
        read_manifest(manifest_path)


def test_review_edit_and_finalize_lifecycle(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"STATION": [_station()]}), encoding="utf-8")
    manifest_path = tmp_path / "qc.json"
    manifest = process_synoptic_json(
        source,
        None,
        tmp_path / "candidate.h5",
        manifest_path,
        tmp_path / "qc.log",
    )

    with pytest.raises(QCError, match="pending"):
        finalize_manifest(manifest_path, tmp_path / "final.h5", "reviewer")

    source_flag = next(item for item in manifest["actions"] if item["code"] == "SRCFLAG")
    edited = edit_action(
        manifest_path,
        source_flag["id"],
        source_flag["selector"],
        {"kind": "no_change"},
        "reviewer",
    )
    replacement = next(item for item in edited["actions"] if item.get("supersedes") == source_flag["id"])
    assert replacement["id"] != source_flag["id"]
    assert (
        next(item for item in edited["actions"] if item["id"] == source_flag["id"])["decision"]["status"]
        == "superseded"
    )

    edited = add_manual_action(
        manifest_path,
        station="TEST1",
        variable="air_temperature",
        selector={"ranges": [{"start": "2021-08-17T07:02:00Z", "end": "2021-08-17T07:02:00Z"}]},
        effect={"kind": "set_nan_ranges", "variables": ["air_temperature"]},
        message="Manual test range",
        reviewer="reviewer",
    )
    manual = next(item for item in edited["actions"] if item["code"] == "MANUAL")
    assert manual["decision"]["status"] == "accepted"

    for action in read_manifest(manifest_path)["actions"]:
        if action["decision"]["status"] != "pending":
            continue
        if action["effect"]["kind"] == "no_change":
            decision = "acknowledged"
        elif action["code"] == "ZEROWIND":
            decision = "accepted"
        else:
            decision = "rejected"
        decide_action(manifest_path, action["id"], decision, "reviewer")

    final_path = tmp_path / "final.h5"
    result = finalize_manifest(manifest_path, final_path, "reviewer")
    assert result["summary"]["pending"] == 0
    with h5py.File(final_path, "r") as output:
        assert output.attrs["wx_qc_stage"] == "final"
        assert output.attrs["wx_qc_finalized_by"] == "reviewer"
        assert "station_TEST1" in output["time_series"]
        np.testing.assert_allclose(
            output["time_series/station_TEST1/wind_speed"][:],
            [np.nan, np.nan, 1.0],
            equal_nan=True,
        )
        assert np.isnan(output["time_series/station_TEST1/air_temperature"][-1])


def test_manual_variable_exclusion_omits_dataset_from_final_h5(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"STATION": [_station()]}), encoding="utf-8")
    manifest_path = tmp_path / "qc.json"
    manifest = process_synoptic_json(
        source,
        None,
        tmp_path / "candidate.h5",
        manifest_path,
        tmp_path / "qc.log",
    )

    manifest = add_manual_action(
        manifest_path,
        station="TEST1",
        variable="wind_speed",
        selector={"scope": "entire_variable", "reason": "mostly zero"},
        effect={"kind": "exclude_variable", "variables": ["wind_speed"]},
        message="Manually omit complete variable wind_speed: mostly zero",
        reviewer="reviewer",
    )
    omitted = next(
        action for action in manifest["actions"] if action["effect"]["kind"] == "exclude_variable"
    )
    assert omitted["id"].startswith("WXQC-MANUAL-")

    for action in read_manifest(manifest_path)["actions"]:
        if action["decision"]["status"] != "pending":
            continue
        decision = "acknowledged" if action["effect"]["kind"] == "no_change" else "rejected"
        decide_action(manifest_path, action["id"], decision, "reviewer")

    final_path = tmp_path / "final.h5"
    result = finalize_manifest(manifest_path, final_path, "reviewer")
    omitted = next(action for action in result["actions"] if action["effect"]["kind"] == "exclude_variable")
    assert omitted["application"]["final"] == "applied"
    with h5py.File(final_path, "r") as output:
        station = output["time_series/station_TEST1"]
        assert "wind_speed" not in station
        assert "air_temperature" in station
