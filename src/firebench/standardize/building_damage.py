import json
from pathlib import Path

import geopandas as gpd
import h5py
import hdf5plugin
import numpy as np
import pandas as pd
from pyproj import CRS
from scipy.spatial import cKDTree
from shapely.errors import ShapelyError
from shapely.geometry import box, shape

from ..tools import calculate_sha256
from ..tools.logging_config import logger
from .std_file_info import POINTS
from .tools import check_std_version

DEFAULT_DAMAGE = "No Damage"
# least to most severe; a label outside this list ranks with `Inaccessible`
DAMAGE_SEVERITY = {
    "No Damage": 0,
    "Inaccessible": 1,
    "Affected (1-9%)": 2,
    "Minor (10-25%)": 3,
    "Major (26-50%)": 4,
    "Destroyed (>50%)": 5,
}
SYNTHETIC_BUILDING_RADIUS_M = 5.0

# column of the DINS table: its name, and whether the name may be followed by other text
_DINS_COLUMNS = {
    "name": ("Incident Name", False),
    "number": ("Incident Number", True),
    "start_date": ("Incident Start Date", False),
    "latitude": ("Latitude", False),
    "longitude": ("Longitude", False),
    "damage": ("Damage", False),
}
_DINS_DATE_FORMAT = "%m/%d/%Y %I:%M:%S %p"
_DATASET_UNITS = {
    "position_lat": "degree",
    "position_lon": "degree",
    "building_damage": "dimensionless",
    "dins_matched": "dimensionless",
    "dins_match_count": "dimensionless",
    "building_source": "dimensionless",
    "dins_match_distance_m": "m",
}


def list_dins_incidents(dins_csv: Path) -> list[dict]:
    """
    List the incidents of a CAL FIRE DINS table.

    An incident name is not one incident: the same name is given to fires of different years and
    places. The incident number alone is not one incident either. An incident is the pair of an
    incident name and an incident number, and this function returns one item per pair.

    Parameters
    ----------
    dins_csv : Path
        The CAL FIRE DINS table. Columns used: `Incident Name`, `Incident Number`,
        `Incident Start Date`, `Latitude`, `Longitude`, `Damage`.

    Returns
    -------
    list[dict]
        One item per incident, sorted by name without case, then start date, then number, with the keys:

        - `incident_name`, `incident_number`: as in the table, without surrounding spaces.
        - `start_date_min`, `start_date_max`: first and last start date of its rows, as ISO 8601
          dates, or None if no date could be read. Rows of one incident may differ by a few days.
        - `n_records`: number of rows.
        - `lat_min`, `lat_max`, `lon_min`, `lon_max`: box of its rows, or None if no position could be read.

    Raises
    ------
    ValueError
        If the table cannot be read or a column is missing.
    """  # pylint: disable=line-too-long
    dins = _read_dins(dins_csv)
    dins = dins[dins["name"] != ""]
    summary = dins.groupby([dins["name"].str.casefold(), "number"], sort=False).agg(
        incident_name=("name", "first"),
        incident_number=("number", "first"),
        start_date_min=("start_date", "min"),
        start_date_max=("start_date", "max"),
        n_records=("name", "size"),
        lat_min=("latitude", "min"),
        lat_max=("latitude", "max"),
        lon_min=("longitude", "min"),
        lon_max=("longitude", "max"),
    )

    incidents = []
    for row in summary.itertuples(index=False):
        incident = {"incident_name": row.incident_name, "incident_number": row.incident_number}
        for key in ("start_date_min", "start_date_max"):
            incident[key] = _iso_date(getattr(row, key))
        incident["n_records"] = int(row.n_records)
        for key in ("lat_min", "lat_max", "lon_min", "lon_max"):
            value = getattr(row, key)
            incident[key] = None if pd.isna(value) else float(value)
        incidents.append(incident)
    return sorted(
        incidents,
        key=lambda item: (
            item["incident_name"].casefold(),
            item["start_date_min"] or "",
            item["incident_number"],
        ),
    )


