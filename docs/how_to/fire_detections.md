# Satellite Fire Detections from FIRMS and GOES

FireBench downloads satellite active-fire detections, with their fire radiative power (FRP), and
stores them in a standard file under `/unstructured/fire_detections` (see the
[standard format](../standard_format.md)). Two sources are supported:

- **VIIRS and MODIS** through NASA FIRMS. FIRMS needs a free MAP_KEY
  (<https://firms.modaps.eosdis.nasa.gov/api/map_key/>). The times each satellite passed over the
  domain come from NASA CMR, which needs no key.
- **GOES-East and GOES-West** fire product (`ABI-L2-FDCC`, continental United States) from the NOAA
  archive on AWS, anonymous.

## Download

Store your FIRMS key once:

```bash
firebench keys set firms
```

Download the detections of a domain and a UTC window as one bundle. The bundle keeps the CSV FIRMS
returned for each request, the overpasses found in CMR, and every request that failed. It never
holds your key.

```bash
firebench data firms --bbox -120.8,38.4,-119.7,39 --start 2021-08-14T00:00Z --end 2021-08-21T00:00Z -o firms.json
```

Download the GOES scans of the same window, one every 30 minutes, into a directory laid out like the
buckets. `--dry-run` prints the number of scans and their size first: a scan is about 0.4 to 0.8 MB.

```bash
firebench data goes-fdc --bbox -120.8,38.4,-119.7,39 --start 2021-08-14T00:00Z --end 2021-08-21T00:00Z --step 30 -o goes --dry-run
```

## Standardize

```python
from datetime import datetime, timezone
from pathlib import Path

from firebench.acquisition import goes_fdc
from firebench.standardize import new_std_file, standardize_firms_bundle, standardize_goes_fdc

bbox = (-120.8, 38.4, -119.7, 39.0)
start = datetime(2021, 8, 14, tzinfo=timezone.utc)
end = datetime(2021, 8, 21, tzinfo=timezone.utc)

with new_std_file("detections.h5", "Your Name") as h5:
    standardize_firms_bundle(Path("firms.json"), h5)
    for segment in goes_fdc.goes_segments(start, end):
        scans = goes_fdc.select_scans(goes_fdc.local_fdc_scans(Path("goes"), segment), 30)
        if scans:
            fetched = goes_fdc.local_fetched_scans(scans, Path("goes"))
            standardize_goes_fdc(fetched, h5, bbox=bbox, start=start, end=end, time_step_min=30)
```

`goes_fdc.fetch_fdc_scans` downloads the scans instead of reading a directory, and deletes each file
once it is read, so a long window needs little disk space.

## FRP series

```python
from firebench.standardize import frp_time_series, list_fire_detection_streams

for stream in list_fire_detection_streams("detections.h5"):
    series = frp_time_series("detections.h5", stream, min_confidence="nominal")
```

`frp_time_series` gives one entry per observation: the FRP total in MW, 0 when the sensor looked and
saw no fire, NaN when every detection lacks FRP. A time the sensor did not look at has no entry.
Sensors differ in pixel size and sensitivity: compare a stream with itself, not with another.
