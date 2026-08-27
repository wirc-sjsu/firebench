import numpy as np
import numba
from numba.core.errors import NumbaError
import h5py

# Registers HDF5 compression filters on import.
import hdf5plugin  # noqa: F401  # pylint: disable=unused-import

from .constants import (
    DROPOUT_MIN_PTS,
    GAP_DT_RATIO,
    FUEL_MOISTURE_FROZEN_MIN_RUN,
    OUTAGE_RUN_FACTOR,
    DEFAULT_MAX_VAR_OUTAGE_MIN,
    DEFAULT_FULL_OUTAGE_MIN,
)
from .time_axis import TimeAxisError, parse_h5_time_axis


def _parse_station_group(grp, stid):
    """Parse HDF5 station group into station dict.

    Shared parser for bulk and incremental loaders. Extracts metadata,
    time array, and all sensor variables from the H5 group.

    Args:
        grp (h5py.Group): HDF5 group for one station.
        stid (str): Station identifier (e.g., "KORD").

    Returns:
        dict: Station dict with keys: stid (str), name (str), lat (float,
            degrees), lon (float, degrees), alt (float, meters), state (str),
            timezone (str), provider (str), times (np.ndarray, dtype=datetime64[us]
            or float64), rel_min (np.ndarray, dtype=float64, minutes since H5
            time_origin), time_axis_error (str or None), variables
            (dict[str, np.ndarray], one float64 array per sensor, NaN = missing
            sample), var_units (dict[str, str]).
    """
    attrs = dict(grp.attrs)
    try:
        times, rel_min = parse_h5_time_axis(grp["time"])
        time_axis_error = None
    except TimeAxisError as exc:
        # Preserve the legacy relative-minute fallback so Phase 2 remains a
        # structural refactor. Phase 3 consumes this error to disable invalid
        # cadence/outage derivatives and expose a QC issue.
        rel_min = np.asarray(grp["time"][:], dtype=np.float64)
        times = rel_min
        time_axis_error = str(exc)
    variables, var_units = {}, {}
    for ds in grp:
        if ds == "time":
            continue
        variables[ds] = grp[ds][:]
        var_units[ds] = grp[ds].attrs.get("units", "")
    return {
        "stid": stid,
        "name": attrs.get("name", stid),
        "lat": float(attrs.get("position_lat", 0.0)),
        "lon": float(attrs.get("position_lon", 0.0)),
        "alt": float(attrs.get("position_alt", 0.0)),
        "state": attrs.get("state", ""),
        "timezone": attrs.get("timezone", ""),
        "provider": attrs.get("providers", ""),
        "times": times,
        "rel_min": rel_min,
        "time_axis_error": time_axis_error,
        "variables": variables,
        "var_units": var_units,
    }


def load_h5(path):
    """Load all stations from an HDF5 file in one pass.

    Args:
        path (str): File path to HDF5 data file.

    Returns:
        dict[str, dict]: Mapping of stid -> station dict. Empty dict if file
            has no time_series group.
    """
    stations = {}
    with h5py.File(path, "r") as f:
        ts_grp = f.get("time_series")
        if ts_grp is None:
            return stations
        for gname in ts_grp:
            stid = gname.removeprefix("station_")
            stations[stid] = _parse_station_group(ts_grp[gname], stid)
    return stations


def iter_h5_stations(path):
    """Incrementally yield stations from HDF5 file, one at a time.

    Allows UI updates between stations during large file processing.
    Yields (stid, station_dict) tuples. Closes file after iteration.

    Args:
        path (str): File path to HDF5 data file.

    Yields:
        tuple: (stid (str), station_dict (dict)). Station dict structure
            same as load_h5 return value.
    """
    with h5py.File(path, "r") as f:
        ts_grp = f.get("time_series")
        if ts_grp is None:
            return
        for gname in ts_grp:
            stid = gname.removeprefix("station_")
            yield stid, _parse_station_group(ts_grp[gname], stid)


