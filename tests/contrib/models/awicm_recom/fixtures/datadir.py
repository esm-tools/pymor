"""Data directory fixtures for AWI-CM 1.0 RECOM biogeochemistry model.

This module provides fixtures for accessing AWI-CM RECOM model run data,
using the BaseModelRun pattern for consistency across model contributions.
"""

import warnings

import pytest

from .model import AwicmRecomModelRun


@pytest.fixture(scope="session")
def awicm_1p0_recom_model_run(request, tmp_path_factory):
    """AWI-CM 1.0 RECOM model run instance.

    This fixture creates an AwicmRecomModelRun instance that handles:
    - Routing between real and stub data based on environment/markers
    - Lazy-loading of data directories and datasets
    - Caching of downloaded/generated resources

    Returns
    -------
    AwicmRecomModelRun
        Model run instance with data access
    """
    use_real = AwicmRecomModelRun.should_use_real_data(request)
    return AwicmRecomModelRun.from_module(
        __file__,
        use_real=use_real,
        tmp_path_factory=tmp_path_factory,
    )


@pytest.fixture(scope="session")
def awicm_1p0_recom_datadir(awicm_1p0_recom_model_run):
    """Data directory for AWI-CM 1.0 RECOM.

    Returns stub data by default, or real data if:
    1. The PYCMOR_USE_REAL_TEST_DATA environment variable is set
    2. The real_data pytest marker is present

    Returns
    -------
    Path
        Path to the data directory
    """
    return awicm_1p0_recom_model_run.datadir


# Deprecated aliases for backward compatibility


@pytest.fixture(scope="session")
def awicm_1p0_recom_real_datadir(tmp_path_factory):
    """Deprecated: Use awicm_1p0_recom_model_run with use_real=True instead."""
    warnings.warn(
        "awicm_1p0_recom_real_datadir is deprecated, use awicm_1p0_recom_model_run",
        DeprecationWarning,
        stacklevel=2,
    )
    model_run = AwicmRecomModelRun.from_module(__file__, use_real=True, tmp_path_factory=tmp_path_factory)
    return model_run.datadir


@pytest.fixture(scope="session")
def awicm_1p0_recom_real_data(awicm_1p0_recom_real_datadir):
    """Deprecated: Use awicm_1p0_recom_datadir instead."""
    warnings.warn(
        "awicm_1p0_recom_real_data is deprecated, use awicm_1p0_recom_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return awicm_1p0_recom_real_datadir


@pytest.fixture(scope="session")
def awicm_1p0_recom_stub_datadir(tmp_path_factory):
    """Deprecated: Use awicm_1p0_recom_model_run with use_real=False instead."""
    warnings.warn(
        "awicm_1p0_recom_stub_datadir is deprecated, use awicm_1p0_recom_model_run",
        DeprecationWarning,
        stacklevel=2,
    )
    model_run = AwicmRecomModelRun.from_module(__file__, use_real=False, tmp_path_factory=tmp_path_factory)
    return model_run.datadir


@pytest.fixture(scope="session")
def awicm_1p0_recom_stub_data(awicm_1p0_recom_stub_datadir):
    """Deprecated: Use awicm_1p0_recom_datadir instead."""
    warnings.warn(
        "awicm_1p0_recom_stub_data is deprecated, use awicm_1p0_recom_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return awicm_1p0_recom_stub_datadir


@pytest.fixture(scope="session")
def awicm_1p0_recom_data(awicm_1p0_recom_datadir):
    """Deprecated: Use awicm_1p0_recom_datadir instead."""
    warnings.warn(
        "awicm_1p0_recom_data is deprecated, use awicm_1p0_recom_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return awicm_1p0_recom_datadir
