import logging

import pytest

from tests.utils.constants import TEST_ROOT  # noqa: F401


@pytest.fixture(scope="session", autouse=True)
def setup_doctest_config_file(tmp_path_factory):
    """Create a temporary config file for doctests that expect inherit section.

    This fixture sets up a temporary XDG_CONFIG_HOME with a pycmor.yaml file
    containing an inherit section, so doctests can demonstrate config behavior
    without requiring actual user config files.
    """
    import os

    import yaml

    # Create a session-scoped temp directory
    tmp_path = tmp_path_factory.mktemp("config")

    # Set XDG_CONFIG_HOME to tmp_path so PycmorConfigManager finds our test config
    config_dir = tmp_path / "pycmor"
    config_dir.mkdir()
    os.environ["XDG_CONFIG_HOME"] = str(tmp_path)

    # Create the config file with inherit section matching doctest examples
    config_file = config_dir / "pycmor.yaml"
    config_content = {
        "inherit": {
            "source_id": "FESOM2",
            "experiment_id": "historical",
            "variant_label": "r1i1p1f1",
            "grid_label": "gn",
            "institution_id": "AWI",
            "output_directory": "/tmp/cmor_output",
        }
    }
    config_file.write_text(yaml.dump(config_content))

    yield

    # Cleanup: remove the env var after session
    if "XDG_CONFIG_HOME" in os.environ:
        del os.environ["XDG_CONFIG_HOME"]


@pytest.fixture(scope="function", autouse=True)
def suppress_third_party_logs():
    """Suppress noisy INFO logs from distributed/dask/prefect during tests.

    This runs before every test function to ensure logs are suppressed even
    when distributed.Client creates new workers.
    """
    # Set WARNING level for all noisy distributed/dask/prefect loggers
    loggers_to_suppress = [
        "distributed",
        "distributed.core",
        "distributed.scheduler",
        "distributed.nanny",
        "distributed.worker",
        "distributed.http.proxy",
        "distributed.worker.memory",
        "distributed.comm",
        "prefect",
    ]

    for logger_name in loggers_to_suppress:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


pytest_plugins = [
    "tests.fixtures.CMIP_Tables_Dir",
    "tests.fixtures.CV_Dir",
    "tests.fixtures.cmip7_test_data",
    "tests.fixtures.config_files",
    "tests.fixtures.configs",
    "tests.fixtures.datasets",
    "tests.fixtures.environment",
    "tests.fixtures.example_data.awicm_recom",
    "tests.fixtures.example_data.fesom_2p6_pimesh",
    "tests.fixtures.example_data.pi_uxarray",
    "tests.fixtures.fake_data.fesom_mesh",
    "tests.fixtures.fake_filesystem",
    "tests.fixtures.sample_rules",
    "tests.fixtures.config_files",
    "tests.fixtures.CV_Dir",
    "tests.fixtures.CMIP_Tables_Dir",
    "tests.fixtures.config_files",
    "tests.fixtures.CV_Dir",
    "tests.fixtures.data_requests",
]
