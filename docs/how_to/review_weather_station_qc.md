# Review Weather-Station Data with the QC GUI

Use the weather-station quality-control (QC) GUI to inspect a FireBench HDF5 file, record station
and observation decisions, and export those decisions without changing the source file.

The same interface also reviews manifests produced by the automatic Synoptic JSON pipeline. The
pipeline creates a candidate HDF5 containing only strict automatic corrections, a machine-readable
JSON manifest, and a text audit log. It never treats a candidate as a reviewed final dataset.

## Process Synoptic JSON automatically

Create a versioned TOML policy. Required windows are optional, repeatable tables; timestamps must
include a UTC offset.

```toml
version = 5
mode = "review"

[output]
authors = "Weather data maintainers"
description = "Quality-controlled weather observations."
compression_level = 3

[thresholds]
zero_wind_fraction = 0.5
zero_wind_exclusion_fraction = 0.8
zero_wind_run_minutes = 1440.0
zero_wind_review_run_minutes = 10080.0
zero_wind_neighbor_noncalm_fraction = 0.25
zero_wind_required_neighbors = 2
temporal_break_factor = 3.0

[review]
target_pending_fraction = 0.05
required_finding_codes = ["dropout", "gap_dt", "max_var_outage", "full_outage"]

[gui]
max_var_outage_min = 1440.0
full_outage_min = 360.0
duplicate_timestamp_limit = 2

[frozen]
adaptive_percentile = 99.0
review_adaptive_percentile = 99.9
review_duration_multiplier = 2.0
automatic_adaptive_percentile = 99.99
automatic_duration_multiplier = 4.0
neighbor_count = 4
neighbor_radius_km = 100.0
required_neighbors = 2
automatic_required_neighbors = 3
minimum_neighbor_coverage = 0.5
automatic_minimum_neighbor_coverage = 0.75
neighbor_change_steps = 3.0
calm_wind_threshold = 1.5
minimum_reference_runs = 100

[frozen.minimum_duration_hours]
air_temperature = 6.0
relative_humidity = 6.0
wind_speed = 3.0
wind_gust = 3.0
wind_direction = 3.0
solar_radiation = 2.0
fuel_moisture_content_10h = 24.0

[bounds]
air_temperature = [-50.0, 60.0, "C"]
relative_humidity = [0.0, 100.0, "%"]
wind_speed = [0.0, 60.0, "m/s"]
wind_gust = [0.0, 80.0, "m/s"]
wind_direction = [0.0, 360.0, "deg"]
solar_radiation = [0.0, 1500.0, "W/m2"]
fuel_moisture_content_10h = [0.0, 60.0, "%"]

[[required_windows]]
name = "W1"
start = "2021-08-17T20:20:00-07:00"
end = "2021-09-10T23:34:00-07:00"
```

Policy versions 1 through 4 remain readable with their historical behavior so older runs stay
reproducible. Version 5 adds the explicit `review` and `conservative_auto` modes. `review` retains
the version-4 risk-based review workflow. `conservative_auto` turns every unresolved review-level
or audit-only doubt into a narrow automatic exclusion and therefore produces no pending actions.

Run the processor with explicit destinations:

```console
firebench wx-qc process wx_caldor_fire.json \
  --policy caldor_qc.toml \
  --candidate Caldor_weather_candidate.h5 \
  --manifest Caldor_weather_qc.json \
  --log Caldor_weather_qc.log
```

The processor interprets every Synoptic timestamp as a UTC wall-clock value while retaining the
station timezone as descriptive metadata. A timestamp's explicit `Z` or numeric offset does not
shift its displayed clock time. The processor also converts numeric sensor-height strings, removes
only rows that are exact duplicates across the timestamp and all observations, replaces
physical-bound violations with NaN, and excludes stations with no
finite supported observations in a required window. These deterministic actions are
`auto_accepted`; a reviewer may still override them. Conflicting duplicate timestamps and invalid
or decreasing time axes are quarantined from the candidate and require a decision.

In `conservative_auto` mode, station-wide, source, structural, time-axis, full-outage, incomplete-
window, and severe zero-wind doubts exclude the complete station. Variable-specific outages,
dropouts, ambiguous or audit-only frozen sensors, and elevated or audit-only zero wind exclude only
the affected station-variable dataset. The processor reruns QC after each new exclusion until it
reaches a fixed point. Use `review` mode when additional coverage is worth human inspection.

