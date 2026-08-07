"""Reproducible release inventory for Caldor weather observations."""

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
from importlib.resources import files
import json
from numbers import Integral
from pathlib import Path
from tempfile import NamedTemporaryFile

from h5py import File
import numpy as np

from firebench import __version__
from firebench import standardize as fs
from firebench.tools import calculate_sha256

from . import c001_caldor
from . import c001_caldor_config as cfg
from ..standardize.sensor_height_resources import (
    SENSOR_HEIGHT_RESOURCE_FILES,
    SENSOR_HEIGHT_RESOURCE_SCHEMA_VERSION,
    SENSOR_HEIGHT_RESOURCE_TYPES,
)

WEATHER_RELEASE_INVENTORY_SCHEMA_VERSION = 1


def _h5_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _is_canonical_confidence(value) -> bool:
    array = np.asarray(value)
    if array.ndim != 0:
        return False
    scalar = array.item()
    if isinstance(scalar, (bool, np.bool_)) or not isinstance(scalar, Integral):
        return False
    return int(scalar) in {int(confidence) for confidence in fs.SensorHeightConfidence}


def _resource_binding() -> dict:
    resource_files = {}
    for record_type in SENSOR_HEIGHT_RESOURCE_TYPES:
        filename = SENSOR_HEIGHT_RESOURCE_FILES[record_type]
        content = files("firebench").joinpath(f"resources/{filename}").read_bytes()
        resource_files[record_type] = {
            "filename": filename,
            "sha256": sha256(content).hexdigest(),
        }

    canonical_binding = json.dumps(resource_files, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": SENSOR_HEIGHT_RESOURCE_SCHEMA_VERSION,
        "expanded_record_counts": fs.validate_installed_sensor_height_resources(),
        "files": resource_files,
        "combined_sha256": sha256(canonical_binding).hexdigest(),
    }


def _empty_confidence_counts() -> dict[str, int]:
    return {str(int(confidence)): 0 for confidence in fs.SensorHeightConfidence}


def _dataset_inventory(obs_dataset: File) -> dict:
    confidence_counts = Counter()
    source_counts = Counter()
    canonical_count = 0
    matching_description_count = 0
    total = 0
    warning_cache = set()

    for station in obs_dataset.get(fs.TIME_SERIES, {}).values():
        for variable_spec in cfg.WX_VARIABLE_SPECS:
            variable = variable_spec["variable"]
            if variable not in station:
                continue
            total += 1
            dataset = station[variable]
            raw_confidence = dataset.attrs.get(fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE)
            confidence = fs.parse_sensor_height_confidence(
                raw_confidence,
                station=station.name.rsplit("/", maxsplit=1)[-1],
                variable=variable,
                warning_cache=warning_cache,
            )
            confidence_counts[str(int(confidence))] += 1
            source_counts[_h5_text(dataset.attrs.get("sensor_height_source", "<missing>"))] += 1
            if _is_canonical_confidence(raw_confidence):
                canonical_count += 1
                description = dataset.attrs.get(fs.SENSOR_HEIGHT_CONFIDENCE_DESCRIPTION_ATTRIBUTE)
                if description is not None and _h5_text(
                    description
                ) == fs.sensor_height_confidence_description(confidence):
                    matching_description_count += 1

    counts = _empty_confidence_counts()
    counts.update(confidence_counts)
    return {
        "variable_datasets": total,
        "confidence_levels": counts,
        "sensor_height_sources": dict(sorted(source_counts.items())),
        "canonical_numeric_confidence": canonical_count,
        "noncanonical_or_missing_confidence": total - canonical_count,
        "canonical_confidence_with_matching_description": matching_description_count,
    }


