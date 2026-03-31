"""
Sanity check for doctest infrastructure.

This module verifies that the doctest fixture setup in conftest.py is working correctly.
"""

import os
import pathlib

import yaml


def test_doctest_infrastructure_core_config_get_inherit_section():
    """
    Test that doctest infrastructure is set up correctly.

    In the CI environment, this test should work fine, as the relevant
    config file is injected by pytest_configure in conftest.py.
    """
    xdg_config_home = pathlib.Path(os.environ["XDG_CONFIG_HOME"])
    config_file = xdg_config_home / "pycmor" / "pycmor.yaml"

    with open(config_file) as f:
        cfg = yaml.safe_load(f)

    # Verify the config file has the expected inherit section
    assert "inherit" in cfg
    assert cfg["inherit"]["source_id"] == "FESOM2"
    assert cfg["inherit"]["experiment_id"] == "historical"


def get_test_config():
    """
    Helper function for doctests to get the test config.

    Examples
    --------
    >>> config = get_test_config()
    >>> config['inherit']['source_id']
    'FESOM2'
    >>> config['inherit']['experiment_id']
    'historical'
    """
    xdg_config_home = pathlib.Path(os.environ["XDG_CONFIG_HOME"])
    config_file = xdg_config_home / "pycmor" / "pycmor.yaml"

    with open(config_file) as f:
        cfg = yaml.safe_load(f)

    return cfg