@numba.njit(cache=True)
def _longest_nan_run(nan_mask):
    """Find longest contiguous run of True values in bool array.

    Args:
        nan_mask (np.ndarray, dtype=bool): Boolean mask where True indicates
            missing/NaN samples.

    Returns:
        int: Length of longest contiguous True run, in sample count.
    """
    gap = 0
    cur = 0
    for i in range(len(nan_mask)):
        cur = cur + 1 if nan_mask[i] else 0
        if cur > gap:
            gap = cur
    return gap


@numba.njit(cache=True)
def _outage_run_metrics(down, eligible, deltas_min, thresh_min):
    """Return longest and cumulative qualifying outage-run minutes.

    An interval is eligible only when both endpoints are eligible. Within an
    eligible interval, both endpoints being down or the interval itself meeting
    the outage threshold makes it part of the current outage run.
    """
    longest = 0.0
    cumulative = 0.0
    run = 0.0
    for i in range(len(deltas_min)):
        interval_eligible = eligible[i] and eligible[i + 1]
        interval_down = interval_eligible and ((down[i] and down[i + 1]) or deltas_min[i] >= thresh_min)
        if interval_down:
            run += deltas_min[i]
        else:
            if run >= thresh_min:
                longest = max(longest, run)
                cumulative += run
            run = 0.0
    if run >= thresh_min:
        longest = max(longest, run)
        cumulative += run
    return longest, cumulative


@numba.njit(cache=True)
def _longest_frozen_run(values, break_before):
    """Find the longest contiguous repeated-value run.

    Args:
        values (np.ndarray, dtype=float64): Sensor readings, including NaNs.
        break_before (np.ndarray, dtype=bool): True where a qualifying temporal
            gap separates a sample from its predecessor.

    Returns:
        tuple: (frozen (int), frozen_val (float)). frozen = length of longest
            equal-value run in sample count. frozen_val = the repeated value,
            or NaN if no frozen run found.
    """
    frozen = 0
    frozen_val = np.nan
    n = len(values)
    if n > 1:
        cur_f = 1
        cur_val = values[0]
        for i in range(1, n):
            if (
                break_before[i]
                or np.isnan(values[i])
                or np.isnan(values[i - 1])
                or values[i] != values[i - 1]
            ):
                cur_f = 1
                cur_val = values[i]
            else:
                cur_f += 1
            if cur_f > frozen:
                frozen = cur_f
                frozen_val = cur_val
    return frozen, frozen_val


@numba.njit(cache=True)
def _longest_true_run(mask, break_before):
    """Return the longest contiguous True run, respecting temporal breaks."""
    longest = 0
    current = 0
    for i in range(len(mask)):
        if break_before[i]:
            current = 0
        if mask[i]:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _temporal_breaks(n_pts, deltas_min, avg_freq, factor=OUTAGE_RUN_FACTOR):
    """Return a point-aligned mask that breaks runs after qualifying gaps."""
    breaks = np.zeros(n_pts, dtype=np.bool_)
    if n_pts > 1 and deltas_min is not None and avg_freq and avg_freq > 0:
        breaks[1:] = np.asarray(deltas_min) >= factor * avg_freq
    return breaks


def _var_stat_block(data, avg_freq, deltas_min=None):
    """Compute statistics for one sensor variable.

    Args:
        data (np.ndarray, dtype=float64): Sensor readings, NaN = missing sample.
        avg_freq (float or None): Valid average sampling frequency in minutes,
            used for gap qualification and display conversions.
        deltas_min (np.ndarray or None): Valid consecutive time differences.
            Qualifying gaps break frozen runs.

    Returns:
        dict: Statistics dict with keys: nan_ct (int, count of NaN), nan_pct
            (float, 0-100), min/max/mean/std (float or None), longest_gap_pts
            (int, samples), longest_gap_hr (float or None, hours),
            longest_frozen (int, samples), longest_frozen_val (float or None).
    """
    nm = np.isnan(data)
    nan_ct = int(nm.sum())
    nan_pct = 100.0 * nan_ct / len(data) if len(data) else 0.0
    valid = data[~nm]
    gap = _longest_nan_run(nm)
    breaks = _temporal_breaks(len(data), deltas_min, avg_freq)
    frozen, frozen_val_raw = _longest_frozen_run(np.asarray(data, dtype=np.float64), breaks)
    frozen_val = None if frozen == 0 or np.isnan(frozen_val_raw) else float(frozen_val_raw)
    return {
        "nan_ct": nan_ct,
        "nan_pct": nan_pct,
        "min": float(valid.min()) if len(valid) else None,
        "max": float(valid.max()) if len(valid) else None,
        "mean": float(valid.mean()) if len(valid) else None,
        "std": float(valid.std()) if len(valid) else None,
        "longest_gap_pts": int(gap),
        "longest_gap_hr": (gap * avg_freq / 60.0) if avg_freq else None,
        "longest_frozen": int(frozen),
        "longest_frozen_val": frozen_val,
    }


