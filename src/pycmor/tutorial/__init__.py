"""Tutorial datasets for pycmor examples and testing.

This module provides an interface similar to xarray.tutorial for accessing
pycmor's example datasets. It allows users and tests to easily load example
climate model data for learning and experimentation.

Examples
--------
Load a dataset from a registered model::

    import pycmor.tutorial as tutorial
    ds = tutorial.open_dataset("fesom_2p6")

List available datasets::

    tutorial.available_datasets()

Get info about a dataset::

    tutorial.info("fesom_2p6")
"""

from .loader import available_datasets, info, open_dataset

__all__ = ["available_datasets", "info", "open_dataset"]