def _period_inventory(obs_dataset: File) -> list[dict]:
    rows = []
    selection_context = {"weather_confidence_warnings": set()}

    # The inventory reports malformed metadata explicitly, so suppress duplicate selector warnings.
    for station_name, station in obs_dataset.get(fs.TIME_SERIES, {}).items():
        for variable_spec in cfg.WX_VARIABLE_SPECS:
            variable = variable_spec["variable"]
            if variable in station:
                selection_context["weather_confidence_warnings"].add((station_name, variable))

    for period_set in cfg.WX_PERIOD_SETS:
        for period_name, period in period_set["periods"].items():
            for variable_spec in cfg.WX_VARIABLE_SPECS:
                variable = variable_spec["variable"]
                all_sources = c001_caldor._select_weather_stations(
                    obs_dataset,
                    variable,
                    period,
                    fs.WeatherStationSet.ALL_SOURCES,
                    selection_context,
                )
                tso = c001_caldor._select_weather_stations(
                    obs_dataset,
                    variable,
                    period,
                    fs.WeatherStationSet.TSO,
                    selection_context,
                )
                confidence_counts = Counter(
                    str(station_info["confidence"]) for station_info in all_sources["included"]
                )
                source_counts = Counter()
                for station_info in all_sources["included"]:
                    dataset = obs_dataset[f"{fs.TIME_SERIES}/{station_info['station']}/{variable}"]
                    source_counts[_h5_text(dataset.attrs.get("sensor_height_source", "<missing>"))] += 1

                counts = _empty_confidence_counts()
                counts.update(confidence_counts)
                rows.append(
                    {
                        "period_set": period_set["name"],
                        "period": period_name,
                        "start": period[0].isoformat(),
                        "end": period[1].isoformat(),
                        "variable": variable,
                        "all_sources_stations": len(all_sources["included"]),
                        "tso_stations": len(tso["included"]),
                        "confidence_levels": counts,
                        "sensor_height_sources": dict(sorted(source_counts.items())),
                    }
                )
    return rows


def build_weather_release_inventory(
    observation_path: Path,
    *,
    benchmark_data_version: str,
) -> dict:
    """Build a deterministic inventory bound to one observation file and resource set."""

    observation_path = Path(observation_path).resolve()
    if not observation_path.is_file():
        raise FileNotFoundError(f"Observational HDF5 file not found: {observation_path}")

    with File(observation_path, "r") as obs_dataset:
        fs.validate_h5_std(obs_dataset)
        file_data_version = _h5_text(obs_dataset.attrs.get("version", ""))
        if file_data_version != benchmark_data_version:
            raise ValueError(
                "Benchmark-data version does not match the observational HDF5 metadata: "
                f"requested {benchmark_data_version!r}, found {file_data_version!r}."
            )
        dataset_inventory = _dataset_inventory(obs_dataset)
        inventory = {
            "inventory_schema_version": WEATHER_RELEASE_INVENTORY_SCHEMA_VERSION,
            "benchmark": {
                "id": cfg.CASE_ID,
                "short_name": cfg.BENCHMARK_SHORT_NAME,
                "data_version": benchmark_data_version,
            },
            "firebench_version": __version__,
            "observation": {
                "filename": observation_path.name,
                "size_bytes": observation_path.stat().st_size,
                "sha256": calculate_sha256(observation_path),
                "FireBench_io_version": _h5_text(
                    obs_dataset.attrs.get("FireBench_io_version", "<missing>")
                ),
                "created_on": _h5_text(obs_dataset.attrs.get("created_on", "<missing>")),
                "description": _h5_text(obs_dataset.attrs.get("description", "<missing>")),
            },
            "trusted_height_resources": _resource_binding(),
            "weather_dataset_totals": dataset_inventory,
            "periods": _period_inventory(obs_dataset),
        }

    contains_weather = dataset_inventory["variable_datasets"] > 0
    inventory["release_checks"] = {
        "all_weather_confidence_is_canonical_numeric": (
            contains_weather and dataset_inventory["noncanonical_or_missing_confidence"] == 0
        ),
        "all_weather_confidence_has_matching_description": (
            contains_weather
            and dataset_inventory["canonical_confidence_with_matching_description"]
            == dataset_inventory["variable_datasets"]
        ),
    }
    return inventory


def write_weather_release_inventory(
    observation_path: Path,
    output_path: Path,
    *,
    benchmark_data_version: str,
    overwrite: bool = False,
) -> dict:
    """Write a deterministic inventory atomically and return its content."""

    output_path = Path(output_path).resolve()
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Weather release inventory already exists: {output_path}")
    inventory = build_weather_release_inventory(
        observation_path,
        benchmark_data_version=benchmark_data_version,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(inventory, temp_file, indent=2, sort_keys=True)
            temp_file.write("\n")
        temp_path.replace(output_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return inventory


def main() -> None:
    """Generate a local weather release inventory from the command line."""

    parser = ArgumentParser(description=__doc__)
    parser.add_argument("observation_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("--benchmark-data-version", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    inventory = write_weather_release_inventory(
        args.observation_path,
        args.output_path,
        benchmark_data_version=args.benchmark_data_version,
        overwrite=args.overwrite,
    )
    print(
        f"Wrote {args.output_path}: observation_sha256={inventory['observation']['sha256']} "
        f"resource_sha256={inventory['trusted_height_resources']['combined_sha256']}"
    )


if __name__ == "__main__":
    main()