def compute_stats(st):
    """Compute full statistics dict for a station.

    Includes time-axis validity and timing metrics plus per-variable raw NaN,
    value-distribution, contiguous frozen-run, and missing-streak statistics.
    Cadence derivatives are unavailable when timestamps are invalid, duplicate,
    or decreasing.
    For wind_direction/gust when wind_speed exists: adds wd/gust NaN% conditional
    on wind_speed > 0.

    Args:
        st (dict): Station dict (from load_h5 or iter_h5_stations).

    Returns:
        dict: Stats dict with "_time" key (timing/monotonicity metrics) and
            one key per variable (containing nan_ct, nan_pct, min/max/mean/std,
            longest_gap_pts, longest_gap_hr, longest_frozen, longest_frozen_val,
            and optionally wd/gust NaN% conditional on wind_speed > 0).
    """
    times = st["times"]
    n = len(times)
    time_array = np.asarray(times)
    if np.issubdtype(time_array.dtype, np.datetime64):
        time_samples_valid = not bool(np.isnat(time_array).any())
    elif np.issubdtype(time_array.dtype, np.number):
        time_samples_valid = bool(np.isfinite(time_array).all())
    else:
        time_samples_valid = True
    deltas = None
    time_axis_error = st.get("time_axis_error")
    if time_axis_error is None and not time_samples_valid:
        time_axis_error = "time axis contains NaT or non-finite values"
    if n > 1:
        rel_min = st.get("rel_min")
        if rel_min is not None and len(rel_min) == n:
            # Use rel_min deltas to avoid Python datetime subtraction cost.
            deltas = np.diff(np.asarray(rel_min, dtype=np.float64))
        else:
            deltas = _deltas_minutes(times)
        n_neg = int(np.sum(deltas < 0))
        n_dup = n - len(set(times))
        finite_deltas = bool(np.all(np.isfinite(deltas)))
        if time_axis_error is None and not finite_deltas:
            time_axis_error = "time axis contains non-finite intervals"
        time_axis_valid = (
            time_axis_error is None and time_samples_valid and finite_deltas and n_neg == 0 and n_dup == 0
        )
        avg_freq = float(np.median(deltas)) if time_axis_valid else None
        max_dt = float(deltas.max()) if time_axis_valid else None
        monotonic = time_axis_valid
        dup_ts = n_dup > 0
    else:
        avg_freq = None
        max_dt = None
        time_axis_valid = time_axis_error is None and time_samples_valid
        monotonic = time_axis_valid
        dup_ts = False
        n_neg = 0
        n_dup = 0

    result = {
        "_time": {
            "n_pts": n,
            "avg_freq_min": avg_freq,
            "max_dt_min": max_dt,
            "monotonic": monotonic,
            "dup_ts": dup_ts,
            "n_neg_deltas": n_neg,
            "n_dup_ts": n_dup,
            "time_axis_valid": time_axis_valid,
            "time_axis_error": time_axis_error,
        }
    }

    for vname, data in st["variables"].items():
        result[vname] = _var_stat_block(data, avg_freq, deltas if time_axis_valid else None)

    vd = st["variables"]
    ws = vd.get("wind_speed")
    if ws is not None:
        for gated_var, field in [
            ("wind_direction", "wd_nan_ws_pos_pct"),
            ("wind_gust", "gust_nan_ws_pos_pct"),
        ]:
            if gated_var in vd and gated_var in result:
                result[gated_var][field] = _ws_gated_nan_pct(vd[gated_var], ws)

    return result


