"""
NASA CMR granule search: when a polar-orbiting sensor looked at a box, and how much of it it covered.

Fire detection lists (FIRMS) say where a fire was seen, not where the sensor looked and saw nothing.
The granules of the sensor's fire product, searched in the Common Metadata Repository, give the
times it passed over a box and the outline of each swath. Consecutive granules of one pass are
merged into an overpass, whose ``observed_fraction`` is the share of the box inside the swath.

The search API is open: no key is needed. Ported from spear ``backends/satellite/earthdata.py``.
"""

import json
import logging
import math
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from .http import http_get

logger = logging.getLogger(__name__)

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
PAGE_SIZE = 2000

# Fire product collections per stream: the standard (archive) collection first, then the
# near-real-time one. CMR's `version` must be written exactly as the provider registered it: a wrong
# form returns no granule and no error. Checked against the live catalogue on 2026-10-15.
COLLECTIONS: dict[str, list[tuple[str, str]]] = {
    "viirs_snpp": [("VNP14IMG", "002"), ("VNP14IMG_NRT", "2")],
    "viirs_noaa20": [("VJ114IMG", "002"), ("VJ114IMG_NRT", "2")],
    "viirs_noaa21": [("VJ214IMG", "002"), ("VJ214IMG_NRT", "2")],
    "modis_terra": [("MOD14", "061"), ("MOD14", "6.1NRT")],
    "modis_aqua": [("MYD14", "061"), ("MYD14", "6.1NRT")],
}

Bbox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Granule:
    """One CMR granule of a fire product: when it was acquired and where it looked."""

    short_name: str
    version: str
    granule_id: str
    time_start: datetime
    time_end: datetime
    # (lon, lat) ring of the swath outline; empty when CMR gives none
    polygon: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class Overpass:
    """Consecutive granules of one pass over the box."""

    time_start: datetime
    time_end: datetime
    granule_ids: tuple[str, ...]
    # share of the box inside the merged swath outlines, NaN when a granule has no outline
    observed_fraction: float


def check_bbox(bbox: Sequence[float]) -> Bbox:
    """Return ``bbox`` as ``(west, south, east, north)`` floats, or raise ``ValueError``."""
    if len(bbox) != 4:
        raise ValueError(f"a box is (west, south, east, north), got {bbox!r}")
    west, south, east, north = (float(value) for value in bbox)
    if not -180 <= west < east <= 180:
        raise ValueError(
            f"box longitudes must satisfy -180 <= west < east <= 180, got {west}, {east}; "
            "a box across the antimeridian is not supported"
        )
    if not -90 <= south < north <= 90:
        raise ValueError(f"box latitudes must satisfy -90 <= south < north <= 90, got {south}, {north}")
    return west, south, east, north


def search_granules(
    short_name: str,
    version: str,
    bbox: Sequence[float],
    start: datetime,
    end: datetime,
    *,
    opener: Callable = urllib.request.urlopen,
) -> list[Granule]:
    """
    Granules of one collection that meet ``bbox`` between ``start`` and ``end``, ordered by start.

    CMR filters on the granule geometry; a granule whose outline does not reach into the box is
    dropped here too, and one without an outline is kept. Granules are deduplicated by id.
    ``start`` and ``end`` are aware datetimes.
    """
    west, south, east, north = check_bbox(bbox)
    params = {
        "short_name": short_name,
        "version": version,
        "temporal": f"{_utc_text(start)},{_utc_text(end)}",
        "bounding_box": f"{west},{south},{east},{north}",
        "page_size": PAGE_SIZE,
        "sort_key": "start_date",
    }
    found: dict[str, Granule] = {}
    page = 1
    while True:
        url = f"{CMR_GRANULES}?{urllib.parse.urlencode({**params, 'page_num': page})}"
        entries = json.loads(http_get(url, opener=opener).decode()).get("feed", {}).get("entry", [])
        for entry in entries:
            granule = _granule(short_name, version, entry)
            if granule.granule_id not in found and _meets_box(granule.polygon, (west, south, east, north)):
                found[granule.granule_id] = granule
        if len(entries) < PAGE_SIZE:
            break
        page += 1
    granules = sorted(found.values(), key=lambda granule: (granule.time_start, granule.granule_id))
    logger.debug("[cmr] %s %s: %d granules over the box", short_name, version, len(granules))
    return granules


def overpasses(
    granules: Sequence[Granule], bbox: Sequence[float], max_gap_s: float = 120
) -> list[Overpass]:
    """
    Merge granules into overpasses and compute the share of the box each one covered.

    Granules are sorted by start. A granule joins the previous overpass when it starts at most
    ``max_gap_s`` seconds after that overpass ends. ``observed_fraction`` is the area of the union of
    the outlines inside the box over the area of the box, in a Lambert azimuthal equal-area
    projection centred on the box; CMR outlines are geodetic, so their edges are followed as great
    circles.
    """
    box = check_bbox(bbox)
    groups: list[list[Granule]] = []
    for granule in sorted(granules, key=lambda item: (item.time_start, item.granule_id)):
        if groups and (granule.time_start - groups[-1][-1].time_end).total_seconds() <= max_gap_s:
            groups[-1].append(granule)
        else:
            groups.append([granule])
    return [
        Overpass(
            time_start=group[0].time_start,
            time_end=max(granule.time_end for granule in group),
            granule_ids=tuple(granule.granule_id for granule in group),
            observed_fraction=_observed_fraction([granule.polygon for granule in group], box),
        )
        for group in groups
    ]


