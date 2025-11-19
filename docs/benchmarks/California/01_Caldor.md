# 2021 Caldor Fire

**Version**: 1.0a
**Case ID**: FB001 

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

The column names from the original csv file have been corrected from "* Damage" to "Damage" and "* Incident Name" to "Incident Name". 
The hash of the original source file is: *0190a5a51aafafa20270fe046a7ae17a53697b1fb218ff8096a3d8ebbc9ef983*.

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

### Benchmark FB001-BD01

**KPI**: Binary structure loss accuracy

### Benchmark FB001-BD02

**KPI**: Binary structure loss precision

### Benchmark FB001-BD03

**KPI**: Binary structure loss recall

### Benchmark FB001-BD04

**KPI**: Binary structure loss false negative rate

### Benchmark FB001-BD05

**KPI**: Binary structure loss false positive rate

### Benchmark FB001-BD06

**KPI**: Binary structure loss F1 score