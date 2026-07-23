# Dependencies

The dependency declarations in `pyproject.toml` are the source of truth. The lists below summarize
the current FireBench 0.10 requirements.

## Required

- Click >= 8.1
- contourpy < 2.0
- Contextily < 2.0
- GeoPandas < 2.0
- h5py < 4.0
- hdf5plugin >= 6.0
- Matplotlib > 3.8
- Numba < 1.0
- NumPy < 3.0
- Pint < 1.0
- pyproj < 4.0
- pytz > 2025.0
- PyYAML >= 6.0
- Rasterio < 2.0
- ReportLab < 5.0
- SALib < 2.0
- SciPy < 2.0
- Tomli >= 2.0 on Python versions earlier than 3.11

## Development

Install the development dependency group with `python -m pip install -e ".[dev]"`. It contains:

- Bandit
- Black
- Pylint
- pytest
- pytest-cov
- pytest-mock
- Shapely

Install the documentation group with `python -m pip install -e ".[docs]"`. It contains MyST Parser,
pytest for validating documentation examples, Sphinx, Sphinx Click, and the Read the Docs theme.
Like the required and development groups, this list is declared only in `pyproject.toml`.
