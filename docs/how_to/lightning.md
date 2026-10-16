# Cloud-to-Ground Lightning

FireBench stores lightning that reached the ground, a possible cause of ignition, in a standard file
under `/unstructured/lightning` (see the [standard format](../standard_format.md)). Two sources are
supported:

- **NLDN tiles** from NOAA NCEI, free and anonymous: the number of Vaisala NLDN cloud-to-ground
  strikes in each 0.1° cell (about 10 km) for each UTC day, from 1986 on. The time and position of
  each strike are not public, so a strike is known to the cell and the day.
- **A stroke file** of a lightning network (NLDN, ENTLN, ...), obtained under that network's
  licence: one row per stroke with its time, position, type, and peak current. Only the strokes to
  ground are kept.

## NLDN tiles

```python
from datetime import datetime, timezone

from firebench.acquisition.nldn_tiles import fetch_nldn_tiles
from firebench.standardize import lightning_time_series, new_std_file, standardize_nldn_tiles

bbox = (-120.8, 38.4, -119.7, 39.0)  # west, south, east, north
start = datetime(2021, 8, 10, tzinfo=timezone.utc)
end = datetime(2021, 9, 20, tzinfo=timezone.utc)

tiles = fetch_nldn_tiles(bbox, start, end)  # downloads the 2021 file (about 11 MB) and keeps the box
with new_std_file("lightning.h5", "me") as h5:
    standardize_nldn_tiles(tiles, h5)
    series = lightning_time_series(h5, "nldn_tiles")  # strikes per UTC day
```

NCEI publishes one file per year once the year is over, and one file per month for the year in
progress. A month of the window that no file covers yet is listed in the stream's `missing`
attribute, and `complete` is False.

## A stroke file

The file is a CSV with a header row. Columns are found by name, whatever the case: the time
(`time`, `timestamp`, or `date` and `time`; UTC when the value has no zone), `latitude`/`lat`,
`longitude`/`lon`, the stroke type (`type`, `cloud_ground`, ...: `G`, `CG`, or `0` for ground; `C`,
`IC`, or `1` for cloud), and optionally the peak current in kA (`peak_current`, `peakcurrent`, ...).
A file without a type column is refused: ground strokes could not be told from cloud flashes.

```python
from firebench.standardize import standardize_lightning_strokes

with new_std_file("strokes.h5", "me") as h5:
    standardize_lightning_strokes("strokes.csv", h5, bbox=bbox, start=start, end=end, network="NLDN")
    series = lightning_time_series(h5, "strokes")  # strokes per hour
```
