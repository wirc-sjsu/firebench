"""
API key manager for data providers.

A key is resolved through a fixed ladder; the first hit wins:

1. an explicit key file named by the caller (for example ``token_file`` in a workflow setup). It is
   a hard error if that file is set but missing, so a typo never silently falls through;
2. the service environment variable (``SYNOPTIC_TOKEN`` for Synoptic);
3. the stored credential file ``<config_dir>/credentials/<service>``, written by
   ``firebench keys set``.

A missing key is data, not an exception: ``resolve_key`` returns a resolution that lists every
place searched, so callers can print a complete blocker report. Key values are never printed; only
their :func:`fingerprint` is shown.
"""

import hashlib
import json
import urllib.parse
import logging
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .cache import config_dir

logger = logging.getLogger(__name__)

SERVICE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
QUERY_SECRET_PATTERN = re.compile(r"(?i)\b(token|apikey|api_key|key|map_key)=([^&\s\"']+)")


@dataclass(frozen=True)
class ServiceInfo:
    """A data provider that may need an API key."""

    name: str
    description: str
    env_var: str | None
    signup_url: str | None = None
    anonymous: bool = False


SERVICES = {
    "synoptic": ServiceInfo(
        name="synoptic",
        description="Synoptic Data weather API token (station observations)",
        env_var="SYNOPTIC_TOKEN",
        signup_url="https://customer.synopticdata.com/",
    ),
    "hrrr": ServiceInfo(
        name="hrrr",
        description="NOAA HRRR forecasts on AWS Open Data (anonymous, no key needed)",
        env_var=None,
        anonymous=True,
    ),
}


class KeyConfigError(ValueError):
    """Invalid service name or unusable explicit key file."""


@dataclass(frozen=True)
class KeyResolution:
    """Outcome of a key lookup; ``value`` is ``None`` when no key was found."""

    service: str
    value: str | None = field(repr=False)
    source: str | None
    searched: tuple[str, ...]
    anonymous: bool = False

    @property
    def found(self) -> bool:
        """Whether the service can be used: a key was found or none is needed."""
        return self.value is not None or self.anonymous


def service_info(service: str) -> ServiceInfo:
    """Return the known service description, or a generic one for any valid service name."""
    name = str(service).strip().lower()
    if not SERVICE_NAME_PATTERN.match(name):
        raise KeyConfigError(
            f"invalid service name {service!r}: use lower-case letters, digits, '-' or '_' "
            "(e.g. 'synoptic')"
        )
    if name in SERVICES:
        return SERVICES[name]
    return ServiceInfo(
        name=name,
        description=f"API key for '{name}'",
        env_var=f"{name.upper().replace('-', '_')}_KEY",
    )


def credentials_dir() -> Path:
    """Directory holding keys stored by ``firebench keys set``."""
    return config_dir() / "credentials"


def key_path(service: str) -> Path:
    """Path of the key stored for ``service`` by ``firebench keys set``."""
    return credentials_dir() / service_info(service).name


def resolve_key(service: str, explicit_file: str | Path | None = None) -> KeyResolution:
    """Resolve the key of ``service`` through the explicit file / env var / stored file ladder."""
    info = service_info(service)
    searched: list[str] = []

    if explicit_file is not None:
        path = Path(explicit_file).expanduser()
        searched.append(f"key file {path}")
        if not path.is_file():
            raise KeyConfigError(f"key file for '{info.name}' does not exist: {path}")
        value = _read_key_file(path)
        if value is None:
            raise KeyConfigError(f"key file for '{info.name}' is empty: {path}")
        return KeyResolution(info.name, value, f"key file {path}", tuple(searched))

    if info.env_var:
        searched.append(f"environment variable {info.env_var}")
        value = os.environ.get(info.env_var, "").strip()
        if value:
            return KeyResolution(info.name, value, f"environment variable {info.env_var}", tuple(searched))

    path = key_path(info.name)
    searched.append(f"stored key {path}")
    if path.is_file():
        _warn_if_readable_by_others(path)
        value = _read_key_file(path)
        if value is not None:
            return KeyResolution(info.name, value, f"stored key {path}", tuple(searched))

    if info.anonymous:
        return KeyResolution(info.name, None, "anonymous access", tuple(searched), anonymous=True)
    return KeyResolution(info.name, None, None, tuple(searched))


def missing_key_message(resolution: KeyResolution) -> str:
    """Explain a missing key: every place searched, and how to add one."""
    info = service_info(resolution.service)
    lines = [f"No API key found for '{info.name}' ({info.description}). Searched:"]
    lines.extend(f"  - {place}" for place in resolution.searched)
    lines.append(f"Add one with: firebench keys set {info.name}")
    if info.signup_url:
        lines.append(f"Get a key at: {info.signup_url}")
    return "\n".join(lines)


