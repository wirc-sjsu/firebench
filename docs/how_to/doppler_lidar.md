# Doppler Wind Lidar Scans

FireBench stores the scans of a Doppler wind lidar in a standard file under `/spatial_3d/lidar`
(see the [standard format](../standard_format.md)), the way the lidar observed them: one row per
ray, a fixed axis of gates, and one row per scan file. It reads the raw files of a Halo Photonics
StreamLine lidar.

## The files

- **Scans** (`.hpl`): a header, then each ray (decimal hour, azimuth, elevation, pitch, roll)
  followed by its gates (Doppler velocity, intensity, backscatter). Every raw scan type is read:
  user scans (CSM, sector), PPI, RHI, VAD rays, and stares. Processed wind profiles
  (`Processed_Wind_Profile_*.hpl`) and background files are not raw scans and are refused.
- **`Time_Sync_*.txt`**: the GPS fixes the lidar records when it sets its clock, with its position.
  A scan takes the position of the fix nearest its start, if one is within `max_fix_gap_h` hours
  (`resources/lidar.toml`). A position can be given instead.
- **The heading**: the azimuths of a scan are relative to the instrument's 0 degree. Give the
  azimuth of that 0, clockwise from true north; it is stored as `azimuth_offset`, and the azimuths
  as recorded.

```python
from datetime import datetime, timezone
from pathlib import Path

from firebench.standardize import lidar_points, lidar_scans, new_std_file, standardize_halo_lidar

scans = sorted(Path("lidar/20230906").glob("*.hpl"))
bbox = (-119.23, 40.775, -119.18, 40.805)  # west, south, east, north
start = datetime(2023, 9, 6, 2, 30, tzinfo=timezone.utc)
end = datetime(2023, 9, 6, 4, 30, tzinfo=timezone.utc)

with new_std_file("lidar.h5", "me") as h5:
    (group,) = standardize_halo_lidar(
        scans, h5, bbox=bbox, start=start, end=end, heading_deg=31.0,
        time_sync=["lidar/Time_Sync_19_202309.txt"],
    )
    for scan in lidar_scans(h5, "HALO_19"):
        if not scan.is_stare:
            points = lidar_points(h5, "HALO_19", scan.index)  # east, north, up from the lidar, in m
```

A scan whose start is outside the window is skipped. A file that cannot be read, a file given
twice, a scan with no position, a scan whose lidar is outside the box, and a file whose gates differ
from the first file of its lidar are not written; the group's `failed` attribute lists them with the
reason.

## Gates

The header gives the number of gates, the range gate length, and its length in points. In an
overlapping scan (the scan type ends with `overlapping`) a gate starts every point, so the gate
centres are `(k + 0.5) * length / points` apart: 1.5 m for a gate of 18 m and 12 points. Otherwise
they are `(k + 0.5) * length`.

## Points

`lidar_points` gives the gates of one scan with a value as east, north, and up from the lidar, with
the heading applied and a flat geometry (no Earth curvature, which the few kilometres of a lidar
allow). By default it keeps the gates that pass the thresholds of `resources/lidar.toml`: a
signal-to-noise ratio of at least `snr_min_db`, a backscatter above `backscatter_min` (aerosol and
smoke), and a radial velocity strictly between 0 and `radial_velocity_max_abs`. With `qc=False` it
keeps every gate with a value. The file itself is never filtered.
