import os
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# Add the src-layout package root so autodoc imports ``firebench`` correctly.
sys.path.insert(0, os.path.abspath('../src'))

project = 'FireBench'
author = 'WIRC SJSU'
project_metadata = tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text())
release = project_metadata['project']['version']
version = release
copyright = '%Y, Aurélien Costes, WIRC SJSU'

extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.mathjax',
    'sphinx.ext.autosummary',
    'sphinx_click',
]

templates_path = ['_templates']
exclude_patterns = []

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

# Enable Markdown features (MyST)
myst_enable_extensions = [
    "deflist",
    "fieldlist",
    "attrs_block",
    "colon_fence",
    "substitution",
    "tasklist",
    "amsmath",
    "dollarmath",
]
myst_heading_anchors = 3

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

autosummary_generate = True
napoleon_numpy_docstring = True

# External services occasionally throttle link checks. Retry transient failures; add a narrowly
# scoped ignore only when an upstream URL has a tracked, persistent availability problem.
linkcheck_retries = 2
linkcheck_timeout = 15
linkcheck_anchors = True
# These publisher and incident pages are valid in a browser but reject automated GET requests with
# bot-protection responses. Their exact URLs are reviewed manually when references change.
linkcheck_ignore = [
    r"https://doi\.org/10\.1175/BAMS-D-(11-00019|16-0236)\.1",
    r"https://doi\.org/10\.(1071|1155|3390)/.*",
    r"https://www\.fire\.ca\.gov/incidents/.*",
    r"https://www\.publish\.csiro\.au/.*",
]

html_logo = "_static/images/firebench_logo.png"
html_static_path = ["_static"]
