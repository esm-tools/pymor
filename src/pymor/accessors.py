"""
Xarray accessor registration module for pymor.

This module imports and registers all xarray accessors used throughout the pymor project.
By importing this module, all accessors become available on xarray DataArrays and Datasets.
"""

# Import modules that register xarray accessors
from .core import infer_freq  # noqa: F401

# Future accessor imports can be added here as the project grows
# from .other_module import other_accessor  # noqa: F401
