"""
A forecast model over a long period, stitched from successive cycles (``firebench wx stitch``).

No forecast cycle covers a study period of several days or weeks (Caldor's ``P01`` is 24 days). A
**stitch rule** takes, from cycles at given UTC hours, a fixed range of leads, and joins them into one
continuous station series: for example leads 1-6 of the 00, 06, 12 and 18 UTC cycles (the freshest
forecast at each hour), or leads 25-48 of the 00 UTC cycle (the forecast made the day before).

1. ``stitch_plan`` gives, for every valid hour the period needs, the cycle and lead it comes from:
   the cycle of the rule with the shortest lead in the range. It refuses a rule that leaves an hour
   without a cycle and a cycle the model's archive does not hold. Hours are grouped into segments,
   one per cycle.
2. ``fetch_segment`` downloads the hours a segment needs (``f00`` for the terrain, and its leads),
   samples them at the stations of the observation file with the model's adapter, and writes one
   station file per cycle, as ``firebench wx run`` does.
3. ``stitch_station_files`` joins the segments of each station and brings the hourly series to the
   observation times within the period, so that a case benchmark that pairs model and observation
   samples one by one (Caldor's ``P01_T``-``P04_T``) can score it. Every choice is declared in the
   file: the rule, the cycles, the leads, the model versions, and the time interpolation.

The time interpolation is linear between hourly valid times; the wind direction is interpolated
through the sine and cosine of its angle. An observation time outside the stitched hours, or next to
a missing value, gets NaN. An observed variable the model does not forecast is written as NaN, with
an attribute saying so: a benchmark then scores it as missing instead of stopping.
"""

import importlib
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import hdf5plugin  # pylint: disable=unused-import  # registers the Zstd filter of observation files
import h5py
import numpy as np

from firebench import __version__ as fb_version
from firebench.acquisition.forecast_models import get_model
from firebench.acquisition.hrrr.forecast import CycleFiles
from firebench.benchmarks.wx_common import get_mask_from_period
from firebench.standardize.files import new_std_file
from firebench.standardize.tools import validate_h5_std
from firebench.standardize.std_file_info import TIME_SERIES

HOUR = timedelta(hours=1)
TIME_INTERPOLATION = (
    "linear in time between the hourly valid times of the stitched series, to each observation time "
    "of the period; wind direction through the sine and cosine of its angle; NaN outside the "
    "stitched hours"
)
NOT_FORECAST = "not_forecast"


class StitchError(ValueError):
    """A stitch FireBench refuses, with the reason."""


@dataclass(frozen=True)
class StitchSegment:
    """The hours one cycle gives to a stitched series: leads ``first_lead`` to ``last_lead``."""

    cycle: datetime
    first_lead: int
    last_lead: int

    @property
    def label(self) -> str:
        return f"{self.cycle:%Y%m%d%H}"

    @property
    def forecast_hours(self) -> tuple[int, ...]:
        """The forecast hours to download: f00, which carries the terrain, and the leads."""
        return tuple(sorted({0, *range(self.first_lead, self.last_lead + 1)}))

    @property
    def valid_from(self) -> datetime:
        return self.cycle + timedelta(hours=self.first_lead)

    @property
    def valid_to(self) -> datetime:
        return self.cycle + timedelta(hours=self.last_lead)


@dataclass(frozen=True)
class StitchPlan:
    """The segments of a stitched series over ``[start, end]``, and the estimated download."""

    model: str
    start: datetime
    end: datetime
    cycle_hours: tuple[int, ...]
    leads: tuple[int, int]
    segments: tuple[StitchSegment, ...]
    download_mb: float

    @property
    def rule(self) -> dict:
        return {"cycle_hours": list(self.cycle_hours), "leads": list(self.leads)}

    def as_dict(self) -> dict:
        """A JSON-serializable description of the plan."""
        return {
            "model": self.model,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "rule": self.rule,
            "segments": [
                {
                    "cycle": segment.cycle.isoformat(),
                    "first_lead": segment.first_lead,
                    "last_lead": segment.last_lead,
                }
                for segment in self.segments
            ],
            "download_mb": self.download_mb,
        }


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise StitchError(f"{label} {value.isoformat()} has no time zone")
    return value.astimezone(timezone.utc)


