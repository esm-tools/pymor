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
    "tests.fixtures.data_requests",
    "tests.fixtures.datasets",
    "tests.fixtures.environment",
    "tests.fixtures.example_data.awicm_recom",
    "tests.fixtures.example_data.fesom_2p6_pimesh",
    "tests.fixtures.example_data.pi_uxarray",
    "tests.fixtures.fake_data.fesom_mesh",
    "tests.fixtures.fake_filesystem",
    "tests.fixtures.sample_rules",
    # Model-contrib fixtures (new structure)
    "tests.contrib.models.awicm_recom.fixtures.datadir",
    "tests.contrib.models.awicm_recom.fixtures.datasets",
    "tests.contrib.models.fesom_2p6_pimesh.fixtures.datadir",
    "tests.contrib.models.fesom_2p6_pimesh.fixtures.datasets",
    "tests.contrib.models.fesom_uxarray.fixtures.datadir",
    "tests.contrib.models.fesom_uxarray.fixtures.datasets",
]


def _discover_model_runs():
    """Discover all model run classes via entry points.

    Discovers both built-in models (shipped with pycmor) and external
    plugin models. All models are registered via the 'pycmor.fixtures.model_runs'
    entry point group in pyproject.toml.

    Returns
    -------
    list
        List of BaseModelRun subclasses
    """
    try:
        import importlib.metadata as importlib_metadata
    except ImportError:
        # Python < 3.8
        import importlib_metadata

    models = []

    # Discover all models via entry points
    entry_points = importlib_metadata.entry_points()

    # Handle both old dict-style and new SelectableGroups-style
    if hasattr(entry_points, "select"):
        # Python 3.10+ with importlib.metadata.EntryPoints
        pycmor_models = entry_points.select(group="pycmor.fixtures.model_runs")
    else:
        # Python 3.9 and earlier
        pycmor_models = entry_points.get("pycmor.fixtures.model_runs", [])

    for entry_point in pycmor_models:
        try:
            model_class = entry_point.load()
            models.append(model_class)
            logging.info(f"Discovered model: {entry_point.name} from {entry_point.value}")
        except Exception as e:
            logging.warning(f"Failed to load model {entry_point.name}: {e}")

    return models


def pytest_generate_tests(metafunc):
    """Dynamically parametrize tests with available model runs.

    This hook enables generic model tests to run against all registered models,
    both built-in and from external plugins. Tests using the 'model_run_class'
    fixture will be parametrized with all discovered model run classes.

    Built-in models are registered in pyproject.toml:

        [project.entry-points."pycmor.fixtures.model_runs"]
        awicm_recom = "tests.contrib.models.awicm_recom.fixtures.model:AwicmRecomModelRun"

    External plugins register their models the same way:

        [project.entry-points."pycmor.fixtures.model_runs"]
        cesm = "pycmor_plugin_cesm.model:CESMModelRun"

    Parameters
    ----------
    metafunc : pytest.Metafunc
        The pytest metafunc object for parametrization
    """
    if "model_run_class" in metafunc.fixturenames:
        # Discover all model run classes via entry points
        all_models = _discover_model_runs()

        # Parametrize with model class and use model_name as test ID
        metafunc.parametrize(
            "model_run_class",
            all_models,
            ids=[model_cls.__name__.replace("ModelRun", "").lower() for model_cls in all_models],
        )


@pytest.fixture(scope="function")
def model_run(model_run_class, request, tmp_path_factory):
    """Instantiate a model run from a parametrized model run class.

    This fixture works in conjunction with pytest_generate_tests to create
    actual model run instances for testing.

    Parameters
    ----------
    model_run_class : type
        The model run class (parametrized by pytest_generate_tests)
    request : pytest.FixtureRequest
        Pytest request object for checking markers
    tmp_path_factory : pytest.TempPathFactory
        Factory for creating temporary directories

    Returns
    -------
    BaseModelRun
        An instance of the model run class
    """
    use_real = model_run_class.should_use_real_data(request)

    # For built-in models, we can use from_module
    # For plugins, we need a different approach since they won't have __file__ in tests
    # Create instance directly with a fixtures_dir based on model_name
    from pathlib import Path

    # Try to infer fixtures_dir from the model class's module
    model_module = model_run_class.__module__
    if model_module.startswith("tests.contrib.models."):
        # Built-in model - use from_module if we can find the file
        import importlib

        module = importlib.import_module(model_module)
        if hasattr(module, "__file__"):
            return model_run_class.from_module(
                module.__file__,
                use_real=use_real,
                tmp_path_factory=tmp_path_factory,
            )

    # For plugins or if from_module doesn't work, create instance directly
    # Use a sensible default for fixtures_dir
    model_name = model_run_class.__name__.replace("ModelRun", "").lower()
    fixtures_dir = Path.cwd() / "fixtures" / model_name

    return model_run_class(
        model_name=model_name,
        fixtures_dir=fixtures_dir,
        use_real=use_real,
        tmp_path_factory=tmp_path_factory,
    )
