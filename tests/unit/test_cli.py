from pathlib import Path

from click.testing import CliRunner

from firebench.cli import main


def _fake_registry(tmp_path, call):
    def fake_runner(model_output, **kwargs):
        call["model_output"] = model_output
        call.update(kwargs)
        return {"ok": True}

    def fake_debug_func(agg_scheme):
        call["debug_agg_scheme"] = agg_scheme

    return {
        "001": {
            "name": "2021 Caldor Fire",
            "url": "https://example.test/caldor",
            "func": fake_runner,
            "debug_func": fake_debug_func,
            "default_options": {
                "agg_scheme": "A",
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

    result = CliRunner().invoke(main, ["run", str(model_output)])

    assert result.exit_code == 0, result.output
    assert call == {
        "model_output": Path(model_output),
        "agg_scheme": "A",
        "name": "",
        "overwrite": False,
        "sign": None,
        "obs_data": tmp_path / "default_obs.h5",
        "output_json": tmp_path / "default_rslt.json",
        "score_card_report": tmp_path / "default.pdf",
    }
    assert (tmp_path / "default.log").exists()


def test_run_command_accepts_unpadded_case_id(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(main, ["run", "-c", "1", str(model_output)])

    assert result.exit_code == 0, result.output
    assert call["model_output"] == Path(model_output)
    assert call["agg_scheme"] == "A"


def test_run_command_accepts_padded_case_id(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(main, ["run", "-c", "001", str(model_output)])

    assert result.exit_code == 0, result.output
    assert call["model_output"] == Path(model_output)
    assert call["agg_scheme"] == "A"


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
            str(model_output),
            "-c",
            "001",
            "-a",
            "B",
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
        ],
    )

    assert result.exit_code == 0, result.output
    assert call == {
        "model_output": Path(model_output),
        "agg_scheme": "B",
        "name": "demo",
        "overwrite": True,
        "sign": ("KEYID", "Signer"),
        "obs_data": Path(obs_data),
        "output_json": Path(output_json),
        "score_card_report": Path(score_card_report),
    }
    assert log_file.exists()


def test_run_command_no_run_prints_registry_without_model_file(monkeypatch, tmp_path):
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    result = CliRunner().invoke(
        main,
        ["run", str(tmp_path / "missing_model.h5"), "-a", "WX_WH1", "--no-run"],
    )

    assert result.exit_code == 0, result.output
    assert call == {"debug_agg_scheme": "WX_WH1"}


def test_run_command_report_creates_report_skeleton(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    call = {}
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, call))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(main, ["run", str(model_output), "--report", "-n", "Demo Model"])

        report_path = Path(cwd) / "firebench_report.md"
        figures_dir = Path(cwd) / "figures"

        assert result.exit_code == 0, result.output
        assert figures_dir.is_dir()
        assert report_path.read_text(encoding="utf-8") == (
            "# Report 2021 Caldor Fire for Demo Model\n"
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

        result = runner.invoke(main, ["run", str(model_output), "--report"])

        assert result.exit_code != 0
        assert "Report file already exists: firebench_report.md" in result.output
        assert report_path.read_text(encoding="utf-8") == "existing report"
        assert call == {}


def test_run_command_unknown_case_fails(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    model_output.write_text("model")
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["run", "-c", "999", str(model_output)])

    assert result.exit_code != 0
    assert "Unknown benchmark case '999'" in result.output
    assert "firebench list" in result.output


def test_list_command_prints_case_names_and_docs(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["list"])

    assert result.exit_code == 0, result.output
    assert result.output == "001  2021 Caldor Fire - docs: https://example.test/caldor\n"
    assert "func" not in result.output
    assert "{" not in result.output


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


def test_data_get_unknown_version_fails(monkeypatch, tmp_path):
    monkeypatch.setattr("firebench.cli.AVAIL_BENCHMARKS", _fake_registry(tmp_path, {}))

    result = CliRunner().invoke(main, ["data", "get", "001", "--version", "missing"])

    assert result.exit_code != 0
    assert "Unknown data version 'missing'" in result.output
    assert "latest, 2026.1" in result.output
