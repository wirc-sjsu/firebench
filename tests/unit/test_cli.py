from pathlib import Path
from datetime import datetime, timezone

from click.testing import CliRunner

from firebench.cli import main


def _fake_registry(tmp_path, call):
    def fake_runner(model_output, **kwargs):
        call["model_output"] = model_output
        call.update(kwargs)
        return {"ok": True}

    def fake_debug_func(benchmark_target):
        call["debug_benchmark_target"] = benchmark_target

    def fake_target_describer(target=None, obs_data=None):
        if target is not None:
            call["target_describer_obs_data"] = obs_data
            if target in {"B", "H013_B"}:
                return {
                    "target": target,
                    "period": (
                        None
                        if target == "B"
                        else {
                            "target": "H013",
                            "start": datetime(2021, 8, 19, 23, 0, tzinfo=timezone.utc),
                            "end": datetime(2021, 8, 21, 23, 0, tzinfo=timezone.utc),
                        }
                    ),
                    "kpi_groups": {
                        "B": "Building Damage",
                    },
                    "perimeters": [],
                    "weather_stations": [],
                    "kpis": [
                        {
                            "id": "FB001_BD01",
                            "name": "",
                            "group": "Building Damage",
                            "weight": 1,
                            "value_norm_param_m": None,
                        },
                        {
                            "id": "FB001_BD06",
                            "name": "",
                            "group": "Building Damage",
                            "weight": 1,
                            "value_norm_param_m": None,
                        },
                    ],
                }
            if target == "H013_W":
                return {
                    "target": "H013_W",
                    "period": {
                        "target": "H013",
                        "start": datetime(2021, 8, 19, 23, 0, tzinfo=timezone.utc),
                        "end": datetime(2021, 8, 21, 23, 0, tzinfo=timezone.utc),
                    },
                    "kpi_groups": {
                        "W": "Weather Stations",
                    },
                    "perimeters": [],
                    "weather_stations": [
                        {
                            "variable": "air_temperature",
                            "label": "Air temp",
                            "stations": 103,
                            "trusted_stations": 14,
                        },
                        {
                            "variable": "wind_speed",
                            "label": "Wind Speed",
                            "stations": 87,
                            "trusted_stations": 10,
                        },
                    ],
                    "kpis": [
                        {
                            "id": "FB001_WX343",
                            "name": "Air temp MAE min WH13 TSO",
                            "group": "Weather Stations",
                            "weight": 1,
                            "value_norm_param_m": 5,
                        },
                    ],
                }
            return {
                "target": "H013_P",
                "period": {
                    "target": "H013",
                    "start": datetime(2021, 8, 19, 23, 0, tzinfo=timezone.utc),
                    "end": datetime(2021, 8, 21, 23, 0, tzinfo=timezone.utc),
                },
                "kpi_groups": {
                    "P": "Fire Perimeters",
                },
                "perimeters": [
                    {
                        "time": "2021-08-20T20:20-07:00",
                        "path": "/polygons/Caldor_2021-08-20T20:20-07:00",
                    },
                    {
                        "time": "2021-08-21T21:15-07:00",
                        "path": "/polygons/Caldor_2021-08-21T21:15-07:00",
                    },
                ],
                "kpis": [
                    {
                        "id": "FB001_FPH097",
                        "name": "Average Jaccard Index",
                        "group": "Fire Perimeters",
                        "weight": 1,
                        "value_norm_param_m": None,
                    },
                    {
                        "id": "FB001_FPH103",
                        "name": "Final Burn Area Bias",
                        "group": "Fire Perimeters",
                        "weight": 2,
                        "value_norm_param_m": 10000,
                    },
                ],
            }
        return {
            "periods": [
                {
                    "target": "H000",
                    "start": datetime(2021, 8, 17, 12, 0, tzinfo=timezone.utc),
                    "end": datetime(2021, 8, 19, 12, 0, tzinfo=timezone.utc),
                },
                {
                    "target": "P01",
                    "start": datetime(2021, 8, 17, 20, 20, tzinfo=timezone.utc),
                    "end": datetime(2021, 9, 10, 23, 34, tzinfo=timezone.utc),
                },
            ],
            "kpi_groups": {
                "B": "Building Damage",
                "P": "Fire Perimeters",
                "W": "Weather Stations",
            },
        }

    def fake_report_figure_func(model_output, obs_data, benchmark_target, target_info, output_dir):
        figure_path = output_dir / f"perimeters_{benchmark_target}.png"
        output_dir.mkdir(exist_ok=True)
        figure_path.write_text("fake figure")
        call["report_figure_model_output"] = model_output
        call["report_figure_obs_data"] = obs_data
        call["report_figure_target"] = benchmark_target
        call["report_figure_target_info"] = target_info
        return [
            {
                "title": "Fire perimeter comparison",
                "path": figure_path,
                "alt": "Observed and modeled fire perimeter contours",
            }
        ]

    return {
        "001": {
            "name": "2021 Caldor Fire",
            "short_name": "2021_Caldor",
            "url": "https://example.test/caldor",
            "func": fake_runner,
            "debug_func": fake_debug_func,
            "target_describer": fake_target_describer,
            "report_figure_func": fake_report_figure_func,
            "default_options": {
                "verbose": 3,
                "log_file": tmp_path / "default.log",
                "obs_data": tmp_path / "default_obs.h5",
                "output_json": tmp_path / "default_rslt.json",
                "score_card_report": tmp_path / "default.pdf",
            },
            "data": {
                "latest": "https://example.test/files/latest.zip?download=1",
                "2026.1": "https://example.test/files/v2026.1.zip?download=1",
            },
        }
    }


