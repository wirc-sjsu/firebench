# Task list: hourly / 3-hourly weather benchmark cadence

Scope note per AGENTS.md: this is not the weather-station QC GUI, so it does not belong in
`FUTURES.md`.

## Goal

Let operational NWP models that only produce hourly (or 3-hourly) output be evaluated against
weather stations without interpolating onto each station's native, irregular timestamps. Today
`bench_wx_generic_index` (`c001_caldor.py`) requires that interpolation and asserts
`np.sum(mask_obs) == np.sum(mask_model)`.

Reference: Brightband's Operational WeatherBench (https://owb.brightband.com/methodology). It scores
operational models at a fixed cadence tied to the initialization cycle, and it **skips rather than
scores** a missing cycle instead of forcing interpolation. That matches the QC philosophy already
used here (exclude on doubt, don't guess). A cadence tier *drops* a station/timestamp pair it cannot
match with confidence and never manufactures a value.

First consumer: the automated HRRR workflow (`firebench wx`, branch `dev-wx-hrrr`), where HRRR is
written at its native hourly valid times and scored through this cadence join.

## Decisions (resolved 2026-09-29)

- [x] **Mandatory timestamps**: UTC top-of-hour marks inside the scored window, with
      `hour % cadence == 0`. There is no per-station origin, so stations such as `station_240PG`,
      which start mid-hour, are handled by the matching tolerance and need no special case.
- [x] **Obs matching tolerance**: the **nearest finite observation within ±10 min** (configurable,
      `obs_tolerance_min`). Measured on Caldor WH12 (115 stations × 49 h), the share of
      station-hours matched is 75 % exact, 89 % at ±5 min, **91 % at ±10 min**, 92 % at ±15 min and
      96 % at ±30 min.
  - ±10 min catches the `:51` RAWS reporters while keeping diurnal-ramp representativeness error
    small.
  - Stations reporting at `:17`/`:36` drop out of the hourly tier. They are counted, not guessed.
  - A NaN at the closest timestamp falls back to the next closest *finite* sample.
- [x] **Tolerance < cadence/2** is enforced (`check_tolerance`). One observation can therefore never
      serve two marks, and no reuse bookkeeping is needed.
- [x] **Model matching**: the model must emit the marks itself. A ±60 s tolerance absorbs float time
      encodings. A missing mark or NaN is **penalized** exactly like the native tier: `-1e6`, or the
      opposite direction for `wind_direction`.
- [x] **Minimum-sample floor**: a station whose observations cover fewer than 50 % of a window's
      marks (`min_coverage`) is excluded from that KPI. The exclusion is recorded in
      `ctx["cadence_exclusions"]` and in the result JSON, in the spirit of `SAFEEXCL`.
- [x] **3-hourly** means UTC `hour % 3 == 0`. For 00/06/12/18Z cycles this is identical to
      `lead % 3 == 0`, which is OWB's cycle anchoring.
- [x] **Precipitation / accumulations**: an explicit **no**. No accumulated or time-statistic
      variable is scored. The HRRR downloader selects instantaneous GRIB messages only, so, for
      example, `WIND:10 m:0-1 hour max` is excluded. If one is ever added, its match window must be
      the accumulation period, not a point.
- [x] **Penalize vs omit** (OWB): FireBench keeps **penalize-don't-drop** for model gaps inside a
      scored window. This is an anti-gaming choice. A forecast cycle that is *missing from the model
      archive* is omitted at the adapter level (the HRRR adapter drops the cycle and lists it), OWB
      style, because the evaluated model did not produce it.

## Weather-model constraints (refinement for HRRR and NWP in general)

- **Forecast cycles, one model file per cycle.** Cycles overlap in valid time (a 48 h HRRR run
  every 6 h), so one station time series cannot hold several cycles. Each cycle is scored against
  its own model file. Periods are the cycle windows `[c, c + horizon]`.
- **Horizon depends on the model version.** HRRR v4 (from 2020-12-02 12Z) runs 48 h at
  00/06/12/18Z, v3 (from 2018-07-12 12Z) runs 36 h, and otherwise 18 h. Horizons and lead bins are
  clamped to the cycle's real horizon.
- **Lead-time bins are sub-windows** of the cycle window (for example `F01-48`, or `F01-24` /
  `F25-48`). They reuse the period machinery unchanged.
- **Lead 0 is the analysis.** HRRR assimilates surface mesonet and METAR observations, so `F00` is
  partly scored against its own inputs. It is scored in a **weight-0 informational group**: it is
  displayed, but it moves neither the numerator nor the denominator of the total. This is the same
  circularity trap as fuel-moisture assimilation.
- **Instantaneous vs averaged.** HRRR T/RH/wind are instantaneous at the valid time, while RAWS
  wind is a 10-min average. This is a documented representativeness caveat and is not corrected.
- **Heights are declared, not assumed.**
  - The 10 m wind is brought to the station sensor height with the neutral log law and HRRR's own
    `SFCR` roughness.
  - The 2 m T/RH are assigned to screen-level sensors (1–3 m) without a transform.
  - The direction is assumed height-invariant in the surface layer.
  - The model's terrain-height difference is written per station as a diagnostic.

## 1. Observation-side timestamp matching

- [x] `firebench.benchmarks.wx_cadence`:
  - `mandatory_timestamps`;
  - `match_nearest` (nearest finite within tolerance, ties to the earlier sample);
  - `station_times_utc` (relative and absolute time encodings).
- [x] Unit tests (`tests/unit/test_wx_cadence.py`):
  - an exact-hour station;
  - a `:51` station matched;
  - a `:36` station never matched;
  - NaN fallback;
  - tie-breaking;
  - the analysis window;
  - tolerance validation.

## 2. Model/obs timestamp join

- [x] New `bench_wx_cadence_index` instead of modifying `bench_wx_generic_index`, so the native tier
      stays bit-identical (the regression pin passes unchanged).
- [x] The position assert is not used in the cadence path. The join is keyed on the mandatory
      marks.
- [x] "No match" accounting: observation-less marks are dropped silently, while station exclusions
      below the coverage floor are logged and returned in `cadence_exclusions`.
- [x] NaN penalty carried over, including the `wind_direction` opposite-direction fix. It is tested.
- [x] The `period` keyword is the lead window widened by ±tolerance, so station selection and
      requirement checks see off-hour observations; the marks come from `lead_window`.

## 3. Requirement validation

- [x] `validate_h5_weather_stations_structure` applies `periods` to the observation file only and
      checks that the model datasets exist. That is sufficient: a model missing marks is penalized
      at scoring time. No pre-check was added.

## 4. Benchmark IDs

- [x] **Semantic IDs for new cases**, e.g. `WX-AT-MAE-MEAN-TSO-1H-F0148`
      (`WX-{var}-{metric}-{stat}-{set}-{cadence}-F{lead bin}`). These IDs are readable, greppable and
      stable when the spec is reordered. The score card shows IDs only with `--full-name`, so their
      length is harmless.
- [x] Caldor's sequential `FB001_WX###` IDs are **untouched**; no migration is needed.

## 5. Registry / config fan-out

- [ ] Generic weather-forecast case (`firebench.benchmarks.wx_forecast`). Its axes are variable ×
      metric × station set × stat × cadence × lead bin. It has one registry per cycle and no module
      globals.
- [x] Shared weather machinery extracted to `firebench.benchmarks.wx_common`, with Caldor wrappers
      bound to its registries.
- [ ] **Caldor fan-out (next)**: an hourly tier for `FB001` (for example `H###_TH` targets). The new
      IDs must live in a registry dict separate from `WX_GROUP_BENCHMARKS`, because
      `tests/regression/test_caldor_weather_registry.py` hashes that dict. The per-period weather
      groups then gain cadence variants.
- [ ] Decide whether Caldor's native tier stays the default target once hourly tiers exist.

## 6. Docs

- [ ] `docs/benchmarks/weather_forecast.md`: cadence, tolerance, lead bins, IDs, penalty, heights,
      exclusions.
- [ ] `docs/tutorials/wx_hrrr_benchmark.md` and `docs/reference/wx_setup_file.md`: the
      `benchmark.cadences` / `obs_tolerance_min` / `lead_bins` keys.
- [x] `CHANGELOG.md` entry (cadence scoring and the shared helpers).
- [ ] `docs/benchmarks/California/01_Caldor.md` R08-R12: relaxed requirement text once the Caldor
      fan-out lands.

## 7. Tests

- [x] `tests/unit`: matching utility, cadence join, wind-direction penalty.
- [ ] `tests/unit`: ID generation of the generic case.
- [ ] `tests/func`: end-to-end offline `firebench wx` workflow with an hourly model and 10-min
      observations.
- [x] `tests/regression`: the Caldor weather registry pin is unchanged after the extraction.

## Notes from Brightband's Operational WeatherBench (external reference)

- A fixed lead-time/cadence grid with named milestones corresponds here to the lead bins; a
  `F01-24` / `F25-48` day-1/day-2 split is a one-line change in the setup file.
- Missing model data leads OWB to omit the model from that metric. FireBench keeps penalization
  inside a scored window, and omission only for cycles absent from the archive (see Decisions).
- OWB maps native-resolution mismatch by documented value reuse, not interpolation. The same spirit
  applies here: nearest grid cell, no temporal interpolation, and every adjustment declared in the
  file attributes.
