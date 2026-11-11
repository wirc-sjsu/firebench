"""
Join standard files that hold successive pieces of the same observations ("fragments").

:func:`firebench.standardize.merge_std_files` puts files that hold *different* groups side by side
and refuses two files that hold the same group. Observations of an active fire arrive as small
files, one per hour of weather stations or per hour of satellite passes, and each one holds the
same station and stream groups. :func:`join_std_files` appends them along time.
"""

import json
import os
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

import h5py
import hdf5plugin
import numpy as np

from ..tools.logging_config import logger
from ..tools.units import ureg
from .files import new_std_file
from .fire_detections import GROUP as FIRE_DETECTIONS_GROUP
from .std_file_info import TIME_SERIES
from .tools import (
    IGNORE_ATTRIBUTES,
    copy_entire_object_zstd,
    merge_authors,
    validate_h5_std,
    _copy_attributes,
)

_ROOT_ATTRIBUTES = IGNORE_ATTRIBUTES["/"]
_TIME_ATTRIBUTES = ("time_origin", "time_units")
# What a fragment without any sample is dated, so that it sorts last.
_SENTINEL_TIME = np.datetime64("9999-01-01T00:00:00", "ms")
# Provenance of one fragment (its source file, its QC run, when its sensor height was checked): kept
# when every fragment agrees, left out of the joined file when they differ.
_PROVENANCE = frozenset(
    {
        "wx_qc_run_id",
        "wx_qc_source_sha256",
        "wx_qc_decision_sha256",
        "source_file_sha256",
        "sensor_height_source_reference",
        "sensor_height_verification_date",
        "source_files",
    }
)


def join_std_files(
    paths: list[str],
    target: str,
    *,
    description: str = "",
    overwrite: bool = False,
    compression_lvl: int = 3,
):
    """
    Join fragments of observations along time into one standard file.

    - ``time_series`` groups holding a ``time`` dataset (weather stations): the samples of every
      fragment in time order. Every dataset whose first dimension is the length of ``time`` is
      appended; ``time`` is written again in seconds from the first sample. A time present twice
      keeps one sample when all values agree (NaN equal to NaN), else ``ValueError``. A series
      that some fragments lack is kept, filled with NaN (or its ``_FillValue``) for them; a
      non-float one without ``_FillValue`` raises ``ValueError``.
    - ``unstructured/fire_detections/<stream>``: the rows of ``observations`` and ``detections``
      in time order, ``observation_index`` shifted to follow its observation, all times on the
      earliest ``time_origin``. ``time_start``, ``time_end``, ``product``, ``product_version``,
      ``failed``, ``observations_complete`` and ``observation_source`` are joined; every other
      attribute must agree. The fragments must not hold the same pass twice: rows are not
      de-duplicated.
    - Everything else (perimeters, ...) goes side by side. The same group in two fragments is
      refused, except a group without attributes that only holds others.

    The attributes of a station, of its datasets and of the root must agree between fragments: a
    difference raises ``ValueError`` naming the object and the attribute. The exception is the
    provenance of each fragment (source file hashes, QC run ids, sensor-height reference and
    verification date): kept when all agree, left out when they differ, since the fragments keep
    them. The datasets of a stream, and the datasets of a station that are not series, must be the
    same in every fragment.

    The fragments are put in the order of their first sample, then of their content, so that the
    same fragments in any order give the same file. ``created_on`` is the latest of the fragments
    and ``created_by`` merges their authors. One fragment is joined as well: the output is
    normalized (time re-origined, repeated times dropped).

    Quality control is not run again: each fragment keeps the result it was given, hour by hour.

    Parameters
    ----------
    paths : list[str]
        Fragments, each a valid standard file. At least one.
    target : str
        The joined file.
    description : str, optional
        The ``description`` attribute of the joined file.
    overwrite : bool, optional
        Replace ``target`` when it exists.
    compression_lvl : int, optional
        Zstandard level of the datasets.

    Notes
    -----
    Referenced files (``rel_path`` of a polygon) are not copied: ``target`` must lie where the
    fragments' relative paths still resolve.
    """
    if not paths:
        raise ValueError("paths must contain at least one file")
    target = Path(target)
    if target.exists() and not overwrite:
        raise FileExistsError(f"file {target} already exists. Use `overwrite=True` to overwrite it.")
    # The file is written beside its final name and moved when complete: a refusal leaves no file.
    partial = target.with_suffix(target.suffix + ".partial")
    with ExitStack() as stack:
        fragments = [stack.enter_context(h5py.File(path, "r")) for path in paths]
        for fragment in fragments:
            validate_h5_std(fragment)
        fragments = _in_time_order(fragments)
        authors = ""
        for fragment in fragments:
            authors = merge_authors(authors, _text(fragment.attrs["created_by"]))
        out = stack.enter_context(new_std_file(str(partial), authors, overwrite=True))
        try:
            out.attrs["created_on"] = max((_text(f.attrs["created_on"]) for f in fragments), key=_utc)
            out.attrs["description"] = description
            _join_root_attributes(fragments, out)
            joined = {path for f in fragments for path in _stations(f) + _streams(f)}
            for fragment in fragments:
                _copy_rest(fragment["/"], out["/"], joined, compression_lvl)
            _join_stations(fragments, out, compression_lvl)
            _join_streams(fragments, out, compression_lvl)
        except BaseException:
            out.close()
            partial.unlink(missing_ok=True)
            raise
    os.replace(partial, target)
    logger.info("join_std_files: joined %s fragments into %s", len(paths), target)


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(timezone.utc)


