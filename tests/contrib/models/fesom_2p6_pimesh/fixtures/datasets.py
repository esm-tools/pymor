"""Dataset fixtures for FESOM 2.6 PI mesh model.

This module provides xarray dataset fixtures that load FESOM 2.6 PI mesh data
using the BaseModelRun pattern.
"""

import pytest


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_ds(fesom_2p6_pimesh_esm_tools_model_run):
    """Open FESOM 2.6 PI mesh dataset with xarray.

    Returns
    -------
    xr.Dataset
        Opened dataset from the model run
    """
    return fesom_2p6_pimesh_esm_tools_model_run.ds
