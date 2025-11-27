"""Library integration tests for pycmor CMORizer class.

This module tests the library interface (CMORizer API) for all registered
model runs with both CMIP6 and CMIP7 configurations. Tests are organized
as a matrix of [model] x [cmip_version].
"""

import pytest
import yaml

from pycmor.core.cmorizer import CMORizer
from pycmor.core.logging import logger
from tests.utils.entry_points import discover_model_runs

# Discover all registered model runs
MODEL_RUNS = discover_model_runs()
MODEL_NAMES = sorted(MODEL_RUNS.keys())


@pytest.fixture(params=MODEL_NAMES)
def model_run_instance(request, tmp_path_factory):
    """Fixture that provides model run instances for all registered models.

    Parameters
    ----------
    request : pytest.FixtureRequest
        Pytest request object with model name as parameter
    tmp_path_factory : pytest.TempPathFactory
        Factory for creating temporary directories

    Returns
    -------
    BaseModelRun
        Model run instance with data and config access
    """
    model_name = request.param
    model_class = MODEL_RUNS[model_name]

    # Determine if we should use real data based on markers or env var
    use_real = model_class.should_use_real_data(request)

    # Create instance using from_module (pass the model.py path)
    # We need to find where the model class is defined
    import inspect

    module_file = inspect.getfile(model_class)
    return model_class.from_module(module_file, use_real=use_real, tmp_path_factory=tmp_path_factory)


@pytest.mark.parametrize("cmip_version", ["cmip6", "cmip7"])
def test_library_initialization(model_run_instance, cmip_version):
    """Test that CMORizer can be initialized from model config (library API).

    This test validates that the CMORizer class can be instantiated from
    configuration without executing the processing pipeline.

    Parameters
    ----------
    model_run_instance : BaseModelRun
        Model run instance with data and config
    cmip_version : str
        CMIP version to test (cmip6 or cmip7)
    """
    # Get the appropriate config path
    if cmip_version == "cmip6":
        config_path = model_run_instance.config_path_cmip6
    else:
        config_path = model_run_instance.config_path_cmip7

    model_name = model_run_instance.__class__.__name__
    logger.info(f"Testing library initialization for {model_name} with {cmip_version.upper()}")

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    # Replace REPLACE_ME placeholders with actual data paths
    for rule in cfg.get("rules", []):
        for input_spec in rule.get("inputs", []):
            if "path" in input_spec and "REPLACE_ME" in input_spec["path"]:
                input_spec["path"] = input_spec["path"].replace("REPLACE_ME", str(model_run_instance.datadir))
        if "mesh_path" in rule and "REPLACE_ME" in rule["mesh_path"]:
            rule["mesh_path"] = rule["mesh_path"].replace("REPLACE_ME", str(model_run_instance.datadir))

    # Test that CMORizer can be constructed
    cmorizer = CMORizer.from_dict(cfg)
    assert cmorizer is not None
    assert len(cmorizer.rules) > 0, "CMORizer should have at least one rule"


@pytest.mark.parametrize("cmip_version", ["cmip6", "cmip7"])
def test_library_process(model_run_instance, cmip_version, tmp_path):
    """Test that CMORizer can process data from model config (library API).

    This test validates the full processing pipeline using the CMORizer
    library interface, from initialization through data processing to
    output file creation.

    Parameters
    ----------
    model_run_instance : BaseModelRun
        Model run instance with data and config
    cmip_version : str
        CMIP version to test (cmip6 or cmip7)
    tmp_path : Path
        Temporary directory for test artifacts
    """
    # Get the appropriate config path
    if cmip_version == "cmip6":
        config_path = model_run_instance.config_path_cmip6
    else:
        config_path = model_run_instance.config_path_cmip7

    model_name = model_run_instance.__class__.__name__
    logger.info(f"Testing library processing for {model_name} with {cmip_version.upper()}")

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    # Replace REPLACE_ME placeholders with actual data paths
    for rule in cfg.get("rules", []):
        for input_spec in rule.get("inputs", []):
            if "path" in input_spec and "REPLACE_ME" in input_spec["path"]:
                input_spec["path"] = input_spec["path"].replace("REPLACE_ME", str(model_run_instance.datadir))
        if "mesh_path" in rule and "REPLACE_ME" in rule["mesh_path"]:
            rule["mesh_path"] = rule["mesh_path"].replace("REPLACE_ME", str(model_run_instance.datadir))

    # Update output directory to tmp_path
    if "general" not in cfg:
        cfg["general"] = {}
    cfg["general"]["output_directory"] = str(tmp_path / "output")

    # Process the data
    cmorizer = CMORizer.from_dict(cfg)
    cmorizer.process()

    # Verify output was created
    from pathlib import Path

    output_dir = Path(cfg["general"]["output_directory"])
    assert output_dir.exists(), f"Output directory not created: {output_dir}"
    output_files = list(output_dir.rglob("*.nc"))
    assert len(output_files) > 0, f"No NetCDF output files created in {output_dir}"
