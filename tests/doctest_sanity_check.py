"""
Sanity check for doctest infrastructure.

This module verifies that the doctest fixture setup in conftest.py is working correctly.
These are regular pytest tests, not doctests, to avoid pulling in heavy dependencies
during doctest collection.

The tests here verify:
1. Config file fixture is properly set up
2. XDG_CONFIG_HOME is correctly configured
3. The inherit section can be read from the test config
"""

import os
import pathlib

import yaml


def test_config_fixture_basic():
    """Test that XDG_CONFIG_HOME is set by the fixture."""
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    assert xdg_home is not None, "XDG_CONFIG_HOME should be set by the fixture"


def test_config_file_exists():
    """Test that the config file actually exists."""
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    assert xdg_home is not None, "XDG_CONFIG_HOME not set"

    config_file = pathlib.Path(xdg_home) / "pycmor" / "pycmor.yaml"
    assert config_file.exists(), f"Config file should exist at {config_file}"


def test_config_file_contents():
    """Test that the config file has the expected inherit section."""
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    assert xdg_home is not None, "XDG_CONFIG_HOME not set"

    config_file = pathlib.Path(xdg_home) / "pycmor" / "pycmor.yaml"
    assert config_file.exists(), f"Config file does not exist at {config_file}"

    with open(config_file) as f:
        config_data = yaml.safe_load(f)

    assert "inherit" in config_data, "Config should have inherit section"
    assert "source_id" in config_data["inherit"], "Inherit section should have source_id"


def test_pycmor_config_manager():
    """Test that PycmorConfigManager can read the inherit section.

    This is the actual test case that verifies config reading works.
    """
    from pycmor.core.config import PycmorConfigManager

    config = PycmorConfigManager.from_pycmor_cfg()
    defaults = config.get_inherit_section()

    assert len(defaults) > 0, "Inherit section should not be empty"
    assert "source_id" in defaults, "Inherit section should have source_id"
    assert defaults["source_id"] == "FESOM2", f"Expected source_id=FESOM2, got {defaults['source_id']}"