def _floor_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _ceil_hour(value: datetime) -> datetime:
    floor = _floor_hour(value)
    return floor if floor == value else floor + HOUR


def stitch_plan(
    model_name: str,
    start: datetime,
    end: datetime,
    cycle_hours,
    leads,
) -> StitchPlan:
    """
    The cycle and leads of every valid hour from the hour at or before ``start`` to the hour at or
    after ``end``, so that every time of the period lies between two stitched hours.

    Each valid hour comes from the cycle of ``cycle_hours`` (UTC) with the shortest lead within
    ``leads`` (``[first, last]`` hours). Raises ``StitchError`` when an hour has no such cycle, or
    when the model's archive does not hold a cycle or its leads.
    """
    model = get_model(model_name)
    start, end = _utc(start, "start"), _utc(end, "end")
    if end <= start:
        raise StitchError(f"the period ends ({end.isoformat()}) before it starts ({start.isoformat()})")
    hours = sorted({int(hour) for hour in cycle_hours})
    if not hours or any(not 0 <= hour <= 23 for hour in hours):
        raise StitchError("cycle_hours must be UTC hours between 0 and 23")
    first, last = (int(value) for value in leads)
    if not 1 <= first <= last:
        raise StitchError(f"leads {[first, last]} must satisfy 1 <= first <= last (hours)")

    leads_by_cycle: dict[datetime, list[int]] = {}
    valid = _floor_hour(start)
    while valid <= _ceil_hour(end):
        lead = next(
            (lead for lead in range(first, last + 1) if (valid - timedelta(hours=lead)).hour in hours),
            None,
        )
        if lead is None:
            raise StitchError(
                f"no {'/'.join(f'{hour:02d}' for hour in hours)}Z cycle gives {valid:%Y-%m-%d %H}Z at a "
                f"lead of {first} to {last} h: the leads must span the time between two cycles"
            )
        leads_by_cycle.setdefault(valid - timedelta(hours=lead), []).append(lead)
        valid += HOUR

    segments = []
    for cycle, cycle_leads in sorted(leads_by_cycle.items()):
        segment = StitchSegment(cycle, min(cycle_leads), max(cycle_leads))
        try:
            max_hour = model.forecast.max_forecast_hour(cycle)
            output = set(model.forecast.output_hours(cycle))
        except ValueError as error:
            raise StitchError(str(error)) from None
        if segment.last_lead > max_hour:
            raise StitchError(
                f"{model.name} cycle {cycle:%Y-%m-%d %HZ} reaches {max_hour} h, not the lead "
                f"{segment.last_lead} h of the rule"
            )
        lacking = [hour for hour in segment.forecast_hours if hour not in output]
        if lacking:
            raise StitchError(
                f"{model.name} cycle {cycle:%Y-%m-%d %HZ} has no output at forecast hour(s) {lacking}: "
                "a stitched series needs every hour"
            )
        segments.append(segment)

    download = sum(
        model.file_mb[0] + model.file_mb[1] * (segment.last_lead - segment.first_lead + 1)
        for segment in segments
    )
    return StitchPlan(
        model=model.name,
        start=start,
        end=end,
        cycle_hours=tuple(hours),
        leads=(first, last),
        segments=tuple(segments),
        download_mb=round(download, 1),
    )