Source `QC_FLAGGED` metadata and incomplete required-window coverage require human review. In policy
version 4, gaps, wind-direction dropouts, longest-variable outages, and full-station outages also
create required `no_change` acknowledgement actions by default. Remove a code from
`review.required_finding_codes` only when that condition should remain a read-only audit finding.
Plausible constant values and low-confidence frozen evidence remain audit-only.

Zero-wind fractions and gap-aware runs of at least 24 hours are audit diagnostics. In policy version
4, a station with at least 80% zero among its finite wind-speed observations always receives a
pending whole-station exclusion action; no overlapping automatic zero-wind correction is applied.
A station from 50% up to 80% zero also always requires review: seven-day ranges propose setting only
wind speed to NaN, while fragmented or shorter zeros require a `no_change` acknowledgement. Below
50%, a run becomes actionable only after seven days and retains the conservative version-3 triage:
all-zero or sufficiently neighbor-corroborated runs may be automatic and ambiguous runs require
review. Shorter calm periods preserve the reported zeros, and a wind-speed finding never removes
gust or direction automatically.

Frozen-sensor checks use elapsed time rather than sample count. FireBench estimates each sensor's
reporting resolution from its finite values, falling back to the dataset-wide estimate for that
variable, and reports half the inferred step as quantization uncertainty. This is not a claim about
the sensor's calibration or total measurement accuracy. A plateau must exceed both its variable
duration floor and a 99th-percentile diagnostic threshold. Review requires a complete plateau longer
than both twice the variable floor and the station-specific 99.9th percentile; pooled variable
durations are used until the sensor has 100 completed runs. At least two of the four nearest usable
stations within 100 km must change by three reporting steps during the interval. Multiple ambiguous
ranges are grouped into one action per station-variable.

Automatic correction is deliberately harder: the range must exceed four times the duration floor
and the 99.99th percentile, have known target resolution, have three changing neighbors with at least
75% temporal coverage, and show activity in another variable at the target station. Other plateaus
remain audit findings without a proposed data change.

Every operation has a content-derived `WXQC-…` ID. The manifest separates the decision state from
candidate/final application state and retains decision history, source and policy hashes, linked
findings, selectors, effects, and artifact paths. The text log repeats the findings and actions in
a human-readable form and is regenerated after decisions or finalization. Outputs are written
atomically; use `--overwrite` only when replacing an intentional previous run.

Open the review directly with:

```console
firebench wx-qc review Caldor_weather_qc.json
```

Opening a version 2, 3, 4, or 5 policy manifest also loads its normalized bounds and QC thresholds into the GUI, so
the Assertions and Variable Stats tabs use the same frozen-sensor settings as the automatic run.

The **Actions** tab filters by status or severity, supports multi-selection decisions, and includes
unlinked audit-only findings as read-only rows. Double-click an action or finding to open Station
Detail on its variable and time range. Matching samples are outlined and the plot is zoomed to the
active range; use **Previous range** and **Next range** for grouped frozen or zero-wind issues.
Selecting a different Actions row preloads that issue into the hidden Detail panel without changing
tabs. Sorting, filtering, or refreshing Actions immediately recalculates the Detail review queue and
its displayed position; double-click still controls when the interface switches to Detail.

The detail review strip shares the reviewer and comment fields with Actions. It enables **Accept**
and **Reject** for data-changing operations, **Acknowledge** and **Reject** for `no_change`
operations, and **Reset** for completed decisions. After a decision, it advances to the next visible
pending action using the Actions tab's current filter and sort order, wrapping once if the review
started in the middle of the list. Audit rows show the same evidence but have no decision controls.

Editing creates a new content-derived operation ID and marks the old operation superseded. A
reviewer identity is mandatory for accept, reject, acknowledge, edit, and finalization events.
Automatic actions need no confirmation, but remain overridable. The Actions tab reports the pending
count against human-review actions only; automatic actions no longer dilute the review fraction.
Exceeding the policy target is diagnostic and does not block processing. A decision comment is
optional and is cleared after the decision is saved.

## Understand review decisions and data effects