def _ws_gated_nan_pct(data, ws):
    """Compute NaN% of variable conditional on wind_speed > 0.

    Used for wind_direction and wind_gust: these are only meaningful when
    wind is blowing (speed > 0). NaN% = 100 * NaN_count_when_ws>0 / total_when_ws>0.

    Args:
        data (np.ndarray, dtype=float64): Sensor readings (e.g., wind_direction
            or wind_gust), NaN = missing sample.
        ws (np.ndarray, dtype=float64): Wind speed array (same length as data),
            units m/s. NaN = missing sample.

    Returns:
        float: NaN percentage (0-100) of data where wind_speed is real and > 0.
            Returns 0.0 if no valid wind_speed > 0 samples.
    """
    ws_pos = ~np.isnan(ws) & (ws > 0)
    n_ws_pos = int(ws_pos.sum())
    return 100.0 * int((np.isnan(data) & ws_pos).sum()) / n_ws_pos if n_ws_pos else 0.0


def _apply_severity_overrides(issues, cfg):
    """Replace each issue's severity with its configured per-category override, if any."""
    overrides = cfg.get("assertion_severity_override")
    if not overrides:
        return issues
    result = []
    for sev, key, msg in issues:
        for category, override_sev in overrides.items():
            if key == category or key.startswith(category):
                sev = override_sev
                break
        result.append((sev, key, msg))
    return result


def run_assertions(st, stats, cfg):
    """Check station data for quality issues (timing, bounds, frozen runs).

    Detects invalid/backwards/duplicate timestamps, sustained wind-direction
    dropout while wind speed is known and positive, excessive temporal gaps,
    physical-bounds violations, and contiguous frozen sensor values. Does not
    check outage duration; use run_outage_assertions after compute_outage_stats.

    Args:
        st (dict): Station dict (from load_h5).
        stats (dict): Stats dict (from compute_stats).
        cfg (dict): Config dict with keys: frozen_min_run (int, sample count),
            bounds (dict[vname, (lo, hi, units)]), dup_max (int, optional).

    Returns:
        list: List of (severity, key, message) tuples. severity is "WARN" or
            "ERROR". key is short assertion-category string (e.g., "time_neg",
            "dup_ts", "dropout", "gap_dt", "lo:air_temperature", "frozen:wind_speed").
            message is human-readable description string.
    """
    issues = []
    ts = stats["_time"]
    n_neg = ts.get("n_neg_deltas", 0)
    n_dup = ts.get("n_dup_ts", 0)

    if ts.get("time_axis_error"):
        issues.append(("ERROR", "time_axis", f"Invalid time axis: {ts['time_axis_error']}"))
    if n_neg > 0:
        # Single backwards jump typically DST fall-back; multiple suggests data corruption.
        sev = "WARN" if n_neg == 1 else "ERROR"
        issues.append(
            (
                sev,
                "time_neg",
                (
                    f"Backwards timestamp: {n_neg} jump(s), likely DST fall-back"
                    if n_neg == 1
                    else f"Backwards timestamps: {n_neg} jumps"
                ),
            )
        )
    if n_dup > 0:
        dup_pct = 100.0 * n_dup / max(ts["n_pts"] - 1, 1)
        sev = "WARN" if n_dup <= cfg.get("dup_max", 5) else "ERROR"
        issues.append((sev, "dup_ts", f"Duplicate timestamps: {n_dup} ({dup_pct:.1f}% of intervals)"))

    vd = st["variables"]
    if not vd:
        issues.append(("ERROR", "no_data", f"No sensor variables recorded ({ts['n_pts']} timestamps only)"))

    if "wind_direction" in vd and "wind_speed" in vd:
        wd, ws = vd["wind_direction"], vd["wind_speed"]
        dropout = np.isnan(wd) & ~np.isnan(ws) & (ws > 0)
        breaks = _temporal_breaks(
            len(dropout),
            _deltas_minutes(st["times"]) if ts.get("time_axis_valid") and len(dropout) > 1 else None,
            ts.get("avg_freq_min"),
        )
        longest_dropout = int(_longest_true_run(dropout, breaks))
        if longest_dropout >= DROPOUT_MIN_PTS:
            n_drop = int(dropout.sum())
            issues.append(
                (
                    "WARN",
                    "dropout",
                    f"Sustained WD dropout while WS>0: longest run={longest_dropout} pts "
                    f"({n_drop} total)",
                )
            )

    frz_min = cfg["frozen_min_run"]
    bounds = cfg["bounds"]
    avg_freq = ts.get("avg_freq_min")
    max_dt = ts.get("max_dt_min")
    # Ratio-based check; GAP_DT_RATIO calibrated to flag only genuine outliers.
    if avg_freq and max_dt and max_dt > GAP_DT_RATIO * avg_freq:
        issues.append(
            (
                "WARN",
                "gap_dt",
                f"Max obs gap={max_dt:.0f} min ({max_dt/avg_freq:.1f}× avg {avg_freq:.0f} min)",
            )
        )

    for vname, vs in stats.items():
        if vname == "_time":
            continue
        if vname in bounds and vs["max"] is not None:
            lo, hi, u = bounds[vname]
            if vs["min"] < lo:
                issues.append(("ERROR", f"lo:{vname}", f"{vname} min={vs['min']:.2f} below {lo} {u}"))
            if vs["max"] > hi:
                issues.append(("ERROR", f"hi:{vname}", f"{vname} max={vs['max']:.2f} above {hi} {u}"))
        # Frozen-run detection varies by variable.
        # wind_speed/wind_gust: skipped (calm at 0.0 is normal, not stuck).
        # wind_direction: optionally exempted (frozen_exempt_calm_wind) since it
        # naturally holds steady during calm periods, not a sensor fault.
        # relative_humidity: optionally exempted (frozen_exempt_rh) since it can
        # legitimately hold steady for long stretches.
        # solar_radiation: allowed only at 0.0 (nighttime).
        # fuel_moisture_content_10h: uses higher threshold (slow changes normal).
        if vname in ("wind_speed", "wind_gust"):
            pass
        elif vname == "wind_direction" and cfg.get("frozen_exempt_calm_wind", False):
            pass
        elif vname == "relative_humidity" and cfg.get("frozen_exempt_rh", False):
            pass
        elif vname == "solar_radiation":
            if vs["longest_frozen"] >= frz_min and vs.get("longest_frozen_val") != 0.0:
                issues.append(("WARN", f"frozen:{vname}", f"{vname} frozen run={vs['longest_frozen']} pts"))
        elif vname == "fuel_moisture_content_10h":
            if vs["longest_frozen"] >= FUEL_MOISTURE_FROZEN_MIN_RUN:
                issues.append(("WARN", f"frozen:{vname}", f"{vname} frozen run={vs['longest_frozen']} pts"))
        elif vs["longest_frozen"] >= frz_min:
            issues.append(("WARN", f"frozen:{vname}", f"{vname} frozen run={vs['longest_frozen']} pts"))

    return _apply_severity_overrides(issues, cfg)


