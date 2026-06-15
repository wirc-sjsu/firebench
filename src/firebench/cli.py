import logging
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlretrieve

import click

from .benchmarks import AVAIL_BENCHMARKS
from .plotting import plot_from_config
from .tools.logging_config import configure_logging

logger = logging.getLogger(__name__)

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


def _get_case_info(case: str) -> tuple[str, dict]:
    case_id = _normalize_case_id(case)
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
    for case_id, case_info in sorted(AVAIL_BENCHMARKS.items()):
        click.echo(f"{case_id}  {case_info['name']} - docs: {case_info['url']}")


@main.command()
@click.argument(
    "model_output",
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option(
    "-c",
    "--case",
    "case_id",
    default="001",
    show_default=True,
    help="Benchmark case ID.",
)
@click.option(
    "-a",
    "--agg-scheme",
    default=None,
    help="Aggregation scheme.",
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
    "--no-run",
    is_flag=True,
    help="Build registries and print selected groups/benchmarks without running metrics.",
)
def run(
    model_output: Path,
    case_id: str,
    agg_scheme: str | None,
    name: str,
    overwrite: bool,
    sign: tuple[str, str] | None,
    verbose: int | None,
    log_file: Path | None,
    no_console: bool,
    obs_data: Path | None,
    output_json: Path | None,
    score_card_report: Path | None,
    no_run: bool,
) -> None:
    """
    Run a benchmark case against model std HDF5 output. Use firebench list to see all available cases.
    """
    selected_case_id, case_info = _get_case_info(case_id)
    agg_scheme = agg_scheme or _get_default(case_info, "agg_scheme")
    verbose = verbose if verbose is not None else _get_default(case_info, "verbose")
    log_file = log_file or _get_default(case_info, "log_file")
    obs_data = obs_data or _get_default(case_info, "obs_data")
    output_json = output_json or _get_default(case_info, "output_json")
    score_card_report = score_card_report or _get_default(case_info, "score_card_report")

    configure_logging(verbose, use_console=not no_console, log_path=log_file)
    logger.info("[CLI] run benchmark case %s with model output: %s", selected_case_id, model_output)
    if no_run:
        debug_func = case_info.get("debug_func")
        if debug_func is None:
            raise click.UsageError(f"Benchmark case '{selected_case_id}' does not support --no-run.")
        debug_func(agg_scheme=agg_scheme)
        return 0

    if not model_output.is_file():
        raise click.UsageError(f"Model output file does not exist: {model_output}")

    case_info["func"](
        model_output,
        agg_scheme=agg_scheme,
        name=name,
        overwrite=overwrite,
        sign=sign,
        obs_data=obs_data,
        output_json=output_json,
        score_card_report=score_card_report,
    )
    return 0


@main.command("list")
def list_cases() -> None:
    """
    List all available benchmarks
    """
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


if __name__ == "__main__":
    main()