def fetch_segment(  # pylint: disable=too-many-arguments
    model_name: str,
    segment: StitchSegment,
    obs_h5_path: Path,
    out_h5_path: Path,
    *,
    cache_root: Path | None = None,
    workers: int = 8,
    keep_grib: bool = False,
    read=None,
) -> dict:
    """
    Download the forecast hours of ``segment`` and sample them at the stations of ``obs_h5_path``
    with the model's adapter, into ``out_h5_path``; returns the adapter's summary.

    Raises ``StitchError`` when the archive lacks one of the hours. Unless ``keep_grib``, the GRIB
    files are deleted once sampled.
    """
    model = get_model(model_name)
    hours = segment.forecast_hours
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"{model.name.lower()}-stitch") as pool:
        futures = {
            fxx: pool.submit(model.forecast.fetch_file, segment.cycle, fxx, cache_root=cache_root)
            for fxx in hours
        }
        files, missing = {}, []
        for fxx, future in futures.items():
            try:
                files[fxx] = future.result()
            except FileNotFoundError:
                missing.append(fxx)
    try:
        if missing:
            raise StitchError(
                f"{model.name} cycle {segment.cycle:%Y-%m-%d %HZ} lacks forecast hour(s) {missing} "
                "in the archive"
            )
        cycle_files = CycleFiles(segment.cycle, segment.last_lead, files=files, hours=hours)
        adapter = importlib.import_module(model.adapter_module)
        kwargs = {"read": read} if read is not None else {}
        return adapter.build_station_file(Path(obs_h5_path), cycle_files, Path(out_h5_path), **kwargs)
    finally:
        if not keep_grib:
            for path in files.values():
                Path(path).unlink(missing_ok=True)


@dataclass
class _StationSeries:
    times: list = field(default_factory=list)
    values: dict = field(default_factory=dict)


def _epoch_seconds(time_dataset) -> np.ndarray:
    origin = datetime.fromisoformat(_text(time_dataset.attrs["time_origin"]))
    units = _text(time_dataset.attrs["time_units"])
    scale = {"s": 1.0, "second": 1.0, "min": 60.0, "minute": 60.0, "h": 3600.0, "hour": 3600.0}
    if units not in scale:
        raise StitchError(f"time units '{units}' of {time_dataset.name} are not s, min or h")
    return origin.timestamp() + np.asarray(time_dataset[:], dtype=np.float64) * scale[units]


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _read_segments(plan: StitchPlan, segment_files: dict) -> tuple[dict, dict, dict, dict]:
    """Per station: the hourly series of the plan's leads; the attributes to carry over; and the
    model version of each cycle (the adapter's ``<model>_version``)."""
    series: dict[str, _StationSeries] = {}
    variable_attrs: dict[str, dict[str, dict]] = {}
    station_attrs: dict[str, dict] = {}
    versions: dict[str, dict] = {}
    for segment in plan.segments:
        path = segment_files.get(segment.label)
        if path is None:
            raise StitchError(f"no station file for cycle {segment.label}")
        with h5py.File(path, "r") as h5:
            version = h5.attrs.get(f"{plan.model.lower()}_version")
            versions[segment.label] = None if version is None else _text(version)
            for station, group in h5[TIME_SERIES].items():
                lead = np.asarray(group["time"][:], dtype=np.float64) / 3600.0
                keep = (lead >= segment.first_lead) & (lead <= segment.last_lead)
                entry = series.setdefault(station, _StationSeries())
                entry.times.append(_epoch_seconds(group["time"])[keep])
                station_attrs.setdefault(station, dict(group.attrs))
                for variable, dataset in group.items():
                    if variable == "time":
                        continue
                    entry.values.setdefault(variable, []).append(
                        np.asarray(dataset[:], dtype=np.float64)[keep]
                    )
                    attrs = dict(dataset.attrs)
                    known = variable_attrs.setdefault(station, {}).setdefault(variable, attrs)
                    if known.get("sensor_height") != attrs.get("sensor_height") or known.get(
                        "units"
                    ) != attrs.get("units"):
                        raise StitchError(
                            f"{station} {variable}: cycle {segment.label} declares another height or unit "
                            "than an earlier cycle"
                        )
    return series, variable_attrs, station_attrs, versions


def _interpolate(variable: str, t_obs: np.ndarray, t_model: np.ndarray, values: np.ndarray) -> np.ndarray:
    result = np.full(t_obs.shape, np.nan)
    inside = (t_obs >= t_model[0]) & (t_obs <= t_model[-1])
    if variable == "wind_direction":
        angle = np.deg2rad(values)
        sine = np.interp(t_obs[inside], t_model, np.sin(angle))
        cosine = np.interp(t_obs[inside], t_model, np.cos(angle))
        result[inside] = np.rad2deg(np.arctan2(sine, cosine)) % 360.0
    else:
        result[inside] = np.interp(t_obs[inside], t_model, values)
    return result


