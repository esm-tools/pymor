"""Configuration fixtures for fesom_2p6_pimesh model."""

import pytest


@pytest.fixture
def fesom_2p6_pimesh_model_run(tmp_path_factory, request):
    """FESOM 2.6 PI mesh model run instance.

    Returns
    -------
    Fesom2p6PimeshModelRun
        Model run instance with data and config access
    """
    from tests.contrib.models.fesom_2p6_pimesh.fixtures.model import Fesom2p6PimeshModelRun

    use_real = Fesom2p6PimeshModelRun.should_use_real_data(request)
    return Fesom2p6PimeshModelRun.from_module(__file__, use_real=use_real, tmp_path_factory=tmp_path_factory)


@pytest.fixture
def fesom_2p6_pimesh_config_path(fesom_2p6_pimesh_model_run):
    """Path to FESOM 2.6 PI mesh CMIP6 config file.

    Returns
    -------
    Path
        Path to config_cmip6.yaml
    """
    return fesom_2p6_pimesh_model_run.config_path_cmip6


@pytest.fixture
def fesom_2p6_pimesh_config_path_cmip7(fesom_2p6_pimesh_model_run):
    """Path to FESOM 2.6 PI mesh CMIP7 config file.

    Returns
    -------
    Path
        Path to config_cmip7.yaml
    """
    return fesom_2p6_pimesh_model_run.config_path_cmip7


# Legacy fixture names for backwards compatibility
fesom_2p6_pimesh_esm_tools_config = fesom_2p6_pimesh_config_path
fesom_2p6_pimesh_esm_tools_config_cmip7 = fesom_2p6_pimesh_config_path_cmip7
