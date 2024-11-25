---
layout: default
title: "Anderson 2015"
parent: "Datasets and fire experiment information"
nav_order: 1
---

# Anderson 2015 validation dataset

## Description

*Under construction*

## Firebench dataset content

*Under construction*

**Table A1 dataset**

## Usage

Import the Anderson 2015 dataset using `FireBench` with:
```python
import firebench.tools as ft
anderson_dataset_A1 = ft.read_data_file("Table_A1", "ros_model_validation/Anderson_2015")
anderson_dataset_8 = ft.read_data_file("Table_8", "ros_model_validation/Anderson_2015")
```
The data is stored in the dictionnary `anderson_dataset_A1` for the data of Table A1 and `anderson_dataset_8` for the data of Table 8.
The keys are the standard variable names and the values are numpy array associated with pint unit.

*Add block asset*

## Reference

[1] [Anderson, W. R., Cruz, M. G., Fernandes, P. M., McCaw, L., Vega, J. A., Bradstock, R. A., ... & van Wilgen, B. W. (2015). A generic, empirical-based model for predicting rate of fire spread in shrublands. International Journal of Wildland Fire, 24(4), 443-460.](https://doi.org/10.1071/WF14130)