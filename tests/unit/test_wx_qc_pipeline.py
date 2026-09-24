"""Focused tests for the auditable Synoptic weather-QC pipeline."""

import json
from datetime import datetime, timedelta, timezone

import h5py
import hdf5plugin  # noqa: F401
import numpy as np
import pytest

from firebench.standardize.synoptic import standardize_synoptic_raws_from_json
from firebench.tools.wx_qc.pipeline import (
    QCError,
    add_manual_action,
    decide_action,
    edit_action,
    finalize_manifest,
    load_policy,
    process_synoptic_json,
    read_manifest,
)
from firebench.tools.wx_qc import pipeline as pipeline_module


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
        assert station["time"].attrs["time_origin"] == "2021-08-17T00:00:00+00:00"
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


def test_synoptic_offsets_are_ignored_and_clock_values_are_utc(tmp_path):
    station = _station()
    station["SENSOR_VARIABLES"]["air_temperature"]["air_temp_set_1"]["position"] = 2.0
    station["OBSERVATIONS"] = {
        "date_time": ["2021-08-17T00:00:00-07:00", "2021-08-17T00:01:00+03:00"],
        "air_temp_set_1": [10.0, 11.0],
        "wind_speed_set_1": [1.0, 2.0],
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"STATION": [station]}), encoding="utf-8")

    direct_output = tmp_path / "direct.h5"
    with h5py.File(direct_output, "w") as output:
        standardize_synoptic_raws_from_json(source, output, time_origin_utc=False)
    with h5py.File(direct_output, "r") as output:
        direct_station = output["time_series/station_TEST1"]
        assert direct_station["time"].attrs["time_origin"] == "2021-08-17T00:00:00+00:00"
        assert direct_station["time"][:].tolist() == [0.0, 1.0]
        assert direct_station.attrs["timezone"] == "America/Los_Angeles"

    candidate = tmp_path / "candidate.h5"
    manifest = process_synoptic_json(
        source,
        None,
        candidate,
        tmp_path / "manifest.json",
        tmp_path / "audit.log",
    )
    time_action = next(item for item in manifest["actions"] if item["code"] == "TIME")
    assert time_action["message"] == "Interpreted 2 Synoptic timestamps as UTC wall-clock values"
    with h5py.File(candidate, "r") as output:
        qc_station = output["time_series/station_TEST1"]
        assert qc_station["time"].attrs["time_origin"] == "2021-08-17T00:00:00+00:00"
        assert qc_station["time"][:].tolist() == [0.0, 1.0]
        assert qc_station.attrs["timezone"] == "America/Los_Angeles"


def test_policy_versions_preserve_legacy_frozen_rules_and_validate_v5_modes():
    legacy = load_policy({"version": 1, "gui": {"frozen_min_run": 12}})
    assert legacy["version"] == 1
    assert legacy["gui"]["frozen_min_run"] == 12
    assert "frozen" not in legacy

    current = load_policy(None)
    assert current["version"] == 5
    assert current["mode"] == "review"
    assert current["frozen"]["minimum_duration_hours"]["air_temperature"] == 6.0
    assert current["review"]["target_pending_fraction"] == 0.05

    version_four = load_policy({"version": 4})
    assert version_four["version"] == 4
    assert "mode" not in version_four

    conservative = load_policy({"version": 5, "mode": "conservative_auto"})
    assert conservative["mode"] == "conservative_auto"

    version_two = load_policy({"version": 2})
    assert version_two["version"] == 2
    assert "review_adaptive_percentile" not in version_two["frozen"]

    with pytest.raises(QCError, match="required_neighbors"):
        load_policy({"version": 2, "frozen": {"neighbor_count": 1, "required_neighbors": 2}})
    with pytest.raises(QCError, match="target_pending_fraction"):
        load_policy({"version": 3, "review": {"target_pending_fraction": 1.1}})
    with pytest.raises(QCError, match="automatic_required_neighbors"):
        load_policy(
            {
                "version": 3,
                "frozen": {"neighbor_count": 2, "automatic_required_neighbors": 3},
                "thresholds": {"zero_wind_required_neighbors": 2},
            }
        )
    with pytest.raises(QCError, match="zero_wind_exclusion_fraction"):
        load_policy({"version": 4, "thresholds": {"zero_wind_exclusion_fraction": 0.4}})
    with pytest.raises(QCError, match="mode"):
        load_policy({"version": 5, "mode": "accept_everything"})


