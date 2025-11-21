# 5. Metrics information
This section describes the high-level metrics available in `FireBench`, listed as `Key Performance Indicator` (KPI). Each KPI represents a quantitative evaluation of performance. 

For implementation details, refer to the [API references](../api/index.rst).

A full list of metrics is also available on the [Content page](../content.md).

## Key Performance Indicator


### Binary Structure Loss Accuracy

*Category*: Structure Damage <br>
*Name used in result files*: Binary Structure Loss Accuracy <br>
*Best Score*: 1 <br>
*Lowest Score*: 0

Measure how accurately the model predicts which structures are destroyed or not destroyed by the fire, based on binary (burned / not burned) observations.

The measure of [accuracy](https://en.wikipedia.org/wiki/Accuracy_and_precision#In_classification) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Accuracy = \frac{TP + TN}{TP + TN + FP + FN},
$$
where $TP$ = True positive (buildings destroyed in both datasets); $FP$ = False positive (buildings destroyed only in model dataset); $TN$ = True negative (buildings not damaged in both datasets); $FN$ = False negative (buildings destroyed only in observational datasets)

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_accurary` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary Structure Loss Precision

*Category*: Structure Damage <br>
*Name used in result files*: Binary Structure Loss Precision <br>
*Best Score*: 1 <br>
*Lowest Score*: 0

Measures how accurately the model predicts which structures are destroyed, by evaluating the proportion of predicted-destroyed buildings that were actually destroyed.

The measure of [precision](https://en.wikipedia.org/wiki/Positive_and_negative_predictive_values#Definition) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Precision = \frac{TP}{TP + FP},
$$
where $TP$ = True positive (buildings destroyed in both datasets); $FP$ = False positive (buildings destroyed only in model dataset).

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_precision` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.


### Binary Structure Loss Recall

*Category*: Structure Damage <br>
*Name used in result files*: Binary Structure Loss Recall <br>
*Best Score*: 1 <br>
*Lowest Score*: 0

Measures how completely the model captures the buildings that were actually destroyed, indicating the fraction of truly destroyed structures that the model successfully identifies.

The measure of [recall](https://en.wikipedia.org/wiki/Precision_and_recall) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Recall = \frac{TP}{TP + FN},
$$
where $TP$ = True positive (buildings destroyed in both datasets); $FN$ = False negative (buildings destroyed only in observational datasets)

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_recall_rate` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary Structure Loss Specificity

*Category*: Structure Damage <br>
*Name used in result files*: Binary Structure Loss Specificity <br>
*Best Score*: 1 <br>
*Lowest Score*: 0

Measures how accurately the model identifies buildings that survived, by quantifying the fraction of intact structures correctly predicted as not destroyed.

The measure of [specificity](https://en.wikipedia.org/wiki/Sensitivity_and_specificity) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Specificity = \frac{TN}{TN + FP}
$$
where $FP$ = False positive (buildings destroyed only in model dataset); $TN$ = True negative (buildings not damaged in both datasets).

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_specificity` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary Structure Loss Negative Predictive Value

*Category*: Structure Damage <br>
*Name used in result files*: Binary Structure Loss Negative Predictive Value <br>
*Best Score*: 1 <br>
*Lowest Score*: 0

Measures the reliability of the model’s predictions for surviving structures, indicating the proportion of predicted-intact buildings that were indeed not destroyed.

The measure of [Negative Predictive Value](https://en.wikipedia.org/wiki/Positive_and_negative_predictive_values) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
Negative Predictive Value = \frac{TN}{TN + FN}
$$
where $TN$ = True negative (buildings not damaged in both datasets); $FN$ = False negative (buildings destroyed only in observational datasets).

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_negative_predicted_value` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.

### Binary Structure Loss F1 Score

*Category*: Structure Damage <br>
*Name used in result files*: Binary Structure Loss F1 Score <br>
*Best Score*: 1 <br>
*Lowest Score*: 0

Provides a balanced measure of model performance by combining precision and recall, capturing how well the model identifies destroyed buildings while limiting false alarms.

The measure of [F1 Score](https://en.wikipedia.org/wiki/F-score) is based on the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from an observational dataset and a model output dataset.

$$
F1 Score =  \frac{2 \times Precision \times Recall}{Precision + Recall}
$$

The implementation of this KPI is done using the `firebench.metrics.confusion_matrix.binary_cm` function and `firebench.metrics.confusion_matrix.binary_f_score` functions (see API documentation for implementation). If some data processing (e.g., for category aggregation) is required, this process is described at the case level.