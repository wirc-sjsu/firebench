import logging
from pathlib import Path

LOG_NAME = "firebench"

logger = logging.getLogger(LOG_NAME)
logger.addHandler(logging.NullHandler())


def verbosity_to_level(v: int) -> int:
    if v <= 0:
        return logging.CRITICAL
    if v == 1:
        return logging.ERROR
    if v == 2:
        return logging.WARNING
    if v == 3:
        return logging.INFO
    return logging.DEBUG


def configure_logging(
    verbose: int,
    use_console: bool = True,
    log_path: str | Path | None = None,
    file_level: int | None = None,
    logname: str = LOG_NAME,
) -> logging.Logger:
    app_logger = logging.getLogger(logname)
    level = verbosity_to_level(verbose)
    handler_levels = [level] if use_console else []
    if log_path:
        handler_levels.append(level if file_level is None else file_level)

    app_logger.setLevel(min(handler_levels) if handler_levels else level)
    app_logger.propagate = True

    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)
        handler.close()

    if use_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        app_logger.addHandler(console_handler)

    if log_path:
        add_file_handler(log_path, level=file_level, logname=logname)

    if not app_logger.handlers:
        app_logger.addHandler(logging.NullHandler())

    return app_logger


def get_logger(verbose: int, use_console: bool = True, logname: str = LOG_NAME) -> logging.Logger:
    return configure_logging(verbose, use_console=use_console, logname=logname)


def add_file_handler(
    log_path: str | Path,
    level: int | None = None,
    logname: str = LOG_NAME,
) -> None:
    app_logger = logging.getLogger(logname)
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_log_path = str(log_path.resolve())

    for handler in app_logger.handlers[:]:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == resolved_log_path:
            app_logger.removeHandler(handler)
            handler.close()

    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setLevel(app_logger.level if level is None else level)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    app_logger.addHandler(file_handler)


def create_file_handler(log_path: str | Path, level: int = logging.WARNING) -> None:
    """
    Compatibility wrapper for older FireBench callers.
    """
    app_logger = logging.getLogger(LOG_NAME)
    app_logger.setLevel(min(app_logger.level, level) if app_logger.level else level)
    app_logger.propagate = True

    for handler in app_logger.handlers[:]:
        if isinstance(handler, logging.NullHandler):
            app_logger.removeHandler(handler)
            handler.close()

    add_file_handler(log_path, level=level)


def set_logging_level(level: int) -> None:
    """
    Compatibility wrapper to set the FireBench logger and handler levels.
    """
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)
