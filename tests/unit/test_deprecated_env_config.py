import os
import subprocess
import sys
import warnings
from pathlib import Path

from click.testing import CliRunner
import pytest

from firebench.cli import main
from firebench.tools.local_db_management import get_local_db_path
from firebench.tools.read_data import get_firebench_data_directory, read_data_file


def test_firebench_imports_without_deprecated_env_vars(monkeypatch):
    env = os.environ.copy()
    env.pop("FIREBENCH_LOCAL_DB", None)
    env.pop("FIREBENCH_DATA_PATH", None)

    result = subprocess.run(
        [sys.executable, "-c", "import firebench; print(firebench.__version__)"],
        check=False,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_cli_list_works_without_deprecated_env_vars(monkeypatch):
    monkeypatch.delenv("FIREBENCH_LOCAL_DB", raising=False)
    monkeypatch.delenv("FIREBENCH_DATA_PATH", raising=False)

    result = CliRunner().invoke(main, ["list"])

    assert result.exit_code == 0, result.output
    assert "2021_Caldor" in result.output


def test_deprecated_env_var_usage_emits_deprecation_warning(monkeypatch, tmp_path):
    data_path = tmp_path / "data"
    local_db_path = tmp_path / "local_db"
    monkeypatch.setenv("FIREBENCH_DATA_PATH", str(data_path))
    monkeypatch.setenv("FIREBENCH_LOCAL_DB", str(local_db_path))

    with pytest.warns(DeprecationWarning, match="FIREBENCH_DATA_PATH is deprecated"):
        assert get_firebench_data_directory() == str(data_path)

    with pytest.warns(DeprecationWarning, match="FIREBENCH_LOCAL_DB is deprecated"):
        assert get_local_db_path() == str(local_db_path)


def test_missing_deprecated_env_vars_do_not_raise(monkeypatch):
    monkeypatch.delenv("FIREBENCH_LOCAL_DB", raising=False)
    monkeypatch.delenv("FIREBENCH_DATA_PATH", raising=False)

    assert Path(get_firebench_data_directory()).name == "data"
    assert Path(get_local_db_path()).name == "local_db"


def test_explicit_data_path_replaces_deprecated_env_var(monkeypatch):
    monkeypatch.setenv("FIREBENCH_DATA_PATH", "/deprecated/path")

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        data = read_data_file("dummy_fuel_model", "test", data_path="data")

    assert data["nb_fuel_classes"] == 3