def standardize_dins_building_damage(
    dins_csv: Path,
    footprints: Path,
    h5file: h5py.File,
    incident_name: str,
    lower_left_corner: tuple[float, float],
    upper_right_corner: tuple[float, float],
    max_match_distance_m: float = 50.0,
    footprints_source: str = "global",
    group_name: str = "building_damaged",
    projected_crs: str | None = None,
    clip_to_box: bool = True,
    overwrite: bool = False,
    compression_lvl: int = 6,
    incident_numbers: list[str] | None = None,
) -> h5py.Group:
    """
    Match the building damage of a CAL FIRE DINS incident to building footprints and write the
    buildings as points in a FireBench HDF5 standard file.

    Each DINS row is matched to the nearest footprint centroid. A row farther than
    `max_match_distance_m` from every centroid becomes a building of its own, at the row's position.
    A footprint takes the most severe damage among its rows, and `No Damage` if it has none. The
    output holds the footprints in file order, then the DINS-only buildings in table order.

    Licence attributes are not written: the caller sets them.

    Parameters
    ----------
    dins_csv : Path
        The CAL FIRE DINS table. Columns used: `Incident Name`, `Incident Number`,
        `Incident Start Date`, `Latitude`, `Longitude`, `Damage`. Rows missing a position or a
        damage are dropped.
    footprints : Path
        Building footprints as line-delimited GeoJSON, the format of Microsoft's Global ML Building
        Footprints. Footprints that intersect the box are kept.
    h5file : h5py.File
        Target HDF5 file.
    incident_name : str
        Incident name, compared without case. See `list_dins_incidents`.
    lower_left_corner : tuple[float, float]
        Lower-left corner of the box, as (latitude, longitude).
    upper_right_corner : tuple[float, float]
        Upper-right corner of the box, as (latitude, longitude).
    max_match_distance_m : float
        Largest distance between a DINS row and the footprint centroid it is matched to.
    footprints_source : str
        Name of the footprints source, stored in the attribute `mbf_source`.
    group_name : str
        Name of the group under `/points`.
    projected_crs : str | None
        Projected CRS, in metres, for centroids and distances. None uses the UTM zone of the box.
    clip_to_box : bool
        Drop the DINS rows outside the box. Default: True
    overwrite : bool
        Replace the group if it exists. Default: False
    compression_lvl : int
        Zstandard compression level of the datasets.
    incident_numbers : list[str] | None
        Incident numbers to keep. Required when the rows of `incident_name` carry more than one
        incident number, because they may then belong to different incidents. Several numbers may
        be given when one incident carries several.

    Returns
    -------
    h5py.Group
        The group written.

    Raises
    ------
    ValueError
        If a file cannot be read, `incident_name` covers several incident numbers and none is given,
        an incident number is unknown, no DINS row or no footprint is left, or the group exists and
        `overwrite` is False.
    """  # pylint: disable=line-too-long
    logger.debug("Standardize DINS building damage of %s from file %s", incident_name, dins_csv)
    check_std_version(h5file)
    group_path = f"/{POINTS}/{group_name}"
    if group_path in h5file and not overwrite:
        raise ValueError(
            f"group {group_path} already exists in {h5file.filename}. Set `overwrite` to True to replace it."
        )

    frame = box(
        min(lower_left_corner[1], upper_right_corner[1]),
        min(lower_left_corner[0], upper_right_corner[0]),
        max(lower_left_corner[1], upper_right_corner[1]),
        max(lower_left_corner[0], upper_right_corner[0]),
    )
    dins = _select_incident(_read_dins(dins_csv), dins_csv, incident_name, incident_numbers)
    dins, n_outside = _usable_rows(dins, frame if clip_to_box else None)
    if dins.empty:
        raise ValueError(
            f"incident {incident_name!r} of {dins_csv} has no row with a position and a damage"
            + (f" inside the box ({n_outside} rows are outside)" if clip_to_box else "")
        )
    buildings = _read_footprints(footprints)
    buildings = buildings[buildings.intersects(frame)]
    if buildings.empty:
        raise ValueError(f"no footprint of {footprints} intersects the box")
    if projected_crs is None:
        projected_crs = gpd.GeoSeries([frame], crs="EPSG:4326").estimate_utm_crs()
    data = _fuse(buildings, dins, _metric_crs(projected_crs), max_match_distance_m)

    if group_path in h5file:
        del h5file[group_path]
    group = h5file.create_group(group_path)
    group.attrs["source_data_hash"] = calculate_sha256(dins_csv)
    group.attrs["mbf_source"] = footprints_source
    group.attrs["mbf_source_data_hash"] = calculate_sha256(footprints)
    group.attrs["default_damage_for_unmatched_mbf"] = DEFAULT_DAMAGE
    group.attrs["dins_only_fallback_distance_m"] = max_match_distance_m
    group.attrs["dins_only_synthetic_building_radius_m"] = SYNTHETIC_BUILDING_RADIUS_M
    group.attrs["dins_record_count"] = len(dins)
    group.attrs["dins_records_outside_box"] = n_outside
    group.attrs["dins_incident_name"] = dins["name"].iloc[0]
    group.attrs["dins_incident_numbers"] = json.dumps(dins["number"].drop_duplicates().tolist())
    group.attrs["dins_incident_start_date"] = _iso_date(dins["start_date"].min()) or ""
    for name, units in _DATASET_UNITS.items():
        dataset = group.create_dataset(name, data=data[name], **hdf5plugin.Zstd(clevel=compression_lvl))
        dataset.attrs["units"] = units
    return group