def set_key(service: str, value: str) -> Path:
    """Store ``value`` as the key of ``service`` (file mode 0600 in a 0700 directory)."""
    info = service_info(service)
    value = str(value).strip()
    if not value:
        raise KeyConfigError("refusing to store an empty key")
    if "\n" in value or "\r" in value:
        raise KeyConfigError("a key must be a single line")

    old_value = _read_key_file(key_path(service)) if key_path(service).is_file() else None
    directory = credentials_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        os.chmod(directory, 0o700)
    path = directory / info.name
    fd, tmp_name = tempfile.mkstemp(prefix=f".{info.name}.", suffix=".part", dir=directory)
    try:
        if sys.platform != "win32":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(value + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    if old_value != value and info.name == "synoptic":
        origins_path().unlink(missing_ok=True)
    logger.info("[keys] stored key for %s in %s (%s)", info.name, path, fingerprint(value))
    return path


def remove_key(service: str) -> bool:
    """Delete the stored key of ``service``. Returns whether a file was removed."""
    path = key_path(service)
    if not path.is_file():
        return False
    path.unlink()
    if service_info(service).name == "synoptic":
        origins_path().unlink(missing_ok=True)
    return True


def list_keys() -> list[KeyResolution]:
    """Resolve every known service plus every service that has a stored key."""
    names = list(SERVICES)
    directory = credentials_dir()
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if path.is_file() and SERVICE_NAME_PATTERN.match(path.name) and path.name not in names:
                names.append(path.name)
    return [resolve_key(name) for name in names]


def fingerprint(value: str) -> str:
    """Identify a key without revealing it: its length and a short SHA-256 prefix."""
    digest = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"{len(value)} chars, sha256:{digest}"


def redact(text: str, secrets=()) -> str:
    """Remove secrets from ``text``: the given values and any ``token=``/``apikey=`` query value."""
    redacted = str(text)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(str(secret), "***")
    return QUERY_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=***", redacted)


def _read_key_file(path: Path) -> str | None:
    for line in path.read_text().splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value
    return None


def _warn_if_readable_by_others(path: Path) -> None:
    if sys.platform == "win32":
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        logger.warning(
            "[keys] %s is readable by other users (mode %o); run: chmod 600 %s",
            path,
            mode,
            path,
        )


def normalize_origin(value: str) -> str:
    """Validate a concrete HTTP origin and normalize a trailing slash."""
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise KeyConfigError("an HTTP origin must be a nonempty URL without whitespace")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
        valid = (
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
            and "*" not in value
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
            and "\\" not in value
            and "?" not in value
            and "#" not in value
            and not parsed.netloc.endswith(":")
        )
    except ValueError:
        valid = False
    if not valid:
        raise KeyConfigError(
            "an HTTP origin must be http(s)://hostname[:port], without credentials or paths"
        )
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme}://{host}" + (f":{port}" if port is not None else "")


def normalize_origins(values) -> tuple[str, ...]:
    """Validate and deduplicate origins while preserving their order."""
    if isinstance(values, str):
        values = [values]
    return tuple(dict.fromkeys(normalize_origin(value) for value in values))


def origins_path() -> Path:
    """Private metadata for the stored Synoptic token."""
    return credentials_dir() / "synoptic.origins.json"


def stored_origins(token: str) -> tuple[str, ...]:
    """Return saved origins only when they belong to this exact token."""
    path = origins_path()
    if not path.is_file():
        return ()
    try:
        _warn_if_readable_by_others(path)
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("unsupported metadata version")
        if not isinstance(data.get("token_sha256"), str) or not isinstance(data.get("origins"), list):
            raise ValueError("invalid metadata fields")
        origins = normalize_origins(data["origins"])
        if data["token_sha256"] != hashlib.sha256(token.encode()).hexdigest():
            return ()
        return origins
    except (OSError, ValueError, TypeError) as error:
        raise KeyConfigError(
            f"invalid Synoptic origin metadata in {path}; remove this sidecar and re-add origins"
        ) from error


def set_origins(values) -> tuple[str, ...]:
    """Replace origins associated with the stored Synoptic token."""
    path = key_path("synoptic")
    token = _read_key_file(path) if path.is_file() else None
    if not token:
        raise KeyConfigError("no stored Synoptic token; run: firebench keys set synoptic")
    origins = normalize_origins(values)
    data = {"version": 1, "token_sha256": hashlib.sha256(token.encode()).hexdigest(), "origins": origins}
    directory = credentials_dir()
    if sys.platform != "win32":
        os.chmod(directory, 0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=".synoptic.origins.", suffix=".part", dir=directory)
    try:
        if sys.platform != "win32":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
            stream.write("\n")
        os.replace(tmp_name, origins_path())
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return origins


def resolve_origins(token: str, explicit=None) -> tuple[tuple[str, ...], str]:
    """Resolve explicit, environment, then token-linked saved origins."""
    if explicit is not None:
        return normalize_origins(explicit), "explicit setting"
    if "SYNOPTIC_ORIGIN" in os.environ:
        return normalize_origins([os.environ["SYNOPTIC_ORIGIN"]]), "SYNOPTIC_ORIGIN"
    origins = stored_origins(token)
    return origins, "saved token origins" if origins else "no Origin header"
