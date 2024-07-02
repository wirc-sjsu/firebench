---
layout: default
title: How to Personalize the Fuel Model
parent: Tutorials
nav_order: 1
---
# How to Personalize the Fuel Model

This guide will walk you through the steps to personalize a fuel model in the FireBench library. Personalizing your fuel model allows you to adapt the default settings to better match the specific conditions and characteristics of your study area.

## Overview

Personalizing a fuel model involves:
1. Understanding the default fuel model structure.
2. Creating a custom fuel model.
3. Integrating the custom fuel model into FireBench.
4. Validating the custom fuel model.

## Prerequisites

Before you begin, ensure you have the following:
- Installed FireBench library.
- Basic understanding of fire modeling concepts.
- Access to relevant fuel data for your specific use case.

## Step 1: Understanding the Default Fuel Model Structure

Firebench contains some default fuel models. The fuel models distributed within the package are listed [here](../content.md).

### Default Fuel Model management

The fuel models are stored as a JSON metedata file and a CSV data file. The CSV data file contains one header containing the name of the variables, and the data as each row represents a fuel class
The metadata file contains information fuel model variables. For example, the `Anderson13` fuel model is composed of the `Anderson13.json` metadata file:

```json
{
    "data_path": "data_Anderson13.csv",
    "metadata": {
      "fgi": {
        "variable_name": "fuel_load_dry_total",
        "unit": "kg/m^2"
      },
      "windrf": {
        "variable_name": "fuel_wind_reduction_factor",
        "unit": "dimensionless"
      }
      ...
}
```
The metadata file stores the path of the data file in `data_path`. The metadata dictionnary contains the following information for each variable in the data file:
- variable name as given within the standard namespace