def _same(first, second) -> bool:
    """Equality of attribute values or sample rows, NaN equal to NaN."""
    try:
        return bool(np.array_equal(first, second, equal_nan=True))
    except TypeError:  # strings and other types without NaN
        return bool(np.array_equal(first, second))


def _read_times(dataset: h5py.Dataset) -> np.ndarray:
    """UTC ``datetime64[ms]`` of a time dataset, relative to ``time_origin`` or absolute ISO 8601."""
    if "time_origin" in dataset.attrs:
        origin = np.datetime64(_utc(_text(dataset.attrs["time_origin"])).replace(tzinfo=None), "ms")
        seconds = ureg.Quantity(
            np.asarray(dataset[:], dtype=np.float64), _text(dataset.attrs["time_units"])
        ).to("s")
        return origin + np.rint(seconds.magnitude * 1000).astype("timedelta64[ms]")
    return np.array(
        [np.datetime64(_utc(_text(value)).replace(tzinfo=None), "ms") for value in dataset[:]],
        dtype="datetime64[ms]",
    )


def _seconds_since(times: np.ndarray, origin: np.datetime64) -> np.ndarray:
    return (times - origin).astype("timedelta64[ms]").astype(np.float64) / 1000.0


def _iso(moment: np.datetime64) -> str:
    return moment.astype("datetime64[ms]").item().replace(tzinfo=timezone.utc).isoformat()


def _stations(fragment: h5py.File) -> list[str]:
    """Paths of the groups under the time-series group that hold a ``time`` dataset."""
    found = []

    def visit(name, item):
        if isinstance(item, h5py.Group) and isinstance(item.get("time"), h5py.Dataset):
            found.append(f"/{TIME_SERIES}/{name}")

    if TIME_SERIES in fragment:
        fragment[TIME_SERIES].visititems(visit)
    return sorted(found)


def _streams(fragment: h5py.File) -> list[str]:
    group = fragment.get(FIRE_DETECTIONS_GROUP)
    return sorted(f"{FIRE_DETECTIONS_GROUP}/{name}" for name in group) if group is not None else []


