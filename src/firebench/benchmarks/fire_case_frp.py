"""
The fire radiative power family of the generic cases (``fire_radiative_power``): the FRP satellites
observed against the band of FRP a model gives.

The observations are the fire detection streams of a standard file, read as one FRP total per
overpass or scan inside the case's frame (``firebench.standardize.frp_time_series``). The model output
gives, at its own times, the lowest and highest FRP it expects over the same frame,
``fire_radiative_power_lower`` and ``fire_radiative_power_upper`` in ``/time_series/fire_total`` by
default. The band is the model's uncertainty on how its heat release becomes FRP, chosen by its
adapter (WRF-SFIRE: the sensible heat flux divided by 5 to 10); FireBench converts nothing.

An observation is scored when its start is in the period, it saw at least ``min_observed_fraction`` of
its frame, it has an FRP total, and a model output time is at most ``max_time_offset`` from it. The
model's bounds are interpolated linearly in time to the observation's start, and held at the first or
last output time. An observation where neither side has fire (an FRP total of 0 and an upper bound of
0) is left out: it would agree whatever the model.

The KPIs are the share of observations inside the band, one per observing system (a set of
instruments, ``[fire_radiative_power.systems]`` of ``fire_case.toml``) so a system that looks often
does not outweigh one that looks rarely, then pooled over every stream, and the shares above and below
the band. A KPI with fewer than ``min_observations`` observations is not computed: its function returns
None and it is left out of its group.

``frp_values`` gives what these KPIs compare, for a figure: every observation with the reason it is not
scored, the model's band, and the position of each scored observation against it.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from h5py import File, Group

from .. import metrics as fm
from .. import standardize as fs
from .. import tools as ft
from ..standardize.fire_detections import GROUP as DETECTION_GROUP
from ..tools.namespace import StandardVariableNames as svn
from ..tools.units import ureg
from .fire_case_parameters import FireRadiativePowerParameters
from .fire_case_radar import _text, _times

MODEL_GROUP = f"/{fs.TIME_SERIES}/fire_total"
LOWER = svn.FIRE_RADIATIVE_POWER_LOWER.value
UPPER = svn.FIRE_RADIATIVE_POWER_UPPER.value
FRAME_KEYS = ("frame_west", "frame_south", "frame_east", "frame_north")


def model_requirements(group: str) -> dict[str, list[str]]:
    """The datasets of the model output the family reads, and the attributes each must have."""
    return {f"{group}/time": [], f"{group}/{LOWER}": ["units"], f"{group}/{UPPER}": ["units"]}


# ---------------------------
# What a standard file holds
# ---------------------------
def stream_instrument(h5: File, stream: str) -> str | None:
    """The instrument of a fire detection stream, or None when the file has no such stream."""
    group = h5.get(f"{DETECTION_GROUP}/{stream}")
    if not isinstance(group, Group) or "instrument" not in group.attrs:
        return None
    return _text(group.attrs["instrument"])


def stream_frame(h5: File, stream: str) -> tuple[float, float, float, float]:
    """The frame a stream was requested on: west, south, east, north, in degrees."""
    attrs = h5[f"{DETECTION_GROUP}/{stream}"].attrs
    return tuple(float(attrs[key]) for key in FRAME_KEYS)


def detection_span(h5: File) -> tuple[datetime, datetime] | None:
    """First and last observation start of the file's fire detection streams, or None."""
    starts = []
    for stream in fs.list_fire_detection_streams(h5):
        times = fs.frp_time_series(h5, stream).time
        if len(times):
            starts.extend((times.min(), times.max()))
    if not starts:
        return None
    return tuple(
        np.datetime64(value, "ms").item().replace(tzinfo=timezone.utc)
        for value in (min(starts), max(starts))
    )


def frp_systems(
    h5: File, parameters: FireRadiativePowerParameters
) -> tuple[dict[str, list[str]], list[str]]:
    """
    The streams of the file by observing system, in the order of the parameters, and the streams no
    system lists (by their instrument).
    """
    systems, unlisted = {}, []
    for stream in fs.list_fire_detection_streams(h5):
        system = parameters.system_of(stream_instrument(h5, stream) or "")
        if system is None:
            unlisted.append(stream)
        else:
            systems.setdefault(system.name, []).append(stream)
    ordered = {system.name: systems[system.name] for system in parameters.systems if system.name in systems}
    return ordered, unlisted


