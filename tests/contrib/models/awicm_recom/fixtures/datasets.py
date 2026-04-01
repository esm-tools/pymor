"""Dataset fixtures for AWI-CM 1.0 RECOM biogeochemistry model.

This module provides xarray dataset fixtures that load AWI-CM RECOM data
using the BaseModelRun pattern.
"""

import pytest


@pytest.fixture(scope="session")
def awicm_1p0_recom_ds(awicm_1p0_recom_model_run):
    """Open AWI-CM 1.0 RECOM dataset with xarray.

    Returns
    -------
    xr.Dataset
        Opened dataset from the model run
    """
    return awicm_1p0_recom_model_run.ds
