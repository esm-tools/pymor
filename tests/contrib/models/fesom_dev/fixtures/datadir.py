"""Data directory fixtures for FESOM UXarray (PI control) tests.

This module provides fixtures for accessing FESOM UXarray model run data,
using the BaseModelRun pattern for consistency across model contributions.
"""

import warnings

import pytest

from .model import FesomDevModelRun


@pytest.fixture(scope="session")
def fesom_uxarray_model_run(request, tmp_path_factory):
    """FESOM UXarray model run instance.

    This fixture creates a FesomDevModelRun instance that handles:
    - Routing between real and stub data based on environment/markers
    - Lazy-loading of data directories, mesh directories, and datasets
    - Caching of downloaded/generated resources

    Returns
    -------
    FesomDevModelRun
        Model run instance with data and mesh access
    """
    use_real = FesomDevModelRun.should_use_real_data(request)
    return FesomDevModelRun.from_module(
        __file__,
        use_real=use_real,
        tmp_path_factory=tmp_path_factory,
    )


@pytest.fixture(scope="session")
def fesom_uxarray_datadir(fesom_uxarray_model_run):
    """Data directory for FESOM UXarray (PI control).

    Returns stub data by default, or real data if:
    1. The PYCMOR_USE_REAL_TEST_DATA environment variable is set
    2. The real_data pytest marker is present

    Returns
    -------
    Path
        Path to the data directory
    """
    return fesom_uxarray_model_run.datadir


@pytest.fixture(scope="session")
def fesom_uxarray_meshdir(fesom_uxarray_model_run):
    """Mesh directory for FESOM UXarray (PI control).

    Returns stub mesh by default, or real mesh if:
    1. The PYCMOR_USE_REAL_TEST_DATA environment variable is set
    2. The real_data pytest marker is present

    Returns
    -------
    Path
        Path to the mesh directory
    """
    return fesom_uxarray_model_run.meshdir


# Deprecated aliases for backward compatibility


@pytest.fixture(scope="session")
def fesom_uxarray_real_datadir(tmp_path_factory):
    """Deprecated: Use fesom_uxarray_model_run with use_real=True instead."""
    warnings.warn(
        "fesom_uxarray_real_datadir is deprecated, use fesom_uxarray_model_run",
        DeprecationWarning,
        stacklevel=2,
    )
    model_run = FesomDevModelRun.from_module(__file__, use_real=True, tmp_path_factory=tmp_path_factory)
    return model_run.datadir


@pytest.fixture(scope="session")
def fesom_uxarray_stub_datadir(tmp_path_factory):
    """Deprecated: Use fesom_uxarray_model_run with use_real=False instead."""
    warnings.warn(
        "fesom_uxarray_stub_datadir is deprecated, use fesom_uxarray_model_run",
        DeprecationWarning,
        stacklevel=2,
    )
    model_run = FesomDevModelRun.from_module(__file__, use_real=False, tmp_path_factory=tmp_path_factory)
    return model_run.datadir


@pytest.fixture(scope="session")
def fesom_uxarray_real_meshdir(tmp_path_factory):
    """Deprecated: Use fesom_uxarray_model_run with use_real=True instead."""
    warnings.warn(
        "fesom_uxarray_real_meshdir is deprecated, use fesom_uxarray_model_run",
        DeprecationWarning,
        stacklevel=2,
    )
    model_run = FesomDevModelRun.from_module(__file__, use_real=True, tmp_path_factory=tmp_path_factory)
    return model_run.meshdir


@pytest.fixture(scope="session")
def fesom_uxarray_stub_meshdir(tmp_path_factory):
    """Deprecated: Use fesom_uxarray_model_run with use_real=False instead."""
    warnings.warn(
        "fesom_uxarray_stub_meshdir is deprecated, use fesom_uxarray_model_run",
        DeprecationWarning,
        stacklevel=2,
    )
    model_run = FesomDevModelRun.from_module(__file__, use_real=False, tmp_path_factory=tmp_path_factory)
    return model_run.meshdir


# Old naming scheme - deprecated


@pytest.fixture(scope="session")
def pi_uxarray_real_data(fesom_uxarray_real_datadir):
    """Deprecated: Use fesom_uxarray_datadir instead."""
    warnings.warn(
        "pi_uxarray_real_data is deprecated, use fesom_uxarray_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_uxarray_real_datadir


@pytest.fixture(scope="session")
def pi_uxarray_stub_data(fesom_uxarray_stub_datadir):
    """Deprecated: Use fesom_uxarray_datadir instead."""
    warnings.warn(
        "pi_uxarray_stub_data is deprecated, use fesom_uxarray_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_uxarray_stub_datadir


@pytest.fixture(scope="session")
def pi_uxarray_data(fesom_uxarray_datadir):
    """Deprecated: Use fesom_uxarray_datadir instead."""
    warnings.warn(
        "pi_uxarray_data is deprecated, use fesom_uxarray_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_uxarray_datadir


@pytest.fixture(scope="session")
def pi_uxarray_real_mesh(fesom_uxarray_real_meshdir):
    """Deprecated: Use fesom_uxarray_meshdir instead."""
    warnings.warn(
        "pi_uxarray_real_mesh is deprecated, use fesom_uxarray_meshdir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_uxarray_real_meshdir


@pytest.fixture(scope="session")
def pi_uxarray_stub_mesh(fesom_uxarray_stub_meshdir):
    """Deprecated: Use fesom_uxarray_meshdir instead."""
    warnings.warn(
        "pi_uxarray_stub_mesh is deprecated, use fesom_uxarray_meshdir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_uxarray_stub_meshdir


@pytest.fixture(scope="session")
def pi_uxarray_mesh(fesom_uxarray_meshdir):
    """Deprecated: Use fesom_uxarray_meshdir instead."""
    warnings.warn(
        "pi_uxarray_mesh is deprecated, use fesom_uxarray_meshdir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_uxarray_meshdir