def common_frame(h5: File, streams: list[str]) -> list[float] | None:
    """The frame every stream of ``streams`` covers, or None when they share none."""
    frames = np.array([stream_frame(h5, stream) for stream in streams])
    west, south = frames[:, 0].max(), frames[:, 1].max()
    east, north = frames[:, 2].min(), frames[:, 3].min()
    if west >= east or south >= north:
        return None
    return [float(west), float(south), float(east), float(north)]


def _corners(frame) -> tuple[tuple[float, float], tuple[float, float]]:
    west, south, east, north = frame
    return (south, west), (north, east)


def has_fire(h5: File, streams: list[str], span, frame, parameters: FireRadiativePowerParameters) -> bool:
    """Whether some stream saw fire (an FRP total above 0) in the frame during ``span``."""
    for stream in streams:
        series = fs.frp_time_series(
            h5, stream, span[0], span[1], _corners(frame), min_confidence=parameters.min_confidence
        )
        if np.any(np.nan_to_num(series.frp_total) > 0):
            return True
    return False


def propose_frp(
    h5: File, window, parameters: FireRadiativePowerParameters
) -> tuple[dict | None, str | None]:
    """
    The keys of the family's entry but its periods (``systems``, ``frame``, ``model_group``) for a file,
    or None and why the family is left out; (None, None) when the file has no fire detection stream.
    """
    systems, unlisted = frp_systems(h5, parameters)
    streams = [stream for items in systems.values() for stream in items]
    if not streams:
        if not unlisted:
            return None, None
        return None, f"no observing system of the parameters lists the instruments of {', '.join(unlisted)}"
    frame = common_frame(h5, streams)
    if frame is None:
        return None, "the fire detection streams have no frame in common"
    if window is None or not has_fire(h5, streams, window, frame, parameters):
        return None, "no fire detection stream saw fire in the window"
    return {"systems": systems, "frame": frame, "model_group": MODEL_GROUP}, None


# ---------------------------
# Pairs
# ---------------------------
@dataclass
class FrpPairs:
    """The observations of a stream in a period that are scored, and the model's band at each."""

    stream: str
    time: np.ndarray  # datetime64[ms], UTC: observation start
    observed: np.ndarray  # MW
    lower: np.ndarray  # MW
    upper: np.ndarray  # MW


