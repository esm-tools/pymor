"""Data directory fixtures for FESOM 2.6 PI mesh model.

This module provides fixtures for accessing FESOM 2.6 PI mesh model run data,
using the BaseModelRun pattern for consistency across model contributions.
"""

import warnings

import pytest

from .model import Fesom2p6PimeshModelRun


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_model_run(request, tmp_path_factory):
    """FESOM 2.6 PI mesh model run instance.

    This fixture creates a Fesom2p6PimeshModelRun instance that handles:
    - Routing between real and stub data based on environment/markers
    - Lazy-loading of data directories and datasets
    - Caching of downloaded/generated resources

    Returns
    -------
    Fesom2p6PimeshModelRun
        Model run instance with data access
    """
    use_real = Fesom2p6PimeshModelRun.should_use_real_data(request)
    return Fesom2p6PimeshModelRun.from_module(
        __file__,
        use_real=use_real,
        tmp_path_factory=tmp_path_factory,
    )


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_datadir(fesom_2p6_pimesh_esm_tools_model_run):
    """Data directory for FESOM 2.6 PI mesh.

    Returns stub data by default, or real data if:
    1. The PYCMOR_USE_REAL_TEST_DATA environment variable is set
    2. The real_data pytest marker is present

    Returns
    -------
    Path
        Path to the data directory
    """
    return fesom_2p6_pimesh_esm_tools_model_run.datadir


# Deprecated aliases for backward compatibility


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_real_datadir(tmp_path_factory):
    """Deprecated: Use fesom_2p6_pimesh_esm_tools_model_run with use_real=True instead."""
    warnings.warn(
        "fesom_2p6_pimesh_esm_tools_real_datadir is deprecated, use fesom_2p6_pimesh_esm_tools_model_run",
        DeprecationWarning,
        stacklevel=2,
    )
    model_run = Fesom2p6PimeshModelRun.from_module(__file__, use_real=True, tmp_path_factory=tmp_path_factory)
    return model_run.datadir


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_real_data(fesom_2p6_pimesh_esm_tools_real_datadir):
    """Deprecated: Use fesom_2p6_pimesh_esm_tools_datadir instead."""
    warnings.warn(
        "fesom_2p6_pimesh_esm_tools_real_data is deprecated, use fesom_2p6_pimesh_esm_tools_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_2p6_pimesh_esm_tools_real_datadir


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_stub_datadir(tmp_path_factory):
    """Deprecated: Use fesom_2p6_pimesh_esm_tools_model_run with use_real=False instead."""
    warnings.warn(
        "fesom_2p6_pimesh_esm_tools_stub_datadir is deprecated, use fesom_2p6_pimesh_esm_tools_model_run",
        DeprecationWarning,
        stacklevel=2,
    )
    model_run = Fesom2p6PimeshModelRun.from_module(__file__, use_real=False, tmp_path_factory=tmp_path_factory)
    return model_run.datadir


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_stub_data(fesom_2p6_pimesh_esm_tools_stub_datadir):
    """Deprecated: Use fesom_2p6_pimesh_esm_tools_datadir instead."""
    warnings.warn(
        "fesom_2p6_pimesh_esm_tools_stub_data is deprecated, use fesom_2p6_pimesh_esm_tools_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_2p6_pimesh_esm_tools_stub_datadir


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_data(fesom_2p6_pimesh_esm_tools_datadir):
    """Deprecated: Use fesom_2p6_pimesh_esm_tools_datadir instead."""
    warnings.warn(
        "fesom_2p6_pimesh_esm_tools_data is deprecated, use fesom_2p6_pimesh_esm_tools_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_2p6_pimesh_esm_tools_datadir
