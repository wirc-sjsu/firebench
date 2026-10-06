"""
YAML setup of the automated weather-forecast benchmark (``firebench wx``).

A setup defines *where* and *when* (a bounding box and a UTC time window, either explicitly or
through a benchmark-case preset such as Caldor ``H012``), where observations come from (Synoptic
download, a saved Synoptic JSON, or an existing FireBench observation file), the QC options, the
forecast model and the scoring options. See ``docs/reference/wx_setup_file.md``.

Every problem found in a setup is collected and reported at once. Secrets never belong in a setup:
the Synoptic token is looked up with ``firebench keys`` (or a ``token_file`` path).
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

TOP_LEVEL_KEYS = {
    "name",
    "output_dir",
    "case",
    "domain",
    "window",
    "observations",
    "qc",
    "model",
    "benchmark",
}
SECRET_KEYS = {"token", "api_key", "apikey", "key", "password", "secret"}
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
CASE_ALIASES = {
    "001": "caldor",
    "1": "caldor",
    "fb001": "caldor",
    "2021_caldor": "caldor",
    "caldor": "caldor",
}
SUPPORTED_MODELS = ("HRRR",)


class SetupError(ValueError):
    """A setup file is invalid; the message lists every problem found."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        super().__init__(f"invalid setup {path}:\n" + "\n".join(f"  - {problem}" for problem in problems))
        self.problems = problems


@dataclass
class ObservationOptions:
    """Where observations come from and how they are fetched."""

    synoptic_json: Path | None = None
    h5: Path | None = None
    token_file: Path | None = None
    origin: str | None = None
    networks: tuple[str, ...] = ()
    context_hours: float = 24.0
    bbox_margin_deg: float = 0.0
    max_chunk_days: float = 7.0

    @property
    def source(self) -> str:
        """``h5``, ``synoptic_json`` or ``synoptic`` (download)."""
        if self.h5 is not None:
            return "h5"
        return "synoptic_json" if self.synoptic_json is not None else "synoptic"


@dataclass
class QCOptions:
    """Automatic weather QC (``conservative_auto`` policy of ``firebench wx-qc``)."""

    reviewer: str = "firebench wx (conservative_auto)"
    overrides: dict = field(default_factory=dict)
    require_window: bool = True


@dataclass
class ModelOptions:
    """Forecast model and cycles."""

    name: str = "HRRR"
    cycle_hours: tuple[int, ...] = (0, 6, 12, 18)
    horizon_hours: int = 48
    cycles: tuple[datetime, ...] | None = None
    download_workers: int = 8
    keep_grib: bool = True


@dataclass
class BenchmarkOptions:
    """Scoring options of the weather-forecast benchmark."""

    cadences: tuple[int, ...] = (1,)
    obs_tolerance_min: float = 10.0
    model_tolerance_s: float = 60.0
    min_coverage: float = 0.5
    lead_bins: tuple[tuple[int, int], ...] = ((1, 48),)
    informational_lead_bins: tuple[tuple[int, int], ...] = ((0, 0),)
    target: str = "ALL"
    full_name: bool = False


@dataclass
class CycleWindow:
    """One forecast cycle to score and its horizon (hours)."""

    cycle: datetime
    horizon_hours: int

    @property
    def label(self) -> str:
        """``YYYYmmddHH`` label used in file names."""
        return f"{self.cycle:%Y%m%d%H}"


@dataclass
class WxSetup:
    """A validated setup with every path resolved and every time in UTC."""

    path: Path
    name: str
    output_dir: Path
    bbox: tuple[float, float, float, float]
    start: datetime
    end: datetime
    preset: dict | None
    observations: ObservationOptions
    qc: QCOptions
    model: ModelOptions
    benchmark: BenchmarkOptions
    cycles: list[CycleWindow]
    notes: list[str] = field(default_factory=list)

    @property
    def fetch_window(self) -> tuple[datetime, datetime]:
        """Observation window: the evaluation window padded by the QC context."""
        pad = timedelta(hours=self.observations.context_hours)
        return self.start - pad, self.end + pad

    @property
    def fetch_bbox(self) -> tuple[float, float, float, float]:
        """Observation bounding box: the domain grown by ``bbox_margin_deg``."""
        margin = self.observations.bbox_margin_deg
        lon_min, lat_min, lon_max, lat_max = self.bbox
        return (lon_min - margin, lat_min - margin, lon_max + margin, lat_max + margin)

    def section_hash(self, *sections: str) -> str:
        """Stable hash of setup sections, used as a cache identity by the workflow stages."""
        values = {section: _jsonable(getattr(self, section)) for section in sections}
        return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def load_setup(path: str | Path) -> WxSetup:
    """Read, validate and resolve a setup file; raises ``SetupError`` listing every problem."""
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise SetupError(path, [f"cannot read the YAML file: {error}"]) from None
    if not isinstance(raw, dict):
        raise SetupError(path, ["the setup must be a YAML mapping"])
    return parse_setup(raw, path)


