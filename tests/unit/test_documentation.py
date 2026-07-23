"""Checks for maintained documentation examples and references."""

import json
from pathlib import Path
import re
import runpy
import shlex
import tomllib
from urllib.parse import unquote

import click
from click.testing import CliRunner
import h5py
import yaml

from firebench.cli import main
from firebench.standardize import validate_h5_std

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = REPOSITORY_ROOT / "docs"
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
HTML_SOURCE = re.compile(r"\b(?:src|href)=[\"']([^\"']+)[\"']")
FENCED_BLOCK = re.compile(r"^```(json|yaml|toml)\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)
SHELL_BLOCK = re.compile(r"^```(?:bash|sh)\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _documentation_pages():
    return sorted(DOCS_ROOT.rglob("*.md"))


def test_local_documentation_links_resolve():
    missing = []
    for page in _documentation_pages():
        content = page.read_text(encoding="utf-8")
        targets = MARKDOWN_LINK.findall(content) + HTML_SOURCE.findall(content)
        for raw_target in targets:
            target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
            if target.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            relative_path = unquote(target.split("#", maxsplit=1)[0])
            if not relative_path:
                continue
            resolved = (page.parent / relative_path).resolve()
            if not resolved.exists():
                missing.append(f"{page.relative_to(REPOSITORY_ROOT)} -> {target}")
    assert not missing, "Missing local documentation targets:\n" + "\n".join(missing)


def test_structured_markdown_examples_parse():
    failures = []
    loaders = {"json": json.loads, "yaml": yaml.safe_load, "toml": tomllib.loads}
    for page in _documentation_pages():
        content = page.read_text(encoding="utf-8")
        for language, block in FENCED_BLOCK.findall(content):
            try:
                loaders[language](block)
            except Exception as exc:  # pragma: no cover - assertion reports source context
                failures.append(f"{page.relative_to(REPOSITORY_ROOT)} ({language}): {exc}")
    assert not failures, "Invalid structured examples:\n" + "\n".join(failures)


def test_external_configuration_examples_parse():
    yaml_config = yaml.safe_load((DOCS_ROOT / "examples/multirun.yml").read_text(encoding="utf-8"))
    with (DOCS_ROOT / "examples/plot.toml").open("rb") as stream:
        toml_config = tomllib.load(stream)

    assert len(yaml_config["models"]) == 2
    assert yaml_config["target"] == "H013_P"
    assert len(toml_config["files"]) == 2
    assert toml_config["perimeter"]["enabled"] is True


def test_model_output_example_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(DOCS_ROOT / "examples/create_model_output.py"), run_name="__main__")

    with h5py.File(tmp_path / "model_output.h5", "r") as h5:
        validate_h5_std(h5)
        assert h5["/spatial_2d/surface/rate_of_spread"].shape == (2, 2, 3)
        assert h5["/spatial_2d/surface/rate_of_spread"].attrs["units"] == "meter / second"


def test_rate_of_spread_example_runs():
    namespace = runpy.run_path(str(DOCS_ROOT / "examples/wind_driven_ros.py"))
    model = namespace["WindDrivenROS"]

    wind_speed = namespace["ft"].StandardVariableNames.WIND_SPEED
    assert model.compute_ros({wind_speed: 5.0}) == 0.2
    converted = model.compute_ros_with_units({wind_speed: 10.0 * namespace["ft"].ureg.mph})
    assert converted.to("meter / second").magnitude > 0


def _parse_click_command(command: click.Command, args: list[str], parent=None):
    try:
        context = command.make_context(command.name or "firebench", args, parent=parent)
    except click.exceptions.Exit as exc:
        assert exc.exit_code == 0
        return
    if isinstance(command, click.Group):
        _, child, remaining = command.resolve_command(context, args)
        _parse_click_command(child, remaining, parent=context)


def test_firebench_commands_shown_in_tutorials_parse():
    documented_commands = []
    for page in sorted((DOCS_ROOT / "tutorials").glob("*.md")):
        content = page.read_text(encoding="utf-8")
        for block in SHELL_BLOCK.findall(content):
            for line in block.replace("\\\n", " ").splitlines():
                line = line.strip()
                if line.startswith("firebench ") and " -c " not in line and " -a " not in line:
                    documented_commands.append((page, shlex.split(line)[1:]))

    assert len(documented_commands) >= 15
    for page, args in documented_commands:
        try:
            _parse_click_command(main, args)
        except click.ClickException as exc:
            raise AssertionError(f"Invalid command in {page.relative_to(REPOSITORY_ROOT)}: {args}") from exc


def test_documented_cli_commands_have_help():
    runner = CliRunner()
    commands = [
        [],
        ["list"],
        ["data"],
        ["data", "list"],
        ["data", "versions"],
        ["data", "get"],
        ["run"],
        ["multirun"],
        ["plot"],
    ]
    for command in commands:
        result = runner.invoke(main, [*command, "--help"])
        assert result.exit_code == 0, result.output
