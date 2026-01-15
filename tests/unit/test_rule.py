import re

import pytest

from pycmor.core.pipeline import TestingPipeline
from pycmor.core.rule import Rule


def test_direct_init(simple_rule):
    rule = simple_rule
    assert all(isinstance(ip, re.Pattern) for ip in rule.input_patterns)
    assert isinstance(rule.cmor_variable, str)
    assert all(isinstance(p, str) for p in rule.pipelines)


def test_from_dict():
    data = {
        "inputs": [
            {
                "path": "/some/files/containing/",
                "pattern": "var1.*.nc",
            },
            {
                "path": "/some/other/files/containing/",
                "pattern": r"var1_(?P<year>\d{4})\.nc",  # noqa: W605
            },
        ],
        "cmor_variable": "var1",
        "pipelines": ["pycmor.core.pipeline.TestingPipeline"],
    }
    rule = Rule.from_dict(data)
    assert all(isinstance(ip, re.Pattern) for ip in rule.input_patterns)
    assert isinstance(rule.cmor_variable, str)
    assert all(isinstance(p, str) for p in rule.pipelines)


def test_from_dict_with_compound_name():
    """Test that compound_name is parsed to extract cmor_variable."""
    data = {
        "inputs": [
            {
                "path": "/some/files/containing/",
                "pattern": "var1.*.nc",
            },
        ],
        "compound_name": "atmos.tas.tavg-h2m-hxy-u.mon.GLB",
        "pipelines": ["pycmor.core.pipeline.TestingPipeline"],
    }
    rule = Rule.from_dict(data)
    assert rule.cmor_variable == "tas"  # Extracted from compound_name
    assert rule.compound_name == "atmos.tas.tavg-h2m-hxy-u.mon.GLB"  # Stored as attribute


def test_from_dict_with_cmip6_compound_name():
    """Test that CMIP6-style compound_name is parsed correctly."""
    data = {
        "inputs": [
            {
                "path": "/some/files/containing/",
                "pattern": "var1.*.nc",
            },
        ],
        "compound_name": "Amon.tas",
        "pipelines": ["pycmor.core.pipeline.TestingPipeline"],
    }
    rule = Rule.from_dict(data)
    assert rule.cmor_variable == "tas"  # Extracted from compound_name


def test_from_dict_both_cmor_variable_and_compound_name_consistent():
    """Test that providing both cmor_variable and compound_name works when they match."""
    data = {
        "inputs": [
            {
                "path": "/some/files/containing/",
                "pattern": "var1.*.nc",
            },
        ],
        "cmor_variable": "tas",
        "compound_name": "atmos.tas.tavg-h2m-hxy-u.mon.GLB",
        "pipelines": ["pycmor.core.pipeline.TestingPipeline"],
    }
    rule = Rule.from_dict(data)
    assert rule.cmor_variable == "tas"


def test_from_dict_both_cmor_variable_and_compound_name_inconsistent():
    """Test that providing both cmor_variable and compound_name fails when they don't match."""
    data = {
        "inputs": [
            {
                "path": "/some/files/containing/",
                "pattern": "var1.*.nc",
            },
        ],
        "cmor_variable": "wrong_var",
        "compound_name": "atmos.tas.tavg-h2m-hxy-u.mon.GLB",
        "pipelines": ["pycmor.core.pipeline.TestingPipeline"],
    }
    with pytest.raises(
        ValueError, match="cmor_variable 'wrong_var' does not match variable extracted from compound_name"
    ):
        Rule.from_dict(data)


def test_from_yaml():
    yaml_str = """
    inputs:
        - path: /some/files/containing/
          pattern: var1.*.nc
        - path: /some/other/files/containing/
          pattern: var1_(?P<year>\d{4})\.nc  # noqa: W605
    cmor_variable: var1
    pipelines:
      - pycmor.core.pipeline.TestingPipeline
    """  # noqa: W605
    rule = Rule.from_yaml(yaml_str)
    assert all(isinstance(ip, re.Pattern) for ip in rule.input_patterns)
    assert isinstance(rule.cmor_variable, str)
    assert all(isinstance(p, str) for p in rule.pipelines)


def test_match_pipelines(simple_rule):
    rule = simple_rule
    pipelines = [TestingPipeline(name="pycmor.pipeline.TestingPipeline")]
    rule.match_pipelines(pipelines)
