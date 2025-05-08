# Welcome to the FireBench Project

<img src="_static/images/firebench_logo.png" alt="FireBench Logo" width="300px">


**FireBench** is a Python library designed for the systematic benchmarking and inter-comparison of fire models.
Recent advancements in fire modeling have introduced complex and varied models, but there is a lack of systematic evaluation regarding their accuracy, efficiency, sensitivity, validity domain, and inter-compatibility.
FireBench aims to address this gap by providing a framework to assess fire models on the following criteria:

- **Accuracy**: Precision in predicting fire front positions and plume dynamics.
- **Efficiency**: Computational resources required for specific computation.
- **Sensitivity**: Model outputs' responsiveness to input variations, crucial for calibration and data assimilation.
- **Validity Domain**: Operational input ranges for which models are applicable.
- **Inter-Compatibility**: Integration capabilities with other models.

FireBench offers a dual approach for evaluation: intercomparison without extensive observational data and benchmarking against a validation dataset. This framework aims to enhance fire modeling for both scientific research and operational applications, with results archived in a dedicated database.


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