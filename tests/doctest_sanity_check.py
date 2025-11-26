"""
Sanity check for doctest infrastructure.

This module verifies that the doctest fixture setup in conftest.py is working correctly.
It should be run with pytest --doctest-modules before running the full doctest suite.

The tests here verify:
1. Config file fixture is properly set up
2. XDG_CONFIG_HOME is correctly configured
3. The inherit section can be read from the test config
"""


def test_config_fixture_basic():
    """
    Test that the config fixture creates a proper config file.

    This verifies the conftest.py fixture is working correctly.

    >>> import os
    >>> import pathlib
    >>> # Check that XDG_CONFIG_HOME is set (by the fixture)
    >>> xdg_home = os.environ.get("XDG_CONFIG_HOME")
    >>> print(f"XDG_CONFIG_HOME is set: {xdg_home is not None}")
    XDG_CONFIG_HOME is set: True
    """
    pass


def test_config_file_exists():
    """
    Test that the config file actually exists.

    >>> import os
    >>> import pathlib
    >>> xdg_home = os.environ.get("XDG_CONFIG_HOME")
    >>> if xdg_home:
    ...     config_file = pathlib.Path(xdg_home) / "pycmor" / "pycmor.yaml"
    ...     print(f"Config file exists: {config_file.exists()}")
    ... else:
    ...     print("XDG_CONFIG_HOME not set")
    Config file exists: True
    """
    pass


def test_config_file_contents():
    """
    Test that the config file has the expected inherit section.

    >>> import os
    >>> import pathlib
    >>> import yaml
    >>> xdg_home = os.environ.get("XDG_CONFIG_HOME")
    >>> if xdg_home:
    ...     config_file = pathlib.Path(xdg_home) / "pycmor" / "pycmor.yaml"
    ...     if config_file.exists():
    ...         with open(config_file) as f:
    ...             config_data = yaml.safe_load(f)
    ...         print(f"Has inherit section: {'inherit' in config_data}")
    ...         if 'inherit' in config_data:
    ...             print(f"source_id in inherit: {'source_id' in config_data['inherit']}")
    ...     else:
    ...         print("Config file does not exist")
    ... else:
    ...     print("XDG_CONFIG_HOME not set")
    Has inherit section: True
    source_id in inherit: True
    """
    pass


def test_pycmor_config_manager():
    """
    Test that PycmorConfigManager can read the inherit section.

    This is the actual test case that's failing in the main codebase.

    >>> from pycmor.core.config import PycmorConfigManager
    >>> config = PycmorConfigManager.from_pycmor_cfg()
    >>> defaults = config.get_inherit_section()
    >>> print(f"Got inherit section: {len(defaults) > 0}")
    Got inherit section: True
    >>> print(f"Has source_id: {'source_id' in defaults}")
    Has source_id: True
    >>> print(f"source_id value: {defaults.get('source_id')}")
    source_id value: FESOM2
    """
    pass


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