def _in_time_order(fragments: list[h5py.File]) -> list[h5py.File]:
    """Order by first sample, then by content (not by file name), so that any input order agrees."""
    # pylint: disable-next=import-outside-toplevel,cyclic-import
    from ..signing.std_files import hdf5_subject_digest_sha256

    def dated(fragment):
        paths = _stations(fragment) + _streams(fragment)
        times = [_read_times(fragment[path]["time"]) for path in _stations(fragment)]
        for path in _streams(fragment):
            for table in ("observations", "detections"):
                times.append(_read_times(fragment[f"{path}/{table}/time"]))
        first = min((t.min() for t in times if t.size), default=_SENTINEL_TIME)
        return first, tuple(paths)

    keys = [dated(fragment) for fragment in fragments]
    # The digest reads the whole file: only the fragments the first sample and the groups leave tied.
    tied = {key for key in keys if keys.count(key) > 1}
    digests = [
        hdf5_subject_digest_sha256(f.filename) if key in tied else "" for f, key in zip(fragments, keys)
    ]
    order = sorted(range(len(fragments)), key=lambda i: (*keys[i], digests[i]))
    return [fragments[i] for i in order]


def _check_attributes(objects: list, label: str, ignore=(), partial: bool = False) -> dict:
    """
    The attributes the objects share.

    One that differs or is missing in one raises ``ValueError``, except a provenance attribute,
    which is then left out. With ``partial``, an object that lacks an attribute is not compared.
    """
    agreed = {}
    for key in sorted(set().union(*(set(item.attrs) for item in objects)) - set(ignore)):
        values = [item.attrs.get(key) for item in objects]  # None: absent (h5py never returns it)
        if partial:
            values = [v for v in values if v is not None]
        if all(v is not None and _same(values[0], v) for v in values):
            agreed[key] = values[0]
        elif key not in _PROVENANCE:
            shown = ["<absent>" if v is None else repr(v) for v in values]
            raise ValueError(f"{label}: attribute '{key}' differs between fragments: {', '.join(shown)}")
    return agreed


def _join_root_attributes(fragments: list[h5py.File], out: h5py.File) -> None:
    out.attrs.update(_check_attributes(fragments, "root", _ROOT_ATTRIBUTES, partial=True))


def _write(group: h5py.Group, name: str, data, dtype, attrs: dict, compression_lvl: int) -> None:
    options = hdf5plugin.Zstd(clevel=compression_lvl) if np.size(data) else {}
    dataset = group.create_dataset(name, data=data, dtype=dtype, **options)
    for key in sorted(attrs):
        dataset.attrs[key] = attrs[key]


def _dataset_names(groups: list[h5py.Group]) -> list[str]:
    """The datasets every fragment holds; a dataset held by some only raises ``ValueError``."""
    names = [sorted(group.keys()) for group in groups]
    if any(item != names[0] for item in names):
        raise ValueError(f"{groups[0].name}: the datasets differ between fragments: {names}")
    return names[0]


def _new_group(out: h5py.File, path: str, attrs: dict) -> h5py.Group:
    group = out.require_group(path)  # the groups above it are the ones copied from the fragments
    for key in sorted(attrs):
        group.attrs[key] = attrs[key]
    return group


def _join_stations(fragments: list[h5py.File], out: h5py.File, compression_lvl: int) -> None:
    for path in sorted({path for f in fragments for path in _stations(f)}):
        _join_station([f[path] for f in fragments if path in f], out, compression_lvl)


def _unique_samples(label: str, times: np.ndarray, columns: dict[str, np.ndarray]) -> np.ndarray:
    """Mask of the first sample of each time; a repeated time whose values differ raises ``ValueError``."""
    kept = np.ones(times.size, dtype=bool)
    first = 0
    for i in range(1, times.size):
        if times[i] != times[i - 1]:
            first = i
            continue
        kept[i] = False
        if not all(_same(column[i], column[first]) for column in columns.values()):
            raise ValueError(f"{label}: the samples at {_iso(times[i])} disagree between fragments")
    return kept


