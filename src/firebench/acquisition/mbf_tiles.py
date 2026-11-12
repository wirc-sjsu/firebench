"""
Microsoft Global ML Building Footprints, by box.

Microsoft publishes the footprints it detected in Bing Maps imagery under CDLA Permissive 2.0, cut in
tiles of the web-mercator grid at zoom 9 (about 78 km at the equator). ``dataset-links.csv`` lists
each tile by its quadkey with the URL of its file: gzipped text with one GeoJSON feature per line,
which is the format ``standardize_dins_building_damage`` reads. The index and the tiles are kept in
the FireBench cache, so a fire next to another one, or a second build, downloads nothing.
"""

import csv
import gzip
import hashlib
import io
import json
import math
import os
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .cache import atomic_write_bytes, cache_subdir
from .http import http_get

INDEX_URL_ENV = "FIREBENCH_MBF_INDEX_URL"
INDEX_URL = "https://bfppub.blob.core.windows.net/%24web/2026-08-13/dataset-links.csv"
ZOOM = 9
INDEX_MAX_AGE = 30 * 24 * 3600  # s; Microsoft refreshes the dataset a few times a year
PRODUCT = "Microsoft Global ML Building Footprints"
LICENSE_NOTE = "Microsoft Global ML Building Footprints, CDLA Permissive 2.0"


@dataclass(frozen=True)
class MbfTile:
    """One tile of the grid a box touches."""

    quadkey: str
    cached: bool = False
    bytes: int = 0


@dataclass(frozen=True)
class MbfFootprints:
    """The footprints written for a box."""

    path: Path
    n_footprints: int
    sha256: str
    tiles: list[MbfTile]


def _check_box(bbox) -> tuple[float, float, float, float]:
    west, south, east, north = (float(value) for value in bbox)
    if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
        raise ValueError(f"invalid box {bbox!r}: expected west < east and south < north, in degrees")
    return west, south, east, north


def _tile_xy(latitude: float, longitude: float, zoom: int = ZOOM) -> tuple[int, int]:
    n = 2**zoom
    x = int((longitude + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def quadkey(x: int, y: int, zoom: int = ZOOM) -> str:
    """The quadkey of tile ``x``, ``y``: one digit (0 to 3) per zoom level, from the coarsest."""
    return "".join(str(((x >> i) & 1) + 2 * ((y >> i) & 1)) for i in range(zoom - 1, -1, -1))


def quadkeys_for_bbox(bbox) -> list[str]:
    """The quadkeys of the zoom 9 tiles a box ``(west, south, east, north)`` touches."""
    west, south, east, north = _check_box(bbox)
    x_min, y_max = _tile_xy(south, west)
    x_max, y_min = _tile_xy(north, east)
    return [quadkey(x, y) for y in range(y_min, y_max + 1) for x in range(x_min, x_max + 1)]


def _index(cache_root: Path | None, opener: Callable) -> dict[str, tuple[str, str]]:
    """``{quadkey: (url, upload date)}`` from the cached index, fetched again when it is old."""
    url = os.environ.get(INDEX_URL_ENV) or INDEX_URL
    path = cache_subdir("mbf", root=cache_root) / "dataset-links.csv"
    stale = not path.is_file() or time.time() - path.stat().st_mtime > INDEX_MAX_AGE
    if stale:
        try:
            atomic_write_bytes(path, http_get(url, opener=opener))
        except ConnectionError:
            if not path.is_file():
                raise
    with open(path, encoding="utf-8", newline="") as lines:
        rows = csv.DictReader(lines)
        return {row["QuadKey"]: (row["Url"], row.get("UploadDate", "")) for row in rows}


def _tile_lines(  # pylint: disable=too-many-locals
    keys: list[str], cache_root, local_dir, opener
) -> list[tuple[MbfTile, bytes]]:
    """The text of each tile that exists, downloaded once and kept in the cache."""
    found = []
    index = None
    for key in keys:
        if local_dir is not None:
            for name in (f"{key}.geojsonl", f"{key}.csv.gz"):
                source = Path(local_dir) / name
                if source.is_file():
                    data = source.read_bytes()
                    data = gzip.decompress(data) if name.endswith(".gz") else data
                    found.append((MbfTile(key, bytes=len(data)), data))
                    break
            continue
        if index is None:
            index = _index(cache_root, opener)
        if key not in index:
            continue  # sea or outside the dataset's coverage
        url, date = index[key]
        target = cache_subdir("mbf", "tiles", root=cache_root) / f"{key}-{date or 'undated'}.csv.gz"
        cached = target.is_file()
        if not cached:
            atomic_write_bytes(target, http_get(url, opener=opener))
        raw = target.read_bytes()
        try:
            found.append((MbfTile(key, cached, len(raw)), gzip.decompress(raw)))
        except (OSError, EOFError) as exc:
            target.unlink(missing_ok=True)  # a torn file must not stay in the cache
            raise ConnectionError(f"the tile {key} of {PRODUCT} is not a gzip file: {exc}") from exc
    return found


def _coordinates(geometry):
    for item in geometry:
        if isinstance(item[0], (int, float)):
            yield item
        else:
            yield from _coordinates(item)


def fetch_mbf_footprints(  # pylint: disable=too-many-locals
    bbox,
    out_file: Path | str,
    *,
    cache_dir: Path | str | None = None,
    local_dir: Path | str | None = None,
    opener: Callable = urllib.request.urlopen,
) -> MbfFootprints:
    """
    Write the footprints that touch a box ``(west, south, east, north)`` as line-delimited GeoJSON.

    The tiles come from Microsoft, or from ``local_dir`` (a folder of ``<quadkey>.csv.gz`` or
    ``<quadkey>.geojsonl`` files, for tests and offline work). Tiles are kept in ``cache_dir`` (the
    FireBench cache by default). Footprints whose bounds miss the box are left out. A tile holds
    up to a few million footprints: the file is written line by line.

    Raises
    ------
    ValueError
        If the box is invalid, or no tile of the dataset covers it.
    ConnectionError
        If the index or a tile cannot be downloaded.
    """
    west, south, east, north = _check_box(bbox)
    keys = quadkeys_for_bbox((west, south, east, north))
    root = Path(cache_dir) if cache_dir is not None else None
    tiles = _tile_lines(keys, root, local_dir, opener)
    if not tiles:
        raise ValueError(f"no tile of {PRODUCT} covers the box {(west, south, east, north)}")
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    digest, count = hashlib.sha256(), 0
    with open(out_file, "wb") as out:
        for _, data in tiles:
            for line in io.BytesIO(data):
                if not line.strip():
                    continue
                try:
                    coords = list(_coordinates(json.loads(line)["geometry"]["coordinates"]))
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f"a line of {PRODUCT} is not a feature: {exc}") from exc
                lons, lats = [c[0] for c in coords], [c[1] for c in coords]
                if max(lons) < west or min(lons) > east or max(lats) < south or min(lats) > north:
                    continue
                out.write(line if line.endswith(b"\n") else line + b"\n")
                digest.update(line)
                count += 1
    return MbfFootprints(out_file, count, digest.hexdigest(), [tile for tile, _ in tiles])
