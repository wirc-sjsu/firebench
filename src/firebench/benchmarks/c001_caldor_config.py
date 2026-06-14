from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytz

from firebench import standardize as fs


CASE_NAME = "Caldor 2021"
CASE_SHORT_NAME = "Caldor"
CASE_ID = "FB001"
DEFAULT_OBS_DATA_PATH = Path("Caldor.h5")
LOG_FILENAME = "Caldor.log"
DEFAULT_LOGGING_LEVEL = 20  # INFO
DEFAULT_VERBOSITY = 3
DEFAULT_AGGREGATION_SCHEME = "A"

DEFAULT_OUTPUT_PATH_JSON = Path(f"{CASE_SHORT_NAME}_rslt.json")
DEFAULT_SCORE_CARD_REPORT_PATH = Path(f"{CASE_SHORT_NAME}.pdf")

TZ_REF = pytz.timezone("US/Pacific")
FORECAST_HOURS = 48
HRRR_CYCLE_HOURS = (0, 6, 12, 18)

PERIMETER_TIMES = [
    "2021-08-17T20:20-07:00",
    "2021-08-18T20:30-07:00",
    "2021-08-19T20:45-07:00",
    "2021-08-20T20:20-07:00",
    "2021-08-21T21:15-07:00",
    "2021-08-24T22:07-07:00",
    "2021-08-26T03:30-06:00",
    "2021-08-26T22:15-06:00",
    "2021-08-27T00:22-06:00",
    "2021-08-28T21:30-06:00",
    "2021-08-29T22:32-07:00",
    "2021-08-30T21:09-07:00",
    "2021-08-31T21:08-07:00",
    "2021-09-01T21:12-07:00",
    "2021-09-03T00:40-07:00",
    "2021-09-04T23:29-07:00",
    "2021-09-05T23:41-07:00",
    "2021-09-06T23:09-07:00",
    "2021-09-07T22:40-07:00",
    "2021-09-08T22:33-07:00",
    "2021-09-10T23:34-07:00",
]


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Perimeter datetime is missing timezone: {value}")
    return parsed


def _localize_in_ref_tz(value: datetime) -> datetime:
    local_value = value.astimezone(TZ_REF).replace(tzinfo=None)
    return TZ_REF.localize(local_value)


def _perimeter_path(value: datetime) -> str:
    return f"/{fs.GEOPOLYGONS}/Caldor_{value.isoformat(timespec='minutes')}"


PERIMETER_DATETIMES = sorted(_parse_time(value) for value in PERIMETER_TIMES)
PERIMETER_PATHS = [_perimeter_path(value) for value in PERIMETER_DATETIMES]

CURATED_VALIDATION_WINDOWS = {
    "W1": {
        "period": (
            _localize_in_ref_tz(PERIMETER_DATETIMES[0]),
            _localize_in_ref_tz(PERIMETER_DATETIMES[-1]),
        ),
        "perimeters": [_perimeter_path(value) for value in PERIMETER_DATETIMES[1:]],
    },
    "W2": {
        "period": (
            _localize_in_ref_tz(PERIMETER_DATETIMES[2]),
            _localize_in_ref_tz(PERIMETER_DATETIMES[4]),
        ),
        "perimeters": [_perimeter_path(value) for value in PERIMETER_DATETIMES[3:5]],
    },
    "W3": {
        "period": (
            _localize_in_ref_tz(PERIMETER_DATETIMES[6]),
            _localize_in_ref_tz(PERIMETER_DATETIMES[9]),
        ),
        "perimeters": [_perimeter_path(value) for value in PERIMETER_DATETIMES[7:10]],
    },
    "W4": {
        "period": (
            _localize_in_ref_tz(PERIMETER_DATETIMES[9]),
            _localize_in_ref_tz(PERIMETER_DATETIMES[14]),
        ),
        "perimeters": [_perimeter_path(value) for value in PERIMETER_DATETIMES[10:15]],
    },
}

CURATED_PERIODS = {
    name: window["period"] for name, window in CURATED_VALIDATION_WINDOWS.items()
}
CURATED_PERIMETERS = {
    name: window["perimeters"] for name, window in CURATED_VALIDATION_WINDOWS.items()
}