def test_conservative_auto_excludes_source_flag_without_pending_review(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"STATION": [_station()]}), encoding="utf-8")
    candidate = tmp_path / "candidate.h5"
    manifest_path = tmp_path / "manifest.json"

    manifest = process_synoptic_json(
        source,
        {"version": 5, "mode": "conservative_auto"},
        candidate,
        manifest_path,
        tmp_path / "audit.log",
    )

    source_exclusion = next(
        item
        for item in manifest["actions"]
        if item["code"] == "SAFEEXCL" and "SRCFLAG" in item["selector"]["reason_codes"]
    )
    assert source_exclusion["effect"] == {"kind": "exclude_station"}
    assert source_exclusion["decision"]["status"] == "auto_accepted"
    assert manifest["summary"]["pending"] == 0
    assert manifest["summary"]["review_actions"] == 0
    with h5py.File(candidate, "r") as output:
        assert "station_TEST1" not in output["time_series"]
        assert output.attrs["wx_qc_mode"] == "conservative_auto"

    finalized = finalize_manifest(manifest_path, tmp_path / "final.h5", "automated workflow")
    assert finalized["final_findings"] == []


def test_conservative_auto_reaches_fixed_point_after_variable_exclusion(tmp_path):
    station = _station()
    station["QC_FLAGGED"] = False
    station["SENSOR_VARIABLES"] = {"wind": {"wind_speed_set_1": {"position": 10.0}}}
    station["OBSERVATIONS"] = {
        "date_time": [f"202108170{i}0000Z" for i in range(10)],
        "wind_speed_set_1": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0],
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"STATION": [station]}), encoding="utf-8")

    manifest = process_synoptic_json(
        source,
        {"version": 5, "mode": "conservative_auto"},
        tmp_path / "candidate.h5",
        tmp_path / "manifest.json",
        tmp_path / "audit.log",
    )

    safe_effects = [item["effect"]["kind"] for item in manifest["actions"] if item["code"] == "SAFEEXCL"]
    assert "exclude_variable" in safe_effects
    assert "exclude_station" in safe_effects
    assert any(item["code"] == "no_data" for item in manifest["findings"])
    assert manifest["summary"]["pending"] == 0


def test_conservative_auto_finalization_rejects_new_post_build_doubt(tmp_path, monkeypatch):
    station = _station()
    station["QC_FLAGGED"] = False
    station["OBSERVATIONS"]["wind_speed_set_1"] = [1.0, 2.0, 3.0, 4.0]
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"STATION": [station]}), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    process_synoptic_json(
        source,
        {"version": 5, "mode": "conservative_auto"},
        tmp_path / "candidate.h5",
        manifest_path,
        tmp_path / "audit.log",
    )

    monkeypatch.setattr(
        pipeline_module,
        "_h5_qc_findings",
        lambda *_args: (
            [],
            [
                {
                    "id": "post-build-doubt",
                    "code": "gap_dt",
                    "severity": "WARN",
                    "target": {"station": "TEST1", "variable": "time"},
                    "message": "New post-build doubt",
                    "selector": {},
                    "evidence": {},
                }
            ],
        ),
    )
    output = tmp_path / "final.h5"
    with pytest.raises(QCError, match="new QC doubts"):
        finalize_manifest(manifest_path, output, "automated workflow")
    assert not output.exists()


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
        selector={"ranges": [{"start": "2021-08-17T00:02:00Z", "end": "2021-08-17T00:02:00Z"}]},
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
            [0.0, 0.0, 1.0],
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