def parse_setup(raw: dict, path: Path) -> WxSetup:  # pylint: disable=too-many-locals
    """Validate an already-loaded setup mapping (``path`` anchors relative paths)."""
    problems: list[str] = []
    notes: list[str] = []
    base = Path(path).resolve().parent
    for key in sorted(set(raw) - TOP_LEVEL_KEYS):
        problems.append(
            f"unknown top-level key '{key}' (expected one of: {', '.join(sorted(TOP_LEVEL_KEYS))})"
        )

    name = str(raw.get("name") or Path(path).stem)
    if not NAME_PATTERN.match(name):
        problems.append(f"name '{name}' must use letters, digits, '.', '_' or '-'")
    output_dir = _resolve(base, raw.get("output_dir") or f"runs/{name}")

    preset = _parse_case(raw.get("case"), problems)
    bbox = _parse_bbox(raw.get("domain"), preset, problems, notes)
    start, end = _parse_window(raw.get("window"), preset, problems, notes)

    observations = _parse_observations(raw.get("observations") or {}, base, problems)
    qc = _parse_qc(raw.get("qc") or {}, problems)
    model = _parse_model(raw.get("model") or {}, problems)
    benchmark = _parse_benchmark(raw.get("benchmark") or {}, problems)
    if bbox is not None:
        _check_hrrr_domain(bbox, problems)

    cycles = []
    if start is not None and end is not None and model is not None:
        cycles = _resolve_cycles(model, start, end, problems)
    if problems:
        raise SetupError(path, problems)
    return WxSetup(
        path=Path(path),
        name=name,
        output_dir=output_dir,
        bbox=bbox,
        start=start,
        end=end,
        preset=preset,
        observations=observations,
        qc=qc,
        model=model,
        benchmark=benchmark,
        cycles=cycles,
        notes=notes,
    )