def stream_overpasses(
    stream: str,
    bbox: Sequence[float],
    start: datetime,
    end: datetime,
    *,
    opener: Callable = urllib.request.urlopen,
) -> tuple[list[Overpass], list[str]]:
    """
    Overpasses of a stream's fire product over ``bbox``, and the collections that gave them.

    The standard collection is searched first, then the near-real-time one from the end of the last
    standard granule (or from ``start`` when the standard collection has none) to ``end``.
    """
    if stream not in COLLECTIONS:
        raise ValueError(f"unknown stream {stream!r}; known streams: {', '.join(COLLECTIONS)}")
    (standard_name, standard_version), (nrt_name, nrt_version) = COLLECTIONS[stream]
    granules = search_granules(standard_name, standard_version, bbox, start, end, opener=opener)
    used = [f"{standard_name} {standard_version}"] if granules else []
    nrt_start = max(granule.time_end for granule in granules) if granules else start
    if nrt_start < end:
        recent = search_granules(nrt_name, nrt_version, bbox, nrt_start, end, opener=opener)
        recent = [granule for granule in recent if granule.time_start >= nrt_start]
        if recent:
            used.append(f"{nrt_name} {nrt_version}")
            granules += recent
    return overpasses(granules, bbox), used


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError(f"{value!r} has no time zone")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: str) -> datetime:
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _granule(short_name: str, version: str, entry: dict) -> Granule:
    granule_id = str(entry.get("producer_granule_id") or entry.get("title") or entry["id"])
    return Granule(
        short_name=short_name,
        version=version,
        granule_id=granule_id,
        time_start=_parse_time(entry["time_start"]),
        time_end=_parse_time(entry.get("time_end") or entry["time_start"]),
        polygon=_polygon(entry),
    )


def _polygon(entry: dict) -> tuple[tuple[float, float], ...]:
    """The outer ring of a granule: CMR writes it as one "lat lon lat lon ..." string."""
    rings = entry.get("polygons") or []
    if not rings or not rings[0]:
        return ()
    values = [float(value) for value in str(rings[0][0]).split()]
    return tuple(zip(values[1::2], values[0::2]))


def _meets_box(polygon, box: Bbox) -> bool:
    if not polygon:
        return True
    lon = [point[0] for point in polygon]
    lat = [point[1] for point in polygon]
    west, south, east, north = box
    if max(lon) < west or min(lon) > east or max(lat) < south or min(lat) > north:
        return False
    return _observed_fraction([polygon], box) > 0


def _observed_fraction(polygons, box: Bbox) -> float:
    if not polygons or any(not polygon for polygon in polygons):
        return math.nan
    # Imported here: the acquisition package stays import-light for the CLI.
    import pyproj  # pylint: disable=import-outside-toplevel
    import shapely  # pylint: disable=import-outside-toplevel
    from shapely.ops import transform  # pylint: disable=import-outside-toplevel

    west, south, east, north = box
    laea = pyproj.Transformer.from_crs(
        "EPSG:4326",
        pyproj.CRS.from_proj4(
            f"+proj=laea +lat_0={(south + north) / 2} +lon_0={(west + east) / 2} +ellps=WGS84 +units=m"
        ),
        always_xy=True,
    )
    project = laea.transform
    box_ring = _densify_linear([(west, south), (east, south), (east, north), (west, north)], 32)
    box_shape = transform(project, shapely.Polygon(box_ring))
    geod = pyproj.Geod(ellps="WGS84")
    swaths = [transform(project, shapely.Polygon(_densify_geodesic(geod, polygon))) for polygon in polygons]
    swath = shapely.union_all([shapely.make_valid(shape) for shape in swaths])
    return float(min(1.0, swath.intersection(box_shape).area / box_shape.area))


def _densify_linear(ring, steps: int) -> list[tuple[float, float]]:
    points = []
    for (x0, y0), (x1, y1) in zip(ring, [*ring[1:], ring[0]]):
        points += [(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps) for i in range(steps)]
    return points


def _densify_geodesic(geod, ring, step_m: float = 20_000) -> list[tuple[float, float]]:
    """Follow each edge of a geodetic ring as a great circle, with a point every ``step_m``."""
    points = []
    closed = list(ring) if ring[0] != ring[-1] else list(ring[:-1])
    for (lon0, lat0), (lon1, lat1) in zip(closed, [*closed[1:], closed[0]]):
        points.append((lon0, lat0))
        _, _, distance = geod.inv(lon0, lat0, lon1, lat1)
        count = int(distance // step_m)
        if count > 0:
            points += geod.npts(lon0, lat0, lon1, lat1, count)
    return points