def _fill_part(group: h5py.Group, name: str, example: h5py.Dataset, label: str) -> np.ndarray:
    """The samples of a series the fragment lacks: its `_FillValue`, else NaN for a float series."""
    fill = example.attrs.get("_FillValue")
    if fill is not None:
        fill = np.asarray(fill).reshape(-1)[0]
    elif example.dtype.kind == "f":
        fill = np.nan
    else:
        raise ValueError(f"{label}, dataset '{name}': missing in some fragments and it has no _FillValue")
    return np.full(group["time"].shape + example.shape[1:], fill, dtype=example.dtype)


def _join_station(groups: list[h5py.Group], out: h5py.File, compression_lvl: int) -> None:
    path = groups[0].name
    label = f"station {path}"
    attrs = _check_attributes(groups, label)
    holders = {name: [g for g in groups if name in g] for name in sorted({n for g in groups for n in g})}
    for name, held in holders.items():
        if any(g[name].dtype != held[0][name].dtype for g in held) and name != "time":
            raise ValueError(f"{label}, dataset '{name}': the type differs between fragments")
    # A dataset is a series when its first dimension is the length of `time`; the others must agree.
    series = [
        n
        for n, held in holders.items()
        if n != "time" and all(g[n].shape[:1] == g["time"].shape for g in held)
    ]
    for name in set(holders) - set(series) - {"time"}:
        if len(holders[name]) < len(groups):
            raise ValueError(f"{label}, dataset '{name}': missing in some fragments and not a series")
    times = np.concatenate([_read_times(g["time"]) for g in groups])
    if not times.size:
        raise ValueError(f"{label}: no sample in any fragment")
    order = np.argsort(times, kind="stable")
    times = times[order]
    columns = {}
    for name in series:
        example = holders[name][0][name]
        parts = [g[name][:] if name in g else _fill_part(g, name, example, label) for g in groups]
        columns[name] = np.concatenate(parts)[order]
    kept = _unique_samples(label, times, columns)
    station = _new_group(out, path, attrs)
    for name, held in holders.items():
        parts = [g[name] for g in held]
        if name == "time":
            dataset_attrs = _check_attributes(parts, f"{label}, dataset 'time'", _TIME_ATTRIBUTES)
            dataset_attrs.update(time_origin=_iso(times[0]), time_units="s")
            data, dtype = _seconds_since(times[kept], times[0]), np.float64
        else:
            dataset_attrs = _check_attributes(parts, f"{label}, dataset '{name}'")
            if name in series:
                data = columns[name][kept]
            elif all(_same(parts[0][()], part[()]) for part in parts):
                data = parts[0][()]
            else:
                raise ValueError(f"{label}, dataset '{name}': differs between fragments")
            dtype = parts[0].dtype
        _write(station, name, data, dtype, dataset_attrs, compression_lvl)


def _join_streams(fragments: list[h5py.File], out: h5py.File, compression_lvl: int) -> None:
    for path in sorted({path for f in fragments for path in _streams(f)}):
        _join_stream([f[path] for f in fragments if path in f], out, compression_lvl)


def _stream_attributes(groups: list[h5py.Group], label: str) -> dict:
    joined = (
        "time_start",
        "time_end",
        "product",
        "product_version",
        "failed",
        "observations_complete",
        "observation_source",
    )
    attrs = _check_attributes(groups, label, joined)
    attrs["time_start"] = min((_text(g.attrs["time_start"]) for g in groups), key=_utc)
    attrs["time_end"] = max((_text(g.attrs["time_end"]) for g in groups), key=_utc)
    attrs["product"] = json.dumps(
        sorted({p for g in groups for p in json.loads(_text(g.attrs["product"]))})
    )
    versions = {v for g in groups for v in _text(g.attrs["product_version"]).split(";") if v}
    attrs["product_version"] = ";".join(sorted(versions))
    failed = {}  # insertion order is the time order of the fragments
    for group in groups:
        for item in json.loads(_text(group.attrs["failed"])):
            failed.setdefault(json.dumps(item, sort_keys=True), item)
    attrs["failed"] = json.dumps(list(failed.values()))
    attrs["observation_source"] = ";".join(sorted({_text(g.attrs["observation_source"]) for g in groups}))
    attrs["observations_complete"] = all(bool(g.attrs["observations_complete"]) for g in groups)
    return attrs


