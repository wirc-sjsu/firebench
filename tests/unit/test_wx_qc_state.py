"""Non-GUI checks for weather-station QC issue and decision state."""

from firebench.tools.wx_qc.constants import default_config
from firebench.tools.wx_qc.state import (
    issue_is_visible,
    mark_stations_greenlit,
    mark_stations_skipped,
    resolve_restored_decisions,
    visible_issues,
)

ISSUES = [
    ("ERROR", "time_axis", "invalid timestamps"),
    ("ERROR", "hi:air_temperature", "temperature too high"),
    ("WARN", "frozen:wind_speed", "wind speed frozen"),
]


def test_issue_visibility_applies_severity_and_category_filters():
    config = default_config()
    assert visible_issues(ISSUES, config) == ISSUES

    config["show_errors"] = False
    assert visible_issues(ISSUES, config) == [ISSUES[2]]

    config["show_errors"] = True
    config["show_warns"] = False
    config["hidden_assertions"] = {"hi:"}
    assert visible_issues(ISSUES, config) == [ISSUES[0]]
    assert not issue_is_visible(ISSUES[1], config)


def test_marking_skipped_removes_greenlit_for_single_and_batch_actions():
    skip_list = {}
    green_list = {"A", "B", "C"}

    mark_stations_skipped(skip_list, green_list, ("A",), "single")
    mark_stations_skipped(skip_list, green_list, ("B", "C"), "batch")

    assert skip_list == {"A": "single", "B": "batch", "C": "batch"}
    assert green_list == set()


def test_marking_greenlit_removes_skipped_for_single_and_batch_actions():
    skip_list = {"A": "old", "B": "old", "C": "old"}
    green_list = set()

    mark_stations_greenlit(skip_list, green_list, ("A",))
    mark_stations_greenlit(skip_list, green_list, ("B", "C"))

    assert skip_list == {}
    assert green_list == {"A", "B", "C"}


def test_restored_conflict_keeps_skip_decision():
    source_skip = {"A": "reject", "B": "reject"}
    source_green = ["B", "C"]

    skip_list, green_list = resolve_restored_decisions(source_skip, source_green)

    assert skip_list == source_skip
    assert green_list == {"C"}
