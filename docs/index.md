# Welcome to the FireBench Project

<img src="_static/images/firebench_logo.png" alt="FireBench Logo" width="300px">


**FireBench** is an open-source Python library for the **systematic benchmarking and intercomparison of fire models**. As fire modeling becomes more sophisticated—spanning physics-based, empirical, and data-driven approaches—there remains a critical need for **standardized, transparent evaluation** of their capabilities.

FireBench addresses this gap by providing a flexible framework to assess fire models across key dimensions:

- 🔍 **Accuracy** — How precisely the model predicts fire front progression and plume behavior.  
- ⚙️ **Efficiency** — The computational cost required for simulations under standardized conditions.  
- 🎯 **Sensitivity** — How model outputs respond to variations in inputs; crucial for calibration and uncertainty analysis.  
- 📈 **Validity Domain** — The range of environmental and operational conditions where the model remains reliable.  
- 🔗 **Inter-Compatibility** — The ease of integration with other tools and workflows in fire or environmental modeling chains.

FireBench supports a **dual evaluation strategy**:
- **Intercomparison** of models under controlled scenarios, even in the absence of observational data.
- **Benchmarking** against validation datasets where ground truth or reference outputs are available.

All benchmark results are **archived in a dedicated database**, enabling reproducibility, transparency, and cumulative progress in fire modeling—for both scientific research and operational decision-making.

## 🔥 Call for Benchmarks 2025

We invite the community to contribute to the **FireBench Benchmarking Campaign 2025**. Researchers, engineers, and model developers are encouraged to propose new benchmarks that evaluate components or full workflows of fire models.

Benchmarks may cover:
- Specific fire sub-models (e.g., **rate of spread**, **plume dynamics**, **heat flux**, **terrain/wind interpolation**)
- 2D or 3D fire dynamics
- Use-case-driven scenarios (e.g., **WUI**, **risk assessment**, **fuel moisture effects**)

### 📅 2025 Benchmarking Timeline

| Phase                          | Deadline             |
|-------------------------------|----------------------|
| 📥 Benchmark Proposal Submission | **July 31, 2025**     |
| 🔍 Benchmark Review & Feedback   | **August 31, 2025**   |
| 🚀 Benchmark Execution Results   | **November 30, 2025** |

Accepted benchmarks will be included in the **FireBench Annual Report**, presented at the **AMS 2026 Annual Meeting**, and archived for reproducibility. Contributors may be credited as co-authors or acknowledged participants depending on their involvement.

---

### 📄 How to Submit a Benchmark

1. Review the [Benchmark Proposal Template](benchmarks/index.md) for formatting guidelines.
2. Fill in your submission using the [Google Doc Template](https://docs.google.com/document/d/19RXwEnl81XxUfCWXOCUENFV-ZB4iz16faCDsJatddc8/edit?usp=sharing).
3. View ongoing submissions in the [List of Submitted Benchmarks](https://docs.google.com/spreadsheets/d/1Ee2G6FgD-c-5fu-oPcsI3ApyQnPQvxZJwKqVOYqtj28/edit?usp=sharing).

💡 If you're interested in **running** a benchmark (using one or more fire models), check out the [Benchmark Execution Guidelines](benchmarks/index.md) to learn how to evaluate and report results.

We’re excited to see how the community will help shape the future of fire modeling!

## Installation

### Prerequisites

Before installing FireBench, you need to install [Git LFS](https://git-lfs.github.com/).

To install the FireBench library, follow these steps:

### 1. Clone the Repository

You can clone the repository using either HTTPS or SSH. Choose one of the following methods:

#### Using HTTPS:
```bash
git clone https://github.com/wirc-sjsu/firebench.git
```

#### Using SSH:
```bash
git clone git@github.com:wirc-sjsu/firebench.git
```

### 2. Install FireBench and its Dependencies

Navigate to the cloned repository and install the FireBench library along with its dependencies using `pip`:

```bash
cd firebench
git lfs pull
pip install .
```

### 3. Set up the path to your local working directory

In order to centralize all the files managed locally by firebench, a working directory called the `firebench local database` has to be defined.
This directory will store the output of workflows.
Add the following line to your `.bashrc` or `.zshrc`:
```bash
export FIREBENCH_LOCAL_DB=/path/to/your/firebench/local/db
```

FireBench contains some data (fuel models, workflow runs, *etc*.) that is contained in the directory `firebench/data`. 
In order to easily access this data, add the absolute path to the `firebench/data` directory to your `.bashrc` or `.zshrc`:
```bash
export FIREBENCH_DATA_PATH=/path/to/package/firebench/data
```

## Community Discussions

We encourage you to use the [GitHub Discussions](https://github.com/wirc-sjsu/firebench/discussions) tab for questions, help requests, and general discussions about the project. This helps keep our issue tracker focused on bugs and feature requests.

### How to Use Discussions

- **Q&A**: If you have a question about using FireBench, please check the Q&A category.
- **Ideas**: Share your ideas for new features or improvements in the Ideas category.
- **Show and Tell**: Showcase your projects and workflows using FireBench.
- **General**: For any other discussions related to FireBench.

Feel free to start a new discussion or join existing ones to engage with the community!

## Contributing

We welcome contributions to FireBench! For more information on how to contribute, please see our [contribution guidelines](contribute.md).

```{toctree}
:maxdepth: 1

dataset_experiments/index.md
fire_models_info/index.md
benchmarks/index.md
workflows_0D_models/index.md
tutorials/index.md
namespace.md
content.md
contribute.md
developers.md
changelog.md
dependencies.md
license.md
api/index.rst
```