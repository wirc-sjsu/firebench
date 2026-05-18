import logging
from pathlib import Path

import click

from .benchmarks import AVAIL_BENCHMARKS
from .tools.logging_config import configure_logging

logger = logging.getLogger(__name__)

FIREBENCH_BANNER = "\b" + r"""
 (     (    (                      )            )  
 )\ )  )\ ) )\ )       (        ( /(    (    ( /(  
(()/( (()/((()/( (   ( )\  (    )\())   )\   )\()) 
 /(_)) /(_))/(_)))\  )((_) )\  ((_)\  (((_) ((_)\  
(_))_|(_)) (_)) ((_)((_)_ ((_)  _((_) )\___  _((_) 
| |_  |_ _|| _ \| __|| _ )| __|| \| |((/ __|| || | 
| __|  | | |   /| _| | _ \| _| | .` | | (__ | __ | 
|_|   |___||_|_\|___||___/|___||_|\_|  \___||_||_|                                                                                          
"""

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


@main.command()
@click.argument(
    "model_output",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
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
    for case_id, case_info in sorted(AVAIL_BENCHMARKS.items()):
        click.echo(f"{case_id}  {case_info['name']} - docs: {case_info['url']}")
    return 0


if __name__ == "__main__":
    main()
