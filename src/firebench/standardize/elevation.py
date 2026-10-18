"""
Ground elevation of a box or a point, from LANDFIRE's elevation and the Copernicus DEM.

LANDFIRE's elevation (``LF20xx_Elev``) is a bare-earth model of the United States derived from
USGS 3DEP, in m above NAVD88, on 30 m cells in EPSG:5070. The Copernicus DEM GLO-30
(:mod:`firebench.acquisition.copernicus_dem`) covers the whole world at 1 arc-second, in m above
EGM2008, but is a surface model: it holds the height of trees and buildings. LANDFIRE is used
wherever it has a value, the Copernicus DEM elsewhere; each cell records which. Both heights are
above mean sea level to within a metre or two.

- :func:`terrain_elevation_grid` samples both on a regular longitude-latitude grid over a box, and
  :func:`standardize_terrain_elevation` writes it to ``/spatial_2d/terrain_elevation``.
- :func:`ground_elevation` gives the elevation of one point.

Licence attributes are not written: the caller sets them, from the sources the grid used.
"""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import hdf5plugin
import numpy as np
import rasterio
from pyproj import CRS as ProjCRS
from pyproj import Transformer
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds
from scipy.ndimage import map_coordinates

from ..tools.namespace import StandardVariableNames as svn
from .std_file_info import SPATIAL_2D
from .tools import check_std_version

GROUP = f"/{SPATIAL_2D}/terrain_elevation"
CRS = "EPSG:4326"
# One arc-second, the cell of the Copernicus DEM; a grid of more cells than the cap is coarser.
DEFAULT_STEP_DEG = 1.0 / 3600.0
MAX_CELLS = 16_000_000
# Codes of `elevation_source`.
NO_SOURCE, LANDFIRE, COPERNICUS = 0, 1, 2
SOURCE_NAMES = {LANDFIRE: "LANDFIRE", COPERNICUS: "Copernicus DEM GLO-30"}


@dataclass
class ElevationGrid:
    """Ground elevation on a regular grid of cell centres, latitudes south to north."""

    lat: np.ndarray  # (n_lat,)
    lon: np.ndarray  # (n_lon,)
    elevation: np.ndarray  # (n_lat, n_lon) float32, m above mean sea level, NaN where no source has one
    source: np.ndarray  # (n_lat, n_lon) uint8, NO_SOURCE, LANDFIRE, or COPERNICUS
    bbox: tuple[float, float, float, float]
    step: float
    # What was read: the LANDFIRE file, and the Copernicus tiles by name with their checksum.
    landfire_file: str | None = None
    copernicus_tiles: dict[str, str | None] = field(default_factory=dict)

    def cells(self, code: int) -> int:
        """How many cells took their elevation from a source."""
        return int((self.source == code).sum())


def terrain_elevation_grid(
    bbox,
    *,
    landfire_path: Path | str | None = None,
    copernicus: Sequence = (),
    step_deg: float = DEFAULT_STEP_DEG,
) -> ElevationGrid:
    """
    The ground elevation of a box ``(west, south, east, north)`` on a grid of ``step_deg``, coarser
    when the box would hold more than ``MAX_CELLS`` cells. Values are bilinear between the cells of
    each source. ``copernicus`` are the tiles of :func:`fetch_copernicus_dem` (or paths).

    Raises
    ------
    ValueError
        If the box is invalid, or no source gives a value anywhere in it.
    """
    west, south, east, north = _bbox(bbox)
    step = float(step_deg)
    cells = ((east - west) / step) * ((north - south) / step)
    if cells > MAX_CELLS:
        step *= math.sqrt(cells / MAX_CELLS)
    # A span of a whole number of steps, give or take rounding, is that many cells.
    lon = west + (np.arange(max(1, math.ceil((east - west) / step - 1e-6))) + 0.5) * step
    lat = south + (np.arange(max(1, math.ceil((north - south) / step - 1e-6))) + 0.5) * step
    grid_lon, grid_lat = np.meshgrid(lon, lat)
    elevation, source, landfire_file, tiles = _sample(
        grid_lon.ravel(), grid_lat.ravel(), landfire_path, copernicus
    )
    if not np.isfinite(elevation).any():
        raise ValueError(
            "no elevation in the box: LANDFIRE does not cover it and no Copernicus tile was read"
        )
    shape = grid_lat.shape
    return ElevationGrid(
        lat=lat,
        lon=lon,
        elevation=elevation.reshape(shape).astype(np.float32),
        source=source.reshape(shape),
        bbox=(west, south, east, north),
        step=step,
        landfire_file=landfire_file,
        copernicus_tiles=tiles,
    )