def test_run_command_uses_registry_defaults(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(main, ["run", "001", "H013_P", str(model_output)])

    assert result.exit_code == 0, result.output
    assert call == {
        "model_output": Path(model_output),
        "benchmark_target": "H013_P",
        "name": "",
        "overwrite": False,
        "sign": None,
        "obs_data": tmp_path / "default_obs.h5",
        "output_json": tmp_path / "default_rslt.json",
        "score_card_report": tmp_path / "default.pdf",
        "score_card_full_name": False,
    }
    assert (tmp_path / "default.log").exists()


def test_run_command_accepts_unpadded_case_id(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(main, ["run", "1", "H013_P", str(model_output)])

    assert result.exit_code == 0, result.output
    assert call["model_output"] == Path(model_output)
    assert call["benchmark_target"] == "H013_P"


def test_run_command_accepts_padded_case_id(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(main, ["run", "001", "H013_P", str(model_output)])

    assert result.exit_code == 0, result.output
    assert call["model_output"] == Path(model_output)
    assert call["benchmark_target"] == "H013_P"


def test_run_command_accepts_short_name(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(main, ["run", "2021_Caldor", "H013_P", str(model_output)])

    assert result.exit_code == 0, result.output
    assert call["model_output"] == Path(model_output)
    assert call["benchmark_target"] == "H013_P"


def test_run_command_requires_case(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(main, ["run", "001", str(model_output)])

    assert result.exit_code != 0
    assert "Missing argument 'MODEL_OUTPUT'" in result.output
    assert call == {}


def test_run_command_overrides_registry_defaults(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    obs_data = tmp_path / "custom_obs.h5"
    log_file = tmp_path / "custom.log"
    output_json = tmp_path / "custom_rslt.json"
    score_card_report = tmp_path / "custom.pdf"
    model_output.write_text("model")
    obs_data.write_text("obs")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(
        main,
        [
            "run",
            "001",
            "H013_P",
            str(model_output),
            "-n",
            "demo",
            "-o",
            "-s",
            "KEYID",
            "Signer",
            "-v",
            "4",
            "--log-file",
            str(log_file),
            "--no-console",
            "--obs-data",
            str(obs_data),
            "--output-json",
            str(output_json),
            "--score-card-report",
            str(score_card_report),
            "--full_name",
        ],
    )

    assert result.exit_code == 0, result.output
    assert call == {
        "model_output": Path(model_output),
        "benchmark_target": "H013_P",
        "name": "demo",
        "overwrite": True,
        "sign": ("KEYID", "Signer"),
        "obs_data": Path(obs_data),
        "output_json": Path(output_json),
        "score_card_report": Path(score_card_report),
        "score_card_full_name": True,
    }
    assert log_file.exists()


def test_run_command_no_run_prints_registry_without_model_file(monkeypatch, tmp_path):
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(
        main,
        ["run", "001", "H013_P", str(tmp_path / "missing_model.h5"), "--no-run"],
    )

    assert result.exit_code == 0, result.output
    assert call == {"debug_benchmark_target": "H013_P"}


def test_run_command_rejects_legacy_agg_scheme_option(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(main, ["run", "001", "H013_P", str(model_output), "-a", "B"])

    assert result.exit_code != 0
    assert "No such option: -a" in result.output
    assert call == {}


def test_run_command_report_creates_report_skeleton(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            main, ["run", "001", "H013_P", str(model_output), "--report", "-n", "Demo Model"]
        )

        report_path = Path(cwd) / "firebench_report.md"
        figures_dir = Path(cwd) / "figures"

        assert result.exit_code == 0, result.output
        assert figures_dir.is_dir()
        assert (figures_dir / "perimeters_H013_P.png").is_file()
        assert call["report_figure_model_output"] == model_output
        assert call["report_figure_obs_data"] == tmp_path / "default_obs.h5"
        assert call["report_figure_target"] == "H013_P"
        assert call["report_figure_target_info"]["target"] == "H013_P"
        assert report_path.read_text(encoding="utf-8") == (
            "# Report 2021 Caldor Fire for Demo Model\n"
            "## Benchmark target information\n"
            "Benchmark target: H013_P\n"
            "\n"
            "### Temporal period\n"
            "Target: H013\n"
            "Start: 2021-08-19T23:00+00:00\n"
            "End: 2021-08-21T23:00+00:00\n"
            "\n"
            "### KPI groups\n"
            "- P: Fire Perimeters\n"
            "\n"
            "### Perimeters\n"
            "| Time |\n"
            "| --- |\n"
            "| 2021-08-20T20:20-07:00 |\n"
            "| 2021-08-21T21:15-07:00 |\n"
            "\n"
            "### KPIs\n"
            "| ID | KPI | Weight | value_norm_param_m |\n"
            "| --- | --- | --- | --- |\n"
            "| FB001_FPH097 | Average Jaccard Index | 1 |  |\n"
            "| FB001_FPH103 | Final Burn Area Bias | 2 | 10000 |\n"
            "\n"
            "## Submitters' comments\n"
            "This section is reserved for the model users who have submitted the model output "
            "to this benchmark.\n"
            "### Short model description and keywords\n"
            "### Setup/Configuration\n"
            "### Inputs\n"
            "### Post-processing\n"
            "### FireBench adapter used\n"
            "## FireBench Team comments\n"
            "This section is reserved to the FireBench team validating this benchmark results\n"
            "## Results\n"
            "### Fire perimeter comparison\n"
            '<p align="center">\n'
            '  <img src="figures/perimeters_H013_P.png" '
            'alt="Observed and modeled fire perimeter contours">\n'
            "</p>\n"
        )


def test_run_command_report_does_not_overwrite_existing_report(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        report_path = Path(cwd) / "firebench_report.md"
        report_path.write_text("existing report", encoding="utf-8")

        result = runner.invoke(main, ["run", "001", "H013_P", str(model_output), "--report"])

        assert result.exit_code != 0
        assert "Report file already exists: firebench_report.md" in result.output
        assert report_path.read_text(encoding="utf-8") == "existing report"
        assert call == {}


def test_run_command_unknown_case_fails(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["run", "999", "H013_P", str(model_output)])

    assert result.exit_code != 0
    assert "Unknown benchmark case '999'" in result.output
    assert "firebench list" in result.output


def test_multirun_command_runs_models_from_yaml_config(monkeypatch, tmp_path):
    config_dir = tmp_path / "case"
    config_dir.mkdir()
    obs_data = config_dir / "obs.h5"
    model_a = config_dir / "model_a.h5"
    model_b = config_dir / "model_b.h5"
    obs_data.write_text("obs")
    model_a.write_text("model-a")
    model_b.write_text("model-b")
    calls = []

    def fake_runner(model_output, **kwargs):
        calls.append({"model_output": model_output, **kwargs})
        total_score = 80.0 if kwargs["name"] == "Model A" else 60.0
        group_score = 90.0 if kwargs["name"] == "Model A" else 50.0
        return {
            "case_id": "FB001",
            "benchmark_short_name": "2021_Caldor",
            "evaluated_model_name": kwargs["name"],
            "firebench_version": "test",
            "case_version": "test",
            "score_card": {
                "Scheme": {
                    "FP_H13": {
                        "weight": 1,
                        "benchmarks": {},
                    },
                },
                "Score Total": total_score,
                "Score FP_H13": group_score,
                "aggregation_scheme_name": "H013_P",
            },
        }

    monkeypatch.setattr(
        "firebench.cli.AVAIL_BENCHMARKS",
        {
            "001": {
                "name": "2021 Caldor Fire",
                "short_name": "2021_Caldor",
                "url": "https://example.test/caldor",
                "func": fake_runner,
                "default_options": {
                    "verbose": 3,
                    "obs_data": tmp_path / "default_obs.h5",
                },
            }
        },
    )
    config_path = config_dir / "multirun.yml"
    config_path.write_text(
        "\n".join(
            [
                "case: 2021_Caldor",
                "target: H013_P",
                "output_dir: out",
                "overwrite: true",
                "obs_data: obs.h5",
                "models:",
                "  - name: Model A",
                "    model_output: model_a.h5",
                "  - name: Model B",
                "    model_output: model_b.h5",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["multirun", str(config_path)])

    output_dir = config_dir / "out"
    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "model_output": model_a,
            "benchmark_target": "H013_P",
            "name": "Model A",
            "overwrite": True,
            "sign": None,
            "obs_data": obs_data,
            "output_json": output_dir / "model-a_rslt.json",
            "score_card_report": output_dir / "model-a_scorecard.pdf",
            "score_card_full_name": False,
        },
        {
            "model_output": model_b,
            "benchmark_target": "H013_P",
            "name": "Model B",
            "overwrite": True,
            "sign": None,
            "obs_data": obs_data,
            "output_json": output_dir / "model-b_rslt.json",
            "score_card_report": output_dir / "model-b_scorecard.pdf",
            "score_card_full_name": False,
        },
    ]
    assert (output_dir / "comparison_scorecard.pdf").exists()
    assert f"Wrote {output_dir / 'comparison_scorecard.pdf'}" in result.output


def test_multirun_command_rejects_duplicate_output_slugs(monkeypatch, tmp_path):
    config_dir = tmp_path / "case"
    config_dir.mkdir()
    model_a = config_dir / "model_a.h5"
    model_b = config_dir / "model_b.h5"
    model_a.write_text("model-a")
    model_b.write_text("model-b")
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))
    config_path = config_dir / "multirun.yml"
    config_path.write_text(
        "\n".join(
            [
                "case: 001",
                "target: H013_P",
                "models:",
                "  - name: Model A",
                "    model_output: model_a.h5",
                "  - name: Model-A",
                "    model_output: model_b.h5",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["multirun", str(config_path)])

    assert result.exit_code != 0
    assert "Duplicate model output slug 'model-a'" in result.output


def test_list_command_prints_case_ids_short_names_and_docs(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["list"])

    assert result.exit_code == 0, result.output
    assert result.output == (
        "ID   Short name   Documentation\n" "001  2021_Caldor  https://example.test/caldor\n"
    )
    assert "func" not in result.output
    assert "{" not in result.output


def test_list_command_prints_case_targets(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["list", "001"])

    assert result.exit_code == 0, result.output
    assert result.output == (
        "ID: 001\n"
        "Short name: 2021_Caldor\n"
        "Documentation: https://example.test/caldor\n"
        "\n"
        "Temporal periods\n"
        "Target   Start   End\n"
        "H000  2021-08-17T12:00+00:00  2021-08-19T12:00+00:00\n"
        "P01  2021-08-17T20:20+00:00  2021-09-10T23:34+00:00\n"
        "\n"
        "KPI groups\n"
        "B: Building Damage\n"
        "P: Fire Perimeters\n"
        "W: Weather Stations\n"
    )


def test_list_command_accepts_case_short_name(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["list", "2021_Caldor"])

    assert result.exit_code == 0, result.output
    assert "ID: 001" in result.output
    assert "H000" in result.output
    assert "B: Building Damage" in result.output
    assert "P: Fire Perimeters" in result.output
    assert "W: Weather Stations" in result.output


def test_list_command_prints_target_details(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["list", "2021_Caldor", "H013_P"])

    assert result.exit_code == 0, result.output
    assert result.output == (
        "ID: 001\n"
        "Short name: 2021_Caldor\n"
        "Documentation: https://example.test/caldor\n"
        "Benchmark target: H013_P\n"
        "\n"
        "Temporal period\n"
        "Target: H013\n"
        "Start: 2021-08-19T23:00+00:00\n"
        "End: 2021-08-21T23:00+00:00\n"
        "\n"
        "KPI groups\n"
        "P: Fire Perimeters\n"
        "\n"
        "Perimeters\n"
        "Time\n"
        "2021-08-20T20:20-07:00\n"
        "2021-08-21T21:15-07:00\n"
        "\n"
        "KPIs\n"
        "ID   KPI   Weight   value_norm_param_m\n"
        "FB001_FPH097  Average Jaccard Index  1  \n"
        "FB001_FPH103  Final Burn Area Bias  2  10000\n"
    )


def test_list_command_prints_weather_target_details(monkeypatch, tmp_path):
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    obs_data = tmp_path / "obs.h5"
    result = CliRunner().invoke(main, ["list", "2021_Caldor", "H013_W", "--obs-data", str(obs_data)])

    assert result.exit_code == 0, result.output
    assert call["target_describer_obs_data"] == obs_data
    assert result.output == (
        "ID: 001\n"
        "Short name: 2021_Caldor\n"
        "Documentation: https://example.test/caldor\n"
        "Benchmark target: H013_W\n"
        "\n"
        "Temporal period\n"
        "Target: H013\n"
        "Start: 2021-08-19T23:00+00:00\n"
        "End: 2021-08-21T23:00+00:00\n"
        "\n"
        "KPI groups\n"
        "W: Weather Stations\n"
        "\n"
        "Weather stations\n"
        "Variable   Stations   Trusted stations\n"
        "air_temperature  103  14\n"
        "wind_speed  87  10\n"
        "\n"
        "KPIs\n"
        "ID   KPI   Weight   value_norm_param_m\n"
        "FB001_WX343  Air temp MAE min WH13 TSO  1  5\n"
    )


def test_list_command_prints_building_damage_target_details(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["list", "2021_Caldor", "H013_B"])

    assert result.exit_code == 0, result.output
    assert result.output == (
        "ID: 001\n"
        "Short name: 2021_Caldor\n"
        "Documentation: https://example.test/caldor\n"
        "Benchmark target: H013_B\n"
        "\n"
        "Temporal period\n"
        "Target: H013\n"
        "Start: 2021-08-19T23:00+00:00\n"
        "End: 2021-08-21T23:00+00:00\n"
        "\n"
        "KPI groups\n"
        "B: Building Damage\n"
        "\n"
        "KPIs\n"
        "ID   KPI   Weight   value_norm_param_m\n"
        "FB001_BD01    1  \n"
        "FB001_BD06    1  \n"
    )


def test_list_command_prints_standalone_building_damage_target_details(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["list", "2021_Caldor", "B"])

    assert result.exit_code == 0, result.output
    assert result.output == (
        "ID: 001\n"
        "Short name: 2021_Caldor\n"
        "Documentation: https://example.test/caldor\n"
        "Benchmark target: B\n"
        "\n"
        "KPI groups\n"
        "B: Building Damage\n"
        "\n"
        "KPIs\n"
        "ID   KPI   Weight   value_norm_param_m\n"
        "FB001_BD01    1  \n"
        "FB001_BD06    1  \n"
    )


def test_data_list_matches_top_level_list(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    top_level = CliRunner().invoke(main, ["list"])
    data_level = CliRunner().invoke(main, ["data", "list"])

    assert top_level.exit_code == 0, top_level.output
    assert data_level.exit_code == 0, data_level.output
    assert data_level.output == top_level.output


def test_data_versions_prints_available_versions(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["data", "versions", "001"])

    assert result.exit_code == 0, result.output
    assert result.output == "001  2021 Caldor Fire\n  latest\n  2026.1\n"


def test_data_versions_accepts_unpadded_case_id(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["data", "versions", "1"])

    assert result.exit_code == 0, result.output
    assert "001  2021 Caldor Fire" in result.output


def test_data_get_downloads_latest_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))
    downloads = []

    def fake_urlretrieve(url, output_path, reporthook=None):
        downloads.append((url, output_path))
        if reporthook is not None:
            reporthook(0, 8192, 16384)
            reporthook(1, 8192, 16384)
            reporthook(2, 8192, 16384)
        output_path.write_text("downloaded")
        return output_path, None

    monkeypatch.setattr("firebench.cli.urlretrieve", fake_urlretrieve)

    result = CliRunner().invoke(main, ["data", "get", "001", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert downloads == [("https://example.test/files/latest.zip?download=1", tmp_path / "latest.zip")]
    assert (tmp_path / "latest.zip").read_text() == "downloaded"


def test_data_get_downloads_selected_version(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))
    downloads = []

    def fake_urlretrieve(url, output_path, reporthook=None):
        downloads.append((url, output_path))
        if reporthook is not None:
            reporthook(0, 8192, 16384)
            reporthook(1, 8192, 16384)
            reporthook(2, 8192, 16384)
        output_path.write_text("downloaded")
        return output_path, None

    monkeypatch.setattr("firebench.cli.urlretrieve", fake_urlretrieve)

    result = CliRunner().invoke(
        main, ["data", "get", "1", "--version", "2026.1", "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert downloads == [("https://example.test/files/v2026.1.zip?download=1", tmp_path / "v2026.1.zip")]


def test_data_get_accepts_short_name(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))
    downloads = []

    def fake_urlretrieve(url, output_path, reporthook=None):
        downloads.append((url, output_path))
        output_path.write_text("downloaded")
        return output_path, None

    monkeypatch.setattr("firebench.cli.urlretrieve", fake_urlretrieve)

    result = CliRunner().invoke(main, ["data", "get", "2021_Caldor", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert downloads == [("https://example.test/files/latest.zip?download=1", tmp_path / "latest.zip")]
    assert "Downloading case 001 data version latest" in result.output


def test_data_get_unknown_version_fails(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["data", "get", "001", "--version", "missing"])

    assert result.exit_code != 0
    assert "Unknown data version 'missing'" in result.output
    assert "latest, 2026.1" in result.output
