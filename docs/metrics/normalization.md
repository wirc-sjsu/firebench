# KPI Normalization

This section describes several normalization schemes used to convert KPI values into a score in the range $[0, 100]$.
Throughout, $x$ denotes the KPI value.

## Linear Bounded Normalization

For KPIs with a **bounded acceptable range** $[a, b]$, with $a < b$, the normalization function is defined as:

$$
\mathcal N(x, a, b) = 100 \, \left( \frac{x - a}{b - a} \right)
$$

Here,
- $a$ corresponds to the **worst** score (0),
- $b$ corresponds to the **best** score (100).

## Linear Half-Open Normalization

For KPIs that have a **minimum acceptable value** $a$ but no finite upper limit, i.e. values in $[a, +\infty[$, we define:

$$
\mathcal N(x, a, m) = 100 \, \max \left(0,  1 - \frac{x-a}{m-a} \right)
$$

where $m > a$ is a parameter specifying the value of $x$ at which the score reaches **0**.

Here,
- $a$ corresponds to the **best** score (100),
- $m$ corresponds to the **worst** score (0).

## Exponential Half-Open Normalization

For KPIs with a minimum acceptable value $a$ and domain $[a, +\infty[$, we define an exponentially decaying score:

$$
\mathcal N(x, a, m) =100 \, \exp \left( - \frac{\ln 2(x-a)}{m-a} \right).
$$

This formulation ensures:

$$
\mathcal N(a,a,m) = 100, \qquad
\mathcal N(m,a,m) = 50.
$$

Thus, $m$ is the KPI value at which the score is exactly **50**.
Here,
- $a$ corresponds to the **best** possible score (100),
- $m$ corresponds to the value at which the score has decreased to **50**,
- scores decay smoothly toward 0 as $x \to +\infty$.