def _read_dins(dins_csv: Path) -> pd.DataFrame:
    """Read the columns of a DINS table this module uses, under the keys of `_DINS_COLUMNS`."""
    try:
        header = pd.read_csv(dins_csv, nrows=0, encoding="utf-8-sig").columns
        columns = {}
        for key, (name, is_prefix) in _DINS_COLUMNS.items():
            matches = [
                column
                for column in header
                if column.strip() == name or (is_prefix and column.strip().startswith(name))
            ]
            if not matches:
                raise ValueError(f"column `{name}` not found")
            columns[matches[0]] = key
        dins = pd.read_csv(dins_csv, usecols=list(columns), encoding="utf-8-sig", dtype=str)
    except (OSError, ValueError) as exc:
        raise ValueError(f"DINS table {dins_csv} could not be read: {exc}") from exc

    dins = dins.rename(columns=columns)
    for key in ("name", "number"):
        dins[key] = dins[key].fillna("").str.strip()
    dins["damage"] = dins["damage"].str.strip().replace("", np.nan)
    dins["start_date"] = pd.to_datetime(dins["start_date"], format=_DINS_DATE_FORMAT, errors="coerce")
    for key in ("latitude", "longitude"):
        dins[key] = pd.to_numeric(dins[key], errors="coerce")
    return dins


def _select_incident(
    dins: pd.DataFrame, dins_csv: Path, incident_name: str, incident_numbers: list[str] | None
) -> pd.DataFrame:
    """Keep the rows of one incident, and refuse a name that covers several incident numbers."""
    rows = dins[dins["name"].str.casefold() == incident_name.strip().casefold()]
    if rows.empty:
        raise ValueError(f"no row of {dins_csv} has the incident name {incident_name!r}")

    found = "; ".join(
        f"{number!r} (start {_iso_date(group['start_date'].min())}, {len(group)} rows)"
        for number, group in rows.groupby("number", sort=False)
    )
    if incident_numbers is None:
        if rows["number"].nunique() > 1:
            raise ValueError(
                f"incident name {incident_name!r} covers several incident numbers in {dins_csv}, which "
                f"may be different incidents. Give `incident_numbers`: {found}"
            )
        return rows

    if isinstance(incident_numbers, str):
        incident_numbers = [incident_numbers]
    wanted = [number.strip() for number in incident_numbers]
    unknown = sorted(set(wanted) - set(rows["number"]))
    if not wanted or unknown:
        raise ValueError(
            f"incident {incident_name!r} of {dins_csv} has no row with the incident numbers {unknown}. "
            f"Its incident numbers: {found}"
        )
    return rows[rows["number"].isin(wanted)]


def _usable_rows(dins: pd.DataFrame, frame) -> tuple[pd.DataFrame, int]:
    """Drop the rows missing a value and, if a box is given, the rows outside it, which are counted."""
    dins = dins.dropna(subset=["latitude", "longitude", "damage"])
    if frame is None:
        return dins, 0
    lon_min, lat_min, lon_max, lat_max = frame.bounds
    inside = dins["latitude"].between(lat_min, lat_max) & dins["longitude"].between(lon_min, lon_max)
    return dins[inside], int((~inside).sum())


