# 2021 Caldor Fire

**Version**: 1.0a <br>
**Case ID**: FB001 <br>
**FireBench IO std version**: >= 0.2 <br>
**Date of last update**: 11/19/2025 

## Contributors
- Aurélien Costes, [Wildfire Interdisciplinary Research Center](https://www.wildfirecenter.org/), San Jose State University, [aurelien.costes@sjsu.edu](mailto:aurelien.costes@sjsu.edu), [ORCID](https://orcid.org/0000-0003-4543-5107)

## Description

This collection of benchmarks uses the public ressources about the 2021 Caldor Fire.
It contains observation datasets for:
- Nearby weather stations (nb of associated benchmarks)
- Infrared fire perimeters
- Burn severity
- Building damaged
- (Plume top height)
- (Smoke concentration ground)

## Buildings damage benchmarks

### Dataset

The data has been collected using **CAL FIRE Damage Inspection (DINS) Data** (version of 2025/11/05).
The original csv file containing multiple fires has been processed to extract the building damaged from the Caldor Fire only. The dataset contains the position (lat, lon) of buildings in the area of influence from the fire. The state of buildings is one of the following:
- 'No Damage',
- 'Affected (1-9%)',
- 'Minor (10-25%)',
- 'Major (26-50%)',
- 'Destroyed (>50%)',
- 'Inaccessible'.


The sha256 of the original source file is: *0190a5a51aafafa20270fe046a7ae17a53697b1fb218ff8096a3d8ebbc9ef983*.

If the evaluated model does not explicitly represent individual buildings, the model should consider every building within a cell to share the cell value for building damage (deterministic models) or share the median of bulding damage distribution (probabilistic models).

Figure 1 shows the spatial distribution of building damage for the Caldor Fire.
![blockdiagram](../../_static/benchmarks/FB001/Caldor_bd_map.png)
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Buildings damage map
    </em>
</p>

Figure 2 shows the distribution of building damage for the Caldor Fire. The following table shows the number of strucure in each damage category.
Damage category        | Counts [-]  
---------------------- | ----------------- 
No Damage              | 3356
Affected (1-9%)        |   56
Minor (10-25%)         |   18
Major (26-50%)         |    7
Destroyed (>50%)       | 1005
Inaccessible           |    2
Total                  | 4444

![blockdiagram](../../_static/benchmarks/FB001/Caldor_bd_distribution.png)
<p style="text-align: center;">
    <strong>
        Fig. 2
    </strong>
    :
    <em>
        Distribution of buildings damage
    </em>
</p>

### Processing of dataset

*Performed at obs dataset level*

The data from the original CSV was standardized without any modification.
The column names from the original csv file were corrected from "* Damage" to "Damage" and "* Incident Name" to "Incident Name" to simplify processing.

#### Binary classes of building damaged

*Performed at benchmark run level*

In order to performe some calculations, the building damaged classes can be aggrageted to form binary classes. The `Inaccessible` is ignored. The following aggragtion method is used:
- `unburnt` binary class contains `No Damage`, `Affected (1-9%)`, and `Minor (10-25%)`,
- `burnt` binary class contains `Major (26-50%)`, and `Destroyed (>50%)`.

### Benchmarks

See Key Performance Indicator (KPI) and normalization defintions [here](../../metrics/index.md).

#### FB001-BD01

**KPI**: Binary Structure Loss Accuracy <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for damaged buildings.

#### FB001-BD02

**KPI**: Binary Structure Loss Precision <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for damaged buildings.

#### FB001-BD03

**KPI**: Binary Structure Loss Recall <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for damaged buildings.

#### FB001-BD04

**KPI**: Binary Structure Loss Specificity <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for damaged buildings.

#### FB001-BD05

**KPI**: Binary Structure Loss Negative Predictive Value <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for damaged buildings.

#### FB001-BD06

**KPI**: Binary Structure Loss F1 Score <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for damaged buildings.


## Burn severity benchmarks

### Dataset

The data has been collected using [Monitoring Trends in Burning Severity](https://mtbs.gov/) (MTBS).
The original zip file contains burn severity, pre/post burn images, and final fire perimeter.
The source of the burn severity used in FireBench is the file `ca3858612053820210815_20210805_20220723_dnbr6.tif`. The source of the final fire perimeter is the kmz file `ca3858612053820210815_20210805_20220723.kmz`.

The burn severity categories, described with the corresponding index used in the dataset, are the following:
- 'no data': 0
- 'unburnt to low': 1
- 'low': 2
- 'moderate': 3
- 'high': 4
- 'increased greeness': 5

The hash of the original source files are: 
- zip file: 171b9604c0654d8612eaabcfcad93d2374762661ab34b4d62718630a13469841
- tif dnbr6: 33db74d3c5798c41ff3a4fc5ee57da9105fdc7a75d7f8af0d053d2f82cfdc0b6
- final perimeter kmz: 4ed7a0ee585f8118b65a29375a3d5ee8a69e85a95ee155205ba5d781289c6e2b

Figure 3 shows the MTBS map from the original source.

![blockdiagram](../../_static/benchmarks/FB001/mtbs_map.jpg)
<p style="text-align: center;">
    <strong>
        Fig. 3
    </strong>
    :
    <em>
        Map of burn severity from MTBS. Source: MTBS (`ca3858612053820210815_map.pdf`)
    </em>
</p>

### Processing of dataset

*Performed at obs dataset level*

The burn severity array is extracted from the original file without any modification. The latitude and longitude array are reconstructed using proejction parameters (see `firebench.standardize.mtbs.standardize_mtbs_from_geotiff`). The final perimeter has been procress using QGIS. The original data (kmz file) has been imported and cleaned. Extra perimeters have been removed to only conserve the final fire perimeter. No modification to the polygons have been performed. Then, the multipolygons was exported to kml format and integrated in the dataset HDF5 file.

#### Binary classes for high severity

*Performed at benchmark run level*

To perform the high severity benchmarks using binary confusion matrix, we construct a binary field based of the high severity index. All the points will a buen severity equal to 4 ('high') will be assigned the value 1. The other points are assigned a value 0. This processing is done when the benchmark is performed.

### Benchmarks

See Key Performance Indicator (KPI) and normalization defintions [here](../../metrics/index.md).

#### FB001-SV01

**KPI**: Binary High Severity Accuracy <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for high severity points (Binary High severity processed variable)

#### FB001-SV02

**KPI**: Binary High Severity Precision <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for high severity points (Binary High severity processed variable)

#### FB001-SV03

**KPI**: Binary High Severity Recall <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for high severity points (Binary High severity processed variable)

#### FB001-SV04

**KPI**: Binary High Severity Specificity <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for high severity points (Binary High severity processed variable)

#### FB001-SV05

**KPI**: Binary High Severity Negative Predictive Value <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for high severity points (Binary High severity processed variable)

#### FB001-SV06

**KPI**: Binary High Severity F1 Score <br>
**Normalization**: Linear Bounded Normalization with $a=0$, $b=1$ <br>
This benchmark is performed on the binary classes for high severity points (Binary High severity processed variable)

## Requirements

The following sections list the datasets requirements to run the different benchmarks. When the benchmark script is run, each requirement is validated on the HDF5 file passed as input (from the model ouput/data the user wants to evaluate). If a requirement is met, each corresponding benchmark is run.
Each requirement lists the required datasets/groups (as path) as well as mandatory attributs for each dataset/group.
The current version of FireBench does not integrate more complex checks (e.g., array size, dtype).


Requirement            | Benchmarks 
---------------------- | ----------------- 
R01                    | FB001-BD01, FB001-BD02, FB001-BD03, FB001-BD04, FB001-BD05, FB001-BD06
R02                    | FB001-SV01, FB001-SV02, FB001-SV03, FB001-SV04, FB001-SV05, FB001-SV06

### R01
Mandatory group/dataset| Mandatory attirbutes 
---------------------- | --------------------
`/points/building_damaged/building_damage` | units

### R02
Mandatory group/dataset| Mandatory attirbutes 
---------------------- | --------------------
`/2D_raster/Caldor_MTBS`| crs
`/2D_raster/Caldor_MTBS/fire_burn_severity`| units, _FillValue
`/2D_raster/Caldor_MTBS/position_lat`| units
`/2D_raster/Caldor_MTBS/position_lon`| units

## Aggregation Schemes

This section provides the weights used to aggregate KPI Unit Scores. More information about aggregation methods [here](../../metrics/index.md). If aggregation scheme `0` is specified, then no aggregation is performed. Therefore, group scores and total score are not computed.

### Scheme A

Group                  | Group Weight | Benchmark ID  | Benchmark weight
---------------------- | ------------ | ------------  | ----------------
Building Damage        | 1            |               | 
|        |                            | BD01 to BD06  | 1
Burn Severity          | 1            |               | 
|        |                            | SV01 to SV06  | 1

## Notes

- Each file hash has been performed using `firebench.standardize.calculate_sha256`.