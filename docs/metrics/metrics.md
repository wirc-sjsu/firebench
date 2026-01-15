# Metrics
This section describes all the metrics used within FireBench benchmarks.

## 1D metrics

**Input:** Two 1D vectors of size $N$:

- $x_i$: evaluated dataset
- $y_i$: reference dataset

### Mean

**Description:** Average value of a 1D vector $x$. <br>
**Range:** Same as range of $x$. <br>
**Units:** Same as input units. <br>
**Formula:**

$$
\bar x = \frac{1}{N} \sum_{i=1}^N x_i
$$

### Bias

**Description:** Difference between the mean of $x$ and the mean of $y$.<br>
**Range:** Same as range of input values.<br>
**Units:** Same as input units.<br>
**Formula:**

$$
B = \bar x - \bar y
$$

### Root Mean Square Error

**Description:** Square root of the mean squared difference between (x) and (y), noted RMSE. <br>
**Range:** $[0, +\infty[$.<br>
**Units:** Same as input units.<br>
**Formula:**

$$
RMSE(x, y) = \sqrt{\frac{1}{N} \sum_{i=1}^N (x_i - y_i)^2}
$$

### Mean Absolute Error

**Description:** Mean of the absolute difference between (x) and (y), noted MAE. <br>
**Range:** $[0, +\infty[$.<br>
**Units:** Same as input units.<br>
**Formula:**

$$
MAE(x, y) = \frac{1}{N} \sum_{i=1}^N  |x_i - y_i |
$$

### Normalized MSE - power normalization

**Description:** RMSE normalized by the range of the reference dataset.<br>
**Range:** $[0, +\infty)$.<br>
**Units:** Dimensionless.<br>
**Formula:**

$$
NMSE_p = \frac{RMSE(x, y)}{\max(y) - \min(y)}
$$

### Normalized MSE – range normalization
**Description:** Squared RMSE normalized by the product of mean values of the datasets.<br>
**Range:** $[0, +\infty)$ (undefined if $\bar x = 0$ or $\bar y = 0$).<br>
**Units:** Dimensionless.<br>
**Formula:**

$$
NMSE_r = \frac{RMSE(x, y)^2}{\bar x \, \bar y}
$$


## Binary Confusion Matrix

**Input:** Two 1D binary vectors (0 or 1) of size $N$:

- $x_i$: evaluated dataset
- $y_i$: reference dataset

The following metrics are derived from the [Binary confusion matrix](https://en.wikipedia.org/wiki/Confusion_matrix#Table_of_confusion) generated from both dataset. The Binary confusion matrix is a 2x2 matrix containing:

|              | Reference = 1 | Reference = 0 |
| ------------ | ------------- | ------------- |
| **Eval = 1** | TP            | FP            |
| **Eval = 0** | FN            | TN            |

Where:
- TP: True Positive
- FP: False Positive
- FN: False Negative
- TN: True Negative

### Accuracy

**Description:** Fraction of correct predictions among all samples (see [accuracy](https://en.wikipedia.org/wiki/Accuracy_and_precision#In_classification)).<br>
**Range:** $[0, 1]$<br>
**Units:** Dimensionless.<br>
**Formula:**

$$
Accuracy = \frac{TP + TN}{TP + TN + FP + FN}
$$

### Precision
**Description:** Fraction of predicted positives that are true positives (see [precision](https://en.wikipedia.org/wiki/Positive_and_negative_predictive_values#Definition)).<br>
**Range:** $[0, 1]$<br>
**Units:** Dimensionless.<br>
**Formula:**

$$
Precision = \frac{TP}{TP + FP},
$$

### Recall
**Description:** Fraction of actual positives correctly identified (see [recall](https://en.wikipedia.org/wiki/Precision_and_recall)). Recall can also be named Sensitivity or True Positive Rate.<br>
**Range:** $[0, 1]$<br>
**Units:** Dimensionless.<br>
**Formula:**

$$
Recall = \frac{TP}{TP + FN},
$$

### Specificity
**Description:** Fraction of actual negatives correctly identified (see [specificity](https://en.wikipedia.org/wiki/Sensitivity_and_specificity)). Recall can also be named True Negative Rate.<br>
**Range:** $[0, 1]$<br>
**Units:** Dimensionless.<br>
**Formula:**

$$
Specificity = \frac{TN}{TN + FP}
$$

### Negative Predictive Value
**Description:** Fraction of predicted negatives that are true negatives (see [Negative Predictive Value](https://en.wikipedia.org/wiki/Positive_and_negative_predictive_values)).<br>
**Range:** $[0, 1]$<br>
**Units:** Dimensionless.<br>
**Formula:**

$$
Negative Predictive Value = \frac{TN}{TN + FN}
$$

### F1 Score
**Description:** Harmonic mean of Precision and Recall (see [F1 Score](https://en.wikipedia.org/wiki/F-score)).<br>
**Range:** $[0, 1]$<br>
**Units:** Dimensionless.<br>
**Formula:**

$$
F1 Score =  \frac{2 \times Precision \times Recall}{Precision + Recall}
$$

