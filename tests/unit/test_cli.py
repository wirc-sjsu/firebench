from pathlib import Path

from click.testing import CliRunner

from firebench.cli import main


def test_run_command_forwards_options(monkeypatch, tmp_path):
    model_output = tmp_path / "model.h5"
    obs_data = tmp_path / "Caldor.h5"
    log_file = tmp_path / "Caldor.log"
    output_json = tmp_path / "Caldor_rslt.json"
    score_card_report = tmp_path / "Caldor.pdf"
    model_output.write_text("model")
    obs_data.write_text("obs")
    call = {}

    def fake_run_caldor_benchmark(**kwargs):
        call.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(
        "firebench.cli.caldor.run_caldor_benchmark",
        lambda model_output, **kwargs: fake_run_caldor_benchmark(model_output=model_output, **kwargs),
    )

    result = CliRunner().invoke(
        main,
        [
            "run",
            str(model_output),
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
