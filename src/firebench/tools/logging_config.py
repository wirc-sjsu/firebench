import logging
import os

# Create a custom logger
logger = logging.getLogger("firebench")

# Create a stream handler by default
c_handler = logging.StreamHandler()

# Set logging level for the stream handler
c_handler.setLevel(logging.WARNING)

# Create formatter and add it to the stream handler
c_format = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
c_handler.setFormatter(c_format)

# Add the stream handler to the logger
logger.addHandler(c_handler)

# Set default logging level for the logger
logger.setLevel(logging.WARNING)

# Prevent propagation to the root logger
logger.propagate = True


def create_file_handler(log_path: str, level=logging.WARNING):
    """
    Create a file handler for logging.

    Parameters
    ----------
    log_path : str
        The path to the log file.
    """  # pylint: disable=line-too-long
    if os.path.isfile(log_path):
        os.remove(log_path)
    f_handler = logging.FileHandler(log_path)
    f_handler.setLevel(level)
    f_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    f_handler.setFormatter(f_format)

    # Add the file handler to the logger
    logger.addHandler(f_handler)


def set_logging_level(level):
    """
    Set the logging level for both the logger and all its handlers.

    Parameters
    ----------
    level : int
        The logging level to set (e.g., logging.DEBUG, logging.INFO).
    """  # pylint: disable=line-too-long
    # Set the logger's level
    logger.setLevel(level)

    # Set the level for all handlers associated with the logger
    for handler in logger.handlers:
        handler.setLevel(level)