def model_band(model: File, model_group: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The model's times (datetime64[ms], sorted) and its lower and upper FRP there, in MW."""
    group = model[model_group]
    times = _times(group["time"])
    bounds = []
    for name in (LOWER, UPPER):
        dataset = group[name]
        values = np.asarray(dataset[()], dtype=np.float64)
        if values.shape != times.shape:
            raise ValueError(
                f"The model's `{model_group}/{name}` has the shape {values.shape}; its `time` has "
                f"{times.shape}. Give one value per output time."
            )
        bounds.append(ureg.Quantity(values, _text(dataset.attrs["units"])).to("MW").magnitude)
    lower, upper = bounds[0], bounds[1]
    finite = np.isfinite(lower) & np.isfinite(upper)
    if np.any(lower[finite] < 0) or np.any(lower[finite] > upper[finite]):
        raise ValueError(
            f"The model's FRP band in `{model_group}` must have 0 <= {LOWER} <= {UPPER} at every time."
        )
    order = np.argsort(times)
    return times[order], lower[order], upper[order]


@dataclass
class FrpObservations:  # pylint: disable=too-many-instance-attributes
    """
    Every observation of a stream in a period, the model's band at its start, and whether it is scored.

    ``reason`` says why an observation is not scored (None when it is), and ``observation_ok`` whether
    the observation alone allows it to be: False when it saw too little of its frame or has no FRP
    total, whatever the model.
    """

    stream: str
    time: np.ndarray  # datetime64[ms], UTC: observation start
    time_end: np.ndarray
    observed: np.ndarray  # MW: 0 without detection, NaN when no detection has an FRP
    observed_fraction: np.ndarray
    lower: np.ndarray  # MW, NaN where the model gives no band
    upper: np.ndarray
    kept: np.ndarray
    observation_ok: np.ndarray
    reason: list[str | None]

    def pairs(self) -> FrpPairs:
        """The observations that are scored."""
        keep = self.kept
        return FrpPairs(
            self.stream, self.time[keep], self.observed[keep], self.lower[keep], self.upper[keep]
        )


def _reasons(checks: list[tuple[np.ndarray, str | np.ndarray]], size: int) -> list[str | None]:
    """The first failed check of each observation, in the order of ``checks``."""
    reasons: list[str | None] = [None] * size
    for failed, text in checks:
        for index in np.flatnonzero(failed):
            if reasons[index] is None:
                reasons[index] = text if isinstance(text, str) else str(text[index])
    return reasons


def frp_observations(  # pylint: disable=too-many-arguments,too-many-locals
    model: File,
    obs: File,
    stream: str,
    period: tuple[datetime, datetime],
    frame,
    model_group: str,
    parameters: FireRadiativePowerParameters,
) -> FrpObservations:
    """Every observation of a stream and a period, and whether it is scored (see the module docstring)."""
    series = fs.frp_time_series(
        obs, stream, period[0], period[1], _corners(frame), min_confidence=parameters.min_confidence
    )
    model_times, model_lower, model_upper = model_band(model, model_group)
    observed = np.asarray(series.frp_total, dtype=np.float64)
    fraction = np.asarray(series.observed_fraction, dtype=np.float64)
    seen = np.nan_to_num(fraction, nan=-1.0) >= parameters.min_observed_fraction
    has_total = np.isfinite(observed)
    minimum = f"{parameters.min_observed_fraction:.0%}"
    checks = [
        (~has_total, "no FRP total: no detection of it has an FRP"),
        (
            ~seen,
            np.array(
                [
                    (
                        f"it saw {value:.0%} of its frame, less than {minimum}"
                        if np.isfinite(value)
                        else "the share of its frame it saw is unknown"
                    )
                    for value in fraction
                ],
                dtype=object,
            ),
        ),
    ]
    if model_times.size == 0:
        lower = upper = np.full(observed.shape, np.nan)
        near = np.zeros(observed.shape, dtype=bool)
        checks.append((~near, "the model gives no output time"))
    else:
        obs_ms = series.time.astype("datetime64[ms]").astype(np.int64).astype(np.float64)
        model_ms = model_times.astype(np.int64).astype(np.float64)
        after = np.clip(np.searchsorted(model_ms, obs_ms), 0, len(model_ms) - 1)
        before = np.clip(after - 1, 0, len(model_ms) - 1)
        offset = np.minimum(np.abs(model_ms[after] - obs_ms), np.abs(model_ms[before] - obs_ms))
        near = offset <= parameters.max_time_offset * 1000.0
        lower = np.interp(obs_ms, model_ms, model_lower)
        upper = np.interp(obs_ms, model_ms, model_upper)
        checks.append((~near, f"no model output time within {parameters.max_time_offset:g} s"))
    has_band = np.isfinite(lower) & np.isfinite(upper)
    no_fire = (observed == 0) & (upper == 0)
    checks += [(~has_band, "the model gives no band at its time"), (no_fire, "no fire on either side")]
    kept = has_total & seen & near & has_band & ~no_fire
    return FrpObservations(
        stream=stream,
        time=series.time,
        time_end=series.time_end,
        observed=observed,
        observed_fraction=fraction,
        lower=lower,
        upper=upper,
        kept=kept,
        observation_ok=has_total & seen,
        reason=_reasons(checks, len(observed)),
    )


def frp_pairs(  # pylint: disable=too-many-arguments
    model: File,
    obs: File,
    stream: str,
    period: tuple[datetime, datetime],
    frame,
    model_group: str,
    parameters: FireRadiativePowerParameters,
) -> FrpPairs:
    """The pairs of a stream and a period (see the module documentation)."""
    observations = frp_observations(model, obs, stream, period, frame, model_group, parameters)
    ft.logger.info(
        "fire radiative power of %s: %d of %d observations scored",
        stream,
        int(observations.kept.sum()),
        len(observations.observed),
    )
    return observations.pairs()


def _pairs(model, obs, ctx, stream, period_name, period, frame, model_group, parameters) -> FrpPairs:
    """The pairs of a stream and a period, computed once for every KPI that uses them."""
    cache = ctx.setdefault("fire_radiative_power", {})
    key = (stream, period_name)
    if key not in cache:
        cache[key] = frp_pairs(model, obs, stream, period, frame, model_group, parameters)
    return cache[key]


# ---------------------------
# KPIs
# ---------------------------
FRP_FRACTIONS = {
    "in_band": (fm.stats.fraction_in_band, False),
    "above": (fm.stats.fraction_above_band, True),
    "below": (fm.stats.fraction_below_band, True),
}


def bench_frp(  # pylint: disable=too-many-arguments
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    kpi: str,
    streams: list[str],
    period_name: str,
    period: tuple[datetime, datetime],
    frame,
    model_group: str,
    parameters: FireRadiativePowerParameters,
):
    """One KPI of the FRP family on the observations of ``streams`` in a period, scored from 0 to 100."""
    pairs = [
        _pairs(model_dataset, obs_dataset, ctx, stream, period_name, period, frame, model_group, parameters)
        for stream in streams
    ]
    observed = np.concatenate([item.observed for item in pairs])
    lower = np.concatenate([item.lower for item in pairs])
    upper = np.concatenate([item.upper for item in pairs])
    label = f"{kpi_name_custom} {period_name}"
    if observed.size < parameters.min_observations:
        ft.logger.warning(
            "Ignoring fire radiative power KPI %s: %d observation(s), fewer than %d.",
            label,
            observed.size,
            parameters.min_observations,
        )
        return None
    func, lower_is_better = FRP_FRACTIONS[kpi]
    value = func(observed, lower, upper)
    score = fm.kpi_norm_bounded_linear(1.0 - value if lower_is_better else value, 0, 1)
    ft.logger.info("%s: %f on %d observations", label, value, observed.size)
    return {kpi_name_custom: value, "Score": score}


# ---------------------------
# Values for figures
# ---------------------------
def _starts_in(times: np.ndarray, period: tuple[datetime, datetime]) -> np.ndarray:
    """The observations whose start is in the period, bounds included, as ``frp_time_series`` keeps them."""
    start, end = (
        np.datetime64(value.astimezone(timezone.utc).replace(tzinfo=None), "ms") for value in period
    )
    return (times >= start) & (times <= end)


def frp_values(  # pylint: disable=too-many-locals
    model: File,
    obs: File,
    entry: dict,
    periods: dict[str, tuple[datetime, datetime]],
    parameters: FireRadiativePowerParameters,
) -> dict:
    """
    What the KPIs of the family compare, for a figure: every observation of the entry's streams over
    the span of its periods, the model's band at its own times and at each observation, and the
    observations each period scores.

    ``observations`` holds one array per field, in the order of the streams of ``entry["systems"]``,
    then of time. ``position`` is where a scored observation lies against the band (``band_position``,
    the rule of the KPIs: "in", "above", or "below"), and "" for one that is not scored, whose
    ``reason`` says why. ``periods`` gives, for each period of the entry, the indices of the
    observations it scores: the fraction KPIs of the period are the shares of their positions.
    """
    names = list(entry["periods"])
    span = (min(periods[name][0] for name in names), max(periods[name][1] for name in names))
    labels = {system.name: system.label for system in parameters.systems}
    model_times, model_lower, model_upper = model_band(model, entry["model_group"])
    parts, fields = [], {"stream": [], "system": [], "instrument": [], "satellite": []}
    for system, streams in entry["systems"].items():
        for stream in streams:
            item = frp_observations(
                model, obs, stream, span, entry["frame"], entry["model_group"], parameters
            )
            parts.append(item)
            attrs = obs[f"{DETECTION_GROUP}/{stream}"].attrs
            for key, value in (
                ("stream", stream),
                ("system", system),
                ("instrument", _text(attrs.get("instrument", ""))),
                ("satellite", _text(attrs.get("satellite", ""))),
            ):
                fields[key].extend([value] * len(item.observed))

    def joined(name: str, dtype) -> np.ndarray:
        arrays = [np.asarray(getattr(item, name)) for item in parts]
        return np.concatenate(arrays).astype(dtype) if arrays else np.array([], dtype=dtype)

    time = joined("time", "datetime64[ms]")
    observed, lower, upper = (joined(name, np.float64) for name in ("observed", "lower", "upper"))
    kept = joined("kept", bool)
    position = np.full(observed.shape, "", dtype="<U5")
    if kept.any():
        position[kept] = fm.stats.band_position(observed[kept], lower[kept], upper[kept])
    return {
        "units": "MW",
        "frame": [float(value) for value in entry["frame"]],
        "model_group": entry["model_group"],
        "systems": [
            {"name": name, "label": labels.get(name, name), "streams": list(streams)}
            for name, streams in entry["systems"].items()
        ],
        "model": {"time": model_times, "lower": model_lower, "upper": model_upper},
        "observations": {
            **{key: np.array(value, dtype=object) for key, value in fields.items()},
            "time": time,
            "time_end": joined("time_end", "datetime64[ms]"),
            "frp_total": observed,
            "observed_fraction": joined("observed_fraction", np.float64),
            "lower": lower,
            "upper": upper,
            "kept": kept,
            "observation_ok": joined("observation_ok", bool),
            "reason": [reason for item in parts for reason in item.reason],
            "position": position,
        },
        "periods": [
            {
                "period": name,
                "start": periods[name][0],
                "end": periods[name][1],
                "scored": np.flatnonzero(kept & _starts_in(time, periods[name])),
            }
            for name in names
        ],
    }
