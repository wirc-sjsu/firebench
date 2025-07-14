import os
import sys

# Add src/ to the path so Sphinx can find the code
sys.path.insert(0, os.path.abspath('../src/firebench'))

project = 'Firebench'
author = 'WIRC SJSU'
version = '0.7.0'
release = '0.7.0'
copyright = '%Y, Aurélien Costes, WIRC SJSU'

extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.mathjax',
    'sphinx.ext.autosummary',
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
    "colon_fence",
]

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

autosummary_generate = True
napoleon_numpy_docstring = True

html_logo = "_static/images/firebench_logo.png"
html_static_path = ["_static"]