def _read_footprints(footprints: Path) -> gpd.GeoSeries:
    """Read the geometries of a line-delimited GeoJSON file, in file order."""
    geometries = []
    try:
        with open(footprints, encoding="utf-8") as lines:
            for number, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                try:
                    geometries.append(shape(json.loads(line)["geometry"]))
                except (ValueError, KeyError, TypeError, AttributeError, ShapelyError) as exc:
                    raise ValueError(f"line {number} is not a GeoJSON feature: {exc}") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"footprints file {footprints} could not be read: {exc}") from exc
    return gpd.GeoSeries(geometries, crs="EPSG:4326")


def _metric_crs(projected_crs) -> CRS:
    crs = CRS.from_user_input(projected_crs)
    if not crs.is_projected or crs.axis_info[0].unit_name != "metre":
        raise ValueError(f"projected_crs {projected_crs!r} must be a projected CRS in metres")
    return crs


def _fuse(buildings: gpd.GeoSeries, dins: pd.DataFrame, crs: CRS, max_match_distance_m: float) -> dict:
    """Match each DINS row to the nearest footprint centroid and return the datasets to write."""
    centroids = buildings.to_crs(crs).centroid
    dins_points = gpd.GeoSeries(
        gpd.points_from_xy(dins["longitude"], dins["latitude"]), crs="EPSG:4326"
    ).to_crs(crs)
    distances, indices = cKDTree(np.column_stack((centroids.x, centroids.y))).query(
        np.column_stack((dins_points.x, dins_points.y)), k=1
    )
    data, dins_only = _assign_damage(
        len(buildings), indices, distances, dins["damage"].to_numpy(), max_match_distance_m
    )

    centroids = centroids.to_crs("EPSG:4326")
    n_dins_only = len(dins_only)
    return {
        "position_lat": np.concatenate((centroids.y.to_numpy(), dins["latitude"].to_numpy()[dins_only])),
        "position_lon": np.concatenate((centroids.x.to_numpy(), dins["longitude"].to_numpy()[dins_only])),
        "building_damage": _as_bytes(
            np.concatenate((data["damage"], dins["damage"].to_numpy()[dins_only]))
        ),
        "dins_matched": np.concatenate((data["match_count"] > 0, np.ones(n_dins_only, dtype=np.bool_))),
        "dins_match_count": np.concatenate((data["match_count"], np.ones(n_dins_only, dtype=np.int32))),
        "building_source": _as_bytes(["MBF"] * len(buildings) + ["DINS"] * n_dins_only),
        "dins_match_distance_m": np.concatenate((data["match_distance"], np.zeros(n_dins_only))),
    }


def _assign_damage(
    n_buildings: int, indices: np.ndarray, distances: np.ndarray, labels: np.ndarray, max_distance: float
) -> tuple[dict, list[int]]:
    """Give each footprint the most severe damage among its rows, and list the rows too far from any."""
    data = {
        "damage": np.full(n_buildings, DEFAULT_DAMAGE, dtype=object),
        "match_count": np.zeros(n_buildings, dtype=np.int32),
        "match_distance": np.full(n_buildings, np.nan, dtype=np.float64),
    }
    damage_rank = np.zeros(n_buildings, dtype=np.int16)
    dins_only = []
    for dins_idx, (building_idx, distance) in enumerate(zip(indices, distances)):
        if distance > max_distance:
            dins_only.append(dins_idx)
            continue

        data["match_count"][building_idx] += 1
        nearest = data["match_distance"][building_idx]
        if np.isnan(nearest) or distance < nearest:
            data["match_distance"][building_idx] = distance
        rank = DAMAGE_SEVERITY.get(labels[dins_idx], 1)
        if rank > damage_rank[building_idx]:
            data["damage"][building_idx] = labels[dins_idx]
            damage_rank[building_idx] = rank
    return data, dins_only


def _as_bytes(values) -> np.ndarray:
    return np.char.encode(np.asarray(values, dtype=str), "utf-8")


def _iso_date(timestamp) -> str | None:
    return None if pd.isna(timestamp) else timestamp.date().isoformat()
