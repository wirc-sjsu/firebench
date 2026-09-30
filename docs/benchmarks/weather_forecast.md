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
  (diagnostic).
- **Score.** Each KPI value is turned into a score with `100 exp(-ln 2 |x| / m)`.
- **Groups and total.** Groups (for example `Air Temp 1h F01-48`) average their KPI scores, and the
  total averages the weighted groups.

A variable absent from the model or from the observations is **excluded** with its reason (`no
model data` or `no observation`) and never scored as empty. HRRR, for example, has no 10-hour fuel
moisture.

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
