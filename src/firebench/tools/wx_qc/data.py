import numpy as np
import numba
import h5py
import hdf5plugin  # noqa: F401  (registers HDF5 compression filters on import)
from datetime import datetime, timedelta, timezone

from .constants import (
    PHYS_BOUNDS,
    DEFAULT_NAN_THRESH,
    DEFAULT_FROZEN_RUN,
    DROPOUT_MIN_PTS,
    GAP_DT_RATIO,
    FUEL_MOISTURE_FROZEN_MIN_RUN,
    OUTAGE_RUN_FACTOR,
    DEFAULT_MAX_VAR_OUTAGE_MIN,
    DEFAULT_FULL_OUTAGE_MIN,
)


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
            time_origin), variables (dict[str, np.ndarray], one float64 array
            per sensor, NaN = missing sample), var_units (dict[str, str]).
    """
    attrs = dict(grp.attrs)
    t0_str = grp["time"].attrs.get("time_origin", "")
    rel_min = grp["time"][:]
    try:
        t0 = datetime.fromisoformat(t0_str)
        if np.isnan(rel_min).any():
            raise ValueError("NaN in time dataset")
        if t0.tzinfo is not None:
            # np.datetime64 has no timezone; normalize to UTC for cross-station
            # time-axis comparability.
            t0 = t0.astimezone(timezone.utc).replace(tzinfo=None)
        # Vectorized datetime64 build (avoid Python-loop per-point cost).
        us = np.rint(rel_min.astype(np.float64) * 60_000_000.0).astype(np.int64)
        times = np.datetime64(t0, "us") + us.astype("timedelta64[us]")
    except Exception:
        times = rel_min.astype(float)
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
def _outage_run_minutes(down, deltas_min, thresh_min):
    """Sum duration (minutes) of outage runs exceeding threshold.

    An interval counts as down if both endpoints are down OR interval itself
    >= thresh_min (large gap = outage even between valid values). Runs
    accumulate until reaching thresh_min threshold, then contribute to total.

    Args:
        down (np.ndarray, dtype=bool): Mask where True indicates down/missing
            samples.
        deltas_min (np.ndarray, dtype=float64): Time deltas between consecutive
            samples, in minutes. Length = len(down) - 1.
        thresh_min (float): Minimum run duration in minutes to count as an
            outage.

    Returns:
        float: Total minutes in down runs >= thresh_min.
    """
    n = len(down)
    total = 0.0
    run = 0.0
    for i in range(n - 1):
        interval_down = (down[i] and down[i + 1]) or deltas_min[i] >= thresh_min
        if interval_down:
            run += deltas_min[i]
        else:
            if run >= thresh_min:
                total += run
            run = 0.0
    if run >= thresh_min:
        total += run
    return total


@numba.njit(cache=True)
def _longest_frozen_run(valid):
    """Find longest run of equal (repeated) values in array.

    Args:
        valid (np.ndarray, dtype=float64): Sensor values (typically already
            filtered to non-NaN samples).

    Returns:
        tuple: (frozen (int), frozen_val (float)). frozen = length of longest
            equal-value run in sample count. frozen_val = the repeated value,
            or NaN if no frozen run found.
    """
    frozen = 0
    frozen_val = np.nan
    n = len(valid)
    if n > 1:
        cur_f = 1
        cur_val = valid[0]
        for i in range(1, n):
            if valid[i] == valid[i - 1]:
                cur_f += 1
            else:
                cur_f = 1
                cur_val = valid[i]
            if cur_f > frozen:
                frozen = cur_f
                frozen_val = cur_val
    return frozen, frozen_val


def _var_stat_block(data, avg_freq):
    """Compute statistics for one sensor variable.

    Args:
        data (np.ndarray, dtype=float64): Sensor readings, NaN = missing sample.
        avg_freq (float or None): Average sampling frequency in minutes (used
            to convert longest NaN run to hours). May be None if < 2 samples.

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
    frozen, frozen_val_raw = _longest_frozen_run(valid)
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

    Includes timing metrics (n_pts, avg_freq_min, monotonicity, duplicates)
    and per-variable stats (NaN%, min/max/mean/std, frozen runs, gaps).
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
    if n > 1:
        rel_min = st.get("rel_min")
        if rel_min is not None and len(rel_min) == n:
            # Use rel_min deltas to avoid Python datetime subtraction cost.
            deltas = np.diff(np.asarray(rel_min, dtype=np.float64))
        else:
            deltas = _deltas_minutes(times)
        avg_freq = float(np.median(deltas))
        max_dt = float(deltas.max())
        n_neg = int(np.sum(deltas < 0))
        n_dup = n - len(set(times))
        monotonic = n_neg == 0 and n_dup == 0
        dup_ts = n_dup > 0
    else:
        avg_freq = None
        max_dt = None
        monotonic = True
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
        }
    }

    for vname, data in st["variables"].items():
        result[vname] = _var_stat_block(data, avg_freq)

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


