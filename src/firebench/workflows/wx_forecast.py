"""
Automated weather-forecast benchmark workflow (``firebench wx run``).

Stages, each recorded in ``<output_dir>/wx_workflow.json`` with the identity of its inputs:

1. ``obs``: Synoptic observations (download, or a saved JSON clipped to the window and domain),
   payload contract, automatic ``conservative_auto`` QC and finalization into ``obs.h5``. A
   pre-built FireBench observation file can be used instead.
2. ``hrrr``: HRRR surface forecasts of every cycle, downloaded into the shared cache. Downloads start
   first and run in parallel with the observation stage.
3. ``adapt``: the embedded HRRR adapter samples each complete cycle at the QC'd stations.
4. ``score``: the weather-forecast benchmark scores each cycle and writes the JSON, the score card
   and ``summary.md``.

A stage whose input identity is unchanged and whose outputs exist is skipped, so a second run
downloads nothing and recomputes nothing. ``force`` re-runs the selected stages.
"""

import hashlib
import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from firebench import __version__ as fb_version
from firebench.acquisition import keys as fb_keys
from firebench.acquisition.cache import atomic_write_json, format_bytes
from firebench.acquisition.hrrr import forecast as hrrr_forecast

from .wx_setup import CycleWindow, WxSetup

logger = logging.getLogger(__name__)

STAGES = ("obs", "hrrr", "adapt", "score")
MANIFEST_NAME = "wx_workflow.json"
DATA_TIER = "provisional"
HRRR_FILE_MB = {0: 11.6, 1: 9.4}  # measured subset sizes (f00 carries the terrain field)


class WorkflowError(RuntimeError):
    """A workflow stage cannot proceed; the message says what to fix."""


@dataclass
class StageRecord:
    """Outcome of one stage for the run summary."""

    name: str
    status: str
    detail: str = ""


@dataclass
class WorkflowResult:
    """What a run did and produced."""

    records: list[StageRecord] = field(default_factory=list)
    obs_h5: Path | None = None
    model_files: dict[str, Path] = field(default_factory=dict)
    results: dict[str, dict] = field(default_factory=dict)
    dropped_cycles: list[dict] = field(default_factory=list)
    summary_path: Path | None = None


