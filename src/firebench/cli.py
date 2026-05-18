import logging
from pathlib import Path

import click

from .benchmarks import caldor
from .tools.logging_config import configure_logging

logger = logging.getLogger(__name__)


@click.group()
def main() -> None:
    """
    @@@@@@ @@ @@@@@   @@@@@  @@@@@   @@@@@  @     @   @@@@@ @@   @@
    @@     @@ @@   @  @@     @   @@  @      @@@   @  @@   @ @@   @@
    @@@@@  @@ @@@@@@  @@@@@  @@@@@@  @@@@   @@ @@ @ @@      @@@@@@@
    @@     @@ @@.@@   @@     @    @  @      @@   @@  @@   @ @@   @@
    @@     @@ @@  @@  @@@@@  @@@@@-  @@@@@  @@    @    @@@  @@   @@
    """
    pass


@main.command()
@click.argument(
    "model_output",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "-a",
    "--agg-scheme",
    default=caldor.DEFAULT_AGGREGATION_SCHEME,
    show_default=True,
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
    default=caldor.DEFAULT_VERBOSITY,
    show_default=True,
    help="Verbosity 0: critical, 1: error, 2: warning, 3: info, 4+: debug.",
)
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path(caldor.LOG_FILENAME),
    show_default=True,
    help="Path to log file.",
)
@click.option("--no-console", is_flag=True, help="Disable console logging.")
@click.option(
    "--obs-data",
    type=click.Path(dir_okay=False, path_type=Path),
    default=caldor.DEFAULT_OBS_DATA_PATH,
    show_default=True,
    help="Path to the Caldor observational HDF5 file.",
)
@click.option(
    "--output-json",
    type=click.Path(dir_okay=False, path_type=Path),
    default=caldor.DEFAULT_OUTPUT_PATH_JSON,
    show_default=True,
    help="Path to write benchmark JSON results.",
)
@click.option(
    "--score-card-report",
    type=click.Path(dir_okay=False, path_type=Path),
    default=caldor.DEFAULT_SCORE_CARD_REPORT_PATH,
    show_default=True,
    help="Path to write the score card PDF.",
)
def run(
    model_output: Path,
    agg_scheme: str,
    name: str,
    overwrite: bool,
    sign: tuple[str, str] | None,
    verbose: int,
    log_file: Path,
    no_console: bool,
    obs_data: Path,
    output_json: Path,
    score_card_report: Path,
) -> None:
    """
    Run the Caldor benchmark against a model HDF5 output.
    """
    configure_logging(verbose, use_console=not no_console, log_path=log_file)
    logger.info("[CLI] run Caldor benchmark with model output: %s", model_output)
    caldor.run_caldor_benchmark(
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


if __name__ == "__main__":
    main()
