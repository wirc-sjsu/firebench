import os
import re
import zipfile
from os.path import getsize
from pathlib import Path

import geopandas as gpd
import h5py
from pyproj import CRS

from ..tools import calculate_sha256, ureg
from ..tools.logging_config import logger
from .std_file_info import GEOPOLYGONS
from .tools import _decode_h5_text, check_std_version, is_iso8601

PERIMETER_LAYER = "fire_perimeter"
_POLYGON_TYPES = ("Polygon", "MultiPolygon")
_UTC_OFFSET = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")
_INNER_BOUNDARY = re.compile(rb"<innerBoundaryIs\b[^>]*>(.*?)</innerBoundaryIs>", re.DOTALL)
_LINEAR_RING = re.compile(rb"<LinearRing\b.*?</LinearRing>", re.DOTALL)


def list_kml_layers(path: Path) -> list[dict]:
    """
    List the layers of a KML or KMZ file, in file order.

    The names are the ones GDAL gives to the layers. They are the only names
    `standardize_perimeter_from_kml` accepts, and they can differ between GDAL builds: a folder that
    only holds other folders may be listed as a layer of its own, with no polygon.

    Parameters
    ----------
    path : Path
        A `.kml` or `.kmz` file. Of a `.kmz` archive, `doc.kml` is read, or else its first KML file.

    Returns
    -------
    list[dict]
        One item per layer: `{"name": str, "n_polygons": int}`, where `n_polygons` counts the
        features of the layer that are polygons or multipolygons.

    Raises
    ------
    ValueError
        If the file is missing, is not a KML or KMZ file, or cannot be read.
    """  # pylint: disable=line-too-long
    return _layers(path, _read_kml(path))


def standardize_perimeter_from_kml(
    kml_path: Path,
    h5file: h5py.File,
    group_name: str,
    time: str,
    kml_dir: Path,
    layer: str | None = None,
    area_crs: str | None = None,
    overwrite: bool = False,
) -> h5py.Group:
    """
    Read one fire perimeter from a KML or KMZ file and register it in a FireBench HDF5 standard file.

    The polygons of the layer are written as one KML file in `kml_dir`, in a layer named
    `fire_perimeter`, and the group `/polygons/<group_name>` references that file. Licence
    attributes are not written: the caller sets them.

    Every hole of a polygon is kept. Some KML files put several rings in one inner boundary, which
    GDAL reads as a single hole: such a boundary is read as one hole per ring.

    When the function raises, the HDF5 file and the KML files are left as they were.

    Parameters
    ----------
    kml_path : Path
        A `.kml` or `.kmz` file.
    h5file : h5py.File
        Target HDF5 file.
    group_name : str
        Name of the group under `/polygons`. The KML file is named after it, with every character
        outside `[A-Za-z0-9_]` replaced by `_`.
    time : str
        Time of the perimeter, ISO 8601 with a UTC offset, for example `2021-08-17T20:20-07:00`.
    kml_dir : Path
        Directory the KML file is written in. It must be inside the directory of the HDF5 file, so
        the stored path is relative.
    layer : str | None
        Layer to read, as named by `list_kml_layers`. None reads the only layer of the file.
    area_crs : str | None
        Projected CRS the burnt area is computed in. None uses a Lambert azimuthal equal-area
        projection centred on the perimeter.
    overwrite : bool
        Replace the group if it exists. Default: False

    Returns
    -------
    h5py.Group
        The group written.

    Raises
    ------
    ValueError
        If the file cannot be read, the layer is unknown or not given when the file has several, the
        layer holds no polygon, the time has no UTC offset, `kml_dir` is outside the directory of the
        HDF5 file, or the group exists and `overwrite` is False.
    """  # pylint: disable=line-too-long
    logger.debug("Standardize perimeter %s from file %s", group_name, kml_path)
    check_std_version(h5file)

    if not is_iso8601(time) or not _UTC_OFFSET.search(time):
        raise ValueError(
            f"time {time!r} must be ISO 8601 with a UTC offset, for example 2021-08-17T20:20-07:00"
        )
    if not group_name or "/" in group_name:
        raise ValueError(f"group name {group_name!r} must not be empty or contain '/'")
    group_path = f"/{GEOPOLYGONS}/{group_name}"
    if group_path in h5file and not overwrite:
        raise ValueError(
            f"group {group_path} already exists in {h5file.filename}. Set `overwrite` to True to replace it."
        )

    h5_dir = Path(h5file.filename).resolve().parent
    kml_dir = Path(kml_dir).resolve()
    if not kml_dir.is_relative_to(h5_dir):
        raise ValueError(f"kml_dir {kml_dir} must be inside the directory of the HDF5 file, {h5_dir}")
    kml_file = kml_dir / (re.sub(r"[^A-Za-z0-9_]", "_", group_name) + ".kml")
    rel_path = kml_file.relative_to(h5_dir).as_posix()
    for other_name, other in h5file.get(GEOPOLYGONS, {}).items():
        if other_name != group_name and _decode_h5_text(other.attrs.get("rel_path")) == rel_path:
            raise ValueError(
                f"group /{GEOPOLYGONS}/{other_name} already uses the file {rel_path}: "
                f"the group name {group_name!r} gives the same KML file name"
            )

    kml = _read_kml(kml_path)
    layer = _select_layer(kml_path, kml, layer)
    perimeter = _read_polygons(kml_path, kml, layer)
    if perimeter.empty:
        raise ValueError(f"layer {layer!r} of {kml_path} holds no polygon")
    burnt_area = _area_acres(perimeter, area_crs)

    perimeter = perimeter.rename(columns={"description": "Description"})
    kept_columns = [name for name in ("Name", "Description") if name in perimeter.columns]
    _write_kml(perimeter[[*kept_columns, perimeter.geometry.name]], kml_file)

    if group_path in h5file:
        del h5file[group_path]
    group = h5file.create_group(group_path)
    group.attrs["rel_path"] = rel_path
    group.attrs["sha256"] = calculate_sha256(kml_file)
    group.attrs["file_size_bytes"] = getsize(kml_file)
    group.attrs["time"] = time
    group.attrs["burnt_area"] = burnt_area
    group.attrs["burnt_area_units"] = "acre"
    return group


