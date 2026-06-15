from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py

try:  # pragma: no cover - exercised only on Python 3.10
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


@dataclass(frozen=True)
class PlotInput:
    path: Path
    label: str
    color: str


@dataclass(frozen=True)
class PerimeterPlotConfig:
    enabled: bool
    paths: tuple[str, ...] | None
    group: str | None
    satellite: bool
    projection: str
    basemap_source: str
    alpha: float
    fill_alpha: float
    linewidth: float
    figsize: tuple[float, float]


@dataclass(frozen=True)
class PlotConfig:
    files: tuple[PlotInput, ...]
    output_dir: Path
    dpi: int
    perimeter: PerimeterPlotConfig


def plot_from_config(config_path: str | Path) -> list[Path]:
    """
    Generate plots described by a TOML plotting configuration.

    The first supported plot type is ``[perimeter]``. It compares KML perimeters
    referenced by common HDF5 datasets carrying a ``rel_path`` attribute.
    """
    config_path = Path(config_path)
    config = load_plot_config(config_path)
    written: list[Path] = []

    if config.perimeter.enabled:
        written.extend(plot_perimeters(config))

    return written


def load_plot_config(config_path: str | Path) -> PlotConfig:
    config_path = Path(config_path)
    with config_path.open("rb") as f:
        raw_config = tomllib.load(f)

    main = raw_config.get("main", {})
    if main is not None and not isinstance(main, dict):
        raise ValueError("[main] must be a TOML table")

    root = {key: value for key, value in raw_config.items() if key not in {"main", "perimeter"}}
    values = {**root, **main}
    base_dir = config_path.parent

    files = _load_inputs(values.get("files"), base_dir)
    output_dir = _required_path(values, "output_dir", base_dir)
    dpi = int(values.get("dpi", 150))
    if dpi <= 0:
        raise ValueError("dpi must be a positive integer")

    perimeter = _load_perimeter_config(raw_config.get("perimeter", {}))
    return PlotConfig(files=files, output_dir=output_dir, dpi=dpi, perimeter=perimeter)


def common_perimeter_paths(files: tuple[PlotInput, ...], perimeter: PerimeterPlotConfig) -> list[str]:
    common_paths: set[str] | None = None
    for plot_input in files:
        with h5py.File(plot_input.path, "r") as h5:
            paths = set(_perimeter_paths_in_h5(h5, perimeter.group))
        common_paths = paths if common_paths is None else common_paths & paths

    selected = sorted(common_paths or [])
    if perimeter.paths is not None:
        requested = {_normalize_h5_path(path) for path in perimeter.paths}
        selected = [path for path in selected if path in requested]
    return selected


def plot_perimeters(config: PlotConfig) -> list[Path]:
    import contextily as cx
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    perimeter_paths = common_perimeter_paths(config.files, config.perimeter)
    if not perimeter_paths:
        raise ValueError("No common perimeter datasets with a rel_path attribute were found.")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for perimeter_path in perimeter_paths:
        fig, ax = plt.subplots(figsize=config.perimeter.figsize)
        plotted_any = False
        legend_handles = []

        for plot_input in config.files:
            with h5py.File(plot_input.path, "r") as h5:
                kml_path = _resolve_h5_relative_path(h5, h5[perimeter_path].attrs["rel_path"])

            gdf = gpd.read_file(kml_path, driver="KML")
            if gdf.empty:
                continue

            if gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")
            gdf = gdf.to_crs(config.perimeter.projection)
            gdf.plot(
                ax=ax,
                facecolor=plot_input.color,
                edgecolor=plot_input.color,
                alpha=config.perimeter.fill_alpha,
                linewidth=config.perimeter.linewidth,
            )
            gdf.boundary.plot(
                ax=ax,
                color=plot_input.color,
                linewidth=config.perimeter.linewidth,
                alpha=config.perimeter.alpha,
            )
            legend_handles.append(
                Line2D([0], [0], color=plot_input.color, linewidth=config.perimeter.linewidth)
            )
            legend_handles[-1].set_label(plot_input.label)
            plotted_any = True

        if not plotted_any:
            plt.close(fig)
            continue

        if config.perimeter.satellite:
            cx.add_basemap(
                ax,
                source=_basemap_source(cx, config.perimeter.basemap_source),
                crs=config.perimeter.projection,
            )

        ax.set_axis_off()
        ax.set_title(perimeter_path.strip("/") or perimeter_path)
        ax.legend(handles=legend_handles, loc="best")
        fig.tight_layout()

        output_path = config.output_dir / f"{_safe_filename(perimeter_path)}.png"
        fig.savefig(output_path, dpi=config.dpi, bbox_inches="tight")
        plt.close(fig)
        written.append(output_path)

    return written