def _read_table(groups: list[h5py.Group], table: str, origin_text: str) -> tuple[dict, dict]:
    """Attributes of a table and its columns (data, dtype, attributes), fragments one after the other."""
    origin = np.datetime64(_utc(origin_text).replace(tzinfo=None), "ms")
    members = [g[table] for g in groups]
    label = f"stream {groups[0].name}, {table}"
    attrs = _check_attributes(members, label)
    columns = {}
    for name in _dataset_names(members):
        parts = [m[name] for m in members]
        if any(part.dtype != parts[0].dtype for part in parts):
            raise ValueError(f"{label}, dataset '{name}': the type differs between fragments")
        is_time = "time_origin" in parts[0].attrs
        dataset_attrs = _check_attributes(
            parts, f"{label}, dataset '{name}'", _TIME_ATTRIBUTES if is_time else ()
        )
        if is_time:
            data = _seconds_since(np.concatenate([_read_times(p) for p in parts]), origin)
            dataset_attrs.update(time_origin=origin_text, time_units="s")
            columns[name] = (data, np.float64, dataset_attrs)
        else:
            columns[name] = (np.concatenate([p[:] for p in parts]), parts[0].dtype, dataset_attrs)
    return attrs, columns


def _join_stream(groups: list[h5py.Group], out: h5py.File, compression_lvl: int) -> None:
    path = groups[0].name
    if any(set(g) != {"detections", "observations"} for g in groups):
        raise ValueError(f"stream {path}: expected the groups `detections` and `observations` alone")
    attrs = _stream_attributes(groups, f"stream {path}")
    origin = min((_text(g["observations/time"].attrs["time_origin"]) for g in groups), key=_utc)
    obs_attrs, obs = _read_table(groups, "observations", origin)
    det_attrs, det = _read_table(groups, "detections", origin)
    # Rows of observations in time order; a detection follows its observation to its new row.
    obs_order = np.argsort(obs["time"][0], kind="stable")
    new_row = np.empty_like(obs_order)
    new_row[obs_order] = np.arange(obs_order.size)
    firsts = np.cumsum([0] + [g["observations/time"].shape[0] for g in groups[:-1]])
    shift = np.repeat(firsts, [g["detections/time"].shape[0] for g in groups])
    index, dtype, index_attrs = det["observation_index"]
    det["observation_index"] = (new_row[index + shift].astype(dtype), dtype, index_attrs)
    det_order = np.argsort(det["time"][0], kind="stable")
    _new_group(out, path, attrs)
    for table, table_attrs, columns, order in (
        ("detections", det_attrs, det, det_order),
        ("observations", obs_attrs, obs, obs_order),
    ):
        group = _new_group(out, f"{path}/{table}", table_attrs)
        for name in sorted(columns):
            data, dtype, dataset_attrs = columns[name]
            _write(group, name, data[order], dtype, dataset_attrs, compression_lvl)


def _copy_rest(src: h5py.Group, dst: h5py.Group, joined: set[str], compression_lvl: int) -> None:
    """Copy what is not joined; a leaf group or a dataset held by two fragments raises ``ValueError``."""
    for name in sorted(src):
        child = src[name]
        if child.name in joined:
            continue
        if isinstance(child, h5py.Dataset):
            if name in dst:
                raise ValueError(f"{child.name} is in two fragments")
            copy_entire_object_zstd(src, dst, name, compression_lvl)
        elif name not in dst:
            target = dst.create_group(name)
            _copy_attributes(child, target, child.name)
            _copy_rest(child, target, joined, compression_lvl)
        elif any(isinstance(item, h5py.Group) for item in child.values()):
            _check_attributes([child, dst[name]], f"group {child.name}")
            _copy_rest(child, dst[name], joined, compression_lvl)
        else:
            raise ValueError(f"{child.name} is in two fragments")
