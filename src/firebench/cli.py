import logging
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlretrieve

import click
import yaml

from .benchmarks import AVAIL_BENCHMARKS
from .metrics.table import save_comparison_as_table
from .plotting import plot_from_config
from .tools.logging_config import configure_logging

logger = logging.getLogger(__name__)

REPORT_PATH = Path("firebench_report.md")
FIGURES_DIR = Path("figures")

FIREBENCH_BANNER = (
    "\b"
    + r"""
 (     (    (                      )            )  
 )\ )  )\ ) )\ )       (        ( /(    (    ( /(  
(()/( (()/((()/( (   ( )\  (    )\())   )\   )\()) 
 /(_)) /(_))/(_)))\  )((_) )\  ((_)\  (((_) ((_)\  
(_))_|(_)) (_)) ((_)((_)_ ((_)  _((_) )\___  _((_) 
| |_  |_ _|| _ \| __|| _ )| __|| \| |((/ __|| || | 
| __|  | | |   /| _| | _ \| _| | .` | | (__ | __ | 
|_|   |___||_|_\|___||___/|___||_|\_|  \___||_||_|                                                                                          
"""
)


@click.group(help=FIREBENCH_BANNER)
def main() -> None:
    pass


def _normalize_case_id(case: str) -> str:
    case_id = str(case).strip()
    if case_id.isdigit():
        return case_id.zfill(3)
    return case_id


def _resolve_case_id(case: str) -> str:
    case_id = _normalize_case_id(case)
    if case_id in AVAIL_BENCHMARKS:
        return case_id

    for registered_case_id, case_info in AVAIL_BENCHMARKS.items():
        if case_id == case_info.get("short_name"):
            return registered_case_id

    return case_id


def _get_case_info(case: str) -> tuple[str, dict]:
    case_id = _resolve_case_id(case)
    try:
        return case_id, AVAIL_BENCHMARKS[case_id]
    except KeyError as exc:
        raise click.UsageError(
            f"Unknown benchmark case '{case}'. Use 'firebench list' to see available cases."
        ) from exc


def _get_default(case_info: dict, key: str):
    return case_info.get("default_options", {}).get(key)


def _get_case_data(case: str) -> tuple[str, dict, dict]:
    case_id, case_info = _get_case_info(case)
    data_versions = case_info.get("data", {})
    if not data_versions:
        raise click.UsageError(f"No data downloads are registered for benchmark case '{case_id}'.")
    return case_id, case_info, data_versions


def _filename_from_url(url: str) -> str:
    filename = Path(urlparse(url).path).name
    if not filename:
        raise click.UsageError(f"Could not infer a file name from download URL: {url}")
    return filename


def _download_with_progress(url: str, output_path: Path) -> None:
    progress_bar = None
    previous_bytes = 0

    def reporthook(block_count: int, block_size: int, total_size: int) -> None:
        nonlocal progress_bar, previous_bytes

        if progress_bar is None:
            progress_length = total_size if total_size > 0 else None
            progress_bar = click.progressbar(
                length=progress_length,
                label=f"Downloading {output_path.name}",
            )
            progress_bar.__enter__()

        downloaded_bytes = block_count * block_size
        if total_size > 0:
            downloaded_bytes = min(downloaded_bytes, total_size)
        delta = downloaded_bytes - previous_bytes
        if delta > 0:
            progress_bar.update(delta)
            previous_bytes = downloaded_bytes

    try:
        urlretrieve(url, output_path, reporthook=reporthook)
    finally:
        if progress_bar is not None:
            progress_bar.__exit__(None, None, None)


def _echo_cases() -> None:
    click.echo("ID   Short name   Documentation")
    for case_id, case_info in sorted(AVAIL_BENCHMARKS.items()):
        short_name = case_info.get("short_name", "")
        click.echo(f"{case_id}  {short_name}  {case_info['url']}")


def _format_target_datetime(value) -> str:
    return value.isoformat(timespec="minutes")


