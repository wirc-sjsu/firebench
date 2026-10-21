# Weather Radar Volumes from NEXRAD

FireBench downloads the NEXRAD Level II volume scans of the WSR-88D weather radars and stores them
in a standard file under `/spatial_3d/radar/<SITE>` (see the
[standard format](../standard_format.md)), as polar sweeps cropped to a domain. A fire plume shows in
reflectivity, and its low correlation coefficient tells it from rain. The archive is the NOAA Open
Data bucket on AWS (`unidata-nexrad-level2`), anonymous, from 1991 on; FireBench reads volumes with
250 m gates (2008 on).

Reading Level II needs the `radar` extra:

```bash
pip install 'firebench[radar]'
```

## Find the sites

Without `--site`, the command lists the sites within 230 km of the domain, nearest first:

```bash
firebench data nexrad --bbox -120.8,38.4,-119.7,39 --start 2021-08-17T00:00Z --end 2021-08-17T02:00Z
```

## Download

A WSR-88D scans a volume every 4 to 10 minutes; a volume is 4 to 12 MB. `--step 10` keeps the first
volume of each 10 minutes, `--step 0` every volume. `--dry-run` prints the number of volumes and
their size first. Each volume is downloaded, cropped, written, and deleted: two hours of two sites
at every volume make a file of about 6 MB.

```bash
firebench data nexrad --bbox -120.8,38.4,-119.7,39 --start 2021-08-17T00:00Z --end 2021-08-17T02:00Z --site KDAX,KRGX --step 10 -o radar.h5 --dry-run
```

`--fields` chooses the Level II moments (`DBZH`, `RHOHV`, `ZDR`, `VRADH`; all by default) and
`--max-height` the ceiling of the crop in km above mean sea level (20 by default).

## Standardize from Python

```python
from datetime import datetime, timezone
from pathlib import Path

from firebench.acquisition import nexrad
from firebench.standardize import new_std_file, standardize_nexrad_level2

bbox = (-120.8, 38.4, -119.7, 39.0)
start = datetime(2021, 8, 17, tzinfo=timezone.utc)
end = datetime(2021, 8, 17, 2, tzinfo=timezone.utc)

volumes = nexrad.select_volumes(nexrad.list_volumes("KDAX", start, end), 10)
with new_std_file("radar.h5", "Your Name") as h5:
    fetched = nexrad.fetch_volumes(volumes, Path("scratch"))
    standardize_nexrad_level2(fetched, h5, site="KDAX", bbox=bbox, start=start, end=end, time_step_min=10)
```

`nexrad.local_volumes` and `nexrad.local_fetched_volumes` read a directory laid out like the bucket
(`unidata-nexrad-level2/YYYY/MM/DD/SITE/…`) instead of downloading.

## Plume readings

```python
from firebench.standardize import list_radar_sites, radar_composite, radar_echo_top_series

for site in list_radar_sites("radar.h5"):
    tops = radar_echo_top_series("radar.h5", site)
    image = radar_composite("radar.h5", site, volume=0)
```

A gate counts as plume when its reflectivity is at least 5 dBZ and its correlation coefficient is
between 0.2 and 0.9 (adapted from Krishna et al., 2024), over the domain. `radar_echo_top_series` gives, for each
volume, the highest plume gate and the 75th and 90th percentiles of their heights, in m above mean
sea level; a volume with no plume gate has NaN heights. `radar_composite` gives the column maximum of
a field over the plume gates on a longitude–latitude grid. Both take other thresholds.
