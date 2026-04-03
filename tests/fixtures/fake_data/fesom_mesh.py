import pytest


def make_fake_grid():
    """
    This grid has all the dimension names and variable names similar to griddes.nc
    The dimension lengths are made up to reduce the size. Dummy values are used for variables.
    The purpose of this fake grid is just to test the setgrid functionality.
    """
    import numpy as np
    import xarray as xr

    # dimensions
    ncells = 100
    vertices = 18
    nlinks_max = 9
    ntriags = 2 * ncells
    Three = 3
    nlev = 3
    # coordinate variables
    lat = np.linspace(-90, 90, ncells)
    lon = np.linspace(-180, 180, ncells)
    # data variables
    lat_bnds = np.linspace(-90, 90, ncells * vertices).reshape(ncells, vertices)
    lon_bnds = np.linspace(-180, 180, ncells * vertices).reshape(ncells, vertices)
    cell_area = np.ones(ncells)
    node_node_links = np.zeros((ncells, nlinks_max))
    triag_nodes = np.zeros((ntriags, Three))
    coast = np.zeros(ncells)
    depth = np.zeros(nlev)
    depth_lev = np.zeros(ncells)
    fake_grid = xr.Dataset(
        data_vars=dict(
            lat_bnds=(["ncells", "vertices"], lat_bnds),
            lon_bnds=(["ncells", "vertices"], lon_bnds),
            cell_area=(["ncells"], cell_area),
            node_node_links=(["ncells", "nlinks_max"], node_node_links),
            triag_nodes=(["ntriags", "Three"], triag_nodes),
            coast=(["ncells"], coast),
            depth=(["nlev"], depth),
            depth_lev=(["ncells"], depth_lev),
        ),
        coords=dict(
            lon=("ncells", lon),
            lat=("ncells", lat),
        ),
        attrs=dict(description="fake grid"),
    )
    return fake_grid


@pytest.fixture
def fake_grid_file(tmp_path):
    d = tmp_path / "grid"
    d.mkdir()
    fake_grid_file = d / "fake_grid.nc"
    fake_grid = make_fake_grid()
    fake_grid.to_netcdf(fake_grid_file)
    return fake_grid_file
