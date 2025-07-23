# 4. Metrics information
This section describes the high-level metrics available in `FireBench`, organized by the type and structure of the observational data they support. These metrics are designed to evaluate model performance in realistic settings and are grouped into categories that reflect typical data sources (e.g., weather stations, satellite imagery, fire perimeters).
Some metrics support observation uncertainty, and others are specifically designed for deterministic or ensemble simulations.

For implementation details, refer to the [API references](../api/index.rst).

A full list of metrics is also available on the [Content page](../content.md).

## Single Point (0D, Time Series)

These metrics apply to **0D signals**, *i.e.*, time series at a single spatial location. This is typical for **weather station data** or **virtual probes** in simulations.

**Use these metrics when**:
- You have observations at fixed points in space (e.g., 10-meter wind at a weather station)
- You want to compute per-station RMSE, bias, correlation, etc.

**List of metrics**
- Bias
- RMSE
- NMSE with range normalization
- NMSE with power normalization

## Network of Probes

Metrics in this category are designed to evaluate a **network of time series** across multiple locations, such as a set of weather stations.

**Use these metrics when**:
- You want to evaluate performance across a full observation network
- You need to analyze spatial structure, coherence, or regional error statistics

## Line or Polygon Observations (1D in Space, Sparse in Time)

These metrics apply to **1D spatial data** that are available at discrete times, for example GIS polygons representing fire perimeters, or airborne measurements along a path

**Use these metrics when**:
- You want to compare the shape, location, or evolution of 1D features
- You need to evaluate model accuracy along a known line or within a boundary

**List of metrics**
- Jaccard index (Intersection over Union)
- Sorensen-Dice index

## 2D Raster Data (Sparse in Time)

Metrics in this group apply to **2D spatial data**, such as satellite imagery, available at discrete times.

**Use these metrics when**:
- You are comparing model outputs to gridded observations
- You want to use spatial scores (e.g., FSS, SAL) or object-based comparison methods

**List of metrics**
- Jaccard index (Intersection over Union)
- Sorensen-Dice index

## 3D Sparse or Semi-Sparse Observations

This category includes **3D datasets** that may be dense in two dimensions and sparse in the third (typically time). Examples include:

* **Lidar scans** (e.g., vertical cross-sections of wind or aerosol)
* **Radar volumes** or **profiling instruments**

**Use these metrics when**:
- Your data span two spatial dimensions (e.g., x-z or y-z) over time
- You want to assess how well the model reproduces layered structures or vertical evolution