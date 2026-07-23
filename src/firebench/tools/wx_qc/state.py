"""Shared issue-visibility and station-decision rules for weather-station QC."""


def issue_is_visible(issue: tuple, config: dict) -> bool:
    """Return whether an issue passes the configured severity and category filters."""
    severity, key, _message = issue
    if severity == "ERROR" and not config.get("show_errors", True):
        return False
    if severity == "WARN" and not config.get("show_warns", True):
        return False
    return not any(
        key == category or key.startswith(category) for category in config.get("hidden_assertions", set())
    )


def visible_issues(issues, config: dict) -> list:
    """Return issues that pass the configured severity and category filters."""
    return [issue for issue in issues if issue_is_visible(issue, config)]


def mark_stations_skipped(skip_list: dict, green_list: set, station_ids, reason: str) -> None:
    """Mark stations skipped and remove any conflicting greenlit decisions."""
    for station_id in station_ids:
        skip_list[station_id] = reason
        green_list.discard(station_id)


def mark_stations_greenlit(skip_list: dict, green_list: set, station_ids) -> None:
    """Mark stations greenlit and remove any conflicting skip decisions."""
    for station_id in station_ids:
        skip_list.pop(station_id, None)
        green_list.add(station_id)


def resolve_restored_decisions(skip_list, green_list) -> tuple[dict, set]:
    """Normalize restored decisions, keeping skip when both states contain a station."""
    restored_skip = dict(skip_list)
    restored_green = set(green_list)
    restored_green.difference_update(restored_skip)
    return restored_skip, restored_green