def _format_norm_param_m(kpi: dict) -> str:
    value = kpi.get("value_norm_param_m")
    if value is None:
        return kpi.get("value_norm_param_m_definition") or ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _format_kpi_weight(kpi: dict) -> str:
    weight = kpi.get("weight")
    return "" if weight is None else str(weight)


def _describe_target(target_describer, target: str | None, obs_data: Path | None = None) -> dict:
    if target is None:
        return target_describer()
    if obs_data is None:
        return target_describer(target)
    try:
        return target_describer(target, obs_data=obs_data)
    except TypeError as exc:
        if "obs_data" not in str(exc):
            raise
        return target_describer(target)


def _echo_case_targets(case: str, target: str | None = None, obs_data: Path | None = None) -> None:
    case_id, case_info = _get_case_info(case)
    click.echo(f"ID: {case_id}")
    click.echo(f"Short name: {case_info.get('short_name', '')}")
    click.echo(f"Documentation: {case_info['url']}")

    target_describer = case_info.get("target_describer")
    if target_describer is None:
        click.echo("No benchmark targets are registered.")
        return

    try:
        target_info = _describe_target(target_describer, target, obs_data)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
    if target is not None:
        click.echo(f"Benchmark target: {target_info['target']}")
        if not target_info.get("aggregated", True):
            click.echo("Aggregation: none (individual KPI scores only)")
        if target_info.get("period"):
            click.echo("")
            click.echo("Temporal period")
            click.echo(f"Target: {target_info['period']['target']}")
            click.echo(f"Start: {_format_target_datetime(target_info['period']['start'])}")
            click.echo(f"End: {_format_target_datetime(target_info['period']['end'])}")

        click.echo("")
        click.echo("KPI groups")
        for flag, description in target_info["kpi_groups"].items():
            click.echo(f"{flag}: {description}")

        if target_info.get("perimeters"):
            click.echo("")
            click.echo("Perimeters")
            click.echo("Time")
            for perimeter in target_info["perimeters"]:
                click.echo(perimeter["time"])

        if target_info.get("weather_stations"):
            click.echo("")
            click.echo("Weather stations")
            click.echo("Variable   Stations   Trusted stations")
            for station_info in target_info["weather_stations"]:
                click.echo(
                    f"{station_info['variable']}  "
                    f"{station_info['stations']}  "
                    f"{station_info['trusted_stations']}"
                )

        click.echo("")
        click.echo("KPIs")
        click.echo("ID   KPI   Weight   value_norm_param_m")
        for kpi in target_info["kpis"]:
            norm_param = _format_norm_param_m(kpi)
            weight = _format_kpi_weight(kpi)
            click.echo(f"{kpi['id']}  {kpi['name']}  {weight}  {norm_param}")
        return

    click.echo("")
    click.echo("Standalone targets")
    for standalone_target, description in target_info["standalone_targets"].items():
        click.echo(f"{standalone_target}: {description}")

    click.echo("")
    click.echo("Period targets")
    click.echo(f"Syntax: {target_info['period_target_syntax']} (for example, H013_BPW or P02_P)")
    click.echo("")
    click.echo("Available periods")
    click.echo("Target   Start   End")
    for period in target_info["periods"]:
        click.echo(
            f"{period['target']}  "
            f"{_format_target_datetime(period['start'])}  "
            f"{_format_target_datetime(period['end'])}"
        )

    click.echo("")
    click.echo("Combinable flags")
    for flag, description in target_info["kpi_groups"].items():
        click.echo(f"{flag}: {description}")


def _get_model_name(model_output: Path, name: str) -> str:
    if name:
        return name
    return model_output.stem


