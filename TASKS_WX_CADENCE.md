# Task list: hourly / 3-hourly weather benchmark cadence

Status: draft, untracked (not committed). Scope note per AGENTS.md: this is not the
weather-station QC GUI, so it does not belong in `FUTURES.md`.

## Goal

Let operational NWP models that only produce hourly (or 3-hourly) output be evaluated against
the Caldor weather stations, without requiring them to interpolate onto each station's native,
irregular timestamp grid the way `bench_wx_generic_index` currently requires
(`c001_caldor.py:705`, `assert np.sum(mask_obs) == np.sum(mask_model)`).

Reference: Brightband's Operational WeatherBench (https://owb.brightband.com/methodology) scores
gridded/global operational models at a fixed cadence (every 6h out to 360h) tied to init cycle,
and explicitly **skips rather than scores** a missing cycle instead of forcing interpolation.
That's the same philosophy we already use for QC (exclude on doubt, don't guess) — worth carrying
over here: a cadence-tier benchmark should *drop* a station/timestamp pair it can't match with
confidence, not manufacture a value.

## Open design decisions (resolve before coding)

- [ ] What exactly is a "mandatory hourly timestamp"? Wall-clock UTC top-of-hour within the
      benchmark period, independent of station-specific offsets — confirm this, since several
      stations (e.g. `station_240PG`) start mid-hour and would otherwise need a per-station
      reference origin.
- [ ] Matching tolerance for obs: exact match only, or a window (e.g. ±5 min)? Stations with
      irregular ~1-8 min native deltas (`E6476`, `F9304`, `GLVNV`, `KAHNV`, `KMEV` — see prior
      audit) will rarely hit `:00` exactly, so tolerance-window matching is effectively required,
      not optional.
- [ ] Matching tolerance for model: does the model declare its own timestamps (and get matched
      with the same tolerance), or is it required to emit exactly on the hour?
- [ ] Minimum-sample floor: if tolerance-matching leaves a station with only a handful of hourly
      pairs in a period, should it be excluded from that cadence tier (mirrors `SAFEEXCL` logic
      in the wx-qc pipeline) rather than scored on a near-empty sample?
- [ ] Does 3-hourly mean `hour % 3 == 0` in UTC, or does it need to respect each period's own
      reference/local anchor (OWB anchors to 00/06/12/18 UTC cycles for a reason — pick and
      document ours)?
- [ ] Precipitation-style exception, borrowing from OWB: some metrics may need a fixed reference
      independent of lead-0/period start. Not obviously applicable here (no accumulation
      variables in the Caldor set today), but worth a explicit "no" rather than an oversight.

## 1. Observation-side timestamp matching

- [ ] New utility (near `get_mask_from_period`, `c001_caldor.py:2343`) that, given a station's
      time array, returns the subset of indices landing on the mandatory grid (exact or
      tolerance-based per the decision above).
- [ ] Unit tests: exact-hour station, tolerance-window match, station that never hits an hour
      mark, station with a duplicate-adjacent sample within tolerance of the same mandatory
      timestamp (must not double-count).

## 2. Model/obs timestamp join (the actual invasive change)

- [ ] Replace the position-based comparison in `bench_wx_generic_index` (`c001_caldor.py:668-731`)
      with a real join: for each mandatory timestamp in the period, find the obs sample (if any,
      within tolerance) and the model sample (if any, within tolerance), and only compare where
      both exist.
- [ ] Remove/replace the `assert np.sum(mask_obs) == np.sum(mask_model)` invariant — it assumes
      identical per-station time arrays, which no longer holds once the model is allowed a
      coarser native cadence than obs.
- [ ] Decide how "no match" is counted for QC/reporting purposes (silent drop vs. a logged count
      of skipped mandatory timestamps per station, similar to `_log_missing_wx_station_requirements`).
- [x] Carry the NaN-penalty behavior (`c001_caldor.py:714-728`) into the new join path. **Fixed**:
      `wind_direction` nans are now penalized as `(obs + 180) % 360` — the worst-case circular
      error at that timestamp — instead of the generic `PENALTY_VALUE = -1e6`, which wrapped to
      80° (`-1e6 mod 360`) and could land close to the true direction. Covered by
      `test_weather_benchmark_penalizes_wind_direction_nan_as_opposite_direction` in
      `tests/unit/test_caldor_benchmark.py`. Still applies when reusing this mechanism across the
      new cadence tiers: no further action needed there, just don't regress it.

## 3. Requirement validation

- [ ] `req_wx_station` / `validate_h5_weather_stations_structure` (`standardize/tools.py:252`)
      only checks dataset existence today, not length — confirm it doesn't need changes, or
      extend it if a cadence tier needs a "model provides at least N mandatory timestamps"
      pre-check before running the benchmark function at all.

## 4. Benchmark ID generation — replace the sequential counter

Current scheme (`add_wx_benchmarks`, `c001_caldor.py:1378-1415`) assigns `FB001_WX{bench_idx:03d}`
by iterating nested loops in a fixed order. Problems this creates *now*, made worse by adding a
third (cadence) axis on top of period × variable × metric × station-set × stat:

