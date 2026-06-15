from pathlib import Path

import h5py
import matplotlib
from click.testing import CliRunner

from firebench.cli import main
from firebench.plotting import common_perimeter_paths, load_plot_config, plot_from_config

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
