"""
Acquisition of external data: HTTP primitives, the local download cache, API keys and data providers.

This package stays import-light so the CLI can load it cheaply. Provider modules that need numpy
(``firebench.acquisition.hrrr``) are imported explicitly by their callers, never from here.
"""