def test_pipeline_v2_requires_neighbor_corroboration_for_frozen_action(tmp_path):
    start = datetime(2021, 8, 17, tzinfo=timezone.utc)
    times = [(start + timedelta(minutes=30 * index)).strftime("%Y%m%d%H%M%SZ") for index in range(13)]

    def station(station_id, longitude, values):
        item = _station()
        item.update(
            {
                "STID": station_id,
                "ID": int(station_id[-1]),
                "LONGITUDE": longitude,
                "QC_FLAGGED": False,
                "SENSOR_VARIABLES": {"air_temperature": {"air_temp_set_1": {"position": 2.0}}},
                "OBSERVATIONS": {"date_time": times, "air_temp_set_1": values},
            }
        )
        return item

    source = tmp_path / "frozen.json"
    source.write_text(
        json.dumps(
            {
                "STATION": [
                    station("TEST1", -120.00, [5.0] * 13),
                    station("TEST2", -120.01, list(range(13))),
                    station("TEST3", -120.02, list(range(10, 23))),
                ]
            }
        ),
        encoding="utf-8",
    )
    policy = {
        "version": 2,
        "frozen": {
            "minimum_duration_hours": {
                "air_temperature": 1.0,
                "relative_humidity": 6.0,
                "wind_speed": 3.0,
                "wind_gust": 3.0,
                "wind_direction": 3.0,
                "solar_radiation": 2.0,
                "fuel_moisture_content_10h": 24.0,
            }
        },
    }
    manifest = process_synoptic_json(
        source,
        policy,
        tmp_path / "candidate.h5",
        tmp_path / "manifest.json",
        tmp_path / "audit.log",
    )

    action = next(
        item
        for item in manifest["actions"]
        if item["code"] == "FROZEN" and item["target"]["station"] == "TEST1"
    )
    assert action["decision"]["status"] == "pending"
    assert action["selector"]["evidence"]["confidence"] == "high"
    assert action["selector"]["evidence"]["resolution"] == pytest.approx(1.0)
    assert len(action["selector"]["evidence"]["neighbors"]) == 2


def test_pipeline_v3_groups_ambiguous_frozen_ranges_by_sensor(tmp_path):
    start = datetime(2021, 8, 17, tzinfo=timezone.utc)
    times = [(start + timedelta(minutes=30 * index)).strftime("%Y%m%d%H%M%SZ") for index in range(11)]

    def station(station_id, longitude, temperatures, humidity):
        item = _station()
        item.update(
            {
                "STID": station_id,
                "ID": int(station_id[-1]),
                "LONGITUDE": longitude,
                "QC_FLAGGED": False,
                "SENSOR_VARIABLES": {
                    "air_temperature": {"air_temp_set_1": {"position": 2.0}},
                    "relative_humidity": {"relative_humidity_set_1": {"position": 2.0}},
                },
                "OBSERVATIONS": {
                    "date_time": times,
                    "air_temp_set_1": temperatures,
                    "relative_humidity_set_1": humidity,
                },
            }
        )
        return item

    source = tmp_path / "grouped.json"
    target_values = [0.0, 5.0, 5.0, 5.0, 5.0, 1.0, 6.0, 6.0, 6.0, 6.0, 2.0]
    stations = [station("TEST1", -120.0, target_values, list(range(30, 41)))]
    for index in range(2, 5):
        stations.append(
            station(
                f"TEST{index}",
                -120.0 + index * 0.01,
                list(range(11)),
                list(range(40, 51)),
            )
        )
    source.write_text(json.dumps({"STATION": stations}), encoding="utf-8")
    policy = load_policy(None)
    policy["frozen"]["minimum_duration_hours"]["air_temperature"] = 0.5
    policy["frozen"]["automatic_duration_multiplier"] = 20.0
    policy["frozen"]["neighbor_change_steps"] = 2.0

    manifest = process_synoptic_json(
        source,
        policy,
        tmp_path / "candidate.h5",
        tmp_path / "manifest.json",
        tmp_path / "audit.log",
    )

    actions = [
        item
        for item in manifest["actions"]
        if item["code"] == "FROZEN" and item["target"]["station"] == "TEST1"
    ]
    assert len(actions) == 1
    assert actions[0]["decision"]["status"] == "pending"
    assert len(actions[0]["selector"]["ranges"]) == 2
    assert actions[0]["selector"]["evidence"]["classification"] == "ambiguous"


