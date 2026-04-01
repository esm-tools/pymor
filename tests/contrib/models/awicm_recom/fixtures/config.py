"""Configuration fixtures for awicm_recom model."""

import pytest


@pytest.fixture
def awicm_recom_model_run(tmp_path_factory, request):
    """AWI-CM RECOM model run instance.

    Returns
    -------
    AwicmRecomModelRun
        Model run instance with data and config access
    """
    from tests.contrib.models.awicm_recom.fixtures.model import AwicmRecomModelRun

    use_real = AwicmRecomModelRun.should_use_real_data(request)
    return AwicmRecomModelRun.from_module(__file__, use_real=use_real, tmp_path_factory=tmp_path_factory)


@pytest.fixture
def awicm_recom_config_path(awicm_recom_model_run):
    """Path to AWI-CM RECOM CMIP6 config file.

    Returns
    -------
    Path
        Path to config_cmip6.yaml
    """
    return awicm_recom_model_run.config_path_cmip6


@pytest.fixture
def awicm_recom_config_path_cmip7(awicm_recom_model_run):
    """Path to AWI-CM RECOM CMIP7 config file.

    Returns
    -------
    Path
        Path to config_cmip7.yaml
    """
    return awicm_recom_model_run.config_path_cmip7


# Legacy fixture names for backwards compatibility
awicm_1p0_recom_config = awicm_recom_config_path
awicm_1p0_recom_config_cmip7 = awicm_recom_config_path_cmip7