def run_outage_assertions(stats, cfg):
    """Check longest-continuous station outage duration thresholds.

    Must be called after compute_outage_stats (which requires global time
    extent). Checks the longest outage in any variable and the longest period
    when all variables are down simultaneously. Cumulative percentages are
    informational and never generate warnings.

    Args:
        stats (dict): Stats dict from compute_stats after compute_outage_stats.
        cfg (dict): Config dict with keys: max_var_outage_min (float, minutes,
            optional), full_outage_min (float, minutes, optional).

    Returns:
        list: List of (severity, key, message) tuples. severity is "WARN".
            key is "max_var_outage" or "full_outage". message is human-readable
            comparison string (e.g., "Longest variable outage=0.5h > 0.2h").
    """
    issues = []
    ts = stats["_time"]
    mvo = ts.get("max_var_outage_min")
    fo = ts.get("full_outage_min")
    mvo_th = cfg.get("max_var_outage_min", DEFAULT_MAX_VAR_OUTAGE_MIN)
    fo_th = cfg.get("full_outage_min", DEFAULT_FULL_OUTAGE_MIN)
    if mvo is not None and mvo > mvo_th:
        issues.append(
            (
                "WARN",
                "max_var_outage",
                f"Longest variable outage={mvo/60:.1f}h > {mvo_th/60:.1f}h",
            )
        )
    if fo is not None and fo > fo_th:
        issues.append(
            (
                "WARN",
                "full_outage",
                f"Longest full-station outage={fo/60:.1f}h > {fo_th/60:.1f}h",
            )
        )
    return _apply_severity_overrides(issues, cfg)


