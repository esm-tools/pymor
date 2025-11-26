"""Dataset fixtures for FESOM UXarray (PI control) tests.

This module provides xarray Dataset fixtures that open the test data.
"""

import pytest


@pytest.fixture(scope="session")
def fesom_uxarray_ds(fesom_uxarray_datadir):
    """Open FESOM UXarray PI control dataset with xarray.

    Returns
    -------
    xr.Dataset
        The opened dataset from FESOM ocean output

    Notes
    -----
    Dataset is opened once per session and shared across tests for efficiency.
    """
    import xarray as xr

    # Find NetCDF files in the data directory
    nc_files = list(fesom_uxarray_datadir.glob("*.nc"))

    if len(nc_files) == 1:
        return xr.open_dataset(nc_files[0])
    else:
        return xr.open_mfdataset(nc_files)
