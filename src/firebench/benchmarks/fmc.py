"""Station fuel-moisture comparisons at sampling-event, native, hourly and daily scales."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np

from .. import __version__
from .. import metrics as fm
from .. import signing as fsi
from ..standardize import validate_h5_std
from ..standardize.fmc import FUEL_DATASETS
from ..tools import calculate_sha256
from ..tools.units import ureg
from pint.errors import PintError
from .wx_common import aggregate_scheme_scores


def _text(value):
    return value.decode() if isinstance(value, bytes) else str(value)


def _series(path):
    """Read series by semantic identity, independent of storage grouping."""
    result = {}
    with h5py.File(path, "r") as handle:
        validate_h5_std(handle)
        for group in handle.get("time_series", {}).values():
            for name, ds in group.items():
                if not isinstance(ds, h5py.Dataset) or "source_fuel_type" not in ds.attrs:
                    continue
                key = (
                    _text(group.attrs["station_id"]),
                    _text(ds.attrs["source_fuel_type"]),
                    _text(ds.attrs.get("source_fuel_variation", "")),
                )
                if key in result:
                    raise ValueError(f"duplicate series identity: {key}")
                time_ds = group["time"]
                if "time_origin" in time_ds.attrs:
                    origin = datetime.fromisoformat(_text(time_ds.attrs["time_origin"]))
                    seconds = (
                        ureg.Quantity(time_ds[:], _text(time_ds.attrs["time_units"])).to("s").magnitude
                    )
                    times = [origin + timedelta(seconds=float(s)) for s in seconds]
                else:
                    times = [datetime.fromisoformat(_text(t).replace("Z", "+00:00")) for t in time_ds[:]]
                if any(t.tzinfo is None for t in times):
                    raise ValueError(f"{key}: time coordinates require time zones")
                try:
                    values = ureg.Quantity(ds[:], _text(ds.attrs["units"])).to("percent").magnitude
                except PintError as exc:
                    raise ValueError(f"{key}: FMC units must convert to percent") from exc
                if np.asarray(values).ndim != 1 or len(times) != len(values):
                    raise ValueError(f"{key}: FMC and time must be equal-length 1D arrays")
                date_only = group.get(f"{name}_date_only")
                assumed = group.get(f"{name}_time_assumed")
                dates = np.zeros(len(times), dtype=bool) if date_only is None else date_only[:]
                guesses = np.zeros(len(times), dtype=bool) if assumed is None else assumed[:]
                if len(dates) != len(times) or len(guesses) != len(times):
                    raise ValueError(f"{key}: invalid time provenance length")
                result[key] = [
                    (t.astimezone(timezone.utc).timestamp(), float(v), bool(d), bool(a))
                    for t, v, d, a in zip(times, values, dates, guesses)
                ]
    return result


def _means(records, mode, live):
    buckets = {}
    for timestamp, value, date_only, assumed in records:
        if not np.isfinite(value) or (mode != "daily" and date_only and not live):
            continue
        width = {"daily": 86400, "hourly": 3600}.get(mode)
        key = (timestamp // width) * width if width else timestamp
        buckets.setdefault(key, []).append((value, assumed))
    return {
        t: (float(np.mean([v for v, _ in samples])), sum(a for _, a in samples))
        for t, samples in buckets.items()
    }


def compare_fmc_series(observations, model, *, live, mode, tolerance_seconds=3600):
    """Compare record tuples (UTC epoch seconds, percent, date_only, time_assumed).

    Daily/hourly use UTC bin means; native uses exact timestamps; events use nearest model
    samples, breaking ties toward earlier times. Duplicate timestamps are averaged first.
    """
    if mode not in ("daily", "hourly", "native", "events"):
        raise ValueError(f"unknown FMC mode: {mode}")
    if not np.isfinite(tolerance_seconds) or tolerance_seconds < 0:
        raise ValueError("event tolerance must be finite and nonnegative")
    obs = _means(observations, mode, live)
    mod = _means(model, mode, live)
    model_times = np.array(sorted(mod))
    pairs, offsets, assumed_count = [], [], 0
    for timestamp, (value, assumed) in sorted(obs.items()):
        matched = timestamp if timestamp in mod else None
        if mode == "events" and len(model_times):
            index = np.searchsorted(model_times, timestamp)
            candidates = model_times[max(0, index - 1) : index + 1]
            nearest = min(candidates, key=lambda t: (abs(t - timestamp), t))
            matched = nearest if abs(nearest - timestamp) <= tolerance_seconds else None
        if matched is not None:
            pairs.append((mod[matched][0], value))
            offsets.append(float(matched - timestamp))
            assumed_count += assumed
    detail = {
        "matched_count": len(pairs),
        "observation_count": len(obs),
        "unmatched_count": len(obs) - len(pairs),
        "assumed_time_count": assumed_count,
        "model_count": len(mod),
        "time_offsets_seconds": offsets,
        "raw_observation_count": len(observations),
        "finite_observation_count": int(sum(np.isfinite(r[1]) for r in observations)),
    }
    if not pairs:
        return {}, {**detail, "reason": "no finite matched observations at this time scale"}
    prediction, reference = np.array(pairs).T
    return {
        label: function(prediction, reference)
        for label, function in (("MAE", fm.stats.mae), ("RMSE", fm.stats.rmse), ("Bias", fm.stats.bias))
    }, detail


def run_fmc_benchmark(
    model_output: Path,
    obs_data: Path,
    *,
    mae_half_score_pp: float,
    event_tolerance_seconds: float = 3600,
    name: str = "",
    output_json: Path = Path("fmc_results.json"),
    score_card_report: Path = Path("fmc_scorecard.pdf"),
    overwrite: bool = False,
    benchmark_target: str = "ALL",
    sign: tuple[str, str] | None = None,
    score_card_full_name: bool = False,
):
    """Write standard benchmark JSON and a PDF; primary MAE scores weight each series equally."""
    if benchmark_target.upper() not in ("ALL", "A"):
        raise ValueError("Unknown FMC target; use ALL.")
    if not np.isfinite(mae_half_score_pp) or mae_half_score_pp <= 0:
        raise ValueError("MAE half-score scale must be finite and positive")
    if not np.isfinite(event_tolerance_seconds) or event_tolerance_seconds < 0:
        raise ValueError("event tolerance must be finite and nonnegative")
    output_json, score_card_report = Path(output_json), Path(score_card_report).with_suffix(".pdf")
    inputs = {Path(model_output).resolve(), Path(obs_data).resolve()}
    if output_json.resolve() == score_card_report.resolve() or any(
        p.resolve() in inputs for p in (output_json, score_card_report)
    ):
        raise ValueError("input and output paths must differ")
    for path in (output_json, score_card_report):
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists; use --overwrite")
    observations, models = _series(obs_data), _series(model_output)
    benchmarks, scheme, details, ignored = {}, {}, {}, {}
    for key, records in sorted(observations.items()):
        live = key[1] not in FUEL_DATASETS
        primary = "events" if live else "daily"
        identity = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]
        for mode in ("events", "daily", "hourly", "native") if live else ("daily", "hourly", "native"):
            group = f'{key[0]} / {key[1]} / {key[2] or "default"} / {mode}'
            values, detail = compare_fmc_series(
                records,
                models.get(key, []),
                live=live,
                mode=mode,
                tolerance_seconds=event_tolerance_seconds,
            )
            details[group] = {
                **detail,
                "station_id": key[0],
                "fuel_type": key[1],
                "variation": key[2],
                "mode": mode,
            }
            scheme[group] = {"weight": 1 if mode == primary else 0, "benchmarks": {}}
            for metric in ("MAE", "RMSE", "Bias"):
                kpi_id = f"FMC-{identity}-{mode.upper()}-{metric.upper()}"
                scheme[group]["benchmarks"][kpi_id] = 1 if metric == "MAE" else 0
                if metric not in values:
                    ignored[kpi_id] = detail["reason"]
                    continue
                value = values[metric]
                # Diagnostic scores are displayed but have zero aggregation weight.
                score = fm.kpi_norm_half_open_exponential(abs(value), 0, mae_half_score_pp)
                benchmarks[kpi_id] = {f"{metric} (percentage points)": value, "Score": score}
    certificates = fsi.retrieve_h5_certificates(obs_data, model_output)
    result = {
        "case_id": "FMC",
        "case_name": "Station Fuel Moisture",
        "benchmark_target": "ALL",
        "certificates_input": certificates,
        "verification_lvl": fsi.compute_input_verification_lvl(certificates),
        "case_version": "Unofficial",
        "benchmark_short_name": "Fuel Moisture",
        "firebench_version": __version__,
        "evaluated_model_name": name or Path(model_output).stem,
        "created_on": datetime.now(timezone.utc).isoformat(),
        "obs_dataset_hash": calculate_sha256(Path(obs_data)),
        "model_output": calculate_sha256(Path(model_output)),
        "benchmark_script": calculate_sha256(Path(__file__)),
        "parameters": {
            "mae_half_score_pp": mae_half_score_pp,
            "event_tolerance_seconds": event_tolerance_seconds,
            "bin_timezone": "UTC",
            "duplicate_policy": "finite mean at same timestamp",
            "primary_live": "events",
            "primary_dead": "daily",
        },
        "series_comparisons": details,
        "ignored_reasons": ignored,
        "ignored_benchmarks": sorted(ignored),
    }
    result.update(aggregate_scheme_scores({"benchmarks": benchmarks}, "FMC", scheme, set(ignored)))
    for path in (output_json, score_card_report):
        path.parent.mkdir(parents=True, exist_ok=True)
    if sign:
        result = fsi.certify_benchmark_run(result, *sign)
    fm.save_as_table(
        score_card_report, result, bool(sign), "certificate_verif_lvl", full_name=score_card_full_name
    )
    result["score_card_report_hash"] = calculate_sha256(score_card_report)
    if sign:
        result, _ = fsi.add_certificate_to_dict(
            result, "certificate_final", fsi.Certificates.FB_SCORE_CARD.value, *sign
        )
    fsi.write_case_results(output_json, result)
    return result