def _deltas_minutes(times):
    """Compute time deltas between consecutive samples, in minutes.

    Handles multiple time formats: numpy datetime64[us] (primary), float64
    (legacy minutes-since-origin), or Python datetime objects (legacy).

    Args:
        times (np.ndarray or list): Time samples. If ndarray, dtype may be
            datetime64[us] or float64. If list, elements are datetime objects.

    Returns:
        np.ndarray, dtype=float64: Time deltas in minutes. Length = len(times) - 1.
    """
    arr = times if isinstance(times, np.ndarray) else np.asarray(times)
    if np.issubdtype(arr.dtype, np.datetime64):
        return np.diff(arr) / np.timedelta64(1, "m")
    if arr.dtype == object:
        return np.array([(arr[i + 1] - arr[i]).total_seconds() / 60.0 for i in range(len(arr) - 1)])
    return np.diff(arr.astype(np.float64))


def _segment_by_gap(times, data, avg_freq, factor=OUTAGE_RUN_FACTOR):
    """Split time series into segments at large gaps to avoid drawing across outages.

    Splits at gaps >= factor * avg_freq. Used for plotting: each segment is
    drawn separately, with gaps shown as visual breaks instead of interpolation.

    Args:
        times (np.ndarray, dtype=datetime64[us] or float64): Sample timestamps
            or minutes-since-origin.
        data (np.ndarray, dtype=float64): Sensor readings, same length as times.
        avg_freq (float or None): Average sampling frequency in minutes. If None
            or < 2 samples, returns entire series as single segment.
        factor (float): Gap threshold multiplier (default OUTAGE_RUN_FACTOR).

    Returns:
        list: List of (t_seg, d_seg) tuples, each containing a time and data
            segment. Length >= 1. If no large gaps found, returns single tuple
            covering entire series.
    """
    n = len(times)
    if n == 0:
        return []
    if not avg_freq or n < 2:
        return [(times, data)]
    thresh = factor * avg_freq
    deltas_min = _deltas_minutes(times)
    split = np.where(deltas_min >= thresh)[0] + 1
    bounds = np.concatenate(([0], split, [n]))
    return [
        (times[bounds[k] : bounds[k + 1]], data[bounds[k] : bounds[k + 1]]) for k in range(len(bounds) - 1)
    ]


