"""Dataset fixtures for FESOM UXarray (PI control) tests.

This module provides xarray dataset fixtures that load FESOM UXarray data
using the BaseModelRun pattern.
"""

import pytest


@pytest.fixture(scope="session")
def fesom_uxarray_ds(fesom_uxarray_model_run):
    """Open FESOM UXarray dataset with xarray.

    Returns
    -------
    xr.Dataset
        Opened dataset from the model run
    """
    return fesom_uxarray_model_run.ds