def _read_kml(path: Path) -> bytes:
    """Return the KML content of a KML or KMZ file, rewritten with one ring per inner boundary."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"file {path} not found")
    suffix = path.suffix.lower()
    if suffix not in (".kml", ".kmz"):
        raise ValueError(f"{path} is not a .kml or .kmz file")

    try:
        if suffix == ".kml":
            kml = path.read_bytes()
        else:
            with zipfile.ZipFile(path) as archive:
                members = [name for name in archive.namelist() if name.lower().endswith(".kml")]
                if not members:
                    raise ValueError(f"KMZ file {path} holds no KML file")
                kml = archive.read("doc.kml" if "doc.kml" in members else members[0])
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{path} is not a KMZ file: it is not a ZIP archive") from exc
    except OSError as exc:
        raise ValueError(f"{path} could not be read: {exc}") from exc
    return _INNER_BOUNDARY.sub(_one_boundary_per_ring, kml)


def _one_boundary_per_ring(inner_boundary: re.Match) -> bytes:
    """
    Rewrite an inner boundary that holds several rings as one inner boundary per ring.

    KML allows one ring per `innerBoundaryIs`. Files that hold several are common, and GDAL keeps
    only one of them, so the other holes of the polygon would be lost.
    """
    rings = _LINEAR_RING.findall(inner_boundary.group(1))
    if len(rings) < 2:
        return inner_boundary.group(0)
    return b"".join(b"<innerBoundaryIs>" + ring + b"</innerBoundaryIs>" for ring in rings)


def _layers(path: Path, kml: bytes) -> list[dict]:
    return [
        {"name": name, "n_polygons": len(_read_polygons(path, kml, name, columns=[]))}
        for name in _layer_names(path, kml)
    ]


def _layer_names(path: Path, kml: bytes) -> list[str]:
    try:
        return [str(name) for name in gpd.list_layers(kml)["name"]]
    except (RuntimeError, OSError) as exc:
        raise ValueError(f"{path} could not be read as a KML file: {exc}") from exc


def _read_polygons(path: Path, kml: bytes, layer: str, columns: list[str] | None = None):
    try:
        features = gpd.read_file(kml, layer=layer, columns=columns)
    except (RuntimeError, OSError) as exc:
        raise ValueError(f"layer {layer!r} of {path} could not be read: {exc}") from exc
    return features[features.geom_type.isin(_POLYGON_TYPES)]


def _select_layer(path: Path, kml: bytes, layer: str | None) -> str:
    names = _layer_names(path, kml)
    if layer is None and len(names) == 1:
        return names[0]
    if layer in names:
        return layer

    available = ", ".join(
        f"{item['name']!r} ({item['n_polygons']} polygons)" for item in _layers(path, kml)
    )
    if layer is None:
        raise ValueError(f"{path} has {len(names)} layers. Name one with `layer`: {available}")
    raise ValueError(f"layer {layer!r} not found in {path}. Layers: {available}")


def _write_kml(perimeter: gpd.GeoDataFrame, kml_file: Path):
    """Write the perimeter as a new KML file, then put it in the place of the previous one, if any."""
    kml_file.parent.mkdir(parents=True, exist_ok=True)
    # GDAL updates an existing KML file with another driver than the one that writes a new file
    new_file = kml_file.with_name(kml_file.name + ".new")
    new_file.unlink(missing_ok=True)
    try:
        perimeter.to_file(new_file, driver="KML", layer=PERIMETER_LAYER)
        os.replace(new_file, kml_file)
    finally:
        new_file.unlink(missing_ok=True)


def _area_acres(perimeter: gpd.GeoDataFrame, area_crs: str | None) -> float:
    if area_crs is None:
        lon_min, lat_min, lon_max, lat_max = perimeter.total_bounds
        area_crs = (
            f"+proj=laea +lat_0={(lat_min + lat_max) / 2} +lon_0={(lon_min + lon_max) / 2} "
            "+datum=WGS84 +units=m"
        )
    else:
        crs = CRS.from_user_input(area_crs)
        if not crs.is_projected or crs.axis_info[0].unit_name != "metre":
            raise ValueError(f"area_crs {area_crs!r} must be a projected CRS in metres")
    area = float(perimeter.to_crs(area_crs).area.sum())
    return ureg.Quantity(area, "m^2").to("acre").magnitude