def compute_outage_stats(
    st,
    stats,
    leading_gap_min=0.0,
    trailing_gap_min=0.0,
    global_duration_min=None,
    factor=OUTAGE_RUN_FACTOR,
):
    """Compute longest and cumulative qualifying outage metrics.

    Regular variables use the global dataset duration as the cumulative
    percentage denominator. Wind direction and gust use only intervals whose
    wind-speed endpoints are both known and positive; calm or unavailable wind
    speed breaks an eligible run. Leading and trailing station gaps are separate
    candidates and are excluded for wind-gated variables.

    Args:
        st (dict): Station dict (from load_h5).
        stats (dict): Stats dict (from compute_stats, modified in-place).
        leading_gap_min (float): Minutes from the global start to the station's
            first timestamp.
        trailing_gap_min (float): Minutes from the station's last timestamp to
            the global end.
        global_duration_min (float or None): Global start-to-end duration. If
            omitted, derives it from the station span plus its two edge gaps.
        factor (float): Gap threshold multiplier (default OUTAGE_RUN_FACTOR) used
            to decide whether a run qualifies as an outage.

    Returns:
        None. Each variable gains ``longest_outage_min``,
            ``cumulative_outage_min``, and ``outage_pct``. ``_time`` gains
            ``max_var_outage_min`` and ``full_outage_min`` (both longest
            continuous durations).
    """
    vd = st["variables"]
    time_stats = stats["_time"]
    leading_gap_min = max(float(leading_gap_min), 0.0)
    trailing_gap_min = max(float(trailing_gap_min), 0.0)
    time_stats["leading_gap_min"] = leading_gap_min
    time_stats["trailing_gap_min"] = trailing_gap_min

    def _mark_unavailable():
        for variable in vd:
            stats[variable]["longest_outage_min"] = None
            stats[variable]["cumulative_outage_min"] = None
            stats[variable]["outage_pct"] = None
        time_stats["max_var_outage_min"] = None
        time_stats["full_outage_min"] = None

    if not vd:
        _mark_unavailable()
        return

    avg_dt = time_stats.get("avg_freq_min")
    n = time_stats["n_pts"]
    if not time_stats.get("time_axis_valid") or not avg_dt or avg_dt <= 0 or n < 2:
        _mark_unavailable()
        return

    thresh_min = factor * avg_dt
    deltas_min = _deltas_minutes(st["times"])
    if global_duration_min is None:
        global_duration_min = leading_gap_min + float(deltas_min.sum()) + trailing_gap_min
    global_duration_min = float(global_duration_min)
    time_stats["global_duration_min"] = global_duration_min
    if not np.isfinite(global_duration_min) or global_duration_min <= 0:
        _mark_unavailable()
        return

    ws = vd.get("wind_speed")
    ws_active = (~np.isnan(ws) & (ws > 0)) if ws is not None else None
    all_eligible = np.ones(n, dtype=np.bool_)

    longest_by_variable = []
    raw_down_masks = []
    for vname, data in vd.items():
        nan_mask = np.isnan(data)
        raw_down_masks.append(nan_mask)
        gated = vname in ("wind_direction", "wind_gust")
        if gated and ws_active is None:
            stats[vname]["longest_outage_min"] = None
            stats[vname]["cumulative_outage_min"] = None
            stats[vname]["outage_pct"] = None
            continue

        eligible = ws_active if gated else all_eligible
        longest, cumulative = _outage_run_metrics(nan_mask, eligible, deltas_min, thresh_min)
        denominator = (
            float(deltas_min[ws_active[:-1] & ws_active[1:]].sum()) if gated else global_duration_min
        )
        if not gated:
            qualifying_edges = [gap for gap in (leading_gap_min, trailing_gap_min) if gap >= thresh_min]
            if qualifying_edges:
                longest = max(longest, max(qualifying_edges))
                cumulative += sum(qualifying_edges)

        stats[vname]["longest_outage_min"] = float(longest)
        stats[vname]["cumulative_outage_min"] = float(cumulative)
        stats[vname]["outage_pct"] = 100.0 * cumulative / denominator if denominator > 0 else None
        longest_by_variable.append(float(longest))

    time_stats["max_var_outage_min"] = max(longest_by_variable) if longest_by_variable else None

    all_down = raw_down_masks[0].copy()
    for down in raw_down_masks[1:]:
        all_down &= down
    full_longest, full_cumulative = _outage_run_metrics(all_down, all_eligible, deltas_min, thresh_min)
    qualifying_edges = [gap for gap in (leading_gap_min, trailing_gap_min) if gap >= thresh_min]
    if qualifying_edges:
        full_longest = max(full_longest, max(qualifying_edges))
        full_cumulative += sum(qualifying_edges)
    time_stats["full_outage_min"] = float(full_longest)


try:
    # Warm numba JIT at import (cache after first run) to avoid stall mid-load.
    _dummy_f = np.zeros(2, dtype=np.float64)
    _dummy_b = np.zeros(2, dtype=np.bool_)
    _longest_nan_run(_dummy_b)
    _longest_frozen_run(_dummy_f, _dummy_b)
    _longest_true_run(_dummy_b, _dummy_b)
    _outage_run_metrics(_dummy_b, _dummy_b, _dummy_f, 1.0)
except (NumbaError, OSError, RuntimeError, TypeError, ValueError):
    pass


def _haversine_km(lat1, lon1, lat2, lon2):
    """Compute great-circle distance between two geographic points.

    Used for station comparison/ranking ("compare" button in detail view).
    Assumes Earth radius = 6371 km (WGS84).

    Args:
        lat1 (float): Latitude of point 1, degrees.
        lon1 (float): Longitude of point 1, degrees.
        lat2 (float): Latitude of point 2, degrees.
        lon2 (float): Longitude of point 2, degrees.

    Returns:
        float: Great-circle distance in kilometers.
    """
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))