**Accept means apply the proposed operation; it does not mean that the source data is acceptable.**
For example, accepting a `SRCFLAG` operation excludes the station, while rejecting it keeps the
station. Always read the Effect and Message columns before deciding an action.

The candidate HDF5 is a fixed preview created during `wx-qc process`. Saving a human decision does
not rewrite that candidate. In particular, rejecting an automatically applied operation does not
undo it in the candidate. Finalization instead rebuilds a new HDF5 from the hash-verified source
JSON and applies the completed decisions.

Control | Decision status | Effect
--- | --- | ---
**Accept** | `accepted` | Apply the proposed effect when building the final HDF5.
**Reject** | `rejected` | Do not apply the proposed effect in the final HDF5. Source observations are preserved unless they are structurally unsafe to standardize.
**Acknowledge** | `acknowledged` | Resolve a `no_change` action after reviewing its warning. No data are changed. Other effect types cannot be acknowledged.
**Reset** | `pending` or `auto_accepted` | Undo the review decision. Human-review actions become pending again; automatic actions return to their automatic decision.
**Edit...** | old action `superseded`; replacement `pending` | Create a new content-derived operation with edited selector/effect JSON. The old operation remains in the audit history.
**Finalize...** | no action status change | Verify that nothing is pending, verify the source hash, and construct the final HDF5. The button is disabled while actions remain pending.

Automatic operations start as `auto_accepted`. A reviewer can accept or reject most of them, but
timestamp and numeric sensor-height normalization are required to standardize the file; rejecting
a `TIME` or `META` operation blocks finalization. A structurally invalid station is quarantined
from the candidate because it cannot be represented safely. Accepting its `EXCL` action confirms
the exclusion; if the station is needed, repair the source and rerun the processor rather than
trying to restore malformed observations with Reject.

### Operation codes

The operation code is the middle component of an ID such as `WXQC-FROZEN-...`.

Code | Default | Typical message | Effect when applied
--- | --- | --- | ---
`EXCL` | Review | `Station has no timestamps`, `Observation arrays do not align with timestamps`, `Timestamp axis has N backwards jump(s)`, or `Conflicting records at N duplicate timestamp(s)` | Quarantine and exclude a station whose structure cannot be standardized safely.
`TIME` | Automatic | `Interpreted N Synoptic timestamps as UTC wall-clock values` | Treat every displayed source clock value as UTC while retaining station-timezone metadata. Explicit offsets are ignored; timestamps are not rounded, resampled, or forced onto an hourly boundary.
`DUP` | Automatic | `Removed N identical duplicate records` | Remove only later rows whose timestamp and complete observation content exactly match an earlier row.
`META` | Automatic | `Converted N numeric sensor-height strings to numbers` | Convert finite numeric sensor-height metadata such as `"10.0"` to a number. Observation values are unchanged.
`BOUND` | Automatic | `Replaced N values outside [low, high] unit with NaN` | Set the named variable to NaN at the listed timestamps. The row and other variables remain present.
`EMPTY` | Automatic | `Excluded station with no finite supported observations` | Exclude the whole station.
`WINDOW` | Automatic | `Excluded station with no finite supported observations in NAME` | Exclude the whole station when it has no usable supported variable in a required policy window.
`SRCFLAG` | Review | `Synoptic source metadata marks this station QC_FLAGGED` | Accept to exclude the whole station; reject to retain it.
`ZEROWIND` | Automatic or review | `Exclude station: 80.0% ... is zero`, `Review N zero-wind range(s)`, or `Acknowledge elevated zero wind ...` | At 80% or more zero wind, propose excluding the station. From 50% to 80%, require review of a wind-speed-only range change or a non-mutating acknowledgement. Below 50%, only qualifying seven-day ranges are actionable.
`FROZEN` | Automatic or review | `Replace N near-certain/ambiguous frozen VARIABLE range(s) with NaN` | Set grouped sensor ranges to NaN. The selector retains range-level duration, thresholds, resolution, quantization uncertainty, neighbor coverage, and same-station activity.
`ACK` | Review | `Acknowledge ... without changing data: ...` | Record required review of non-mutating conditions. Version 4 defaults to acknowledgement actions for incomplete windows, gaps, dropouts, variable outages, and full-station outages; low-confidence plateaus remain audit-only.
`SAFEEXCL` | Automatic in conservative mode | `Conservative-auto excluded ... for QC doubt` | Exclude the complete station for station-wide doubt or only the named station-variable dataset for variable-specific doubt. The selector lists every triggering finding and original action.
`MANUAL` | Accepted when created | `Manually exclude station: ...`, `Manual range removal: ...`, or `Manually omit complete variable ...` | Apply a reviewer-authored station exclusion, set selected variable/range values to NaN, or omit one station variable.