def test_pipeline_v3_applies_only_near_certain_frozen_ranges(tmp_path):
    start = datetime(2021, 8, 17, tzinfo=timezone.utc)
    times = [(start + timedelta(minutes=30 * index)).strftime("%Y%m%d%H%M%SZ") for index in range(8)]

    def station(station_id, longitude, temperatures, humidity):
        item = _station()
        item.update(
            {
                "STID": station_id,
                "ID": int(station_id[-1]),
                "LONGITUDE": longitude,
                "QC_FLAGGED": False,
                "OBSERVATIONS": {
                    "date_time": times,
                    "air_temp_set_1": temperatures,
                    "relative_humidity_set_1": humidity,
                },
            }
        )
        return item

    source = tmp_path / "automatic.json"
    stations = [station("TEST1", -120.0, [4.0] + [5.0] * 6 + [6.0], list(range(8)))]
    for index in range(2, 5):
        stations.append(
            station(
                f"TEST{index}",
                -120.0 + index * 0.01,
                list(range(8)),
                list(range(10, 18)),
            )
        )
    source.write_text(json.dumps({"STATION": stations}), encoding="utf-8")
    policy = load_policy(None)
    policy["frozen"]["minimum_duration_hours"]["air_temperature"] = 0.5

    candidate = tmp_path / "candidate.h5"
    manifest = process_synoptic_json(
        source,
        policy,
        candidate,
        tmp_path / "manifest.json",
        tmp_path / "audit.log",
    )

    action = next(
        item
        for item in manifest["actions"]
        if item["code"] == "FROZEN" and item["target"]["station"] == "TEST1"
    )
    assert action["decision"]["status"] == "auto_accepted"
    assert action["selector"]["evidence"]["classification"] == "near-certain"
    with h5py.File(candidate, "r") as output:
        values = output["time_series/station_TEST1/air_temperature"][:]
        assert np.isnan(values[1:7]).all()
        assert np.isfinite(values[[0, 7]]).all()


def test_pipeline_v3_automates_weeklong_all_zero_speed_without_removing_gust(tmp_path):
    start = datetime(2021, 8, 1, tzinfo=timezone.utc)
    count = 24 * 9 + 1
    times = [(start + timedelta(hours=index)).strftime("%Y%m%d%H%M%SZ") for index in range(count)]
    station = _station()
    station.update(
        {
            "QC_FLAGGED": False,
            "OBSERVATIONS": {
                "date_time": times,
                "wind_speed_set_1": [0.0] * count,
                "wind_gust_set_1": [2.0] * count,
            },
        }
    )
    source = tmp_path / "zero.json"
    source.write_text(json.dumps({"STATION": [station]}), encoding="utf-8")
    candidate = tmp_path / "candidate.h5"

    manifest = process_synoptic_json(
        source,
        {"version": 3},
        candidate,
        tmp_path / "manifest.json",
        tmp_path / "audit.log",
    )

    action = next(item for item in manifest["actions"] if item["code"] == "ZEROWIND")
    assert action["decision"]["status"] == "auto_accepted"
    assert action["effect"]["variables"] == ["wind_speed"]
    with h5py.File(candidate, "r") as output:
        group = output["time_series/station_TEST1"]
        assert np.isnan(group["wind_speed"][:]).all()
        np.testing.assert_allclose(group["wind_gust"][:], 2.0)
    assert manifest["summary"]["pending_fraction"] == pytest.approx(
        manifest["summary"]["pending"] / manifest["summary"]["actions"]
    )


def test_pipeline_v3_keeps_nonmutating_dropout_as_finding_only(tmp_path):
    station = _station()
    station["QC_FLAGGED"] = False
    station["OBSERVATIONS"]["wind_speed_set_1"] = [1.0, 1.0, 1.0, 1.0]
    station["OBSERVATIONS"]["wind_direction_set_1"] = [None, None, None, None]
    source = tmp_path / "dropout.json"
    source.write_text(json.dumps({"STATION": [station]}), encoding="utf-8")

    manifest = process_synoptic_json(
        source,
        {"version": 3},
        tmp_path / "candidate.h5",
        tmp_path / "manifest.json",
        tmp_path / "audit.log",
    )

    assert any(item["code"] == "dropout" for item in manifest["findings"])
    assert not any(item["code"] == "ACK" for item in manifest["actions"])


def test_pipeline_v4_requires_extreme_zero_wind_station_review_and_preserves_candidate(tmp_path):
    station = _station()
    station["QC_FLAGGED"] = False
    station["OBSERVATIONS"] = {
        "date_time": [f"202108170{i}0000Z" for i in range(10)],
        "wind_speed_set_1": [0.0] * 9 + [1.0],
    }
    source = tmp_path / "extreme-zero.json"
    source.write_text(json.dumps({"STATION": [station]}), encoding="utf-8")
    candidate = tmp_path / "candidate.h5"

    manifest = process_synoptic_json(
        source, None, candidate, tmp_path / "manifest.json", tmp_path / "audit.log"
    )

    action = next(item for item in manifest["actions"] if item["code"] == "ZEROWIND")
    assert action["decision"]["status"] == "pending"
    assert action["effect"] == {"kind": "exclude_station"}
    assert action["selector"]["predicate"] == {"variable": "wind_speed", "equals": 0.0}
    with h5py.File(candidate, "r") as output:
        np.testing.assert_allclose(output["time_series/station_TEST1/wind_speed"][:], [0.0] * 9 + [1.0])


