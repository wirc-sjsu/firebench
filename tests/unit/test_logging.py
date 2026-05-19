import logging

import pytest

import firebench.tools as ft
from firebench.tools.logging_config import configure_logging, create_file_handler, verbosity_to_level


@pytest.fixture(autouse=True)
def reset_firebench_logger():
    configure_logging(2, use_console=False)
    yield
    configure_logging(2, use_console=False)


@pytest.mark.parametrize(
    "verbose, level",
    [
        (0, logging.CRITICAL),
        (1, logging.ERROR),
        (2, logging.WARNING),
        (3, logging.INFO),
        (4, logging.DEBUG),
        (10, logging.DEBUG),
    ],
)
def test_verbosity_to_level(verbose, level):
    assert verbosity_to_level(verbose) == level


def test_configure_logging_resets_handlers(tmp_path):
    first_log = tmp_path / "first.log"
    second_log = tmp_path / "second.log"

    app_logger = configure_logging(4, use_console=True, log_path=first_log)
    assert app_logger.level == logging.DEBUG
    assert app_logger.propagate is True
    assert any(isinstance(handler, logging.StreamHandler) for handler in app_logger.handlers)
    assert any(
        isinstance(handler, logging.FileHandler) and handler.baseFilename == str(first_log.resolve())
        for handler in app_logger.handlers
    )

    app_logger = configure_logging(3, use_console=False, log_path=second_log)
    file_handlers = [handler for handler in app_logger.handlers if isinstance(handler, logging.FileHandler)]

    assert app_logger.level == logging.INFO
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(second_log.resolve())


def test_create_file_handler_overwrites_and_avoids_duplicates(tmp_path):
    log_path = tmp_path / "test_log.log"
    log_path.write_text("old content")

    create_file_handler(log_path)
    assert log_path.read_text() == ""

    ft.logger.warning("Test warning message")
    for handler in ft.logger.handlers:
        handler.flush()
    assert "Test warning message" in log_path.read_text()

    create_file_handler(log_path)
    file_handlers = [
        handler
        for handler in ft.logger.handlers
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == str(log_path.resolve())
    ]

    assert len(file_handlers) == 1
    assert log_path.read_text() == ""


@pytest.mark.parametrize(
    "level, expected_messages, unexpected_messages",
    [
        (logging.DEBUG, ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], []),
        (logging.INFO, ["INFO", "WARNING", "ERROR", "CRITICAL"], ["DEBUG"]),
        (logging.WARNING, ["WARNING", "ERROR", "CRITICAL"], ["DEBUG", "INFO"]),
        (logging.ERROR, ["ERROR", "CRITICAL"], ["DEBUG", "INFO", "WARNING"]),
        (logging.CRITICAL, ["CRITICAL"], ["DEBUG", "INFO", "WARNING", "ERROR"]),
    ],
)
def test_set_logging_level(tmp_path, level, expected_messages, unexpected_messages):
    log_path = tmp_path / "levels.log"
    create_file_handler(log_path, logging.DEBUG)
    ft.set_logging_level(level)

    ft.logger.debug("DEBUG")
    ft.logger.info("INFO")
    ft.logger.warning("WARNING")
    ft.logger.error("ERROR")
    ft.logger.critical("CRITICAL")
    for handler in ft.logger.handlers:
        handler.flush()

    log_content = log_path.read_text()
    for message in expected_messages:
        assert message in log_content
    for message in unexpected_messages:
        assert message not in log_content
