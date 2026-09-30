"""
Local download cache and user configuration directories.

Cache directory resolution: ``FIREBENCH_CACHE_DIR`` environment variable, else the platform cache
location (``$XDG_CACHE_HOME/firebench`` or ``~/.cache/firebench`` on Linux). Unlike spear, this never
prompts: an interactive ``input()`` would hang or fail in CI and cron jobs.

Configuration directory (API keys): ``FIREBENCH_CONFIG_DIR``, else ``$XDG_CONFIG_HOME/firebench`` or
``~/.config/firebench`` on Linux.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

CACHE_DIR_ENV = "FIREBENCH_CACHE_DIR"
CONFIG_DIR_ENV = "FIREBENCH_CONFIG_DIR"


def config_dir() -> Path:
    """Return the FireBench user configuration directory (not created)."""
    env = os.environ.get(CONFIG_DIR_ENV)
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "firebench"


def default_cache_dir() -> Path:
    """Return the platform cache location used when ``FIREBENCH_CACHE_DIR`` is not set."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "firebench" / "cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "firebench"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "firebench"


def cache_dir_source() -> str:
    """Describe where the cache directory comes from, for ``firebench cache info``."""
    return f"environment variable {CACHE_DIR_ENV}" if os.environ.get(CACHE_DIR_ENV) else "platform default"


def get_cache_dir(create: bool = True) -> Path:
    """Return the FireBench download cache directory."""
    env = os.environ.get(CACHE_DIR_ENV)
    cache_dir = Path(env).expanduser().resolve() if env else default_cache_dir()
    if create:
        cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def cache_subdir(*parts: str, root: Path | None = None) -> Path:
    """Return (and create) a subdirectory of the cache, e.g. ``cache_subdir("hrrr", "20210820")``."""
    path = (Path(root) if root is not None else get_cache_dir()).joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a unique temporary file and ``os.replace``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, obj) -> None:
    """Write ``obj`` as indented JSON to ``path`` atomically."""
    atomic_write_bytes(path, (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode())


def directory_usage(path: Path) -> tuple[int, int]:
    """Return ``(n_files, n_bytes)`` below ``path``; ``(0, 0)`` when it does not exist."""
    n_files = 0
    n_bytes = 0
    for file_path in Path(path).rglob("*"):
        if file_path.is_file():
            n_files += 1
            n_bytes += file_path.stat().st_size
    return n_files, n_bytes


def format_bytes(n_bytes: int) -> str:
    """Format a byte count for humans, e.g. ``1.2 GB``."""
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(n_bytes)
    index = 0
    while value >= 1000 and index < len(units) - 1:
        value /= 1000
        index += 1
    return f"{n_bytes} B" if index == 0 else f"{value:.1f} {units[index]}"