def ground_elevation(
    latitude: float,
    longitude: float,
    *,
    landfire_path: Path | str | None = None,
    copernicus: Sequence = (),
) -> tuple[float, str] | None:
    """The ground elevation of a point in m above mean sea level and the name of its source, or None
    when neither source has one."""
    elevation, source, _, _ = _sample(
        np.array([float(longitude)]), np.array([float(latitude)]), landfire_path, copernicus
    )
    if not np.isfinite(elevation[0]):
        return None
    return float(elevation[0]), SOURCE_NAMES[int(source[0])]


def standardize_terrain_elevation(
    grid: ElevationGrid, h5file: h5py.File, *, overwrite: bool = False, compression_lvl: int = 6
) -> h5py.Group:
    """
    Write ``/spatial_2d/terrain_elevation``: ``position_lat`` and ``position_lon`` (cell centres),
    ``terrain_elevation`` (m above mean sea level, NaN where none), and ``elevation_source``.

    Raises
    ------
    ValueError
        If the group exists and ``overwrite`` is False.
    """
    check_std_version(h5file)
    if GROUP in h5file:
        if not overwrite:
            raise ValueError(f"group {GROUP} already exists in {h5file.filename}. Set `overwrite` to True.")
        del h5file[GROUP]
    # The parent group carries no attribute, so fragments merge without conflict.
    group = h5file.require_group(f"/{SPATIAL_2D}").create_group(GROUP.rsplit("/", 1)[-1])
    west, south, east, north = grid.bbox
    attrs = {
        "crs": CRS,
        "description": (
            "Ground elevation: LANDFIRE's bare-earth elevation (USGS 3DEP) where it has a value, the "
            "Copernicus DEM GLO-30 (a surface model) elsewhere; elevation_source tells which."
        ),
        "vertical_reference": "mean sea level: NAVD88 for LANDFIRE, EGM2008 for the Copernicus DEM",
        "step": grid.step,
        "step_units": "degree",
        "sources": json.dumps(
            {
                "landfire": {"file": grid.landfire_file, "cells": grid.cells(LANDFIRE)},
                "copernicus": {
                    "tiles": [{"name": name, "sha256": sha} for name, sha in grid.copernicus_tiles.items()],
                    "cells": grid.cells(COPERNICUS),
                },
            }
        ),
    }
    for name, value in (("west", west), ("south", south), ("east", east), ("north", north)):
        attrs[f"frame_{name}"] = float(value)
        attrs[f"frame_{name}_units"] = "degree"
    for key, value in attrs.items():
        group.attrs[key] = value
    compression = hdf5plugin.Zstd(clevel=compression_lvl)
    for name, data, units in (("position_lat", grid.lat, "degree"), ("position_lon", grid.lon, "degree")):
        dataset = group.create_dataset(name, data=np.asarray(data, dtype=np.float64), **compression)
        dataset.attrs["units"] = units
    values = group.create_dataset(
        svn.TERRAIN_ELEVATION.value,
        data=grid.elevation.astype(np.float32),
        chunks=True,
        fillvalue=np.float32(np.nan),
        **compression,
    )
    values.attrs["units"] = "m"
    values.attrs["description"] = "Ground elevation above mean sea level at the cell centre"
    origin = group.create_dataset(
        "elevation_source", data=grid.source.astype(np.uint8), chunks=True, **compression
    )
    origin.attrs["flag_values"] = np.array([NO_SOURCE, LANDFIRE, COPERNICUS], dtype=np.uint8)
    origin.attrs["flag_meanings"] = "none landfire copernicus_dem_glo30"
    return group