def parse_utc(value, label: str) -> datetime:
    """Parse a YAML/ISO datetime and return it in UTC; naive values and bare dates are rejected."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        raise ValueError(f"{label} is a date without a time; write e.g. {value.isoformat()}T00:00Z")
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise ValueError(f"{label} '{value}' is not an ISO 8601 datetime") from None
    else:
        raise ValueError(f"{label} must be an ISO 8601 datetime with a time zone, got {value!r}")
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise ValueError(
            f"{label} '{value}' has no time zone; add 'Z' for UTC or an offset such as '-07:00'"
        )
    return parsed.astimezone(timezone.utc)


def _parse_case(value, problems: list[str]) -> dict | None:
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or set(value) - {"id", "period"}
        or "id" not in value
        or "period" not in value
    ):
        problems.append(
            "case must be a mapping with 'id' (e.g. 2021_Caldor) and 'period' (e.g. H012 or P02)"
        )
        return None
    case = CASE_ALIASES.get(str(value["id"]).strip().lower())
    if case is None:
        problems.append(f"unknown case '{value['id']}' (available: 2021_Caldor)")
        return None
    # pylint: disable-next=import-outside-toplevel
    from firebench.benchmarks import c001_caldor_config as caldor

    period = str(value["period"]).strip().upper()
    match = re.fullmatch(r"(H|P)(\d+)", period)
    periods = caldor.HRRR_PERIODS if match and match.group(1) == "H" else caldor.CURATED_PERIODS
    key = (
        f"WH{int(match.group(2))}"
        if match and match.group(1) == "H"
        else f"W{int(match.group(2))}" if match else None
    )
    if key not in periods:
        problems.append(
            f"unknown Caldor period '{value['period']}' (available: H001-H{len(caldor.HRRR_PERIODS):03d} "
            f"for the HRRR cycle windows, P01-P{len(caldor.CURATED_PERIODS):02d} for the curated windows)"
        )
        return None
    start, end = periods[key]
    label = f"H{int(match.group(2)):03d}" if match.group(1) == "H" else f"P{int(match.group(2)):02d}"
    return {
        "case": "2021_Caldor",
        "period": label,
        "bbox": tuple(caldor.WX_DOMAIN_BBOX),
        "start": start.astimezone(timezone.utc),
        "end": end.astimezone(timezone.utc),
    }


def _parse_bbox(value, preset: dict | None, problems: list[str], notes: list[str]):
    if value is None:
        if preset is None:
            problems.append("set domain.bbox [lon_min, lat_min, lon_max, lat_max] or a case preset")
        return preset["bbox"] if preset else None
    bbox = value.get("bbox") if isinstance(value, dict) else None
    try:
        lon_min, lat_min, lon_max, lat_max = (float(item) for item in bbox)
    except (TypeError, ValueError):
        problems.append("domain.bbox must be [lon_min, lat_min, lon_max, lat_max] in degrees")
        return None
    if not (-180 <= lon_min < lon_max <= 180 and -90 <= lat_min < lat_max <= 90):
        problems.append(f"domain.bbox {list(bbox)} is not ordered [lon_min, lat_min, lon_max, lat_max]")
        return None
    if preset is not None:
        notes.append(f"domain.bbox overrides the {preset['case']} {preset['period']} preset bbox")
    return (lon_min, lat_min, lon_max, lat_max)


def _parse_window(value, preset: dict | None, problems: list[str], notes: list[str]):
    if value is None:
        if preset is None:
            problems.append("set window.start and window.end, or a case preset")
            return None, None
        return preset["start"], preset["end"]
    if not isinstance(value, dict) or set(value) != {"start", "end"}:
        problems.append("window must be a mapping with 'start' and 'end'")
        return None, None
    try:
        start = parse_utc(value["start"], "window.start")
        end = parse_utc(value["end"], "window.end")
    except ValueError as error:
        problems.append(str(error))
        return None, None
    if end <= start:
        problems.append("window.end must be after window.start")
        return None, None
    if preset is not None:
        notes.append(f"window overrides the {preset['case']} {preset['period']} preset window")
    return start, end


def _parse_observations(value: dict, base: Path, problems: list[str]) -> ObservationOptions:
    options = ObservationOptions()
    allowed = {
        "synoptic_json",
        "h5",
        "token_file",
        "origin",
        "networks",
        "context_hours",
        "bbox_margin_deg",
        "max_chunk_days",
    }
    if not _check_mapping(value, "observations", allowed, problems):
        return options
    if "synoptic_json" in value and "h5" in value:
        problems.append("observations.synoptic_json and observations.h5 are mutually exclusive")
    for key in ("synoptic_json", "h5", "token_file"):
        if value.get(key) is not None:
            setattr(options, key, _resolve(base, value[key]))
    for key in ("synoptic_json", "h5"):
        path = getattr(options, key)
        if path is not None and not path.is_file():
            problems.append(f"observations.{key} does not exist: {path}")
    if "origin" in value:
        from firebench.acquisition.keys import KeyConfigError, normalize_origin

        try:
            options.origin = normalize_origin(value["origin"])
        except KeyConfigError as error:
            problems.append(f"observations.origin: {error}")
    networks = value.get("networks") or ()
    options.networks = tuple(str(item) for item in (networks if isinstance(networks, list) else [networks]))
    for key in ("context_hours", "bbox_margin_deg", "max_chunk_days"):
        if key in value:
            setattr(options, key, _number(value[key], f"observations.{key}", problems, minimum=0))
    if options.max_chunk_days is not None and options.max_chunk_days <= 0:
        problems.append("observations.max_chunk_days must be positive")
    return options


def _parse_qc(value: dict, problems: list[str]) -> QCOptions:
    options = QCOptions()
    if not _check_mapping(value, "qc", {"reviewer", "overrides", "require_window"}, problems):
        return options
    if "reviewer" in value:
        options.reviewer = str(value["reviewer"]).strip()
        if not options.reviewer:
            problems.append("qc.reviewer must not be empty")
    overrides = value.get("overrides") or {}
    if not isinstance(overrides, dict):
        problems.append("qc.overrides must be a mapping of QC policy tables")
    elif "mode" in overrides:
        problems.append("qc.overrides.mode is fixed to 'conservative_auto' by the automated workflow")
    else:
        options.overrides = overrides
    if "require_window" in value:
        options.require_window = bool(value["require_window"])
    return options


def _parse_model(value: dict, problems: list[str]) -> ModelOptions:
    options = ModelOptions()
    allowed = {"name", "cycle_hours", "horizon_hours", "cycles", "download_workers", "keep_grib"}
    if not _check_mapping(value, "model", allowed, problems):
        return options
    options.name = str(value.get("name", options.name)).upper()
    if options.name not in SUPPORTED_MODELS:
        problems.append(
            f"model.name '{options.name}' is not supported (available: {', '.join(SUPPORTED_MODELS)})"
        )
    if "cycle_hours" in value:
        hours = value["cycle_hours"]
        if not isinstance(hours, list) or not all(
            isinstance(hour, int) and 0 <= hour <= 23 for hour in hours
        ):
            problems.append("model.cycle_hours must be a list of UTC hours (0-23)")
        else:
            options.cycle_hours = tuple(sorted(set(hours)))
    if "horizon_hours" in value:
        options.horizon_hours = int(
            _number(value["horizon_hours"], "model.horizon_hours", problems, minimum=1) or 48
        )
    if value.get("cycles") is not None:
        cycles = []
        for index, item in enumerate(
            value["cycles"] if isinstance(value["cycles"], list) else [value["cycles"]]
        ):
            try:
                cycles.append(parse_utc(item, f"model.cycles[{index}]"))
            except ValueError as error:
                problems.append(str(error))
        options.cycles = tuple(cycles)
    if "download_workers" in value:
        options.download_workers = int(
            _number(value["download_workers"], "model.download_workers", problems, minimum=1) or 8
        )
    if "keep_grib" in value:
        options.keep_grib = bool(value["keep_grib"])
    return options


def _parse_benchmark(value: dict, problems: list[str]) -> BenchmarkOptions:
    options = BenchmarkOptions()
    allowed = {
        "cadences",
        "obs_tolerance_min",
        "model_tolerance_s",
        "min_coverage",
        "lead_bins",
        "informational_lead_bins",
        "target",
        "full_name",
    }
    if not _check_mapping(value, "benchmark", allowed, problems):
        return options
    if "cadences" in value:
        options.cadences = _parse_cadences(value["cadences"], problems) or options.cadences
    for key, minimum in (("obs_tolerance_min", 0), ("model_tolerance_s", 0), ("min_coverage", 0)):
        if key in value:
            setattr(options, key, _number(value[key], f"benchmark.{key}", problems, minimum=minimum))
    if not 0 <= (options.min_coverage or 0) <= 1:
        problems.append("benchmark.min_coverage must be between 0 and 1")
    if options.obs_tolerance_min is not None and options.obs_tolerance_min * 60 >= 1800 * min(
        options.cadences
    ):
        problems.append(
            "benchmark.obs_tolerance_min must be below half the shortest cadence (30 min for hourly)"
        )
    for key in ("lead_bins", "informational_lead_bins"):
        if key in value:
            bins = _parse_bins(value[key], f"benchmark.{key}", problems)
            if bins is not None:
                setattr(options, key, bins)
    if "target" in value:
        options.target = str(value["target"]).upper()
    if "full_name" in value:
        options.full_name = bool(value["full_name"])
    return options


def _parse_cadences(value, problems: list[str]) -> tuple[int, ...] | None:
    valid = (
        isinstance(value, list)
        and value
        and all(isinstance(item, int) and item in (1, 3) for item in value)
    )
    if not valid:
        problems.append("benchmark.cadences must be a list of cadences in hours, 1 and/or 3")
        return None
    return tuple(sorted(set(value)))


def _parse_bins(value, label: str, problems: list[str]):
    if value in (None, []):
        return ()
    try:
        bins = tuple((int(start), int(end)) for start, end in value)
    except (TypeError, ValueError):
        problems.append(f"{label} must be a list of [start, end] lead hours, e.g. [[1, 48]]")
        return None
    for start, end in bins:
        if not 0 <= start <= end:
            problems.append(f"{label} bin [{start}, {end}] must satisfy 0 <= start <= end")
    return bins


def _resolve_cycles(
    model: ModelOptions, start: datetime, end: datetime, problems: list[str]
) -> list[CycleWindow]:
    # pylint: disable-next=import-outside-toplevel
    from firebench.acquisition.hrrr.forecast import max_forecast_hour

    if model.cycles:
        candidates = sorted(model.cycles)
    else:
        candidates = []
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= end:
            candidates.extend(day + timedelta(hours=hour) for hour in model.cycle_hours)
            day += timedelta(days=1)
    cycles = []
    for cycle in candidates:
        if cycle.minute or cycle.second:
            problems.append(f"model cycle {cycle.isoformat()} is not at the top of an hour")
            continue
        horizon = min(model.horizon_hours, max_forecast_hour(cycle))
        if model.cycles or (start <= cycle and cycle + timedelta(hours=horizon) <= end):
            cycles.append(CycleWindow(cycle, horizon))
    if not cycles:
        problems.append(
            f"no {'/'.join(f'{hour:02d}' for hour in model.cycle_hours)}Z cycle with a full "
            f"{model.horizon_hours} h forecast fits in {start.isoformat()} .. {end.isoformat()}; widen the "
            "window, shorten model.horizon_hours, or list model.cycles explicitly"
        )
    return cycles


def _check_hrrr_domain(bbox, problems: list[str]) -> None:
    # pylint: disable-next=import-outside-toplevel
    from firebench.acquisition.hrrr.grid import HRRRGrid

    lon_min, lat_min, lon_max, lat_max = bbox
    grid = HRRRGrid()
    i, j = grid.ij_arrays_from_latlon(
        [lat_min, lat_min, lat_max, lat_max], [lon_min, lon_max, lon_min, lon_max]
    )
    if not all(grid.contains(i, j)):
        problems.append(f"domain.bbox {list(bbox)} is not fully inside the HRRR CONUS grid")


def _check_mapping(value, label: str, allowed: set[str], problems: list[str]) -> bool:
    if not isinstance(value, dict):
        problems.append(f"{label} must be a mapping")
        return False
    secrets = sorted(key for key in value if str(key).lower() in SECRET_KEYS)
    for key in secrets:
        problems.append(
            f"{label}.{key}: secrets do not belong in a setup file (it gets shared); store the token with "
            "'firebench keys set synoptic' or point to a file with observations.token_file"
        )
    for key in sorted(set(value) - allowed - set(secrets)):
        problems.append(f"unknown key {label}.{key} (expected one of: {', '.join(sorted(allowed))})")
    return True


def _number(value, label: str, problems: list[str], minimum: float | None = None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        problems.append(f"{label} must be a number")
        return None
    if minimum is not None and number < minimum:
        problems.append(f"{label} must be >= {minimum:g}")
    return number


def _resolve(base: Path, value) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _jsonable(value):
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


def setup_template(
    name: str,
    *,
    case: str | None = None,
    period: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    start: str | None = None,
    end: str | None = None,
    synoptic_json: str | None = None,
) -> str:
    """Commented setup file for ``firebench wx init``."""
    if case or period:
        where = (
            f"case: {{id: {case or '2021_Caldor'}, period: {period or 'H012'}}}   # preset: bbox + window\n"
        )
        where += "# domain: {bbox: [lon_min, lat_min, lon_max, lat_max]}   # overrides the preset bbox\n"
        where += (
            "# window: {start: 2021-08-20T00:00Z, end: 2021-08-22T00:00Z}   # overrides the preset window\n"
        )
    else:
        box = ", ".join(f"{value:g}" for value in (bbox or (-120.8, 38.6, -120.4, 38.9)))
        where = f"domain: {{bbox: [{box}]}}   # lon_min, lat_min, lon_max, lat_max (degrees)\n"
        window = f"{{start: {start or '2026-09-25T00:00Z'}, end: {end or '2026-09-27T00:00Z'}}}"
        where += f"window: {window}   # UTC\n"
    observations = (
        f"  synoptic_json: {synoptic_json}   # saved Synoptic payload (no download, no token)\n"
        if synoptic_json
        else "  # synoptic_json: path/to/saved.json  # use a saved payload instead of downloading\n"
    )
    return f"""# FireBench automated weather-forecast benchmark setup (firebench wx)
