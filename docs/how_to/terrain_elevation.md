# Ground Elevation

FireBench gives the ground elevation of a box or a point from two models, and stores a box's grid in
a standard file under `/spatial_2d/terrain_elevation` (see the [standard format](../standard_format.md)).

- **LANDFIRE's elevation** (`LF20xx_Elev_CONUS`): a bare-earth model of the United States derived from
  USGS 3DEP, 30 m cells in EPSG:5070, metres above NAVD88. FireBench reads a mosaic you have on disk.
- **The Copernicus DEM GLO-30**: the whole world at 1 arc-second, metres above EGM2008, from the open
  archive on AWS (`firebench.acquisition.copernicus_dem`, no key). It is a surface model: it holds
  the height of trees and buildings.

LANDFIRE is used wherever it has a value, the Copernicus DEM elsewhere; each cell records which.

```python
from pathlib import Path

from firebench.acquisition.copernicus_dem import fetch_copernicus_dem
from firebench.standardize import ground_elevation, new_std_file, standardize_terrain_elevation, terrain_elevation_grid

bbox = (-119.23, 40.775, -119.18, 40.805)  # west, south, east, north
landfire = "LANDFIRE/LF2020_Elev_CONUS/Tif/LF2020_Elev_CONUS.tif"
tiles = fetch_copernicus_dem(bbox, Path("dem_tiles"))  # 10 to 40 MB a 1° tile

print(ground_elevation(40.79113, -119.19991, landfire_path=landfire, copernicus=tiles))  # (1191.0, 'LANDFIRE')
grid = terrain_elevation_grid(bbox, landfire_path=landfire, copernicus=tiles)
with new_std_file("terrain.h5", "me") as h5:
    standardize_terrain_elevation(grid, h5)
```

Values are bilinear between the cells of each model. A box of more than 16 million cells at one
arc-second is sampled on a coarser grid. Tiles of the Copernicus archive that are all sea do not
exist: their cells get no value from it.
