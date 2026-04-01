"""Fixtures for xarray datasets.

Note: Heavy dependencies (xarray) are imported lazily inside fixtures
to avoid slowing down test collection.
"""

import pytest


@pytest.fixture
def fesom_pi_sst_ds():
    import xarray as xr

    from tests.utils.constants import TEST_ROOT

    return xr.open_dataset(TEST_ROOT / "data/test_experiments/piControl_on_PI/output_pi/sst.fesom.1948.nc")
