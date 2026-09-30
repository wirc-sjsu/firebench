"""
Embedded HRRR adapter: sample HRRR surface forecasts at weather stations.

For one forecast cycle, the adapter writes a FireBench-standard model file with one
``/time_series/station_<STID>`` group per observation station. Values stay at HRRR's **native
hourly valid times**, with no time interpolation, and are scored through the cadence join of
``firebench.benchmarks.wx_cadence``.

Every adjustment is declared in the file, never applied silently:

- sampling: the nearest HRRR grid cell of each station, whose terrain-height difference with the
  station is written as a per-station diagnostic (a first-order temperature bias in mountains);
- wind direction: the grid-relative 10 m winds are rotated to earth-relative components;
- wind speed: the 10 m wind is brought to the station sensor height with the neutral log law and
  HRRR's own surface roughness (``SFCR``);
- temperature and humidity: the 2 m values are assigned, untransformed, to screen-level sensors;
  outside the screen-level band the native 2 m height is declared, so trusted-source scoring
  excludes the station instead of comparing different heights.

Sensor heights are declared through ``adapter_common.weather.write_model_sensor_height_metadata``.
"""

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import hdf5plugin  # pylint: disable=unused-import  # registers the Zstd filter of observation datasets
import h5py
import numpy as np

from firebench import __version__ as fb_version
from firebench.acquisition.hrrr import forecast as hrrr_forecast
from firebench.acquisition.hrrr.forecast import CycleFiles
from firebench.acquisition.hrrr.grid import HRRRGrid, rotate_winds_to_earth
from firebench.acquisition.hrrr.read import read_fields
from firebench.adapter_common.weather import write_model_sensor_height_metadata
from firebench.standardize.files import new_std_file
from firebench.standardize.sensor_height import read_sensor_height
from firebench.standardize.std_file_info import TIME_SERIES
from firebench.tools.logging_config import logger
from firebench.tools.units import ureg

ADAPTER_NAME = "firebench.adapters.hrrr_weather"
SCREEN_LEVEL_BAND_M = (1.0, 3.0)
SCREEN_LEVEL_HEIGHT_M = 2.0
WIND_REFERENCE_HEIGHT_M = 10.0
Z0_MIN_M = 1e-4

TEMPERATURE = "TMP:2 m above ground"
HUMIDITY = "RH:2 m above ground"
WIND_U = "UGRD:10 m above ground"
WIND_V = "VGRD:10 m above ground"
ROUGHNESS = "SFCR:surface"
TERRAIN = "HGT:surface"
VARIABLE_UNITS = {
    "air_temperature": "K",
    "relative_humidity": "percent",
    "wind_speed": "m/s",
    "wind_direction": "degree",
}


@dataclass
class StationSite:
    """Location and observed sensor heights (m, ``None`` if unknown) of one observation station."""

    name: str
    lat: float
    lon: float
    elevation_m: float
    heights: dict[str, float | None] = field(default_factory=dict)


def read_station_sites(obs_h5: h5py.File) -> list[StationSite]:
    """Read every ``station*`` group of an observation file."""
    sites = []
    for name, group in obs_h5[TIME_SERIES].items():
        if not name.startswith("station"):
            continue
        heights = {}
        for variable in VARIABLE_UNITS:
            if variable not in group:
                continue
            try:
                heights[variable] = float(
                    read_sensor_height(
                        group[variable],
                        dataset_path=f"{TIME_SERIES}/{name}/{variable}",
                        allow_legacy_text=True,
                    )
                    .to("m")
                    .magnitude
                )
            except ValueError:
                heights[variable] = None
        sites.append(
            StationSite(
                name=name,
                lat=float(group.attrs["position_lat"]),
                lon=float(group.attrs["position_lon"]),
                elevation_m=_elevation_m(group),
                heights=heights,
            )
        )
    return sites


def wind_at_height(speed_10m, height_m, z0_m, z0_min: float = Z0_MIN_M):
    """
    Neutral log-law wind speed at ``height_m`` from the 10 m wind and roughness length ``z0_m``.

    Port of the WRF-SFIRE adapter's ``wind_from10m_with_roughness``: ``z0`` is floored at ``z0_min``,
    the target height at ``z0``, and the result is NaN where ``z0 >= 10 m`` (no log profile).
    """
    z0_eff = np.maximum(np.asarray(z0_m, dtype=np.float64), z0_min)
    z_eff = np.maximum(np.asarray(height_m, dtype=np.float64), z0_eff)
    denominator = np.log(WIND_REFERENCE_HEIGHT_M / z0_eff)
    denominator = np.where(denominator > 0, denominator, np.nan)
    return np.maximum(np.asarray(speed_10m, dtype=np.float64) * np.log(z_eff / z0_eff) / denominator, 0.0)


def wind_direction_from_components(u_earth, v_earth):
    """Meteorological direction the wind blows from, in degrees (north = 0, east = 90)."""
    return (270.0 - np.degrees(np.arctan2(v_earth, u_earth))) % 360.0


