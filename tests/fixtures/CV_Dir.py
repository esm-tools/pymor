import pytest


@pytest.fixture
def CV_dir():
    from tests.utils.constants import TEST_ROOT

    return TEST_ROOT / "data" / "CV" / "CMIP6_CVs"
