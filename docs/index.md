# Welcome to the FireBench Project

<img src="_static/images/firebench_logo.png" alt="FireBench Logo" width="300px">


**FireBench** is an open-source Python library for the **systematic benchmarking and intercomparison of fire models**. As fire modeling becomes more sophisticated—spanning physics-based, empirical, and data-driven approaches—there remains a critical need for **standardized, transparent evaluation** of their capabilities.

FireBench addresses this gap by providing a flexible framework to assess fire models performance using various datasets and metrics.
See the list of benchmarks for more information about datasets, metrics and evaluation method.

## Installation

### Prerequisites

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
pip install .
```

### 3. Set up local paths

FireBench uses `~/.firebench/local_db` as the default local database directory for files managed locally by workflows.
Functions that write workflow records also accept an explicit `local_db_path` argument.

FireBench contains package data such as fuel models in the repository `data` directory.
Data helpers use that directory by default, and `get_firebench_data_directory(data_path=...)` can be used when a custom data location is needed.

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
:maxdepth: 2
:caption: User Documentation

getting_started/index.md
tutorials/index.md
how_to/index.md
reference/index.md
```

```{toctree}
:maxdepth: 1
:caption: Contributors

contributing/index.md
```
