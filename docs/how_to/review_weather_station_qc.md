# Review Weather-Station Data with the QC GUI

Use the weather-station quality-control (QC) GUI to inspect a FireBench HDF5 file, record station
and observation decisions, and export those decisions without changing the source file.

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

Launch the GUI with:

```console
firebench wx-qc
```

Select **Open H5**, choose a weather-station file, and allow incremental loading to finish before
reviewing dataset-wide outage values. Use **Settings** to change assertion visibility, physical
bounds, run lengths, or outage-warning thresholds. Settings are applied only after every value
passes validation.

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
Frozen values | Warning at 10 contiguous equal samples by default. NaNs and qualifying time gaps break a run. Wind speed and gust are exempt; zero solar radiation is exempt; 10-hour fuel moisture uses a fixed 15-sample threshold.
Variable outage | Warning when the longest continuous outage for any variable exceeds 1,440 minutes by default.
Full-station outage | Warning when the longest continuous period in which all available variables are down exceeds 360 minutes by default.

Run lengths are counts of samples, while outage settings are minutes. A qualifying temporal gap
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
decisions, record removals, current station, map mode, and Overview column visibility. It contains
no station data or cached statistics. On restore, the complete JSON shape and field types are
validated before application state changes, then the referenced HDF5 file is reloaded and all
statistics are recomputed. If a restored file somehow marks a station both skipped and greenlit,
the skip decision wins.

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
normalizes ISO timestamps to UTC, removes rows that duplicate both timestamp and every sensor
value, standardizes the JSON into a new FireBench HDF5 file, omits skip-listed stations, and sets
selected floating-point record ranges to NaN. Its JSON and output paths are the values entered in
the export dialog; review them before running the script. The script creates or replaces its
output, not the HDF5 currently open in the GUI.

**Export cleaned H5** makes a copy of the currently open HDF5, deletes skip-listed station groups,
and sets selected inclusive ranges to NaN in retained floating-point sensor datasets. Greenlit
status has no effect on the copy. The source HDF5 is never modified. The completion dialog reports
omitted stations, modified retained stations, values set to NaN, and any datasets it could not
change.

Inspect exported files before publishing them. In particular, neither a greenlit decision nor the
absence of visible assertions proves that a station is scientifically suitable for every
benchmark.
