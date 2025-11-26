"""Dataset fixtures for FESOM 2.6 PI mesh model.

This module provides xarray Dataset fixtures that open the test data.
"""

import pytest


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_ds(fesom_2p6_pimesh_esm_tools_datadir):
    """Open FESOM 2.6 PI mesh dataset with xarray.

    Returns
    -------
    xr.Dataset
        The opened multi-file dataset from FESOM ocean output

    Notes
    -----
    Dataset is opened once per session and shared across tests for efficiency.
    """
    import xarray as xr

    matching_files = [
        f for f in (fesom_2p6_pimesh_esm_tools_datadir / "outdata/fesom/").iterdir() if f.name.startswith("temp.fesom")
    ]

    return xr.open_mfdataset(matching_files)
