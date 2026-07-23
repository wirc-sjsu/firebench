"""Atomic file-writing helpers shared by weather-station QC exports."""

import os
import tempfile
from pathlib import Path


def temporary_sibling(destination):
    """Create and return an empty temporary sibling of ``destination``."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    os.close(file_descriptor)
    return Path(temporary_name)


def atomic_write_text(destination, text):
    """Atomically replace ``destination`` with UTF-8 ``text``."""
    destination = Path(destination)
    temporary_path = temporary_sibling(destination)
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