class WxForecastWorkflow:
    """Run the stages of one setup inside its output directory."""

    def __init__(
        self,
        setup: WxSetup,
        *,
        force: bool = False,
        cache_root: Path | None = None,
        synoptic_opener: Callable | None = None,
        read_fields: Callable | None = None,
    ) -> None:
        self.setup = setup
        self.force = force
        self.forced_stages: tuple[str, ...] = STAGES if force else ()
        self.cache_root = cache_root
        self.synoptic_opener = synoptic_opener
        self.read_fields = read_fields
        self.out = setup.output_dir
        self.manifest_path = self.out / MANIFEST_NAME
        self.manifest = self._load_manifest()

    # ---------------------------------------------------------------- paths
    @property
    def obs_dir(self) -> Path:
        """Directory of the observation stage outputs."""
        return self.out / "observations"

    def model_path(self, cycle: CycleWindow, model_name: str = "HRRR") -> Path:
        """Model file of one cycle."""
        return self.out / "models" / f"{model_name.lower()}_{cycle.label}.h5"

    def score_paths(self, cycle: CycleWindow, model_name: str = "HRRR") -> tuple[Path, Path]:
        """Result JSON and score-card PDF of one cycle."""
        stem = f"{_slug(model_name)}_{cycle.label}"
        return self.out / "scores" / f"{stem}_rslt.json", self.out / "scores" / f"{stem}_scorecard.pdf"

    # ------------------------------------------------------------------ run
    def run(self, steps=STAGES) -> WorkflowResult:
        """Run the selected stages in order and return what was done."""
        steps = tuple(step for step in STAGES if step in steps)
        # --force re-runs the selected stages only; the others stay reusable
        self.forced_stages = steps if self.force else ()
        result = WorkflowResult()
        self.out.mkdir(parents=True, exist_ok=True)

        obs_identity = self._obs_identity()
        obs_current = self._is_current("obs", obs_identity)
        obs_sha = self._stage("obs")["outputs"]["obs_sha256"] if obs_current else None
        pending_cycles = self._cycles_to_download(steps, obs_sha)

        with ThreadPoolExecutor(
            max_workers=self.setup.model.download_workers, thread_name_prefix="hrrr"
        ) as executor:
            pending = {
                cycle.label: hrrr_forecast.submit_cycle(
                    cycle.cycle, cycle.horizon_hours, executor, self.cache_root
                )
                for cycle in pending_cycles
            }
            if pending:
                result.records.append(
                    StageRecord("hrrr", "started", f"{len(pending)} cycle(s) downloading in the background")
                )

            if "obs" in steps or any(step in steps for step in ("adapt", "score")):
                result.obs_h5 = self._run_obs(obs_identity, obs_current, "obs" in steps, result)
            if "adapt" in steps or "hrrr" in steps:
                self._run_hrrr_and_adapt(pending, executor, "adapt" in steps, result)

        if "score" in steps:
            self._run_score(result)
            result.summary_path = self._write_summary(result)
        return result

    def score_model(self, model_output: Path, cycle_label: str, name: str) -> dict:
        """Score another model file of one cycle against the workflow observations."""
        cycle = next((item for item in self.setup.cycles if item.label == cycle_label), None)
        if cycle is None:
            available = ", ".join(item.cycle.isoformat() for item in self.setup.cycles)
            raise WorkflowError(
                f"cycle {cycle_label} is not a cycle of this setup (available: {available})"
            )
        obs_record = self._stage("obs")
        if not obs_record or not Path(obs_record["outputs"]["obs_h5"]).is_file():
            raise WorkflowError("run the observation stage first: firebench wx run SETUP --steps obs")
        output_json, score_card = self.score_paths(cycle, name)
        return self._score_cycle(
            Path(model_output), Path(obs_record["outputs"]["obs_h5"]), cycle, name, output_json, score_card
        )

    # ----------------------------------------------------------------- plan
    def plan_lines(self) -> list[str]:
        """Offline description of what ``run`` would do."""
        setup = self.setup
        lines = [
            f"Setup: {setup.path} ({setup.name})",
            f"Output directory: {self.out}",
        ]
        if setup.preset:
            lines.append(f"Preset: {setup.preset['case']} {setup.preset['period']}")
        lines += [f"Note: {note}" for note in setup.notes]
        lines += [
            "Domain bbox (lon_min, lat_min, lon_max, lat_max): "
            + ", ".join(f"{value:g}" for value in setup.bbox),
            f"Evaluation window (UTC): {setup.start.isoformat()} .. {setup.end.isoformat()}",
            "",
            "Observations:",
        ]
        lines += self._plan_observations()
        lines += ["", f"Model: {setup.model.name} (NOAA Open Data on AWS, anonymous access)"]
        total_mb = 0.0
        for cycle in setup.cycles:
            n_files = cycle.horizon_hours + 1
            cached = sum(
                hrrr_forecast.is_cached(
                    hrrr_forecast.cached_file_path(cycle.cycle, fxx, self.cache_root),
                    hrrr_forecast.fields_for_hour(fxx),
                )
                for fxx in range(n_files)
            )
            size_mb = HRRR_FILE_MB[0] + HRRR_FILE_MB[1] * cycle.horizon_hours
            total_mb += size_mb * (n_files - cached) / n_files
            lines.append(
                f"  cycle {cycle.cycle:%Y-%m-%d %HZ} (HRRR v{hrrr_forecast.hrrr_version(cycle.cycle)}): "
                f"f00-f{cycle.horizon_hours:02d}, {n_files} files, {cached} cached"
            )
        lines.append(f"  download still needed: about {format_bytes(int(total_mb * 1e6))}")
        lines += ["", "Stages:"]
        lines.append(
            f"  obs: {'up to date' if self._is_current('obs', self._obs_identity()) else 'to run'}"
        )
        for cycle in setup.cycles:
            state = (
                "up to date"
                if self.model_path(cycle).is_file() and self._stage(f"adapt:{cycle.label}")
                else "to run"
            )
            lines.append(f"  adapt {cycle.label}: {state}")
        bench = setup.benchmark
        lines += [
            "",
            f"Scoring: target {bench.target}, cadences {list(bench.cadences)} h, "
            f"lead bins {[list(item) for item in bench.lead_bins]}, "
            f"informational {[list(item) for item in bench.informational_lead_bins]}, "
            f"obs tolerance +/-{bench.obs_tolerance_min:g} min, min coverage {bench.min_coverage:g}",
        ]
        return lines

    def _plan_observations(self) -> list[str]:
        setup = self.setup
        start, end = setup.fetch_window
        source = setup.observations.source
        if source == "h5":
            return [f"  existing FireBench observation file: {setup.observations.h5}"]
        lines = [
            f"  QC: conservative_auto, reviewer '{setup.qc.reviewer}'",
            f"  window with QC context: {start.isoformat()} .. {end.isoformat()}",
        ]
        if source == "synoptic_json":
            return [
                f"  saved Synoptic JSON (clipped to window and domain): {setup.observations.synoptic_json}"
            ] + lines
        resolution = self._synoptic_key(raise_missing=False)
        lines.insert(
            0, "  Synoptic download, bbox " + ", ".join(f"{value:g}" for value in setup.fetch_bbox)
        )
        if resolution.value is None:
            lines += ["  " + line for line in fb_keys.missing_key_message(resolution).splitlines()]
        else:
            lines.append(f"  Synoptic key: {resolution.source} ({fb_keys.fingerprint(resolution.value)})")
        return lines

    # ------------------------------------------------------------ obs stage
    def _obs_identity(self) -> dict:
        setup = self.setup
        options = setup.observations
        identity = {"firebench_version": fb_version, "source": options.source}
        if options.source == "h5":
            identity["h5_sha256"] = _sha256(options.h5)
            return identity
        start, end = setup.fetch_window
        identity.update(
            {
                "bbox": list(setup.fetch_bbox),
                "fetch_window": [start.isoformat(), end.isoformat()],
                "evaluation_window": [setup.start.isoformat(), setup.end.isoformat()],
                "qc": setup.section_hash("qc"),
            }
        )
        if options.source == "synoptic_json":
            identity["synoptic_json_sha256"] = _sha256(options.synoptic_json)
        else:
            identity["networks"] = list(options.networks)
        return identity

    def _run_obs(self, identity: dict, current: bool, requested: bool, result: WorkflowResult) -> Path:
        record = self._stage("obs")
        if current:
            result.records.append(StageRecord("obs", "skipped", "observations up to date"))
            return Path(record["outputs"]["obs_h5"])
        if not requested:
            raise WorkflowError(
                "observations are missing or out of date; run with --steps obs (or no --steps)"
            )
        if self.setup.observations.source == "h5":
            obs_h5 = self.setup.observations.h5
            outputs = {"obs_h5": str(obs_h5), "obs_sha256": _sha256(obs_h5), "dropped_stations": []}
            self._record("obs", identity, outputs)
            result.records.append(StageRecord("obs", "done", f"using existing observation file {obs_h5}"))
            return obs_h5
        outputs = self._build_observations()
        self._record("obs", identity, outputs)
        result.records.append(
            StageRecord(
                "obs",
                "done",
                f"{outputs['stations']} stations after QC, "
                f"{len(outputs['dropped_stations'])} dropped before QC",
            )
        )
        return Path(outputs["obs_h5"])

    def _build_observations(self) -> dict:
        # pylint: disable-next=import-outside-toplevel
        from firebench.acquisition import synoptic

        # pylint: disable-next=import-outside-toplevel
        from firebench.tools.wx_qc.pipeline import QCError, finalize_manifest, process_synoptic_json

        setup = self.setup
        start, end = setup.fetch_window
        self.obs_dir.mkdir(parents=True, exist_ok=True)
        if setup.observations.source == "synoptic_json":
            logger.info("[wx] clipping %s to the window and domain", setup.observations.synoptic_json)
            payload = json.loads(setup.observations.synoptic_json.read_text())
            payload = synoptic.clip_payload(payload, start, end, setup.fetch_bbox)
        else:
            token = self._synoptic_key(raise_missing=True).value
            client = synoptic.SynopticTimeseriesClient(
                token, **({"opener": self.synoptic_opener} if self.synoptic_opener else {})
            )
            payload = client.fetch(
                setup.fetch_bbox,
                start,
                end,
                networks=setup.observations.networks or None,
                max_chunk_days=setup.observations.max_chunk_days,
                cache_root=self.cache_root,
            )
        payload, dropped = synoptic.validate_payload(payload)
        if not payload["STATION"]:
            raise WorkflowError("no weather station with observations in the domain and window")
        source_json = self.obs_dir / "synoptic.json"
        source_json.write_text(json.dumps(payload))

        policy = {"mode": "conservative_auto", **setup.qc.overrides}
        if setup.qc.require_window:
            window = {
                "name": "evaluation window",
                "start": setup.start.isoformat(),
                "end": setup.end.isoformat(),
            }
            policy["required_windows"] = [*policy.get("required_windows", []), window]
        candidate = self.obs_dir / "obs_candidate.h5"
        qc_manifest = self.obs_dir / "obs_qc.json"
        qc_log = self.obs_dir / "obs_qc.log"
        obs_h5 = self.obs_dir / "obs.h5"
        try:
            process_synoptic_json(source_json, policy, candidate, qc_manifest, qc_log, overwrite=True)
            finalize_manifest(qc_manifest, obs_h5, setup.qc.reviewer, overwrite=True)
        except QCError as error:
            raise WorkflowError(f"automatic weather QC failed: {error} (see {qc_log})") from None
        self._stamp_observations(obs_h5)
        with _open_h5(obs_h5) as h5:
            n_stations = sum(1 for name in h5.get("time_series", {}) if name.startswith("station"))
        return {
            "obs_h5": str(obs_h5),
            "obs_sha256": _sha256(obs_h5),
            "synoptic_json": str(source_json),
            "qc_manifest": str(qc_manifest),
            "qc_log": str(qc_log),
            "stations": n_stations,
            "dropped_stations": dropped,
        }

    def _stamp_observations(self, obs_h5: Path) -> None:
        setup = self.setup
        with _open_h5(obs_h5, "a") as h5:
            h5.attrs["data_tier"] = DATA_TIER
            h5.attrs["description"] = (
                f"Weather-station observations for firebench wx setup '{setup.name}', automatically "
                "quality controlled (conservative_auto)"
            )
            h5.attrs["wx_setup_name"] = setup.name
            h5.attrs["wx_bbox"] = list(setup.bbox)
            h5.attrs["wx_window_start"] = setup.start.isoformat()
            h5.attrs["wx_window_end"] = setup.end.isoformat()

    def _synoptic_key(self, raise_missing: bool):
        resolution = fb_keys.resolve_key("synoptic", explicit_file=self.setup.observations.token_file)
        if raise_missing and resolution.value is None:
            raise WorkflowError(fb_keys.missing_key_message(resolution))
        return resolution

    # -------------------------------------------------------- model stages
    def _adapt_identity(self, cycle: CycleWindow, obs_sha: str) -> dict:
        # pylint: disable-next=import-outside-toplevel
        from firebench.adapters.hrrr_weather import SCREEN_LEVEL_BAND_M

        return {
            "firebench_version": fb_version,
            "obs_sha256": obs_sha,
            "cycle": cycle.cycle.isoformat(),
            "horizon_hours": cycle.horizon_hours,
            "product": hrrr_forecast.PRODUCT,
            "fields": list(hrrr_forecast.FIELDS + hrrr_forecast.STATIC_FIELDS),
            "screen_level_band_m": list(SCREEN_LEVEL_BAND_M),
        }

    def _cycles_to_download(self, steps, obs_sha: str | None) -> list[CycleWindow]:
        if "hrrr" not in steps and "adapt" not in steps:
            return []
        if "adapt" not in steps or obs_sha is None:
            return list(self.setup.cycles)
        return [
            cycle
            for cycle in self.setup.cycles
            if not (
                self.model_path(cycle).is_file()
                and self._is_current(f"adapt:{cycle.label}", self._adapt_identity(cycle, obs_sha))
            )
        ]

    def _run_hrrr_and_adapt(self, pending: dict, executor, adapt: bool, result: WorkflowResult) -> None:
        obs_record = self._stage("obs")
        obs_sha = obs_record["outputs"]["obs_sha256"] if obs_record else None
        for cycle in self.setup.cycles:
            model_path = self.model_path(cycle)
            identity = self._adapt_identity(cycle, obs_sha) if obs_sha else None
            if adapt and model_path.is_file() and self._is_current(f"adapt:{cycle.label}", identity):
                result.model_files[cycle.label] = model_path
                result.records.append(
                    StageRecord(f"adapt {cycle.label}", "skipped", "model file up to date")
                )
                continue
            submitted = pending.get(cycle.label) or hrrr_forecast.submit_cycle(
                cycle.cycle, cycle.horizon_hours, executor, self.cache_root
            )
            cycle_files = submitted.result()
            if not cycle_files.complete:
                reason = f"forecast hours missing from the archive: {cycle_files.missing}"
                result.dropped_cycles.append({"cycle": cycle.cycle.isoformat(), "reason": reason})
                result.records.append(StageRecord(f"hrrr {cycle.label}", "dropped", reason))
                logger.warning("[wx] cycle %s dropped: %s", cycle.label, reason)
                continue
            result.records.append(
                StageRecord(f"hrrr {cycle.label}", "done", f"{len(cycle_files.files)} files in the cache")
            )
            if not adapt:
                continue
            if obs_sha is None:
                raise WorkflowError("observations are missing; run the obs stage first")
            self._adapt_cycle(cycle, cycle_files, identity, result)

    def _adapt_cycle(self, cycle: CycleWindow, cycle_files, identity: dict, result: WorkflowResult) -> None:
        # pylint: disable-next=import-outside-toplevel
        from firebench.adapters.hrrr_weather import build_hrrr_station_file

        model_path = self.model_path(cycle)
        obs_h5 = Path(self._stage("obs")["outputs"]["obs_h5"])
        kwargs = {"read": self.read_fields} if self.read_fields is not None else {}
        summary = build_hrrr_station_file(obs_h5, cycle_files, model_path, **kwargs)
        self._record(f"adapt:{cycle.label}", identity, {"model_h5": str(model_path), "summary": summary})
        result.model_files[cycle.label] = model_path
        result.records.append(
            StageRecord(f"adapt {cycle.label}", "done", f"{summary['stations']} stations")
        )
        if not self.setup.model.keep_grib:
            for path in cycle_files.files.values():
                path.unlink(missing_ok=True)
            logger.info("[wx] deleted the GRIB files of cycle %s (keep_grib: false)", cycle.label)

    # ------------------------------------------------------------ scoring
    def _run_score(self, result: WorkflowResult) -> None:
        obs_record = self._stage("obs")
        if not obs_record:
            raise WorkflowError("observations are missing; run the obs stage first")
        obs_h5 = Path(obs_record["outputs"]["obs_h5"])
        for cycle in self.setup.cycles:
            model_path = self.model_path(cycle)
            if not model_path.is_file() or not self._stage(f"adapt:{cycle.label}"):
                continue
            output_json, score_card = self.score_paths(cycle, self.setup.model.name)
            identity = {
                "model_sha256": _sha256(model_path),
                "obs_sha256": obs_record["outputs"]["obs_sha256"],
                "benchmark": self.setup.section_hash("benchmark"),
                "firebench_version": fb_version,
            }
            key = f"score:{self.setup.model.name}:{cycle.label}"
            if output_json.is_file() and score_card.is_file() and self._is_current(key, identity):
                result.results[cycle.label] = json.loads(output_json.read_text())
                result.records.append(StageRecord(f"score {cycle.label}", "skipped", "scores up to date"))
                continue
            scored = self._score_cycle(
                model_path, obs_h5, cycle, self.setup.model.name, output_json, score_card
            )
            self._record(key, identity, {"json": str(output_json), "score_card": str(score_card)})
            result.results[cycle.label] = scored
            total = scored.get("score_card", {}).get("Score Total")
            result.records.append(
                StageRecord(
                    f"score {cycle.label}",
                    "done",
                    "not scored" if total is None else f"total score {total:.2f}",
                )
            )

    def _score_cycle(
        self,
        model_path: Path,
        obs_h5: Path,
        cycle: CycleWindow,
        name: str,
        output_json: Path,
        score_card: Path,
    ) -> dict:
        # pylint: disable-next=import-outside-toplevel
        from firebench.benchmarks.wx_forecast import WxForecastSpec, run_wx_forecast_benchmark

        bench = self.setup.benchmark
        spec = WxForecastSpec(
            case_name=f"{self.setup.name} {cycle.cycle:%Y-%m-%d %HZ}",
            cycle=cycle.cycle,
            horizon_hours=cycle.horizon_hours,
            lead_bins=bench.lead_bins,
            informational_lead_bins=bench.informational_lead_bins,
            cadences=bench.cadences,
            obs_tolerance_s=bench.obs_tolerance_min * 60.0,
            model_tolerance_s=bench.model_tolerance_s,
            min_coverage=bench.min_coverage,
        )
        return run_wx_forecast_benchmark(
            model_path,
            obs_h5,
            spec,
            target=bench.target,
            name=f"{name} {cycle.cycle:%Y-%m-%d %HZ}",
            overwrite=True,
            output_json=output_json,
            score_card_report=score_card,
            full_name=bench.full_name,
        )

    def _write_summary(self, result: WorkflowResult) -> Path:
        path = self.out / "summary.md"
        lines = [f"# Weather forecast benchmark: {self.setup.name}", ""]
        lines += [
            f"- Domain bbox: {', '.join(f'{value:g}' for value in self.setup.bbox)}",
            f"- Window (UTC): {self.setup.start.isoformat()} .. {self.setup.end.isoformat()}",
            f"- Model: {self.setup.model.name}",
            f"- FireBench version: {fb_version}",
        ]
        if self.setup.preset:
            lines.append(f"- Preset: {self.setup.preset['case']} {self.setup.preset['period']}")
        results = [result.results[label] for label in sorted(result.results)]
        if results:
            lines.append(f"- Observation data tier: {results[0].get('data_tier', 'unknown')}")
            groups = list(results[0]["score_card"]["Scheme"])
            lines += ["", "## Scores per cycle", ""]
            lines.append(
                "| Group | Weight | " + " | ".join(item["cycle"][:13] + "Z" for item in results) + " |"
            )
            lines.append("|---|---|" + "---|" * len(results))
            for group in ["Total", *groups]:
                weight = (
                    "" if group == "Total" else str(results[0]["score_card"]["Scheme"][group]["weight"])
                )
                scores = [item["score_card"].get(f"Score {group}") for item in results]
                cells = ["not scored" if score is None else f"{score:.2f}" for score in scores]
                lines.append(f"| {group} | {weight} | " + " | ".join(cells) + " |")
            excluded = results[0].get("excluded_kpis", [])
            if excluded:
                lines += ["", "## Excluded variables", ""]
                lines += [f"- {item['variable']}: {item['reason']}" for item in excluded]
            lines += ["", "## Station exclusions (observation coverage below the minimum)", ""]
            for item in results:
                n_exclusions = len(item.get("cadence_exclusions", []))
                lines.append(f"- {item['cycle']}: {n_exclusions} station/variable/lead-bin exclusions")
            policy = results[0].get("height_policy")
            if policy:
                lines += ["", "## Declared model sensor heights", ""]
                for variable, counts in sorted(policy.items()):
                    for adjustment, count in sorted(counts.items()):
                        lines.append(f"- {variable}: {count} station(s), {adjustment}")
        if result.dropped_cycles:
            lines += ["", "## Dropped cycles", ""]
            lines += [f"- {item['cycle']}: {item['reason']}" for item in result.dropped_cycles]
        if len(results) > 1:
            # pylint: disable-next=import-outside-toplevel
            from firebench.metrics.table import save_comparison_as_table

            comparison = self.out / "scores" / "cycles_comparison.pdf"
            save_comparison_as_table(comparison, results)
            lines += ["", f"Cycle comparison score card: `{comparison.relative_to(self.out)}`"]
        lines += [
            "",
            "Caveats: HRRR values are instantaneous at the valid time while RAWS wind is a 10-min",
            "average; F00 is the analysis, which assimilates surface observations (weight 0).",
        ]
        path.write_text("\n".join(lines) + "\n")
        return path

    # ---------------------------------------------------------- manifest
    def _load_manifest(self) -> dict:
        try:
            manifest = json.loads(self.manifest_path.read_text())
        except (OSError, ValueError):
            manifest = {}
        manifest.setdefault("stages", {})
        return manifest

    def _stage(self, key: str) -> dict | None:
        return self.manifest["stages"].get(key)

    def _is_current(self, key: str, identity: dict | None) -> bool:
        record = self._stage(key)
        forced = key.split(":", 1)[0] in self.forced_stages
        return bool(
            identity is not None
            and not forced
            and record
            and record.get("identity") == _canonical(identity)
        )

    def _record(self, key: str, identity: dict, outputs: dict) -> None:
        self.manifest["stages"][key] = {
            "identity": _canonical(identity),
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "outputs": outputs,
        }
        self.manifest["setup"] = str(self.setup.path)
        self.manifest["firebench_version"] = fb_version
        atomic_write_json(self.manifest_path, self.manifest)


def _canonical(value) -> dict:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _slug(name: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in name)


def _open_h5(path: Path, mode: str = "r"):
    import hdf5plugin  # pylint: disable=import-outside-toplevel,unused-import
    import h5py  # pylint: disable=import-outside-toplevel

    return h5py.File(path, mode)