def _render_report_target_information(target: str, target_info: dict | None = None) -> str:
    lines = [
        "## Benchmark target information",
        f"Benchmark target: {target_info['target'] if target_info is not None else target}",
    ]

    if target_info is None:
        return "\n".join(lines)

    if not target_info.get("aggregated", True):
        lines.append("Aggregation: none (individual KPI scores only)")

    if target_info.get("period"):
        lines.extend(
            [
                "",
                "### Temporal period",
                f"Target: {target_info['period']['target']}",
                f"Start: {_format_target_datetime(target_info['period']['start'])}",
                f"End: {_format_target_datetime(target_info['period']['end'])}",
            ]
        )

    lines.extend(["", "### KPI groups"])
    for flag, description in target_info["kpi_groups"].items():
        lines.append(f"- {flag}: {description}")

    if target_info.get("perimeters"):
        lines.extend(["", "### Perimeters", "| Time |", "| --- |"])
        for perimeter in target_info["perimeters"]:
            lines.append(f"| {perimeter['time']} |")

    if target_info.get("weather_stations"):
        lines.extend(
            [
                "",
                "### Weather stations",
                "| Variable | Stations | Trusted stations |",
                "| --- | --- | --- |",
            ]
        )
        for station_info in target_info["weather_stations"]:
            lines.append(
                f"| {station_info['variable']} | "
                f"{station_info['stations']} | "
                f"{station_info['trusted_stations']} |"
            )

    if target_info.get("kpis"):
        lines.extend(
            [
                "",
                "### KPIs",
                "| ID | KPI | Weight | value_norm_param_m |",
                "| --- | --- | --- | --- |",
            ]
        )
        for kpi in target_info["kpis"]:
            norm_param = _format_norm_param_m(kpi)
            weight = _format_kpi_weight(kpi)
            lines.append(f"| {kpi['id']} | {kpi['name']} | {weight} | {norm_param} |")

    return "\n".join(lines)


def _render_report_figures(figures: list[dict] | None = None) -> str:
    if not figures:
        return ""

    lines = []
    for figure in figures:
        lines.extend(
            [
                f"### {figure['title']}",
                '<p align="center">',
                f'  <img src="{Path(figure["path"]).as_posix()}" alt="{figure["alt"]}">',
                "</p>",
                "",
            ]
        )
    return "\n".join(lines)


def _render_report_skeleton(
    benchmark_name: str,
    model_name: str,
    target: str,
    target_info: dict | None = None,
    figures: list[dict] | None = None,
) -> str:
    target_information = _render_report_target_information(target, target_info)
    report_figures = _render_report_figures(figures)
    return f"""# Report {benchmark_name} for {model_name}
{target_information}

## Submitters' comments
This section is reserved for the model users who have submitted the model output to this benchmark.
### Short model description and keywords
### Setup/Configuration
### Inputs
### Post-processing
### FireBench adapter used
## FireBench Team comments
This section is reserved to the FireBench team validating this benchmark results
## Results
{report_figures}"""


def _check_report_skeleton_paths(overwrite: bool) -> None:
    if REPORT_PATH.exists() and not overwrite:
        raise click.UsageError(f"Report file already exists: {REPORT_PATH}. Use --overwrite to replace it.")
    if FIGURES_DIR.exists() and not FIGURES_DIR.is_dir():
        raise click.UsageError(f"Figures path exists and is not a directory: {FIGURES_DIR}")


def _write_report_skeleton(
    benchmark_name: str,
    model_name: str,
    target: str,
    target_info: dict | None = None,
    figures: list[dict] | None = None,
) -> None:
    FIGURES_DIR.mkdir(exist_ok=True)
    REPORT_PATH.write_text(
        _render_report_skeleton(benchmark_name, model_name, target, target_info, figures),
        encoding="utf-8",
    )


def _create_report_figures(
    case_info: dict,
    model_output: Path,
    obs_data: Path,
    target: str,
    target_info: dict | None,
) -> list[dict]:
    report_figure_func = case_info.get("report_figure_func")
    if report_figure_func is None:
        return []
    try:
        return report_figure_func(
            model_output=model_output,
            obs_data=obs_data,
            benchmark_target=target,
            target_info=target_info,
            output_dir=FIGURES_DIR,
        )
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc


