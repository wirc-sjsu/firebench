"""
Copernicus DEM GLO-30 tiles from the open archive on AWS.

The Copernicus DEM is a digital surface model of the whole world at 1 arc-second (about 30 m),
heights in m above the EGM2008 geoid, published by ESA under a free licence that asks for
attribution. It is cut in 1 by 1 degree tiles, each a cloud-optimized GeoTIFF of the bucket
``copernicus-dem-30m``, named by the south-west corner of the tile. A tile that is all sea is not
published: asking for it gives no file.
"""

import hashlib
import math
import shutil
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .http import http_get

BUCKET = "copernicus-dem-30m"
BASE_URL = f"https://{BUCKET}.s3.amazonaws.com"
PRODUCT = "Copernicus DEM GLO-30"
LICENSE_NOTE = (
    "Copernicus DEM GLO-30, © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided "
    "under COPERNICUS by the European Union and ESA; all rights reserved"
)


@dataclass(frozen=True)
class CopernicusTile:
    """One tile asked for: its file once read, or None when the archive has none (sea)."""

    name: str
    path: Path | None
    sha256: str | None = None
    bytes: int = 0


def tile_name(latitude: float, longitude: float) -> str:
    """The name of the tile holding a point, e.g. ``Copernicus_DSM_COG_10_N40_00_W120_00_DEM``."""
    south, west = math.floor(latitude), math.floor(longitude)
    north_south = f"N{south:02d}" if south >= 0 else f"S{-south:02d}"
    east_west = f"E{west:03d}" if west >= 0 else f"W{-west:03d}"
    return f"Copernicus_DSM_COG_10_{north_south}_00_{east_west}_00_DEM"


def tiles_for_bbox(bbox) -> list[str]:
    """The names of the tiles a box ``(west, south, east, north)`` touches, south-west first."""
    west, south, east, north = (float(value) for value in bbox)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"invalid box {bbox!r}: expected west < east and south < north, in degrees")
    names = []
    for lat in range(math.floor(south), math.ceil(north)):
        for lon in range(math.floor(west), math.ceil(east)):
            names.append(tile_name(lat + 0.5, lon + 0.5))
    return names


def tile_url(name: str) -> str:
    return f"{BASE_URL}/{name}/{name}.tif"


def fetch_copernicus_dem(
    bbox,
    directory: Path | str,
    *,
    local_dir: Path | str | None = None,
    opener: Callable = urllib.request.urlopen,
) -> list[CopernicusTile]:
    """
    Get the tiles a box touches into ``directory``: downloaded from the archive, or copied from
    ``local_dir`` (a folder of ``<name>.tif`` files, for tests and offline work). A tile the archive
    does not have is returned with no path. A tile is 10 to 40 MB; the caller deletes the directory.

    Raises
    ------
    ConnectionError
        If the archive cannot be reached.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name in tiles_for_bbox(bbox):
        target = directory / f"{name}.tif"
        if local_dir is not None:
            source = Path(local_dir) / f"{name}.tif"
            if not source.is_file():
                tiles.append(CopernicusTile(name=name, path=None))
                continue
            shutil.copyfile(source, target)
        else:
            try:
                target.write_bytes(http_get(tile_url(name), opener=opener, not_found_codes=(403, 404)))
            except FileNotFoundError:
                tiles.append(CopernicusTile(name=name, path=None))
                continue
        data = target.read_bytes()
        tiles.append(
            CopernicusTile(name=name, path=target, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        )
    return tiles
