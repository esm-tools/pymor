"""Generic configuration file fixtures.

Model-specific config fixtures have been moved to their respective
model fixture modules in tests/contrib/models/<model>/fixtures/config.py
"""

import pytest


@pytest.fixture
def test_config():
    """Generic test config file path."""
    from tests.utils.constants import TEST_ROOT

    return TEST_ROOT / "configs" / "test_config.yaml"


@pytest.fixture
def fesom_pi_mesh_config_file():
    """FESOM PI mesh config file path (legacy)."""
    from tests.utils.constants import TEST_ROOT

    return TEST_ROOT / "configs/fesom_pi_mesh_run.yaml"


@pytest.fixture
def test_config_cmip6():
    """Generic CMIP6 test config file path."""
    from tests.utils.constants import TEST_ROOT

    return TEST_ROOT / "configs" / "test_config_cmip6.yaml"


@pytest.fixture
def test_config_cmip7():
    """Generic CMIP7 test config file path."""
    from tests.utils.constants import TEST_ROOT

    return TEST_ROOT / "configs" / "test_config_cmip7.yaml"
