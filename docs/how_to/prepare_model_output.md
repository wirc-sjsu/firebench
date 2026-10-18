# Prepare a model output for a benchmark case

A benchmark case defined by a document (schema `fb-case-v1`, see
[Define a benchmark case from a dataset](define_benchmark_case.md)) is scored against an
observation file that its keeper may not give out: it can hold values whose licence forbids passing
them on. What a model output needs from that file is its layout, its grids and positions, and its
observation times, never the observed values. FireBench writes them in two files:

- a **model-output template**, the observation file's layout for the case, with no observed value;
- a **requirement list**, what FireBench will check in the model output, with the stations it
  selected.

The keeper of the case makes both and gives them to the modeller, for example in a *benchmark kit*
with the licences of the data and an adapter config.

```bash
firebench case template case.json obs.h5 -o template.h5
firebench case requirements case.json obs.h5 -o requirements.json
```

`case.json` is the definition. Give `-` instead to read the definition kept in `obs.h5`
(`/benchmark_case/definition`). From Python, the functions are `write_model_output_template` and
`case_requirements` in `firebench.benchmarks.fire_case_template`.

## What the template holds

The template is a standard file with the root attribute `firebench_template = "model-output"` and
the `case_definition_sha256` of the case. It holds the case's definition and, at the paths of the
observation file, only the groups the case scores:

| Family | In the template | Emptied |
|---|---|---|
| `fire_perimeters` | each perimeter group of the definition, with its `time` | no `rel_path`, `sha256`, or `file_size_bytes`, no KML file, no burnt area |
| `burn_severity_cbi` | the CBI group: `position_lat`, `position_lon`, `crs`, `units`, `_FillValue` | every value is the `_FillValue` |
| `canopy_cover_loss` | the RAVG canopy cover loss group, as for `burn_severity_cbi`; not the LANDFIRE layers, read from the observations | every value is the `_FillValue` |
| `building_damage` | the buildings' `position_lat` and `position_lon` | every damage is `""`, except `"Inaccessible"`, a building that was not surveyed |
| `weather_stations` | each station the case selects, with its attributes, its `time`, and each variable it is selected for, with `units` and the sensor height attributes | every value is NaN |
| `radar_plume` | the model's plume group (`/spatial_3d/plume`), empty, with a `description` and the `required_datasets` | the model writes it on its own grid: `time`, `position_lat`, `position_lon`, `position_z` (m above mean sea level), `passive_tracer`, `wind_u`, `wind_v`, `wind_w` (earth-relative), each `(time, z, y, x)` |

Each group keeps its licence attributes (`license`, `redistribution_allowed`,
`public_access_level`, `data_use_restrictions`, `data_source`). Nothing else is written: satellite
detections, radar, lightning, and every other group of the observation file stay out.

A template is never an observation file: `load_case`, `check_case`, and `run_benchmark` refuse one
("This file is a model-output template, not an observation file.").

## Read the requirement list

`requirements.json` has the schema `fb-requirements-v1`:

- `case` names the definition by its SHA-256 and its parameter set;
- `periods` are the case's periods, in UTC;
- `requirements` has one entry per requirement of the case, with the KPIs it runs (`kpis`) and the
  KPI groups that hold them (`kpi_groups`). A model output that does not meet a requirement is not
  scored on its KPIs; the other KPIs still are;
  - for fire perimeters, burn severity, and building damage, `datasets` gives each dataset the
    model output must hold and the attributes it must carry;
  - for a weather variable, `stations` gives, per period and station set (`TSO` or `ALL`), the
    stations FireBench selected (`included`) and why it left out the others (`excluded`). The model
    output must hold `time` and the variable for every station included somewhere;
- `summary` counts the families, periods, perimeters, and the stations and sensor heights of each
  weather variable.

## Write the model output on the template

Write a new standard file (`new_std_file`) with the template's paths. Do not edit the template in
place: the model output must not carry `firebench_template`.

- **Fire perimeters.** For each perimeter group, contour the model's fire arrival time at the
  group's `time` and write a KML file beside the output. Give the group `rel_path`, `sha256`, and
  `file_size_bytes` of that file, and the same `time`.
- **Burn severity.** Interpolate the model onto the template's grid (`position_lat`,
  `position_lon`, `crs`) and write the classes with the template's `units` and `_FillValue`.
- **Building damage.** Give one status per building of the template, in the same order, and pass
  `"Inaccessible"` through unchanged.
- **Weather stations.** For each station and variable of the template, give the model's value at
  each time of the template's `time` that lies in the periods. FireBench compares the model and the
  observation sample by sample, so the station's series must span the period with as many samples
  as the observation.

For a TSO station of a variable that depends on the sensor height, prepare the model's value at
the observation's trusted height and record it; FireBench includes the station only when the two
heights agree within 0.01 m:

```python
from firebench import adapter_common

height = adapter_common.trusted_observation_sensor_height(template, "station_ABC", "wind_speed")
dataset[...] = interpolate_wind(model_profile, target_height=height)
adapter_common.write_model_sensor_height_metadata(dataset, height)
```

`trusted_observation_sensor_height` reads the template as it reads an observation file: the
template keeps every sensor height attribute. See [Convert model-specific output](convert_model_output.md)
for the rest of an adapter's work.