def stitch_station_files(  # pylint: disable=too-many-locals
    plan: StitchPlan,
    segment_files: dict,
    obs_h5_path: Path,
    out_h5_path: Path,
    *,
    name: str | None = None,
) -> dict:
    """
    Join the station files of ``plan``'s segments (``{segment.label: path}``, written by
    ``fetch_segment``) into one model file over the plan's period, at the observation times of
    ``obs_h5_path``; returns a summary.

    Each station of the observation file gets its observation times within ``[plan.start,
    plan.end]`` (closed, as the case benchmarks select them) and, for every variable it observes,
    the stitched model values at those times. A variable the model does not forecast is NaN.
    """
    series, variable_attrs, station_attrs, versions = _read_segments(plan, segment_files)
    expected = int(round((_ceil_hour(plan.end) - _floor_hour(plan.start)) / HOUR)) + 1
    period = (plan.start, plan.end)
    out_h5_path = Path(out_h5_path)
    out_h5_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{out_h5_path.stem}.", suffix=".h5", dir=out_h5_path.parent)
    os.close(fd)
    os.unlink(tmp_name)
    summary = {"stations": 0, "samples": 0, "not_forecast": {}, "hours": expected}
    try:
        with (
            h5py.File(obs_h5_path, "r") as obs,
            new_std_file(tmp_name, f"FireBench {plan.model} stitch") as out,
        ):
            out.attrs["model_name"] = name or f"{plan.model} stitched"
            out.attrs["description"] = (
                f"{plan.model} forecasts stitched over {plan.start:%Y-%m-%d %H:%M}Z to "
                f"{plan.end:%Y-%m-%d %H:%M}Z: leads {plan.leads[0]}-{plan.leads[1]} h of the "
                f"{'/'.join(f'{hour:02d}' for hour in plan.cycle_hours)}Z cycles"
            )
            out.attrs["stitch_plan"] = json.dumps(plan.as_dict(), sort_keys=True)
            out.attrs["stitch_model_versions"] = json.dumps(versions, sort_keys=True)
            out.attrs["time_interpolation"] = TIME_INTERPOLATION
            out.attrs["observation_file"] = Path(obs_h5_path).name
            out.attrs["adapter_version"] = fb_version
            for station, group in obs[TIME_SERIES].items():
                if station not in series:
                    raise StitchError(
                        f"{station} of the observation file is missing from the station files"
                    )
                entry = series[station]
                t_model = np.concatenate(entry.times)
                order = np.argsort(t_model)
                t_model = t_model[order]
                if t_model.size != expected or np.any(np.diff(t_model) != 3600.0):
                    raise StitchError(
                        f"{station}: the segments give {t_model.size} hourly values, not the {expected} "
                        "consecutive hours of the plan"
                    )
                mask = get_mask_from_period(obs, f"{TIME_SERIES}/{station}", period)
                t_obs = _epoch_seconds(group["time"])[mask]
                target = out.create_group(f"{TIME_SERIES}/{station}")
                for key, value in station_attrs[station].items():
                    target.attrs[key] = value
                time = target.create_dataset("time", data=np.asarray(group["time"][:])[mask])
                for key in ("time_origin", "time_units"):
                    time.attrs[key] = group["time"].attrs[key]
                for variable in group:
                    if variable == "time":
                        continue
                    if variable in entry.values:
                        values = np.concatenate(entry.values[variable])[order]
                        dataset = target.create_dataset(
                            variable, data=_interpolate(variable, t_obs, t_model, values)
                        )
                        for key, value in variable_attrs[station][variable].items():
                            dataset.attrs[key] = value
                    else:
                        dataset = target.create_dataset(variable, data=np.full(t_obs.shape, np.nan))
                        dataset.attrs["units"] = group[variable].attrs["units"]
                        dataset.attrs[NOT_FORECAST] = f"{plan.model} does not forecast {variable}: NaN"
                        summary["not_forecast"][variable] = summary["not_forecast"].get(variable, 0) + 1
                summary["stations"] += 1
                summary["samples"] += int(t_obs.size)
            validate_h5_std(out)
        os.replace(tmp_name, out_h5_path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return summary
