# Weather Forecast Benchmark

The weather-forecast benchmark scores one forecast cycle of a weather model against weather-station
observations. It is generated for any domain and window by `firebench wx` (see
[Benchmark HRRR forecasts against weather stations](../tutorials/wx_hrrr_benchmark.md)); it is not a
certified benchmark case. Its observations are automatically quality-controlled and tagged
`data_tier: provisional`, which the score card states.

## Inputs

**Observations.** A FireBench standard file with one `/time_series/station_<STID>` group per
station, as produced by the Synoptic standardization and the weather QC. Sensor heights and their
source confidence follow [Weather sensor heights](../reference/weather_sensor_height.md).

**Model.** One file per forecast cycle with the same station groups. Each group holds `time` and at
least one of `air_temperature`, `relative_humidity`, `wind_speed` and `wind_direction`, with `units`
and, for trusted-source scoring, a numeric `sensor_height` and `sensor_height_units`. Values are
given at the model's own output times; hourly output is enough. The model file must contain every
station that the benchmark selects.

## Cadence join

The benchmark compares model and observations on mandatory timestamps: the UTC top-of-hour marks
of the scored window with `hour % cadence == 0`.

- **Observation.** The nearest *finite* sample within `±obs_tolerance` (10 min by default). Missing
  observations are never interpolated. The tolerance must stay below half the cadence, so one
  sample never serves two marks.
- **Model.** The value at the mark within `±model_tolerance` (60 s). A missing or NaN model value
  is penalized, as in the Caldor weather benchmark: `-1e6`, or the direction opposite to the
  observation for `wind_direction`.
- **Coverage.** A station observing fewer than `min_coverage` (50 %) of the marks of a lead bin is
  excluded from that bin, and the exclusion is listed in the result JSON (`cadence_exclusions`).

## Lead-time bins

Each forecast cycle is scored over lead-time bins, by default hours 1–48. Hour 0 is the analysis.
Operational analyses such as HRRR's assimilate surface observations, so hour 0 is partly scored
against its own inputs. It is therefore scored in **informational** groups of weight 0: displayed on
the score card, but excluded from both the numerator and the denominator of the total.

## KPIs

For each variable, cadence, and lead bin:

| Variable | Metrics | Unit | Normalization parameter m |
|---|---|---|---|
| Air temperature | MAE, RMSE, bias | degC | 5 |
| Relative humidity | MAE, RMSE, bias | % | 15 |
| Wind speed | MAE, RMSE, bias | m/s | 5 |
| Wind direction | circular bias | degree | 45 |
| 10-hour fuel moisture | MAE, RMSE, bias | % | 5 |

- **Summaries.** Each metric is computed per station, then summarized over stations by its minimum,
  mean and maximum.
- **Station sets.** Trusted-source stations (TSO) have weight 1; all stations have weight 0
  (diagnostic). Every fuel-moisture sensor is in TSO, whatever its sensor-height confidence.
- **Score.** Each KPI value is turned into a score with `100 exp(-ln 2 |x| / m)`.
- **Groups and total.** Groups (for example `Air Temp 1h F01-48`) average their KPI scores, and the
  total averages the weighted groups.

A variable absent from the model or from the observations is **excluded** with its reason (`no
model data` or `no observation`) and never scored as empty. HRRR, for example, has no 10-hour fuel
moisture.

## Fire-weather diagnostics

Two families of KPIs evaluate what matters for fire, beyond the mean error of each variable. They
are optional: list them in `benchmark.diagnostics` of the setup file. Their groups have weight 0,
like the analysis: they are displayed, and the total keeps its definition.

**Fire-weather indices** (`fire_weather_index`). An index is computed from the station variables,
the same way for the model and for the observations, at each hour where every input is observed.
It is then scored like a variable: MAE, RMSE, and bias per station, summarized over stations.

| Index | Inputs | Unit | Normalization parameter m |
|---|---|---|---|
| Vapour pressure deficit (VPD) | air temperature, relative humidity | hPa | 10 |
| Fosberg fire weather index | air temperature, relative humidity, wind speed | - | 10 |

