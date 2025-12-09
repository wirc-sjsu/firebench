# Key Performance Indicator Definitions

This section describes the Key Performance Indicators (KPI) used within FireBench benchmarks.
KPIs are grouped by context. Output bounds are given as `worst` and `best` values. 

KPIs can be described as:
- Template: generic definition of a KPI. It can be related to generic input variable(s) and have parameters.
- Intance: the final form of a KPI that can be used in a benchmark. It has explicitly defined input variable(s) and no parameters.

## Burn Severity 

### Binary High Severity Accuracy

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measure how accurately the model predicts which point are identified as high severity, based on binary (high severity / not high severity) observations.

The measure of [accuracy](https://en.wikipedia.org/wiki/Accuracy_and_precision#In_classification) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Accuracy = \frac{TP + TN}{TP + TN + FP + FN},
$$
where $TP$ = True positive (high severity in both datasets); $FP$ = False positive (high severity only in model dataset); $TN$ = True negative (not high severity in both datasets); $FN$ = False negative (high severity only in observational datasets)

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_accurary` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary High Severity Precision

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measures how accurately the model predicts which cells are high severity, by evaluating the proportion of predicted high severity points that were actually high severity.

The measure of [precision](https://en.wikipedia.org/wiki/Positive_and_negative_predictive_values#Definition) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Precision = \frac{TP}{TP + FP},
$$
where $TP$ = True positive (high severity in both datasets); $FP$ = False positive (high severity only in model dataset)

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_precision` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary High Severity Recall

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measures how completely the model captures the cells with a high severity index, indicating the fraction of truly high severity cells that the model successfully identifies.

The measure of [recall](https://en.wikipedia.org/wiki/Precision_and_recall) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Recall = \frac{TP}{TP + FN},
$$
where $TP$ = True positive (high severity in both datasets); $FN$ = False negative (high severity only in observational datasets)

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_recall_rate` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary High Severity Specificity

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measures how accurately the model identifies cells with another severity index than high, by quantifying the fraction of other indices correctly predicted as other (not high).

The measure of [specificity](https://en.wikipedia.org/wiki/Sensitivity_and_specificity) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Specificity = \frac{TN}{TN + FP}
$$
where $FP$ = False positive (high severity only in model dataset); $TN$ = True negative (not high severity in both datasets)

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_specificity` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary High Severity Negative Predictive Value

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measures the reliability of the model’s predictions for cells identified with another severuty index than high, indicating the proportion of points predicted index as other (not high) that were indeed observed as other.

The measure of [Negative Predictive Value](https://en.wikipedia.org/wiki/Positive_and_negative_predictive_values) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Negative Predictive Value = \frac{TN}{TN + FN}
$$
where $TN$ = True negative (not high severity in both datasets); $FN$ = False negative (high severity only in observational datasets)

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_negative_predicted_value` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary High Severity F1 Score

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Provides a balanced measure of model performance by combining precision and recall, capturing how well the model identifies high severity cells while limiting false alarms.

The measure of [F1 Score](https://en.wikipedia.org/wiki/F-score) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
F1 Score =  \frac{2 \times Precision \times Recall}{Precision + Recall}
$$

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_f_score` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

## Structure Loss

### Binary Structure Loss Accuracy

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measure how accurately the model predicts which structures are destroyed or not destroyed by the fire, based on binary (burned / not burned) observations.

The measure of [accuracy](https://en.wikipedia.org/wiki/Accuracy_and_precision#In_classification) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Accuracy = \frac{TP + TN}{TP + TN + FP + FN},
$$
where $TP$ = True positive (buildings destroyed in both datasets); $FP$ = False positive (buildings destroyed only in model dataset); $TN$ = True negative (buildings not damaged in both datasets); $FN$ = False negative (buildings destroyed only in observational datasets)

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_accurary` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary Structure Loss Precision

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measures how accurately the model predicts which structures are destroyed, by evaluating the proportion of predicted-destroyed buildings that were actually destroyed.

The measure of [precision](https://en.wikipedia.org/wiki/Positive_and_negative_predictive_values#Definition) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Precision = \frac{TP}{TP + FP},
$$
where $TP$ = True positive (buildings destroyed in both datasets); $FP$ = False positive (buildings destroyed only in model dataset).

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_precision` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.


### Binary Structure Loss Recall

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measures how completely the model captures the buildings that were actually destroyed, indicating the fraction of truly destroyed structures that the model successfully identifies.

The measure of [recall](https://en.wikipedia.org/wiki/Precision_and_recall) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Recall = \frac{TP}{TP + FN},
$$
where $TP$ = True positive (buildings destroyed in both datasets); $FN$ = False negative (buildings destroyed only in observational datasets)

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_recall_rate` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary Structure Loss Specificity

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measures how accurately the model identifies buildings that survived, by quantifying the fraction of intact structures correctly predicted as not destroyed.

The measure of [specificity](https://en.wikipedia.org/wiki/Sensitivity_and_specificity) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Specificity = \frac{TN}{TN + FP}
$$
where $FP$ = False positive (buildings destroyed only in model dataset); $TN$ = True negative (buildings not damaged in both datasets).

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_specificity` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary Structure Loss Negative Predictive Value

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Measures the reliability of the model’s predictions for surviving structures, indicating the proportion of predicted-intact buildings that were indeed not destroyed.

The measure of [Negative Predictive Value](https://en.wikipedia.org/wiki/Positive_and_negative_predictive_values) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Negative Predictive Value = \frac{TN}{TN + FN}
$$
where $TN$ = True negative (buildings not damaged in both datasets); $FN$ = False negative (buildings destroyed only in observational datasets).

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_negative_predicted_value` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary Structure Loss F1 Score

*Type*: Instance <br>
*Best*: 1 <br>
*Worst*: 0

Provides a balanced measure of model performance by combining precision and recall, capturing how well the model identifies destroyed buildings while limiting false alarms.

The measure of [F1 Score](https://en.wikipedia.org/wiki/F-score) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
F1 Score =  \frac{2 \times Precision \times Recall}{Precision + Recall}
$$

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_f_score` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

## Weather stations

### Wind Speed Bias Average

*Type*: Template <br>
*Best*: 0 <br>
*Worst*: increasing $|bias|$ <br>
*Parameters*:
- $t_1$: period starting time
- $t_2$: period ending time

Provides the average bias over multiple weather stations over a period 24h for wind speed.

The average bias is calculated as:

$$
\overline{Bias} = \frac{1}{N_s} \sum_{k=1}^{N_s} \frac{1}{N_t} \sum_{i=1}^{N_t} (m_{ki} - o_{ki})
$$
where $N_s$ is the number of weather stations, $N_t$ is the number of time step between $t_1$ and $t_2$, $m_{ki}$ is the model data for station $k$ at time step $i$, and $o_{ki}$ is the observation data for station $k$ at time step $i$.

The implementation of this KPI is done using `firebench.metrics.stats.bias`.

#### 24h forecast Wind Speed RMSE Average

*Category*: Weather Stations <br>
*Name used in result files*: 24h forecast Wind Speed RMSE Average <br>
*Best*: 0 <br>
*Worst*: increasing $|bias|$ <br>
*Parameters*:
- $t_s$: 24h period starting time

Provides the average RMSE over multiple weather stations over a period 24h for wind speed.

The average RMSE is calculated as:

$$
\overline{RMSE} = \frac{1}{N_s} \sum_{k=1}^{N_s} \sqrt{\frac{1}{N_t} \sum_{i=1}^{N_t} (m_{ki} - o_{ki})^2}
$$
where $N_s$ is the number of weather stations, $N_t$ is the number of time step over the 24h period, $m_{ki}$ is the model data for station $k$ at time step $i$, and $o_{ki}$ is the observation data for station $k$ at time step $i$.

The implementation of this KPI is done using `firebench.metrics.stats.rmse`.

#### 24h forecast Wind Direction RMSE Average

*Category*: Weather Stations <br>
*Name used in result files*: 24h forecast Wind Direction RMSE Average <br>
*Best*: 0 <br>
*Worst*: increasing $|bias|$ <br>
*Parameters*:
- $t_s$: 24h period starting time


Wind direction difference is calculated as
$$
d_{wd} = ((x - y + 180) \mod 360 ) - 180
$$

#### 24h forecast Wind Gust RMSE Average

*Category*: Weather Stations <br>
*Name used in result files*: 24h forecast Wind Gust RMSE Average <br>
*Best*: 0 <br>
*Worst*: increasing $|bias|$ <br>
*Parameters*:
- $t_s$: 24h period starting time

#### 24h forecast Sustained Wind Speed Average

*Category*: Weather Stations <br>
*Name used in result files*: 24h forecast Wind Gust RMSE Average <br>
*Best*: 0 <br>
*Worst*: increasing $|bias|$ <br>
*Parameters*:
- $t_s$: 24h period starting time
- $U_0$: Value of thresehold

Calculate the amount of time when the wind speed is above a defined threshold. Compare this time to observation and average it over multiple weather stations.


