"""Generic tests that run against all registered model runs.

This test module runs against all model runs registered via:
- Built-in models in tests/contrib/models/
- External plugins registered via 'pycmor.models' entry points

External plugin developers can extend pycmor's test coverage by:
1. Creating a model run class inheriting from BaseModelRun
2. Registering it via entry points in their package
3. Installing their package with [test] extra: pip install pycmor-plugin-foo[test]

Example plugin setup:

    [project.entry-points."pycmor.models"]
    my_model = "pycmor_plugin_foo.model:MyModelRun"

When the plugin is installed, these tests will automatically run against
the plugin's model, ensuring compatibility with pycmor.
"""

import pytest


def test_model_run_has_datadir(model_run):
    """Test that model run can provide a data directory."""
    datadir = model_run.datadir
    assert datadir is not None
    assert datadir.exists(), f"Data directory {datadir} does not exist"


def test_model_run_can_open_dataset(model_run):
    """Test that model run can open an xarray dataset."""
    ds = model_run.ds
    assert ds is not None
    assert hasattr(ds, "data_vars"), "Dataset does not have data_vars attribute"
    assert len(ds.data_vars) > 0, "Dataset has no data variables"


def test_model_run_has_registry_path(model_run):
    """Test that model run has a registry path property."""
    registry_path = model_run.registry_path
    assert registry_path is not None
    assert str(registry_path).endswith("registry.yaml")


def test_model_run_has_stub_manifest_path(model_run):
    """Test that model run has a stub manifest path property."""
    stub_manifest_path = model_run.stub_manifest_path
    assert stub_manifest_path is not None
    assert str(stub_manifest_path).endswith("stub_manifest.yaml")


def test_model_run_has_model_name(model_run):
    """Test that model run has a model_name attribute."""
    assert hasattr(model_run, "model_name")
    assert isinstance(model_run.model_name, str)
    assert len(model_run.model_name) > 0


def test_model_run_datadir_is_lazy_loaded(model_run_class, request, tmp_path_factory):
    """Test that datadir is lazy-loaded (not fetched until accessed)."""
    use_real = model_run_class.should_use_real_data(request)

    # Create instance
    import importlib

    model_module = model_run_class.__module__
    if model_module.startswith("tests.contrib.models."):
        module = importlib.import_module(model_module)
        if hasattr(module, "__file__"):
            instance = model_run_class.from_module(
                module.__file__,
                use_real=use_real,
                tmp_path_factory=tmp_path_factory,
            )
        else:
            pytest.skip("Cannot test lazy loading for this model")
    else:
        pytest.skip("Cannot test lazy loading for plugin models")

    # Check that _datadir is None before access
    assert instance._datadir is None, "datadir should not be loaded yet"

    # Access datadir
    _ = instance.datadir

    # Check that _datadir is now set
    assert instance._datadir is not None, "datadir should be loaded after access"


def test_model_run_ds_is_lazy_loaded(model_run_class, request, tmp_path_factory):
    """Test that dataset is lazy-loaded (not opened until accessed)."""
    use_real = model_run_class.should_use_real_data(request)

    # Create instance
    import importlib

    model_module = model_run_class.__module__
    if model_module.startswith("tests.contrib.models."):
        module = importlib.import_module(model_module)
        if hasattr(module, "__file__"):
            instance = model_run_class.from_module(
                module.__file__,
                use_real=use_real,
                tmp_path_factory=tmp_path_factory,
            )
        else:
            pytest.skip("Cannot test lazy loading for this model")
    else:
        pytest.skip("Cannot test lazy loading for plugin models")

    # Check that _ds is None before access
    assert instance._ds is None, "dataset should not be loaded yet"

    # Access ds
    _ = instance.ds

    # Check that _ds is now set
    assert instance._ds is not None, "dataset should be loaded after access"
