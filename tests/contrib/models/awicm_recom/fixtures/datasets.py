"""Dataset fixtures for AWI-CM 1.0 RECOM biogeochemistry model.

This module provides xarray Dataset fixtures that open the test data.
"""

import pytest


@pytest.fixture(scope="session")
def awicm_1p0_recom_ds(awicm_1p0_recom_datadir):
    """Open AWI-CM 1.0 RECOM dataset with xarray.

    Returns
    -------
    xr.Dataset
        The opened multi-file dataset from FESOM ocean output

    Notes
    -----
    Uses netcdf4 engine for reading. Dataset is opened once per session
    and shared across tests for efficiency.
    """
    import xarray as xr

    return xr.open_mfdataset(
        f"{awicm_1p0_recom_datadir}/awi-esm-1-1-lr_kh800/piControl/outdata/fesom/*.nc",
        engine="netcdf4",
    )
