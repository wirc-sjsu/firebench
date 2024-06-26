# FireBench

[![CI](https://github.com/wirc-sjsu/firebench/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/ci.yml)
[![pages-build-deployment](https://github.com/wirc-sjsu/firebench/actions/workflows/pages/pages-build-deployment/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/pages/pages-build-deployment)
[![codecov](https://codecov.io/github/wirc-sjsu/firebench/graph/badge.svg?token=8F44OX12EW)](https://codecov.io/github/wirc-sjsu/firebench)
[![Security Analysis](https://github.com/wirc-sjsu/firebench/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/security.yml)
![Pylint Score](https://img.shields.io/badge/Pylint-10.00-brightgreen.svg)
[![Check linting with Pylint](https://github.com/wirc-sjsu/firebench/actions/workflows/pylint.yml/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/pylint.yml)
[![Black Code Formatting Check](https://github.com/wirc-sjsu/firebench/actions/workflows/black.yml/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/black.yml)
![GitHub License](https://img.shields.io/github/license/wirc-sjsu/firebench)

**FireBench** is a Python library designed for the systematic benchmarking and inter-comparison of fire models.
Recent advancements in fire modeling have introduced complex and varied models, but there is a lack of systematic evaluation regarding their accuracy, efficiency, sensitivity, validity domain, and inter-compatibility.
FireBench aims to address this gap by providing a framework to assess fire models on the following criteria:

- **Accuracy**: Precision in predicting fire front positions and plume dynamics.
- **Efficiency**: Computational resources required for specific computation.
- **Sensitivity**: Model outputs' responsiveness to input variations, crucial for calibration and data assimilation.
- **Validity Domain**: Operational input ranges for which models are applicable.
- **Inter-Compatibility**: Integration capabilities with other models.

FireBench offers a dual approach for evaluation: intercomparison without extensive observational data and benchmarking against a validation dataset. This framework aims to enhance fire modeling for both scientific research and operational applications, with results archived in a dedicated database.

## Community Discussions

We encourage you to use the [GitHub Discussions](https://github.com/wirc-sjsu/firebench/discussions) tab for questions, help requests, and general discussions about the project. This helps keep our issue tracker focused on bugs and feature requests.

### How to Use Discussions

- **Q&A**: If you have a question about using FireBench, please check the Q&A category.
- **Ideas**: Share your ideas for new features or improvements in the Ideas category.
- **Show and Tell**: Showcase your projects and workflows using FireBench.
- **General**: For any other discussions related to FireBench.

Feel free to start a new discussion or join existing ones to engage with the community!

## Contributing

We welcome contributions to FireBench! Please see our [contribution guidelines](CONTRIBUTE.md) for more information on how to contribute.