The same station can have several operations. An accepted `exclude_station` effect takes precedence
over all narrower effects, and an accepted `exclude_variable` effect takes precedence over value-
or range-level effects for that variable. Every shadowed operation remains in the manifest and log
for auditability.

### Effect and selector values

Effect kind | Data result
--- | ---
`exclude_station` | Omit the complete `station_<ID>` group from the final HDF5.
`exclude_variable` | Omit the named variable dataset from one station in the final HDF5. The station, time axis, and other variables remain present.
`normalize_timestamps` | Interpret every valid Synoptic timestamp's displayed clock value as UTC.
`remove_identical_duplicates` | Delete the selected duplicate rows while retaining alignment across every observation array.
`normalize_sensor_height` | Change numeric sensor-height metadata from string to numeric form.
`set_nan` | Replace values for the listed variables at explicit selector timestamps with NaN.
`set_nan_ranges` | Replace values for the listed variables wherever a predicate, timestamp, or inclusive time range matches. It does not remove time records.
`no_change` | Preserve the data and store only the reviewer acknowledgement and comment.

The Selector column defines the exact scope. It can contain raw row indices, timestamps, inclusive
UTC ranges, a value predicate such as `wind_speed == 0`, a required window, or a station-wide
reason. For a multi-range action, the table shows the first range and the number of additional
ranges. Inspect the selector before accepting because the message normally reports only the
longest or aggregate condition.

The Application column reports what happened in the candidate or final artifact; it is separate
from the review Decision. The candidate may say `applied` for an automatic action that a reviewer
later rejects because the rejection takes effect only in the rebuilt final file.

### Other GUI review controls

GUI control | Effect
--- | ---
**Mark Greenlit** | Mark a station as reviewed and hide it from the default review lists. It does not alter observations or apply an automated-manifest operation.
**Un-greenlit** | Return a greenlit station to the active review lists. It does not alter data.
**Add to Skip List** | Exclude the station from a cleaned export. When a single-station exclusion is added while an automated manifest is open, the GUI records an accepted `MANUAL` `exclude_station` operation with the reviewer and reason.
**Remove records** | Select one point or inclusive range in Station Detail and set the selected variable values to NaN in the cleaned output. With an automated manifest open, this becomes an accepted `MANUAL` `set_nan_ranges` operation.
**Omit variable from output** | Select a station and a stored variable in Station Detail, optionally enter a reason, and omit that complete variable dataset from the final HDF5. This creates an accepted `MANUAL` `exclude_variable` operation and requires an open automated manifest. For the combined **wind** plot, select `wind_speed`, `wind_direction`, or `wind_gust` first.

When useful, use the optional inline comment to record why evidence justified a decision. The
comment is applied to every selected operation. Bulk decisions are appropriate only when the
selected operations share both the same effect and the same review rationale.

Finalization is disabled while any action is pending. Once review is complete, either use the GUI
or run:

```console
firebench wx-qc finalize Caldor_weather_qc.json \
  --output Caldor_weather_final.h5 \
  --reviewer "Reviewer Name"
```

Finalization verifies the source SHA-256 and rebuilds from that immutable JSON rather than copying
the candidate. Accepted station and variable exclusions dominate narrower range operations;
shadowed actions remain visible in the audit record. The output records the run, source, policy,
mode, decision digest, stage, and final reviewer as HDF5 attributes. Conservative-auto finalization
also reruns QC and fails rather than publishing a file if a new unresolved doubt appears.

## Install and launch

Install FireBench in a Python environment:

```console
python -m pip install firebench
```

The GUI uses Tk, which is supplied by the operating system rather than by FireBench. Verify that
it is available before launching:

```console
python -m tkinter
```