def _hrrr_cycle_starts(first_time: datetime, last_time: datetime) -> list[datetime]:
    first_utc = first_time.astimezone(timezone.utc)
    last_utc = last_time.astimezone(timezone.utc)
    first_day = first_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    start_day = first_day - timedelta(hours=FORECAST_HOURS)
    end_day = last_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    starts: list[datetime] = []
    current_day = start_day
    while current_day <= end_day:
        for hour in HRRR_CYCLE_HOURS:
            starts.append(current_day + timedelta(hours=hour))
        current_day += timedelta(days=1)

    return starts


def _build_hrrr_validation_windows() -> dict[str, dict[str, tuple[datetime, datetime] | list[str]]]:
    windows = {}
    for start in _hrrr_cycle_starts(PERIMETER_DATETIMES[0], PERIMETER_DATETIMES[-1]):
        end = start + timedelta(hours=FORECAST_HOURS)
        contained = [
            perimeter_time
            for perimeter_time in PERIMETER_DATETIMES
            if start <= perimeter_time.astimezone(timezone.utc) <= end
        ]
        if len(contained) < 2:
            continue

        name = f"WH{len(windows) + 1}"
        windows[name] = {
            "period": (_localize_in_ref_tz(start), _localize_in_ref_tz(end)),
            "perimeters": [_perimeter_path(value) for value in contained[1:]],
        }
    return windows


HRRR_VALIDATION_WINDOWS = _build_hrrr_validation_windows()
HRRR_PERIODS = {name: window["period"] for name, window in HRRR_VALIDATION_WINDOWS.items()}
HRRR_PERIMETERS = {
    name: window["perimeters"] for name, window in HRRR_VALIDATION_WINDOWS.items()
}

WX_PERIOD_SETS = (
    {
        "name": "curated",
        "periods": CURATED_PERIODS,
        "aggregation_prefix": "WX",
        "all_aggregation": None,
    },
    {
        "name": "hrrr",
        "periods": HRRR_PERIODS,
        "aggregation_prefix": "WX_",
        "all_aggregation": "WX_WH_ALL",
    },
)

WX_SUMMARY_STATS = ("min", "mean", "max")
WX_TRUSTED_SOURCE_OPTIONS = (
    ("TSO", False),
    ("", True),
)
WX_VARIABLE_SPECS = (
    {
        "requirement": "R08",
        "label": "Air temp",
        "group_label": "Air Temp",
        "variable": "air_temperature",
        "common_unit": "degC",
        "norm_m": 5,
        "metric_set": "standard",
    },
    {
        "requirement": "R09",
        "label": "RH",
        "group_label": "RH",
        "variable": "relative_humidity",
        "common_unit": "percent",
        "norm_m": 15,
        "metric_set": "standard",
    },
    {
        "requirement": "R10",
        "label": "Wind Speed",
        "group_label": "Wind Speed",
        "variable": "wind_speed",
        "common_unit": "m/s",
        "norm_m": 5,
        "metric_set": "standard",
    },
    {
        "requirement": "R11",
        "label": "Wind Direction",
        "group_label": "Wind Direction",
        "variable": "wind_direction",
        "common_unit": "degree",
        "norm_m": 45,
        "metric_set": "wind_direction",
    },
    {
        "requirement": "R12",
        "label": "FMC 10h",
        "group_label": "FMC 10h",
        "variable": "fuel_moisture_content_10h",
        "common_unit": "percent",
        "norm_m": 5,
        "metric_set": "standard",
    },
)

CTX_SPEC = {
    ("agg_bin", "building_damage", "obs"): "Aggregate building damage dataset to binary classes for obs",
    ("agg_bin", "building_damage", "model"): "Aggregate building damage dataset to binary classes for model",
    ("agg_bin", "mtbs_severity", "obs"): "Aggregate mtbs severity dataset to binary classes for obs",
    ("agg_bin", "mtbs_severity", "model"): "Aggregate mtbs severity dataset to binary classes for model",
    (
        "mask",
        "landfire_canopy",
        "all",
    ): "LANDFIRE canopy mask using all canopy fields interpolated on benchmark field grid",
}
