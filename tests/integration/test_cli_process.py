"""CLI integration tests for pycmor process command.

This module tests the CLI interface (`pycmor process`) for all registered
model runs with both CMIP6 and CMIP7 configurations. Tests are organized
as a matrix of [model] x [cmip_version].
"""

import subprocess
from pathlib import Path

import pytest
import yaml
from jinja2 import Template

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

    # Determine if we should use real data
    use_real = model_class.should_use_real_data(request)

    # Create instance
    import inspect

    module_file = inspect.getfile(model_class)
    return model_class.from_module(module_file, use_real=use_real, tmp_path_factory=tmp_path_factory)


@pytest.mark.parametrize("cmip_version", ["cmip6", "cmip7"])
@pytest.mark.parametrize(
    "orchestrator_config",
    [
        pytest.param({"pipeline_workflow_orchestrator": "prefect", "enable_dask": "yes"}, id="prefect-dask"),
        pytest.param({"pipeline_workflow_orchestrator": "native", "enable_dask": "yes"}, id="native-dask"),
        pytest.param({"pipeline_workflow_orchestrator": "native", "enable_dask": "no"}, id="native-nodask"),
    ],
)
def test_cli_process(model_run_instance, cmip_version, orchestrator_config, tmp_path):
    """Test pycmor process CLI command with model configurations.

    This test creates a temporary config file with updated paths and runs
    the pycmor CLI process command. Tests multiple orchestrator configurations.

    Parameters
    ----------
    model_run_instance : BaseModelRun
        Model run instance with data and config
    cmip_version : str
        CMIP version to test (cmip6 or cmip7)
    orchestrator_config : dict
        Orchestrator configuration to test (pipeline_workflow_orchestrator, enable_dask)
    tmp_path : Path
        Temporary directory for test artifacts
    """
    # Mark as xfail if config is not available (will show XPASS when implemented)
    if cmip_version not in model_run_instance.configs:
        pytest.xfail(f"{cmip_version.upper()} config not available for this model")

    # Get the appropriate config path
    config_path = model_run_instance.configs[cmip_version]

    # Load config as Jinja2 template and render with datadir
    with open(config_path, "r") as f:
        template = Template(f.read())

    rendered_config = template.render(datadir=str(model_run_instance.datadir))
    cfg = yaml.safe_load(rendered_config)

    # Update output directory to tmp_path (both general and per-rule)
    output_dir = str(tmp_path / "output")
    if "general" not in cfg:
        cfg["general"] = {}
    cfg["general"]["output_directory"] = output_dir
    for rule in cfg.get("rules", []):
        rule["output_directory"] = output_dir

    # Apply orchestrator configuration
    if "pycmor" not in cfg:
        cfg["pycmor"] = {}
    cfg["pycmor"].update(orchestrator_config)

    # Write modified config to temporary file
    orch_type = orchestrator_config["pipeline_workflow_orchestrator"]
    dask_status = "dask" if orchestrator_config["enable_dask"] == "yes" else "nodask"
    orchestrator_desc = f"{orch_type}-{dask_status}"
    temp_config = tmp_path / f"config_{cmip_version}_{orchestrator_desc}.yaml"
    with open(temp_config, "w") as f:
        yaml.dump(cfg, f)

    # Run CLI command
    result = subprocess.run(
        ["pycmor", "process", str(temp_config)],
        capture_output=True,
        text=True,
        timeout=300,  # 5 minutes timeout
        check=False,  # Don't raise exception on non-zero exit, we'll check manually
    )

    # Check that command succeeded - if it fails, provide detailed error info
    if result.returncode != 0:
        error_msg = (
            f"CLI command 'pycmor process' failed with exit code {result.returncode}\n"
            f"Command: pycmor process {temp_config}\n"
            f"\n=== STDERR ===\n{result.stderr}\n"
            f"\n=== STDOUT ===\n{result.stdout}"
        )
        pytest.fail(error_msg)

    # Verify output was created
    output_dir = Path(cfg["general"]["output_directory"])
    assert output_dir.exists(), f"Output directory not created: {output_dir}"
    output_files = list(output_dir.rglob("*.nc"))
    assert len(output_files) > 0, f"No NetCDF output files created in {output_dir}"