- IDs are positional, not semantic — reordering config or adding a dimension reassigns every
  downstream ID, silently breaking anything that pins a specific `FB001_WX###` (saved score
  cards, aggregation-scheme exclusion lists, historical run comparisons).
- Adding cadence roughly **triples** the WX benchmark count (HRRR period sets alone can already
  be dozens of cycle starts); a flat opaque list stops being navigable or debuggable at that
  size.

Two options, pick one:

- [ ] **Structured/semantic ID** (matches OWB's own convention: `[Model][Region][Variable]
      [Metric][LeadTime]`): something like
      `FB001_WX-{variable}-{cadence}-{metric}-{stationset}-{stat}-{period_slug}`. Pros: readable,
      greppable, stable to reordering. Cons: long; needs a slug/abbreviation table per axis to
      stay within any HDF5/JSON key-length conventions already in use elsewhere in the repo —
      check those before committing to a format.
- [ ] **Stable content-addressed ID**, reusing the pattern already in this codebase
      (`wx_qc/pipeline.py:_operation_id`/`_finding_id`: `f"{prefix}-{code}-{sha256(identity)[:12].upper()}"`).
      Hash the tuple `(variable, cadence, metric, station_set, stat, period_name)` instead of a
      counter. Pros: order-independent by construction, no new naming/abbreviation scheme needed,
      consistent with how the project already solved this exact "stable ID across a growing,
      reorderable enumeration" problem. Cons: opaque without a lookup (need a name/description
      field alongside the ID, which `bench_name` already provides — cheap to keep).
- [ ] Either way: write a migration note in `CHANGELOG.md` — old sequential IDs will not match
      new IDs, and any stored results/score cards referencing the old scheme need regeneration,
      not a silent renumbering.

## 5. Registry / config fan-out

- [ ] Add `cadence` as a third axis in `add_wx_benchmarks` (`c001_caldor.py:1378`) and a
      `WX_CADENCE_SPECS` table in `c001_caldor_config.py` (mirrors `WX_VARIABLE_SPECS`,
      `WX_PERIOD_SETS`) — e.g. `("native", None)`, `("hourly", 1)`, `("3-hourly", 3)`.
  - keep this in mind: is `native` still meaningful for models that supply full-resolution
    output, or does the new cadence axis fully replace today's behavior? If it replaces it,
    document that as a behavior change (existing model submissions still validate under
    `native`).
- [ ] `_weather_group_names` / `_weather_period_aggregation` / `_weather_period_tso_aggregation`
      (`c001_caldor.py:1558-1577`) group by period only today — decide whether cadence tiers get
      their own top-level groups (e.g. "Air Temp Hourly W1") or fold into existing groups with a
      cadence-aware weight.
- [ ] `create_aggregation_schemes()` (`c001_caldor.py:1898`) — audit for any hardcoded assumption
      about WX benchmark count or naming.

## 6. Docs

- [ ] `docs/benchmarks/California/01_Caldor.md` R08-R12 tables — add the relaxed requirement
      text for cadence-tiered benchmarks (model no longer needs a full native-resolution time
      series for those tiers).
- [ ] `docs/tutorials/cli_caldor_benchmark.md` — mention the cadence option if it's user-facing
      (CLI flag / config key), with an example for an hourly-only model submission.
- [ ] `CHANGELOG.md` entry under `[Unreleased]`.

## 7. Tests

- [ ] `tests/unit` — new join/matching utility, ID generation scheme, `PENALTY_VALUE` fix for
      `wind_direction`.
- [ ] `tests/func` — end-to-end hourly-cadence benchmark run against a small fixture with a mix
      of aligned and non-aligned stations.
- [ ] `tests/regression` — confirm existing (native-cadence) WX benchmark results are bit-for-bit
      unchanged after this lands, since this should be purely additive for existing submissions.

## Notes from Brightband's Operational WeatherBench (external reference)

- Fixed lead-time/cadence grid (every 6h to 360h) with named milestones (day 1/3/5/7/10/15) —
  analogous shape to a `native` / `hourly` / `3-hourly` tier system, if we ever want named
  "checkpoint" groupings rather than just raw cadence.
- Missing model data for a given metric → that model is **dropped from that metric** ("omit ...
  to ensure fairness"), not penalized. This is the opposite of FireBench's `PENALTY_VALUE`
  approach. Worth an explicit decision, not a default: do we want anti-gaming penalization
  (current FireBench philosophy, keep it) or fairness-by-omission (OWB's philosophy) for the new
  cadence tiers specifically? Recommend keeping FireBench's existing penalize-don't-drop stance
  for consistency, but call it out since it's a deliberate divergence, not an oversight.
- Native-resolution mismatch (GEFS 0.5° mapped to a common 0.25° grid "by value replication
  rather than interpolation") is handled by explicit, documented value-reuse rather than
  interpolation — same spirit as "no forced interpolation, just an honest, documented match
  policy" for hourly/3-hourly stations here.
- Naming convention `[Model][Region][Variable][Metric][LeadTime]` supports the semantic-ID
  option in section 4.
