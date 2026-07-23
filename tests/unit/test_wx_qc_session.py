"""Focused tests for versioned weather-station QC JSON sessions."""

import copy
import json

import pytest

from firebench.tools.wx_qc.constants import default_config
from firebench.tools.wx_qc.session import (
    AUTOSAVE_PATH,
    SESSION_VERSION,
    SessionMixin,
    SessionValidationError,
    read_session_file,
    validate_session_state,
    write_session_file,
)
from firebench.tools.wx_qc.tabs.skiplist import SkiplistTabMixin


class FakeVariable:
    """Small stand-in for Tk variables used by session code."""

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeLabel:
    """Capture the latest configured label text."""

    def __init__(self):
        self.text = ""

    def config(self, **kwargs):
        self.text = kwargs.get("text", self.text)


class SessionApp(SessionMixin):
    """Headless App-shaped object for session round-trip tests."""

    def __init__(self, h5_path):
        self.h5_path = h5_path
        self.cfg = default_config()
        self.cfg["hidden_assertions"] = {"dup_ts"}
        self.skip_list = {"SKIP": "bad sensor"}
        self.green_list = {"GREEN", "SKIP"}
        self.removal_list = {
            "SKIP": [
                {
                    "var": "air_temperature",
                    "t0": "2020-01-01T00:00:00",
                    "t1": "2020-01-01T01:00:00",
                    "reason": "bad range",
                }
            ]
        }
        self._current_stid = "GREEN"
        self.var_map_color = FakeVariable("qc_status")
        self._ov_col_vars = {
            "Name": FakeVariable(False),
            "AirT Max": FakeVariable(True),
        }
        self.lbl_file = FakeLabel()
        self.lbl_status = FakeLabel()
        self.stations = {}
        self.all_stats = {"cached": {"must": "not be serialized"}}
        self._perim_data = []
        self._perim_loaded_path = None
        self.load_kwargs = None
        self.refreshes = []
        self.navigated_to = None
        self.col_visibility_applied = False

    def _load_data(self, **kwargs):
        self.load_kwargs = kwargs
        self.stations = {"GREEN": {}}
        self.all_stats = {"GREEN": {"recomputed": True}}
        kwargs["on_complete"]()

    def _apply_col_visibility(self):
        self.col_visibility_applied = True

    def _navigate_to_station(self, station_id):
        self.navigated_to = station_id

    def _refresh_skiplist(self):
        self.refreshes.append("skiplist")

    def _refresh_overview(self):
        self.refreshes.append("overview")

    def _refresh_station_list(self):
        self.refreshes.append("stations")

    def _load_perim_h5(self, _path):
        raise AssertionError("default session should not load perimeter data")


def test_json_session_round_trip_restores_state_and_recomputes_statistics(tmp_path):
    h5_path = tmp_path / "test_weather_data.h5"
    h5_path.touch()
    source = SessionApp(h5_path)
    destination = tmp_path / "nested" / "weather_qc.json"

    state = source._session_state()
    write_session_file(destination, state)
    decoded = json.loads(destination.read_text(encoding="utf-8"))

    assert decoded["version"] == SESSION_VERSION
    assert "all_stats" not in decoded
    assert decoded["cfg"]["hidden_assertions"] == ["dup_ts"]
    assert not list(destination.parent.glob(f".{destination.name}.*.tmp"))

    target = SessionApp(None)
    target.skip_list = {"OLD": "unchanged only until validation succeeds"}
    target.all_stats = {"stale": True}
    target._restore_session(read_session_file(destination))

    assert target.load_kwargs is not None
    assert set(target.load_kwargs) == {"on_complete"}
    assert target.all_stats == {"GREEN": {"recomputed": True}}
    assert target.skip_list == {"SKIP": "bad sensor"}
    assert target.green_list == {"GREEN"}
    assert target.removal_list == source.removal_list
    assert target.cfg["hidden_assertions"] == {"dup_ts"}
    assert target.cfg["bounds"] == source.cfg["bounds"]
    assert target._ov_col_vars["Name"].get() is False
    assert target.var_map_color.get() == "qc_status"
    assert target.navigated_to == "GREEN"
    assert target.col_visibility_applied
    assert target.refreshes == ["skiplist", "overview", "stations"]
    assert "recomputing statistics" not in target.lbl_status.text
    assert target.lbl_status.text.startswith("Session restored")


def test_session_validation_rejects_invalid_versions_types_and_cached_stats(tmp_path):
    h5_path = tmp_path / "source.h5"
    h5_path.touch()
    valid = SessionApp(h5_path)._session_state()

    invalid_sessions = []

    invalid = copy.deepcopy(valid)
    invalid["version"] = SESSION_VERSION + 1
    invalid_sessions.append((invalid, "unsupported session version"))

    invalid = copy.deepcopy(valid)
    invalid["skip_list"] = ["SKIP"]
    invalid_sessions.append((invalid, "skip_list must be an object"))

    invalid = copy.deepcopy(valid)
    invalid["green_list"] = "GREEN"
    invalid_sessions.append((invalid, "green_list must be an array"))

    invalid = copy.deepcopy(valid)
    del invalid["removal_list"]["SKIP"][0]["reason"]
    invalid_sessions.append((invalid, "removal_list.*missing reason"))

    invalid = copy.deepcopy(valid)
    invalid["cfg"]["hidden_assertions"] = "dup_ts"
    invalid_sessions.append((invalid, "hidden_assertions must be an array"))

    invalid = copy.deepcopy(valid)
    invalid["ov_col_vis"]["Name"] = 1
    invalid_sessions.append((invalid, "ov_col_vis must map"))

    invalid = copy.deepcopy(valid)
    invalid["all_stats"] = {"untrusted": True}
    invalid_sessions.append((invalid, "unexpected all_stats"))

    for session, message in invalid_sessions:
        with pytest.raises(SessionValidationError, match=message):
            validate_session_state(session)


def test_invalid_session_does_not_change_application_state(tmp_path):
    h5_path = tmp_path / "source.h5"
    h5_path.touch()
    app = SessionApp(h5_path)
    original_config = app.cfg
    original_skip = app.skip_list
    invalid = app._session_state()
    invalid["map_color"] = "not-a-map-mode"

    with pytest.raises(SessionValidationError, match="map_color"):
        app._restore_session(invalid)

    assert app.cfg is original_config
    assert app.skip_list is original_skip
    assert app.load_kwargs is None


def test_pickle_sessions_are_rejected_without_deserialization(tmp_path):
    legacy_path = tmp_path / "legacy.pkl"
    legacy_path.write_bytes(b"not even a valid pickle")

    assert AUTOSAVE_PATH.suffix == ".json"
    with pytest.raises(SessionValidationError, match="pickle sessions are not supported"):
        read_session_file(legacy_path)


def test_decision_export_writes_json_qc_snapshot_without_statistics(tmp_path):
    h5_path = tmp_path / "fire_weather_data.h5"
    h5_path.touch()
    app = SessionApp(h5_path)
    decision_path = tmp_path / "decisions.py"

    _, qc_path = SkiplistTabMixin._skip_export_write(app, decision_path)

    assert qc_path == tmp_path / "fire_QC.json"
    snapshot = json.loads(qc_path.read_text(encoding="utf-8"))
    assert "all_stats" not in snapshot
    validate_session_state(snapshot)
    assert not list(tmp_path.glob("*_QC.pkl"))