def _load_inputs(value: Any, base_dir: Path) -> tuple[PlotInput, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("files must be a non-empty list of TOML tables")

    inputs = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"files[{idx}] must be a TOML table")
        path = _required_path(item, "path", base_dir)
        label = str(item.get("label", path.stem))
        color = str(item.get("color", f"C{idx}"))
        if not path.is_file():
            raise FileNotFoundError(f"HDF5 input file does not exist: {path}")
        inputs.append(PlotInput(path=path, label=label, color=color))

    return tuple(inputs)


def _load_perimeter_config(value: Any) -> PerimeterPlotConfig:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("[perimeter] must be a TOML table")

    raw_paths = value.get("paths")
    paths = None
    if raw_paths is not None:
        if not isinstance(raw_paths, list) or not all(isinstance(item, str) for item in raw_paths):
            raise ValueError("perimeter.paths must be a list of strings")
        paths = tuple(_normalize_h5_path(path) for path in raw_paths)

    raw_figsize = value.get("figsize", [8.0, 8.0])
    if (
        not isinstance(raw_figsize, list)
        or len(raw_figsize) != 2
        or not all(isinstance(item, (int, float)) for item in raw_figsize)
    ):
        raise ValueError("perimeter.figsize must contain two numbers")

    group = value.get("group", "/polygons")
    if group is not None:
        group = _normalize_h5_path(str(group))

    return PerimeterPlotConfig(
        enabled=bool(value.get("enabled", True)),
        paths=paths,
        group=group,
        satellite=bool(value.get("satellite", True)),
        projection=str(value.get("projection", "EPSG:3857")),
        basemap_source=str(value.get("basemap_source", "Esri.WorldImagery")),
        alpha=float(value.get("alpha", 1.0)),
        fill_alpha=float(value.get("fill_alpha", 0.25)),
        linewidth=float(value.get("linewidth", 2.0)),
        figsize=(float(raw_figsize[0]), float(raw_figsize[1])),
    )


def _required_path(values: dict[str, Any], key: str, base_dir: Path) -> Path:
    value = values.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _perimeter_paths_in_h5(h5: h5py.File, group: str | None) -> list[str]:
    paths: list[str] = []

    def visitor(name: str, obj: h5py.Dataset) -> None:
        if not isinstance(obj, h5py.Dataset) or "rel_path" not in obj.attrs:
            return
        normalized = _normalize_h5_path(name)
        if group is not None and not (normalized == group or normalized.startswith(f"{group}/")):
            return
        paths.append(normalized)

    h5.visititems(visitor)
    return paths


def _resolve_h5_relative_path(h5: h5py.File, rel_path: str | bytes | Path) -> Path:
    path = Path(rel_path.decode() if isinstance(rel_path, bytes) else rel_path)
    if path.is_absolute():
        return path
    return Path(h5.filename).resolve().parent / path


def _normalize_h5_path(path: str) -> str:
    return "/" + path.strip("/")


def _safe_filename(path: str) -> str:
    filename = path.strip("/") or "root"
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
    return filename.strip("_") or "perimeter"


def _basemap_source(cx: Any, source_name: str) -> Any:
    source: Any = cx.providers
    for part in source_name.split("."):
        source = getattr(source, part)
    return source
