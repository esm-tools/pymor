# Just import dask for parallelisms...
import os

import dask  # noqa
import pytest
import xarray as xr

# Meta tests validate environment setup (NetCDF libraries, engines)
# These tests should use real data when validating the environment,
# but can be skipped when using stub data in regular CI
pytestmark = pytest.mark.skipif(
    not os.getenv("PYCMOR_USE_REAL_TEST_DATA"),
    reason="Meta tests require real data for environment validation (set PYCMOR_USE_REAL_TEST_DATA=1)",
)


@pytest.mark.parametrize(
    "engine",
    [
        "netcdf4",
    ],
)
def test_open_awicm_1p0_recom(awicm_1p0_recom_datadir, engine):
    ds = xr.open_mfdataset(
        f"{awicm_1p0_recom_datadir}/awi-esm-1-1-lr_kh800/piControl/outdata/fesom/*.nc",
        engine=engine,
    )
    assert isinstance(ds, xr.Dataset)


@pytest.mark.parametrize(
    "engine,use_cftime,parallel",
    [
        pytest.param("h5netcdf", False, False, id="basic"),
        pytest.param("h5netcdf", True, False, id="with_cftime"),
        pytest.param("h5netcdf", False, True, id="with_parallel"),
        pytest.param("h5netcdf", True, True, id="with_cftime_and_parallel"),
    ],
)
def test_open_fesom_2p6_pimesh_esm_tools(fesom_2p6_pimesh_esm_tools_datadir, engine, use_cftime, parallel):
    matching_files = [
        f for f in (fesom_2p6_pimesh_esm_tools_datadir / "outdata/fesom/").iterdir() if f.name.startswith("temp.fesom")
    ]
    assert len(matching_files) > 0

    kwargs = {"engine": engine}
    if use_cftime:
        kwargs["use_cftime"] = True
    if parallel:
        kwargs["parallel"] = True

    ds = xr.open_mfdataset(matching_files, **kwargs)
    assert isinstance(ds, xr.Dataset)