def _read_multirun_config(config_path: Path) -> dict:
    if config_path.suffix.lower() not in {".yml", ".yaml"}:
        raise click.UsageError("Multirun config must be a .yml or .yaml file.")
    if not config_path.is_file():
        raise click.UsageError(f"Multirun config file does not exist: {config_path}")
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise click.UsageError(f"Invalid YAML config: {exc}") from exc
    if not isinstance(config, dict):
        raise click.UsageError("Multirun config must contain a YAML mapping.")
    return config


def _resolve_config_relative_path(config_dir: Path, value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return config_dir / path


def _slugify_model_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "model"


def _validate_multirun_models(config: dict, config_dir: Path) -> list[dict]:
    models = config.get("models")
    if not isinstance(models, list) or len(models) < 2:
        raise click.UsageError("Multirun config requires at least two models.")

    resolved_models = []
    used_slugs = set()
    for index, model in enumerate(models, start=1):
        if not isinstance(model, dict):
            raise click.UsageError(f"Model entry {index} must be a YAML mapping.")
        name = model.get("name")
        model_output = model.get("model_output")
        if not name:
            raise click.UsageError(f"Model entry {index} requires a name.")
        if not model_output:
            raise click.UsageError(f"Model entry {index} requires model_output.")

        resolved_model_output = _resolve_config_relative_path(config_dir, model_output)
        if not resolved_model_output.is_file():
            raise click.UsageError(f"Model output file does not exist: {resolved_model_output}")

        slug = _slugify_model_name(str(name))
        if slug in used_slugs:
            raise click.UsageError(f"Duplicate model output slug '{slug}'. Use distinct model names.")
        used_slugs.add(slug)
        resolved_models.append(
            {
                "name": str(name),
                "model_output": resolved_model_output,
                "slug": slug,
            }
        )
    return resolved_models


def _resolve_multirun_config(config_path: Path) -> dict:
    config_path = config_path.resolve()
    config = _read_multirun_config(config_path)
    config_dir = config_path.parent

    case = config.get("case")
    target = config.get("target")
    if not case:
        raise click.UsageError("Multirun config requires case.")
    if not target:
        raise click.UsageError("Multirun config requires target.")

    selected_case_id, case_info = _get_case_info(str(case))
    target = str(target)
    target_normalizer = case_info.get("target_normalizer")
    if target_normalizer is not None:
        try:
            target = target_normalizer(target)
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc

    output_dir = _resolve_config_relative_path(config_dir, config.get("output_dir")) or config_dir
    obs_data = _resolve_config_relative_path(config_dir, config.get("obs_data")) or _get_default(
        case_info, "obs_data"
    )
    comparison_report = config.get("comparison_score_card_report", "comparison_scorecard.pdf")
    comparison_report = Path(comparison_report)
    if not comparison_report.is_absolute():
        comparison_report = output_dir / comparison_report

    return {
        "case_id": selected_case_id,
        "case_info": case_info,
        "target": target,
        "output_dir": output_dir,
        "overwrite": bool(config.get("overwrite", False)),
        "verbose": config.get("verbose", _get_default(case_info, "verbose")),
        "no_console": bool(config.get("no_console", False)),
        "obs_data": obs_data,
        "full_name": bool(config.get("full_name", False)),
        "comparison_include_kpis": bool(config.get("comparison_include_kpis", False)),
        "comparison_score_card_report": comparison_report,
        "models": _validate_multirun_models(config, config_dir),
    }


@main.command()
@click.argument("case", type=str)
@click.argument("target", type=str)
@click.argument(
    "model_output",
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option(
    "-n",
    "--name",
    default="",
    help="Name of the evaluated model/configuration.",
)
@click.option(
    "-o",
    "--overwrite",
    is_flag=True,
    help="Overwrite existing results if present.",
)
@click.option(
    "-s",
    "--sign",
    nargs=2,
    metavar="KEYID SIGNER",
    help="Sign with Verification Level (VL) using KEYID and SIGNER.",
)
@click.option(
    "-v",
    "--verbose",
    default=None,
    type=int,
    help="Verbosity 0: critical, 1: error, 2: warning, 3: info, 4+: debug.",
)
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to log file.",
)
@click.option("--no-console", is_flag=True, help="Disable console logging.")
@click.option(
    "--obs-data",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to the Caldor observational HDF5 file.",
)
@click.option(
    "--output-json",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to write benchmark JSON results.",
)
@click.option(
    "--score-card-report",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to write the score card PDF.",
)
@click.option(
    "--full-name",
    "--full_name",
    is_flag=True,
    help="Use full benchmark IDs and KPI names in the score-card PDF.",
)
@click.option(
    "--no-run",
    is_flag=True,
    help="Build registries and print selected groups/benchmarks without running metrics.",
)
@click.option(
    "--report",
    is_flag=True,
    help="Create firebench_report.md and the figures directory for the benchmark run.",
)
def run(
    case: str,
    target: str,
    model_output: Path,
    name: str,
    overwrite: bool,
    sign: tuple[str, str] | None,
    verbose: int | None,
    log_file: Path | None,
    no_console: bool,
    obs_data: Path | None,
    output_json: Path | None,
    score_card_report: Path | None,
    full_name: bool,
    no_run: bool,
    report: bool,
) -> None:
    """
    Run a benchmark target against model std HDF5 output.
    """
    selected_case_id, case_info = _get_case_info(case)
    target_normalizer = case_info.get("target_normalizer")
    if target_normalizer is not None:
        try:
            target = target_normalizer(target)
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc

    verbose = verbose if verbose is not None else _get_default(case_info, "verbose")
    log_file = log_file or _get_default(case_info, "log_file")
    obs_data = obs_data or _get_default(case_info, "obs_data")
    output_json = output_json or _get_default(case_info, "output_json")
    score_card_report = score_card_report or _get_default(case_info, "score_card_report")

    configure_logging(verbose, use_console=not no_console, log_path=log_file)
    logger.info(
        "[CLI] run benchmark case %s target %s with model output: %s",
        selected_case_id,
        target,
        model_output,
    )
    if no_run:
        debug_func = case_info.get("debug_func")
        if debug_func is None:
            raise click.UsageError(f"Benchmark case '{selected_case_id}' does not support --no-run.")
        debug_func(benchmark_target=target)
        return 0

    if not model_output.is_file():
        raise click.UsageError(f"Model output file does not exist: {model_output}")
    if report:
        _check_report_skeleton_paths(overwrite)
        target_describer = case_info.get("target_describer")
        if target_describer is not None:
            try:
                target_info = _describe_target(target_describer, target, obs_data)
            except ValueError as exc:
                raise click.UsageError(str(exc)) from exc
        else:
            target_info = None

    case_info["func"](
        model_output,
        benchmark_target=target,
        name=name,
        overwrite=overwrite,
        sign=sign,
        obs_data=obs_data,
        output_json=output_json,
        score_card_report=score_card_report,
        score_card_full_name=full_name,
    )
    if report:
        report_figures = _create_report_figures(
            case_info=case_info,
            model_output=model_output,
            obs_data=obs_data,
            target=target,
            target_info=target_info,
        )
        _write_report_skeleton(
            benchmark_name=case_info["name"],
            model_name=_get_model_name(model_output, name),
            target=target,
            target_info=target_info,
            figures=report_figures,
        )
    return 0


@main.command()
@click.argument(
    "config",
    type=click.Path(dir_okay=False, path_type=Path),
)
def multirun(config: Path) -> None:
    """
    Run one benchmark target against multiple model outputs from a YAML config.
    """
    resolved_config = _resolve_multirun_config(config)
    case_info = resolved_config["case_info"]
    output_dir = resolved_config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    comparison_report = resolved_config["comparison_score_card_report"]
    comparison_report.parent.mkdir(parents=True, exist_ok=True)
    if comparison_report.exists() and not resolved_config["overwrite"]:
        raise click.UsageError(
            f"Comparison score card report already exists: {comparison_report}. "
            "Set overwrite: true to replace it."
        )

    results = []
    for model in resolved_config["models"]:
        output_json = output_dir / f"{model['slug']}_rslt.json"
        score_card_report = output_dir / f"{model['slug']}_scorecard.pdf"
        log_file = output_dir / f"{model['slug']}.log"
        configure_logging(
            resolved_config["verbose"],
            use_console=not resolved_config["no_console"],
            log_path=log_file,
        )
        logger.info(
            "[CLI] multirun benchmark case %s target %s with model output: %s",
            resolved_config["case_id"],
            resolved_config["target"],
            model["model_output"],
        )
        result = case_info["func"](
            model["model_output"],
            benchmark_target=resolved_config["target"],
            name=model["name"],
            overwrite=resolved_config["overwrite"],
            sign=None,
            obs_data=resolved_config["obs_data"],
            output_json=output_json,
            score_card_report=score_card_report,
            score_card_full_name=resolved_config["full_name"],
        )
        if not result or "score_card" not in result:
            raise click.UsageError(
                f"Benchmark result for model '{model['name']}' did not include a score card."
            )
        results.append(result)

    save_comparison_as_table(
        comparison_report,
        results,
        include_kpis=resolved_config["comparison_include_kpis"],
        full_name=resolved_config["full_name"],
    )
    click.echo(f"Wrote {comparison_report}")


@main.command("list")
@click.argument("case", required=False, type=str)
@click.argument("target", required=False, type=str)
@click.option(
    "--obs-data",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to the observational HDF5 file for target data summaries.",
)
def list_cases(case: str | None, target: str | None, obs_data: Path | None) -> None:
    """
    List available benchmarks or targets for a benchmark case.
    """
    if case:
        _echo_case_targets(case, target, obs_data)
        return 0
    _echo_cases()
    return 0


@main.command()
@click.argument(
    "config",
    type=click.Path(dir_okay=False, path_type=Path),
)
def plot(config: Path) -> None:
    """
    Generate plots from a TOML configuration file.
    """
    written = plot_from_config(config)
    for output_path in written:
        click.echo(f"Wrote {output_path}")
    return 0


@main.group()
def data() -> None:
    """
    Download benchmark data.
    """
    pass


@data.command("list")
def data_list_cases() -> None:
    """
    List all available benchmarks.
    """
    _echo_cases()
    return 0


@data.command("versions")
@click.argument("case", type=str)
def data_versions(case: str) -> None:
    """
    List available data versions for a benchmark case.
    """
    case_id, case_info, data_by_version = _get_case_data(case)
    click.echo(f"{case_id}  {case_info['name']}")
    for version in data_by_version:
        click.echo(f"  {version}")
    return 0


@data.command("get")
@click.argument("case", type=str)
@click.option("--version", default="latest", show_default=True, help="Data version to download.")
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Directory where the downloaded archive will be saved.",
)
def data_get(case: str, version: str, output_dir: Path) -> None:
    """
    Download data for a benchmark case.
    """
    case_id, _, data_by_version = _get_case_data(case)
    if version not in data_by_version:
        available_versions = ", ".join(data_by_version)
        raise click.UsageError(
            f"Unknown data version '{version}' for benchmark case '{case_id}'. "
            f"Available versions: {available_versions}"
        )

    url = data_by_version[version]
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / _filename_from_url(url)
    click.echo(f"Downloading case {case_id} data version {version} to {output_path}")
    _download_with_progress(url, output_path)
    click.echo(f"Downloaded {output_path}")
    return 0


@main.command("wx-qc")
def wx_qc() -> None:
    """
    Launch the weather station QC GUI.
    """
    from .tools.wx_qc.app import App

    App().mainloop()


if __name__ == "__main__":
    main()