- The saturation vapour pressure is Bolton's (1980). The Fosberg index (1978) uses the equilibrium
  moisture content of Simard (1968) and is not capped at 100.
- The Fosberg index is defined with the 20 ft wind. Here the wind is the one at each station's
  sensor height, to which the model wind was brought, so both sides use the same height.

**Threshold events** (`event_threshold`). An event occurs at an hour of a station when its
condition holds. Hits, misses, and false alarms are counted over every station of the set and
every hour of the lead bin at once (the `pooled` summary): a ratio per station would rest on too
few events.

| Event | Condition |
|---|---|
| Low RH | relative humidity ≤ 20 % |
| Strong wind | wind speed ≥ 4.5 m/s |
| Critical fire weather | both at the same hour |

| Metric | Definition | Score |
|---|---|---|
| POD, probability of detection | hits / (hits + misses) | 100 × POD |
| FAR, false alarm ratio | false alarms / (hits + false alarms) | 100 × (1 − FAR) |
| CSI, critical success index | hits / (hits + misses + false alarms) | 100 × CSI |

- A ratio without a denominator is not computed: an event that was not observed has no detection
  rate. The KPI is listed in `ignored_benchmarks` and its reason in `ignored_reasons`.
- A station is in a set when the set includes it for every input. A station observing fewer than
  `min_coverage` of the hours, with every input, is excluded.
- An hour where the model misses an input is penalized: `-1e6` for an index, and a wrong forecast
  for an event (a miss when the event was observed, a false alarm otherwise).
- A diagnostic whose input the model or the observations lack is excluded with its reason, for
  example `no model data for wind_speed`.

## Benchmark IDs

Benchmark IDs are semantic and do not depend on the order of the setup lists:
`WX-{variable}-{metric}-{stat}-{station set}-{cadence}H-F{lead bin}`. For example,
`WX-AT-MAE-MEAN-TSO-1H-F0148` is the mean over trusted-source stations of the air-temperature MAE,
hourly, for lead hours 1 to 48.

| Code | Meaning |
|---|---|
| `AT`, `RH`, `WS`, `WD`, `FM10` | air temperature, relative humidity, wind speed, wind direction, 10-hour fuel moisture |
| `MAE`, `RMSE`, `BIAS`, `CBIAS` | metrics (`CBIAS` is the circular bias) |
| `MIN`, `MEAN`, `MAX` | summary over stations |
| `VPD`, `FFWI` | vapour pressure deficit, Fosberg fire weather index |
| `RHLOW`, `WSHIGH`, `CFW` | events: low RH, strong wind, critical fire weather |
| `POD`, `FAR`, `CSI` | event metrics |
| `POOLED` | counted over every station and hour at once |
| `TSO`, `ALL` | trusted-source stations, all stations |

## HRRR adapter

The embedded HRRR adapter writes the model file of a cycle from the HRRR surface product (`wrfsfc`).
It declares every adjustment in the file:

- **Sampling.** Values are taken at the nearest grid cell, at HRRR's native hourly valid times.
- **Terrain.** Each station group records `model_terrain_height`, `station_elevation`, and their
  difference `terrain_height_difference`, which is a first-order temperature bias in mountains.
- **Wind direction.** The grid-relative 10 m winds are rotated to earth-relative components. The
  direction is assumed height-invariant in the surface layer.
- **Wind speed.** It is brought from 10 m to the station sensor height with the neutral log law and
  HRRR's surface roughness `SFCR` (`height_adjustment`, `z0_source` attributes).
- **Temperature and humidity.** The 2 m values are assigned to screen-level sensors (1–3 m).
  Outside that band, the native 2 m height is declared, so the station leaves the trusted-source
  set instead of being compared at a different height.

## Caveats

- HRRR values are instantaneous at the valid time, while RAWS wind is a 10-minute average.
- Cycles missing from the model archive are omitted and listed; hours missing *inside* a scored
  cycle are penalized.
- Minimum and maximum summaries of a signed bias select the most extreme station in each direction,
  so a single station with an opposite mean wind direction dominates the circular-bias minimum and
  maximum.