def run_assertions(st, stats, cfg):
    """Check station data for quality issues (timing, bounds, frozen runs).

    Detects: backwards timestamps, duplicate timestamps, wind_direction dropout
    during wind_speed > 0, excessive gaps, physical bounds violations, and
    frozen (stuck) sensor values. Does NOT check outage duration (use
    run_outage_assertions after compute_outage_stats).

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

    if n_neg > 0:
        # Single backwards jump typically DST fall-back; multiple suggests data corruption.
        sev = "WARN" if n_neg == 1 else "ERROR"
        issues.append(
            (
                sev,
                "time_neg",
                (
                    f"Backwards timestamp: {n_neg} jump(s) — likely DST fall-back"
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
    if "wind_direction" in vd and "wind_speed" in vd:
        wd, ws = vd["wind_direction"], vd["wind_speed"]
        n_drop = int((np.isnan(wd) & ~np.isnan(ws) & (ws > 0)).sum())
        # Require sustained minimum count to exclude zero-crossing noise.
        if n_drop >= DROPOUT_MIN_PTS:
            issues.append(
                ("WARN", "dropout", f"WD NaN while WS>0: {n_drop} pts ({100*n_drop/len(wd):.1f}%)")
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
        # Outage metrics now replace per-variable NaN% assertions.
        if vname in bounds and vs["max"] is not None:
            lo, hi, u = bounds[vname]
            if vs["min"] < lo:
                issues.append(("ERROR", f"lo:{vname}", f"{vname} min={vs['min']:.2f} below {lo} {u}"))
            if vs["max"] > hi:
                issues.append(("ERROR", f"hi:{vname}", f"{vname} max={vs['max']:.2f} above {hi} {u}"))
        # Frozen-run detection varies by variable.
        # wind_speed/wind_gust: skipped (calm at 0.0 is normal, not stuck).
        # solar_radiation: allowed only at 0.0 (nighttime).
        # fuel_moisture_content_10h: uses higher threshold (slow changes normal).
        if vname in ("wind_speed", "wind_gust"):
            pass
        elif vname == "solar_radiation":
            if vs["longest_frozen"] >= frz_min and vs.get("longest_frozen_val") != 0.0:
                issues.append(("WARN", f"frozen:{vname}", f"{vname} frozen run={vs['longest_frozen']} pts"))
        elif vname == "fuel_moisture_content_10h":
            if vs["longest_frozen"] >= FUEL_MOISTURE_FROZEN_MIN_RUN:
                issues.append(("WARN", f"frozen:{vname}", f"{vname} frozen run={vs['longest_frozen']} pts"))
        elif vs["longest_frozen"] >= frz_min:
            issues.append(("WARN", f"frozen:{vname}", f"{vname} frozen run={vs['longest_frozen']} pts"))

    return issues


def run_outage_assertions(stats, cfg):
    """Check station-level outage duration thresholds.

    Must be called after compute_outage_stats (which requires global time
    extent). Checks: max_var_outage_min (longest outage in any variable) and
    full_outage_min (when all variables down simultaneously).

    Args:
        stats (dict): Stats dict (from compute_stats, after compute_outage_stats
            added outage_min to each variable and _time).
        cfg (dict): Config dict with keys: max_var_outage_min (float, minutes,
            optional), full_outage_min (float, minutes, optional).

    Returns:
        list: List of (severity, key, message) tuples. severity is "WARN".
            key is "max_var_outage" or "full_outage". message is human-readable
            comparison string (e.g., "Max variable outage=0.5h > 0.2h").
    """
    issues = []
    ts = stats["_time"]
    mvo = ts.get("max_var_outage_min")
    fo = ts.get("full_outage_min")
    mvo_th = cfg.get("max_var_outage_min", DEFAULT_MAX_VAR_OUTAGE_MIN)
    fo_th = cfg.get("full_outage_min", DEFAULT_FULL_OUTAGE_MIN)
    if mvo is not None and mvo > mvo_th:
        issues.append(("WARN", "max_var_outage", f"Max variable outage={mvo/60:.1f}h > {mvo_th/60:.1f}h"))
    if fo is not None and fo > fo_th:
        issues.append(("WARN", "full_outage", f"Full station outage={fo/60:.1f}h > {fo_th/60:.1f}h"))
    return issues


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


def compute_outage_stats(st, stats, edge_gap_min, factor=OUTAGE_RUN_FACTOR):
    """Compute outage duration (minutes) for each variable and station-level totals.

    Outage = edge gaps (time before first or after last sample) + within-record
    NaN/gap runs >= factor*avg_dt. Wind direction/gust only count as down when
    wind_speed is real and > 0. Stamps results into stats dicts.

    Must be called after global time extent is known (for edge_gap_min calculation).

    Args:
        st (dict): Station dict (from load_h5).
        stats (dict): Stats dict (from compute_stats, modified in-place).
        edge_gap_min (float): Minutes between global dataset start/end and this
            station's first/last sample. Contributes to all variables' outage totals.
        factor (float): Gap threshold multiplier (default OUTAGE_RUN_FACTOR) used
            in _outage_run_minutes.

    Returns:
        None. Modifies stats in-place, adding: stats[vname]["outage_min"] (float)
            for each variable, stats["_time"]["max_var_outage_min"] (float, longest
            in any variable), stats["_time"]["full_outage_min"] (float, when all
            variables simultaneously down).
    """
    vd = st["variables"]
    if not vd:
        stats["_time"]["max_var_outage_min"] = None
        stats["_time"]["full_outage_min"] = edge_gap_min
        return

    avg_dt = stats["_time"].get("avg_freq_min")
    n = stats["_time"]["n_pts"]
    if not avg_dt or n < 2:
        # No usable cadence to measure a "run" against — the only outage
        # signal available is the record not covering the global period.
        for vname in vd:
            stats[vname]["outage_min"] = edge_gap_min
        stats["_time"]["max_var_outage_min"] = edge_gap_min
        stats["_time"]["full_outage_min"] = edge_gap_min
        return

    thresh_min = factor * avg_dt
    deltas_min = _deltas_minutes(st["times"])
    ws = vd.get("wind_speed")
    ws_real_pos = (~np.isnan(ws) & (ws > 0)) if ws is not None else None

    down_masks = {}
    for vname, data in vd.items():
        nan_mask = np.isnan(data)
        gated = vname in ("wind_direction", "wind_gust") and ws_real_pos is not None
        down = (nan_mask & ws_real_pos) if gated else nan_mask
        down_masks[vname] = down
        body = _outage_run_minutes(down, deltas_min, thresh_min)
        stats[vname]["outage_min"] = body + edge_gap_min

    stats["_time"]["max_var_outage_min"] = max(stats[v]["outage_min"] for v in vd)

    all_down = None
    for down in down_masks.values():
        all_down = down.copy() if all_down is None else (all_down & down)
    full_body = _outage_run_minutes(all_down, deltas_min, thresh_min)
    stats["_time"]["full_outage_min"] = full_body + edge_gap_min


try:
    # Warm numba JIT at import (cache after first run) to avoid stall mid-load.
    _dummy_f = np.zeros(2, dtype=np.float64)
    _dummy_b = np.zeros(2, dtype=np.bool_)
    _longest_nan_run(_dummy_b)
    _longest_frozen_run(_dummy_f)
    _outage_run_minutes(_dummy_b, _dummy_f, 1.0)
except Exception:
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