That command should open a small Tk test window. If the import fails, install the Tk package for
your Python distribution. Common package names are `python3-tk` on Debian/Ubuntu and
`python3-tkinter` on Fedora. The installers from python.org include Tk on Windows and macOS.
FireBench also needs a graphical desktop; a terminal-only or headless session cannot display the
application.

### Install Tk on macOS with Homebrew

Homebrew packages the Tk bindings separately for each Python minor version. First check the
version used by the environment where FireBench is installed:

```console
python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
```

Install the matching formula. For example, use this command for Python 3.13:

```console
brew install python-tk@3.13
```

Replace `3.13` with the reported version, such as `3.10`, `3.11`, `3.12`, or `3.14`. See the
[Homebrew `python-tk` formula](https://formulae.brew.sh/formula/python-tk@3.14) for the currently
available versions.

The formula is built for the corresponding Homebrew Python. It does not add Tk to a Python
installed by pyenv, Conda, or another distributor. If `python -m tkinter` still reports
`No module named '_tkinter'`, identify the active interpreter:

```console
python -c "import sys; print(sys.executable)"
```

Either install Tk using that Python distributor's instructions or create the environment with the
matching Homebrew Python. For Python 3.13, for example:

```console
brew install python@3.13 python-tk@3.13
"$(brew --prefix python@3.13)/bin/python3.13" -m venv .venv
source .venv/bin/activate
python -m pip install firebench
python -m tkinter
```

The last command should open the Tk test window. Close it before launching the FireBench GUI.

Launch the GUI with:

```console
firebench wx-qc
```

Select **Open H5**, choose a weather-station file, and allow incremental loading to finish before
reviewing dataset-wide outage values. Use **Settings** to change assertion visibility, physical
bounds, run lengths, or outage-warning thresholds. Settings are applied only after every value
passes validation.

## Use the station map

The **Map** tab displays weather stations over the standard OpenStreetMap road map. Tile detail
updates automatically after you zoom or pan with the Matplotlib toolbar. Fire perimeters, station
colors, wind arrows, missing-data markers, and selection popups remain above the road layer.

The road map requires network access. Clear **Road map** to use the plain longitude/latitude map
without requesting tiles. If a request fails, the GUI keeps the plain map, turns the option off,
and shows the complete error in a dialog and in the terminal log; select **Road map** again to
retry. Downloaded tiles are cached under the user cache directory so revisiting an area does not
request the same tiles again. The GUI requests only the current visible extent and does not provide
map prefetch or offline downloads. Map data is © OpenStreetMap contributors.

## Expected HDF5 structure

The input must contain a `time_series` group with one group per station. Station group names use
the `station_<station-id>` form. Each station group contains:

- a one-dimensional numeric `time` dataset, expressed in minutes from its ISO 8601
  `time_origin` attribute;
- one-dimensional sensor datasets aligned with `time`, with missing readings represented by
  floating-point NaN values; and
- optional station attributes `name`, `position_lat`, `position_lon`, `position_alt`, `state`,
  `timezone`, and `providers`.

The GUI displays arbitrary sensor datasets. It provides physical bounds and specialized behavior
for these standard FireBench variable names:

Variable | Default valid range | Unit
--- | ---: | ---
`air_temperature` | -50 to 60 | °C
`relative_humidity` | 0 to 100 | %
`wind_speed` | 0 to 60 | m/s
`wind_gust` | 0 to 80 | m/s
`wind_direction` | 0 to 360 | degrees
`solar_radiation` | 0 to 1500 | W/m²
`fuel_moisture_content_10h` | 0 to 60 | %

An absent, malformed, non-finite, duplicate, or decreasing time axis is reported as a QC issue.
Cadence, gap, and outage calculations that require an ordered time axis are then shown as
unavailable rather than calculated from invalid timestamps.

## Understand the assertions

Assertions identify observations that deserve review; they do not alter the input. **Errors**
indicate invalid time metadata or values outside physical bounds. **Warnings** indicate suspicious
timing, dropout, frozen values, or outages. The Overview, station badges, Detail tab, variable
highlighting, and issue-count map all honor the selected severity and category filters.

Assertion | Default semantics
--- | ---
Invalid time axis | Error when the time dataset or its `time_origin` cannot be parsed.
Negative time jumps | One backward jump is a warning; more than one is an error.
Duplicate timestamps | Warning for 1–5 duplicates; error above 5.
Wind-direction dropout | Warning for at least 3 contiguous missing wind-direction samples while wind speed is known and greater than zero.
Large observation gap | Warning when the largest interval is more than 100 times the median interval.
Physical bounds | Error when a named variable has a value strictly below its lower bound or above its upper bound.
Frozen sensors | A plateau must exceed a variable-specific elapsed-time floor and, when enough reference runs exist, the dataset's 99th-percentile plateau duration. Two changing nearby stations confirm a warning; insufficient neighbors produce a low-confidence warning without a removal proposal; constant neighbors suppress it. NaNs and qualifying time gaps break a plateau. Calm wind and nighttime zero solar radiation are treated as plausible regimes.
Variable outage | Warning when the longest continuous outage for any variable exceeds 1,440 minutes by default.
Full-station outage | Warning when the longest continuous period in which all available variables are down exceeds 360 minutes by default.

Frozen duration is measured in hours, while outage settings are minutes. A qualifying temporal gap
is at least three times the station's median sampling interval. Leading and trailing gaps relative
to the full dataset extent are considered as separate outage candidates. Raw NaN counts and
percentages remain visible for inspection but are not assertion thresholds.

The GUI also reports cumulative outage percentage as information only:

- ordinary variables use the global dataset duration as the denominator;
- wind direction and wind gust use only intervals whose wind-speed endpoints are known and
  greater than zero;
- calm or unavailable wind speed is excluded and breaks an eligible outage run; and
- cumulative outage percentage never creates a warning.

## Record review decisions

A station begins **undecided**. Mark it **greenlit** when it is acceptable, or **skipped** when the
entire station should be excluded and supply a reason. These states are mutually exclusive:
greenlighting a skipped station removes its skip decision, and skipping a greenlit station removes
its approval.

For a localized problem, select a range in a single-station time-series plot and create a
**record removal** for one variable or for all variables. The range endpoints are inclusive.
Removal entries can be reviewed, edited, or deleted in the Skip List tab. They are decisions only:
plots continue to show the original observations until an export applies the removals.

## Save and restore sessions

**Save Session** writes versioned UTF-8 JSON containing the HDF5 path, QC settings, station
decisions, record removals, current station, map mode, road-map visibility, and Overview column
visibility. Version 3 introduced the optional automated-QC manifest reference and reviewer identity;
version 4 stores resolution-aware frozen-sensor settings, and version 5 stores review-triage settings.
Versions 1 through 4 remain readable.
The session contains no station data or cached statistics. On restore, the complete JSON shape and
field types are validated before application state changes, then the referenced HDF5 file is reloaded
and all statistics are recomputed. If a restored file somehow marks a station both skipped and
greenlit, the skip decision wins.

Closing a session with work present writes
`~/.firebench/wx_qc_autosave.json`; the next launch offers to restore it. Legacy pickle sessions
are intentionally unsupported and are never deserialized.

## Choose an export

All text exports use UTF-8, and all destination files are assembled as temporary siblings before
atomic replacement where the filesystem supports it.

**Export Python** writes `skip_stations`, `skip_reasons`, and `remove_records` Python literals for
use in another workflow. When an HDF5 file is loaded, it also writes a sibling `<fire>_QC.json`
session snapshot. The Python file records decisions but does not apply them by itself.

**Export Script** writes a standalone processing script for a Synoptic JSON source. The script
interprets ISO timestamp clock values as UTC, removes rows that duplicate both timestamp and every
sensor value, standardizes the JSON into a new FireBench HDF5 file, omits skip-listed stations, and
sets selected floating-point record ranges to NaN. Its JSON and output paths are the values entered
in the export dialog; review them before running the script. The script creates or replaces its
output, not the HDF5 currently open in the GUI.

**Export cleaned H5** makes a copy of the currently open HDF5, deletes skip-listed station groups,
and sets selected inclusive ranges to NaN in retained floating-point sensor datasets. Greenlit
status has no effect on the copy. The source HDF5 is never modified. The completion dialog reports
omitted stations, modified retained stations, values set to NaN, and any datasets it could not
change.

Inspect exported files before publishing them. In particular, neither a greenlit decision nor the
absence of visible assertions proves that a station is scientifically suitable for every
benchmark.