def build_hrrr_station_file(
    obs_h5_path: Path,
    cycle_files: CycleFiles,
    out_h5_path: Path,
    *,
    screen_level_band_m: tuple[float, float] = SCREEN_LEVEL_BAND_M,
    read: Callable = read_fields,
) -> dict:
    """
    Write the station-collocated HRRR model file of one cycle; returns a summary.

    Every observation station must lie on the HRRR grid, because the benchmark requires the model to
    provide every selected station (a station outside the grid is an error, not a silent gap).
    """
    with h5py.File(obs_h5_path, "r") as obs_h5:
        sites = read_station_sites(obs_h5)
    if not sites:
        raise ValueError(f"no station found in observation file {obs_h5_path}")

    samples = sample_cycle(sites, cycle_files, read=read)
    policy = _height_policy(sites, screen_level_band_m)

    out_h5_path = Path(out_h5_path)
    out_h5_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{out_h5_path.stem}.", suffix=".h5", dir=out_h5_path.parent)
    os.close(fd)
    os.unlink(tmp_name)  # reserve a unique name; new_std_file creates the file
    try:
        with new_std_file(tmp_name, "FireBench HRRR adapter") as h5:
            _write_root_attributes(h5, cycle_files, samples, policy, obs_h5_path)
            for index, site in enumerate(sites):
                _write_station(h5, site, index, samples, cycle_files, policy[site.name])
        os.replace(tmp_name, out_h5_path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise

    summary = {
        "cycle": cycle_files.cycle.isoformat(),
        "stations": len(sites),
        "forecast_hours": samples["forecast_hours"],
        "missing_forecast_hours": list(cycle_files.missing),
        "height_policy": _policy_counts(policy),
    }
    logger.info(
        "[hrrr] wrote %s: %d stations x %d forecast hours",
        out_h5_path,
        len(sites),
        len(samples["forecast_hours"]),
    )
    return summary


def sample_cycle(
    sites: list[StationSite], cycle_files: CycleFiles, *, read: Callable = read_fields
) -> dict:
    """Sample every forecast hour of a cycle at the nearest HRRR cell of each station."""
    grid = HRRRGrid()
    lat = np.array([site.lat for site in sites])
    lon = np.array([site.lon for site in sites])
    i_frac, j_frac = grid.ij_arrays_from_latlon(lat, lon)
    inside = grid.contains(i_frac, j_frac)
    if not np.all(inside):
        outside = [site.name for site, ok in zip(sites, inside) if not ok]
        raise ValueError(f"stations outside the HRRR CONUS grid: {', '.join(outside)}")
    i_cell = np.rint(i_frac).astype(int)
    j_cell = np.rint(j_frac).astype(int)

    hours = sorted(cycle_files.files)
    shape = (len(hours), len(sites))
    samples = {
        "forecast_hours": hours,
        "i": i_frac,
        "j": j_frac,
        "terrain": np.full(len(sites), np.nan),
        **{name: np.full(shape, np.nan) for name in ("temperature", "humidity", "u", "v", "z0")},
    }
    for row, fxx in enumerate(hours):
        fields = read(cycle_files.files[fxx])
        samples["temperature"][row] = fields[TEMPERATURE][j_cell, i_cell]
        samples["humidity"][row] = fields[HUMIDITY][j_cell, i_cell]
        samples["z0"][row] = fields[ROUGHNESS][j_cell, i_cell]
        u_earth, v_earth = rotate_winds_to_earth(
            fields[WIND_U][j_cell, i_cell], fields[WIND_V][j_cell, i_cell], lon
        )
        samples["u"][row] = u_earth
        samples["v"][row] = v_earth
        if TERRAIN in fields:
            samples["terrain"] = np.asarray(fields[TERRAIN][j_cell, i_cell], dtype=np.float64)
    return samples


def _height_policy(sites: list[StationSite], band: tuple[float, float]) -> dict[str, dict]:
    """Declared height and adjustment of every variable of every station."""
    policy = {}
    for site in sites:
        station_policy = {}
        for variable in ("air_temperature", "relative_humidity"):
            height = site.heights.get(variable)
            if height is not None and band[0] <= height <= band[1]:
                station_policy[variable] = (
                    height,
                    "none: 2 m value assigned to the screen-level sensor height",
                )
            else:
                station_policy[variable] = (SCREEN_LEVEL_HEIGHT_M, "none: native 2 m height")
        wind_height = site.heights.get("wind_speed")
        if wind_height is not None:
            station_policy["wind_speed"] = (
                wind_height,
                "neutral log law from 10 m with HRRR SFCR roughness",
            )
        else:
            station_policy["wind_speed"] = (WIND_REFERENCE_HEIGHT_M, "none: native 10 m height")
        direction_height = site.heights.get("wind_direction")
        if direction_height is not None:
            station_policy["wind_direction"] = (
                direction_height,
                "none: 10 m direction assumed height-invariant in the surface layer",
            )
        else:
            station_policy["wind_direction"] = (WIND_REFERENCE_HEIGHT_M, "none: native 10 m height")
        policy[site.name] = station_policy
    return policy


def _policy_counts(policy: dict[str, dict]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for station_policy in policy.values():
        for variable, (_, adjustment) in station_policy.items():
            counts.setdefault(variable, {}).setdefault(adjustment, 0)
            counts[variable][adjustment] += 1
    return counts


def _write_root_attributes(
    h5, cycle_files: CycleFiles, samples: dict, policy: dict, obs_h5_path: Path
) -> None:
    cycle = cycle_files.cycle
    h5.attrs["description"] = (
        f"HRRR {hrrr_forecast.PRODUCT} forecast cycle {cycle:%Y-%m-%d %HZ} at weather stations"
    )
    h5.attrs["model_name"] = "HRRR"
    h5.attrs["hrrr_cycle"] = cycle.isoformat()
    h5.attrs["hrrr_version"] = hrrr_forecast.hrrr_version(cycle)
    h5.attrs["hrrr_product"] = hrrr_forecast.PRODUCT
    h5.attrs["source_bucket"] = hrrr_forecast.SOURCE_BUCKET
    h5.attrs["horizon_hours"] = cycle_files.horizon
    h5.attrs["forecast_hours"] = np.asarray(samples["forecast_hours"], dtype=np.int64)
    h5.attrs["missing_forecast_hours"] = np.asarray(cycle_files.missing, dtype=np.int64)
    h5.attrs["adapter"] = ADAPTER_NAME
    h5.attrs["adapter_version"] = fb_version
    h5.attrs["interpolation"] = "nearest HRRR grid cell; native hourly valid times, no time interpolation"
    h5.attrs["observation_file"] = Path(obs_h5_path).name
    h5.attrs["height_policy"] = json.dumps(_policy_counts(policy), sort_keys=True)


def _write_station(
    h5, site: StationSite, index: int, samples: dict, cycle_files: CycleFiles, policy: dict
) -> None:
    group = h5.create_group(f"{TIME_SERIES}/{site.name}")
    group.attrs["position_lat"] = site.lat
    group.attrs["position_lon"] = site.lon
    group.attrs["position_lat_units"] = "degree"
    group.attrs["position_lon_units"] = "degree"
    group.attrs["model_grid_i"] = float(samples["i"][index])
    group.attrs["model_grid_j"] = float(samples["j"][index])
    group.attrs["model_terrain_height"] = float(samples["terrain"][index])
    group.attrs["model_terrain_height_units"] = "m"
    group.attrs["station_elevation"] = site.elevation_m
    group.attrs["station_elevation_units"] = "m"
    group.attrs["terrain_height_difference"] = float(samples["terrain"][index] - site.elevation_m)
    group.attrs["terrain_height_difference_units"] = "m"

    time = group.create_dataset(
        "time", data=3600.0 * np.asarray(samples["forecast_hours"], dtype=np.float64)
    )
    time.attrs["time_origin"] = cycle_files.cycle.isoformat()
    time.attrs["time_units"] = "s"

    speed_10m = np.hypot(samples["u"][:, index], samples["v"][:, index])
    values = {
        "air_temperature": samples["temperature"][:, index],
        "relative_humidity": samples["humidity"][:, index],
        "wind_direction": wind_direction_from_components(samples["u"][:, index], samples["v"][:, index]),
    }
    wind_height, wind_adjustment = policy["wind_speed"]
    if wind_adjustment.startswith("neutral log law"):
        values["wind_speed"] = wind_at_height(speed_10m, wind_height, samples["z0"][:, index])
    else:
        values["wind_speed"] = speed_10m

    native_heights = {
        "air_temperature": SCREEN_LEVEL_HEIGHT_M,
        "relative_humidity": SCREEN_LEVEL_HEIGHT_M,
        "wind_speed": WIND_REFERENCE_HEIGHT_M,
        "wind_direction": WIND_REFERENCE_HEIGHT_M,
    }
    for variable, units in VARIABLE_UNITS.items():
        dataset = group.create_dataset(variable, data=values[variable])
        dataset.attrs["units"] = units
        height, adjustment = policy[variable]
        write_model_sensor_height_metadata(dataset, ureg.Quantity(height, "m"))
        dataset.attrs["model_native_height"] = native_heights[variable]
        dataset.attrs["model_native_height_units"] = "m"
        dataset.attrs["height_adjustment"] = adjustment
        if variable == "wind_speed" and adjustment.startswith("neutral log law"):
            dataset.attrs["z0_source"] = f"HRRR {ROUGHNESS}"


def _elevation_m(group) -> float:
    if "position_alt" not in group.attrs:
        return float("nan")
    units = group.attrs.get("position_alt_units", "m")
    units = units.decode() if isinstance(units, bytes) else str(units)
    try:
        return float(ureg.Quantity(float(group.attrs["position_alt"]), units).to("m").magnitude)
    except (TypeError, ValueError):
        return float("nan")