def read_terrain_elevation(h5file: h5py.File) -> ElevationGrid:
    """The grid of ``/spatial_2d/terrain_elevation``."""
    group = h5file.get(GROUP)
    if not isinstance(group, h5py.Group):
        raise ValueError(f"no {GROUP} in the file")
    sources = json.loads(_text(group.attrs["sources"]))
    return ElevationGrid(
        lat=group["position_lat"][()],
        lon=group["position_lon"][()],
        elevation=group[svn.TERRAIN_ELEVATION.value][()],
        source=group["elevation_source"][()],
        bbox=tuple(float(group.attrs[f"frame_{side}"]) for side in ("west", "south", "east", "north")),
        step=float(group.attrs["step"]),
        landfire_file=sources["landfire"]["file"],
        copernicus_tiles={item["name"]: item["sha256"] for item in sources["copernicus"]["tiles"]},
    )


# Sampling ------------------------------------------------------------------------------------------


def _sample(lon: np.ndarray, lat: np.ndarray, landfire_path, copernicus):
    elevation = np.full(lon.shape, np.nan)
    source = np.zeros(lon.shape, dtype=np.uint8)
    landfire_file = None
    if landfire_path is not None:
        landfire_file = Path(landfire_path).name
        values = _bilinear(Path(landfire_path), lon, lat)
        found = np.isfinite(values)
        elevation[found], source[found] = values[found], LANDFIRE
    tiles = {}
    for tile in copernicus:
        # A tile of `fetch_copernicus_dem`, or the path of one.
        if isinstance(tile, (str, Path)):
            path, name, sha256 = Path(tile), Path(tile).stem, None
        else:
            path, name, sha256 = tile.path, tile.name, tile.sha256
        tiles[name] = sha256
        missing = ~np.isfinite(elevation)
        if path is None or not missing.any():
            continue
        values = np.full(lon.shape, np.nan)
        values[missing] = _bilinear(Path(path), lon[missing], lat[missing])
        found = missing & np.isfinite(values)
        elevation[found], source[found] = values[found], COPERNICUS
    return elevation, source, landfire_file, tiles


def _bilinear(path: Path, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Values of the first band of a GeoTIFF at points, bilinear between cell centres; NaN outside it
    or next to a cell with no value."""
    out = np.full(lon.shape, np.nan)
    if lon.size == 0:
        return out
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"{path.name} has no coordinate reference system")
        target = ProjCRS.from_wkt(src.crs.to_wkt())
        if target.equals(ProjCRS.from_user_input(CRS)):
            xs, ys = lon, lat
        else:
            xs, ys = Transformer.from_crs(CRS, target, always_xy=True).transform(lon, lat)
        bounds = transform_bounds(CRS, src.crs, lon.min(), lat.min(), lon.max(), lat.max(), densify_pts=21)
        window = from_bounds(*bounds, transform=src.transform)
        col0 = max(0, math.floor(window.col_off) - 2)
        row0 = max(0, math.floor(window.row_off) - 2)
        col1 = min(src.width, math.ceil(window.col_off + window.width) + 3)
        row1 = min(src.height, math.ceil(window.row_off + window.height) + 3)
        if col1 <= col0 or row1 <= row0:
            return out
        data = src.read(1, window=Window(col0, row0, col1 - col0, row1 - row0)).astype(np.float64)
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        if np.issubdtype(src.dtypes[0], np.signedinteger):
            # LANDFIRE marks cells outside the United States with negative values.
            data[data < -1000] = np.nan
        inverse = ~src.transform
    xs, ys = np.asarray(xs), np.asarray(ys)
    cols = inverse.a * xs + inverse.b * ys + inverse.c - 0.5 - col0
    rows = inverse.d * xs + inverse.e * ys + inverse.f - 0.5 - row0
    inside = (cols >= -0.5) & (cols <= data.shape[1] - 0.5) & (rows >= -0.5) & (rows <= data.shape[0] - 0.5)
    out[inside] = map_coordinates(data, [rows[inside], cols[inside]], order=1, mode="nearest")
    return out


def _bbox(bbox) -> tuple[float, float, float, float]:
    west, south, east, north = (float(value) for value in bbox)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"invalid box {bbox!r}: expected west < east and south < north, in degrees")
    return west, south, east, north


def _text(value) -> str:
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else str(value)