# Reference: https://firebench.readthedocs.io/en/latest/reference/wx_setup_file.html
name: {name}
output_dir: runs/{name}                  # workspace (relative to this file)
{where}
observations:
{observations}  # h5: path/to/obs.h5                   # or an existing FireBench observation file
  # token_file: ~/secrets/synoptic.txt   # default: firebench keys set synoptic / SYNOPTIC_TOKEN
  # origin: https://your-allowed-domain.example  # override token-linked origins
  # networks: [RAWS]                     # optional Synoptic network filter
  context_hours: 24                      # QC context before and after the window
  bbox_margin_deg: 0.0                   # grow the station search box

qc:
  reviewer: firebench wx (conservative_auto)
  overrides: {{}}                          # QC policy tables, e.g. {{bounds: {{wind_speed: [0, 50, m/s]}}}}

model:
  name: HRRR
  cycle_hours: [0, 6, 12, 18]            # 48 h cycles (HRRR v4)
  horizon_hours: 48
  # cycles: [2021-08-20T00:00Z]          # explicit cycles instead of every cycle in the window
  download_workers: 8
  keep_grib: true                        # false deletes GRIB files once adapted

benchmark:
  cadences: [1]                          # hourly; add 3 for a 3-hourly tier
  obs_tolerance_min: 10                  # nearest finite observation within +/-10 min of each hour
  model_tolerance_s: 60
  min_coverage: 0.5                      # minimum share of hourly marks observed per station
  lead_bins: [[1, 48]]                   # scored lead-time bins (hours)
  informational_lead_bins: [[0, 0]]      # F00 is the analysis: shown with weight 0
  target: ALL
"""