def test_pipeline_v4_rechecks_zero_wind_after_finalization(tmp_path):
    station = _station()
    station["QC_FLAGGED"] = False
    start = datetime(2021, 8, 17, tzinfo=timezone.utc)
    station["OBSERVATIONS"] = {
        "date_time": [
            (start + timedelta(minutes=5 * index)).strftime("%Y%m%d%H%M%SZ") for index in range(10)
        ],
        "wind_speed_set_1": [0.0] * 9 + [1.0],
    }
    source = tmp_path / "final-zero.json"
    source.write_text(json.dumps({"STATION": [station]}), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest = process_synoptic_json(
        source, None, tmp_path / "candidate.h5", manifest_path, tmp_path / "audit.log"
    )
    action = next(item for item in manifest["actions"] if item["code"] == "ZEROWIND")
    decide_action(manifest_path, action["id"], "rejected", "reviewer")

    finalized = finalize_manifest(manifest_path, tmp_path / "final.h5", "reviewer")

    assert any(item["code"] == "ZEROWIND" for item in finalized["final_findings"])


def test_pipeline_v4_requires_acknowledgement_for_elevated_fragmented_zero_wind(tmp_path):
    station = _station()
    station["QC_FLAGGED"] = False
    station["OBSERVATIONS"] = {
        "date_time": [f"202108170{i}0000Z" for i in range(10)],
        "wind_speed_set_1": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0],
    }
    source = tmp_path / "elevated-zero.json"
    source.write_text(json.dumps({"STATION": [station]}), encoding="utf-8")

    manifest = process_synoptic_json(
        source,
        None,
        tmp_path / "candidate.h5",
        tmp_path / "manifest.json",
        tmp_path / "audit.log",
    )

    action = next(item for item in manifest["actions"] if item["code"] == "ZEROWIND")
    assert action["decision"]["status"] == "pending"
    assert action["effect"] == {"kind": "no_change"}
    assert manifest["summary"]["pending_fraction"] == pytest.approx(
        manifest["summary"]["pending"] / manifest["summary"]["review_actions"]
    )


def test_pipeline_v4_requires_dropout_acknowledgement_with_temporal_selector(tmp_path):
    station = _station()
    station["QC_FLAGGED"] = False
    station["OBSERVATIONS"]["wind_speed_set_1"] = [1.0, 1.0, 1.0, 1.0]
    station["OBSERVATIONS"]["wind_direction_set_1"] = [None, None, None, None]
    source = tmp_path / "dropout-v4.json"
    source.write_text(json.dumps({"STATION": [station]}), encoding="utf-8")

    manifest = process_synoptic_json(
        source,
        None,
        tmp_path / "candidate.h5",
        tmp_path / "manifest.json",
        tmp_path / "audit.log",
    )

    action = next(item for item in manifest["actions"] if item["code"] == "ACK")
    assert action["target"]["variable"] == "wind_direction"
    assert action["effect"] == {"kind": "no_change"}
    assert action["selector"]["ranges"]


def test_manifest_schema_one_remains_readable(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"STATION": [_station()]}), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest = process_synoptic_json(
        source,
        {"version": 3},
        tmp_path / "candidate.h5",
        manifest_path,
        tmp_path / "audit.log",
    )
    manifest["schema_version"] = 1
    for finding in manifest["findings"]:
        finding.pop("selector", None)
        finding.pop("evidence", None)
        finding["target"].pop("variable", None)
        finding["id"] = pipeline_module._legacy_finding_id(  # pylint: disable=protected-access
            manifest["source"]["sha256"], finding["code"], finding["target"], finding["message"]
        )
    # Re-link actions by code/station where their schema-2 finding ID changed.
    for action in manifest["actions"]:
        action["linked_findings"] = [
            finding["id"]
            for finding in manifest["findings"]
            if finding["code"].removeprefix("AUTO_") == action["code"]
            and finding["target"].get("station") == action["target"].get("station")
        ][:1]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert read_manifest(manifest_path)["schema_version"] == 1
