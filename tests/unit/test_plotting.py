from pathlib import Path

import h5py
import matplotlib
import geopandas as gpd
from click.testing import CliRunner
from shapely.geometry import Polygon

from firebench.cli import main
from firebench.plotting import (
    _perimeter_metrics_summary,
    common_perimeter_paths,
    load_plot_config,
    plot_from_config,
    plot_perimeter_contours,
)

matplotlib.use("Agg")


KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>perimeter</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              -120.00,38.00,0 -119.99,38.00,0 -119.99,38.01,0 -120.00,38.01,0 -120.00,38.00,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""


def _write_h5(path: Path, perimeter_paths: tuple[str, ...]) -> None:
    with h5py.File(path, "w") as h5:
        for perimeter_path in perimeter_paths:
            dset = h5.create_dataset(perimeter_path, data=0)
            kml_path = path.with_name(f"{Path(perimeter_path).name}.kml")
            kml_path.write_text(KML)
            dset.attrs["rel_path"] = kml_path.name


def test_load_plot_config_accepts_root_level_inputs(tmp_path):
    model = tmp_path / "model.h5"
    _write_h5(model, ("/polygons/A",))
    config_path = tmp_path / "plot.toml"
    config_path.write_text(
        f"""
output_dir = "plots"
dpi = 220

[[files]]
path = "{model.name}"
label = "Model"
color = "#cc3311"

[perimeter]
satellite = false
"""
    )

    config = load_plot_config(config_path)

    assert config.output_dir == tmp_path / "plots"
    assert config.dpi == 220
    assert config.files[0].path == model
    assert config.files[0].label == "Model"
    assert config.perimeter.satellite is False


def test_load_plot_config_accepts_main_section_inputs(tmp_path):
    model = tmp_path / "model.h5"
    _write_h5(model, ("/polygons/A",))
    config_path = tmp_path / "plot.toml"
    config_path.write_text(
        f"""
[main]
output_dir = "plots"
dpi = 180

[[main.files]]
path = "{model.name}"
label = "Model"
color = "C0"
"""
    )

    config = load_plot_config(config_path)

    assert config.output_dir == tmp_path / "plots"
    assert config.dpi == 180
    assert config.files[0].path == model


def test_common_perimeter_paths_only_returns_shared_h5_parameters(tmp_path):
    model_a = tmp_path / "model_a.h5"
    model_b = tmp_path / "model_b.h5"
    _write_h5(model_a, ("/polygons/A", "/polygons/B"))
    _write_h5(model_b, ("/polygons/A", "/polygons/C"))
    config_path = tmp_path / "plot.toml"
    config_path.write_text(
        f"""
output_dir = "plots"

[[files]]
path = "{model_a.name}"
label = "A"
color = "red"

[[files]]
path = "{model_b.name}"
label = "B"
color = "blue"

[perimeter]
satellite = false
"""
    )
    config = load_plot_config(config_path)

    assert common_perimeter_paths(config.files, config.perimeter) == ["/polygons/A"]


def test_plot_from_config_writes_one_png_per_common_perimeter(tmp_path):
    model_a = tmp_path / "model_a.h5"
    model_b = tmp_path / "model_b.h5"
    _write_h5(model_a, ("/polygons/A", "/polygons/B"))
    _write_h5(model_b, ("/polygons/A",))
    config_path = tmp_path / "plot.toml"
    config_path.write_text(
        f"""
output_dir = "plots"
dpi = 72

[[files]]
path = "{model_a.name}"
label = "A"
color = "red"

[[files]]
path = "{model_b.name}"
label = "B"
color = "blue"

[perimeter]
satellite = false
"""
    )

    written = plot_from_config(config_path)

    assert written == [tmp_path / "plots" / "polygons_A.png"]
    assert written[0].is_file()


def test_plot_perimeter_contours_writes_report_figure_without_basemap(tmp_path):
    obs = tmp_path / "obs.h5"
    model = tmp_path / "model.h5"
    _write_h5(obs, ("/polygons/A",))
    _write_h5(model, ("/polygons/A",))
    output_path = tmp_path / "figures" / "perimeters_H013_P.png"

    written = plot_perimeter_contours(
        model_output=model,
        obs_data=obs,
        perimeter_paths=["/polygons/A"],
        output_path=output_path,
        basemap_source=None,
        dpi=72,
    )

    assert written == output_path
    assert output_path.is_file()


def test_perimeter_metrics_summary_formats_kpis_and_burn_areas():
    obs = gpd.GeoDataFrame(
        geometry=[Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 0)])],
        crs="EPSG:5070",
    )
    model = gpd.GeoDataFrame(
        geometry=[Polygon([(500, 0), (1500, 0), (1500, 1000), (500, 1000), (500, 0)])],
        crs="EPSG:5070",
    )

    summary = _perimeter_metrics_summary([(obs, model)], "EPSG:5070")

    assert summary == "IoU = 0.333 | DS = 0.500 | Obs burn = 247.1 acre | Model burn = 247.1 acre"


def test_format_burn_area_uses_scaled_acres():
    from firebench.plotting import _format_burn_area

    assert _format_burn_area(1_000_000) == "247.1 acre"
    assert _format_burn_area(100_000 * 4046.8564224) == "100 1e3 acre"
    assert _format_burn_area(2_500_000 * 4046.8564224) == "2.5 1e6 acre"


def test_plot_command_delegates_to_plot_config(monkeypatch, tmp_path):
    config_path = tmp_path / "plot.toml"
    config_path.write_text("output_dir = 'plots'\n")
    output_path = tmp_path / "plots" / "figure.png"
    calls = []

    def fake_plot_from_config(path):
        calls.append(path)
        return [output_path]

    monkeypatch.setattr("firebench.cli.plot_from_config", fake_plot_from_config)

    result = CliRunner().invoke(main, ["plot", str(config_path)])

    assert result.exit_code == 0, result.output
    assert calls == [config_path]
    assert f"Wrote {output_path}" in result.output
