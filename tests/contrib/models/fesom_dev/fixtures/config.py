"""Configuration fixtures for fesom_uxarray model."""

import pytest


@pytest.fixture
def fesom_uxarray_model_run(tmp_path_factory, request):
    """FESOM UXArray model run instance.

    Returns
    -------
    FesomUxarrayModelRun
        Model run instance with data and config access
    """
    from tests.contrib.models.fesom_uxarray.fixtures.model import FesomUxarrayModelRun

    use_real = FesomUxarrayModelRun.should_use_real_data(request)
    return FesomUxarrayModelRun.from_module(__file__, use_real=use_real, tmp_path_factory=tmp_path_factory)


@pytest.fixture
def fesom_uxarray_config_path(fesom_uxarray_model_run):
    """Path to FESOM UXArray CMIP6 config file.

    Returns
    -------
    Path
        Path to config_cmip6.yaml
    """
    return fesom_uxarray_model_run.config_path_cmip6


@pytest.fixture
def fesom_uxarray_config_path_cmip7(fesom_uxarray_model_run):
    """Path to FESOM UXArray CMIP7 config file.

    Returns
    -------
    Path
        Path to config_cmip7.yaml
    """
    return fesom_uxarray_model_run.config_path_cmip7


# Legacy fixture names for backwards compatibility
pi_uxarray_config = fesom_uxarray_config_path
pi_uxarray_config_cmip7 = fesom_uxarray_config_path_cmip7
