"""Synthetic event catalogues, templates filled as models, and bundles, for the catalogue tests."""

import hashlib
import shutil
from pathlib import Path

import geopandas as gpd
import h5py
import numpy as np
import pandas as pd
from shapely.geometry import Point

from firebench import standardize as fs
from firebench.benchmarks.catalogue_scoring import BUILDING_DAMAGE_PATH, FINAL_PERIMETER_PATH
from firebench.standardize import write_event_catalogue

ALBERS = "EPSG:5070"
CENTRE_X, CENTRE_Y = -2_000_000.0, 1_800_000.0
# Radii in metres: 70, 780, 7,000 and 26,000 acres, and class G.
RADII = {"ev_a": 300.0, "ev_b": 1000.0, "ev_c": 3000.0, "ev_d": 5000.0, "ev_e": 2000.0, "ev_f": 4000.0}
DAMAGE_E1 = ["Destroyed (>50%)"] * 8 + ["Major (26-50%)"] * 2 + ["No Damage"] * 2
DAMAGE_E2 = ["Destroyed (>50%)", "No Damage", "No Damage"]


def disc(event_id: str, extra: float = 0.0):
    """The disc of an event (radius plus ``extra`` metres) in EPSG:4326, centred on the event's point."""
    index = sorted(RADII).index(event_id)
    centre = Point(CENTRE_X + index * 150_000.0, CENTRE_Y)
    return (
        gpd.GeoSeries([centre.buffer(RADII[event_id] + extra, 128)], crs=ALBERS).to_crs("EPSG:4326").iloc[0]
    )


def make_catalogue(path, ids=None, structures=True, area_crs=ALBERS):
    ids = sorted(RADII) if ids is None else ids
    rows, geometries = [], []
    for position, event_id in enumerate(ids):
        perimeter = disc(event_id)
        centre = perimeter.centroid
        rows.append(
            {
                "event_id": event_id,
                "ignition_lat": centre.y,
                "ignition_lon": centre.x,
                "anchor_time": f"{2020 + position % 2}-08-1{position + 1}",
                "anchor_precision": "day",
                "containment_time": f"{2020 + position % 2}-08-2{position}" if position % 2 else "",
                "containment_precision": "day" if position % 2 else "",
            }
        )
        geometries.append(perimeter)
    events = gpd.GeoDataFrame(rows, geometry=geometries, crs="EPSG:4326")
    extra = {}
    if structures:
        records = []
        for event_id, labels in (("ev_a", DAMAGE_E1), ("ev_b", DAMAGE_E2)):
            if event_id in ids:
                centre = disc(event_id).centroid
                records += [
                    {"event_id": event_id, "lat": centre.y + 0.001 * k, "lon": centre.x, "damage": label}
                    for k, label in enumerate(labels)
                ]
        extra = {
            "structures": pd.DataFrame(records),
            "structures_license": "CC BY 4.0",
            "structures_data_source": "CAL FIRE DINS",
        }
    return write_event_catalogue(
        path,
        events,
        authors="tests",
        license="Public domain",
        data_source="tests",
        area_crs=area_crs,
        **extra,
    )


def kml(geometry) -> str:
    """A KML file of a polygon; None or an empty geometry gives a KML file with no polygon."""
    if geometry is None or geometry.is_empty:
        return '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document/></kml>'
    coordinates = " ".join(f"{lon!r},{lat!r},0" for lon, lat in geometry.exterior.coords)
    return (
        '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        "<Placemark><name>perimeter</name><Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{coordinates}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        "</Document></kml>"
    )


def write_model(directory: Path, geometry, labels=None, attributes=None, perimeter=True) -> Path:
    """A model file of an event: a perimeter KML beside it, and the building damage when given."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "model.h5"
    h5 = fs.new_std_file(path, "tests", overwrite=True)
    try:
        for key, value in {"model_name": "toy", "model_version": "1", **(attributes or {})}.items():
            if value is not None:
                h5.attrs[key] = value
        if perimeter:
            kml_path = directory / "perimeter.kml"
            kml_path.write_text(kml(geometry), encoding="utf-8")
            group = h5.create_group(FINAL_PERIMETER_PATH)
            group.attrs["rel_path"] = kml_path.name
            group.attrs["file_size_bytes"] = kml_path.stat().st_size
            group.attrs["sha256"] = hashlib.sha256(kml_path.read_bytes()).hexdigest()
            group.attrs["time"] = "2020-08-15T00:00:00Z"
        if labels is not None:
            h5.create_dataset(BUILDING_DAMAGE_PATH, data=np.array(labels, dtype="S16"))
    finally:
        h5.close()
    return path


def perfect_bundle(bundle: Path, catalogue_path, skip=(), labels=None):
    """A bundle whose models are the observed perimeters (and the observed damage when it is a case)."""
    from firebench.standardize import read_event_catalogue  # pylint: disable=import-outside-toplevel

    catalogue = read_event_catalogue(catalogue_path)
    for event_id, geometry in zip(catalogue.events["event_id"], catalogue.events.geometry):
        if event_id in skip:
            continue
        given = (
            {"ev_a": DAMAGE_E1, "ev_b": DAMAGE_E2}.get(event_id) if labels is None else labels.get(event_id)
        )
        write_model(bundle / event_id, geometry, given)
    return bundle


def fill_template(template: Path, model_dir: Path, geometry, labels=None) -> Path:
    """What an adapter does with a template: copy it, write the perimeter's KML, and the labels."""
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / "model.h5"
    shutil.copy(template, path)
    kml_path = model_dir / "perimeter.kml"
    kml_path.write_text(kml(geometry), encoding="utf-8")
    with h5py.File(path, "a") as h5:
        del h5.attrs["firebench_template"]
        h5.attrs["model_name"] = "toy"
        group = h5[FINAL_PERIMETER_PATH]
        group.attrs["rel_path"] = kml_path.name
        group.attrs["file_size_bytes"] = kml_path.stat().st_size
        group.attrs["sha256"] = hashlib.sha256(kml_path.read_bytes()).hexdigest()
        if labels is not None:
            h5[BUILDING_DAMAGE_PATH][...] = np.array(labels, dtype="S16")
    return path
