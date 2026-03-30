"""Tests for the accessor API: lazy registration, StdLibAccessor, process(), and _build_rule()."""

import pytest
import xarray as xr

import pycmor
from pycmor.xarray.accessor import _build_rule


class TestLazyRegistration:
    """Test lazy accessor registration via enable_xarray_accessor()."""

    def test_flag_exists(self):
        """The _accessor_registered flag should exist on the pycmor module."""
        assert hasattr(pycmor, "_accessor_registered")

    def test_idempotent(self):
        """Calling enable_xarray_accessor() multiple times is safe."""
        pycmor.enable_xarray_accessor()
        assert pycmor._accessor_registered is True
        # Call again -- should not raise
        pycmor.enable_xarray_accessor()
        assert pycmor._accessor_registered is True

    def test_accessor_available_after_enable(self):
        """After enable, ds.pycmor should be accessible."""
        pycmor.enable_xarray_accessor()
        ds = xr.Dataset({"x": (["t"], [1.0])})
        assert hasattr(ds, "pycmor")


class TestStdLibAccessor:
    """Test the StdLibAccessor exposed via ds.pycmor.stdlib."""

    @pytest.fixture(autouse=True)
    def _enable(self):
        pycmor.enable_xarray_accessor()

    def test_dir_lists_steps(self):
        """dir(ds.pycmor.stdlib) should list std_lib __all__ entries."""
        ds = xr.Dataset({"tas": (["time"], [1.0, 2.0])})
        stdlib_dir = dir(ds.pycmor.stdlib)
        assert "convert_units" in stdlib_dir
        assert "load_data" in stdlib_dir
        assert "set_global_attributes" in stdlib_dir

    def test_unknown_step_raises(self):
        """Accessing a non-existent step should raise AttributeError."""
        ds = xr.Dataset({"tas": (["time"], [1.0])})
        with pytest.raises(AttributeError, match="no step named"):
            ds.pycmor.stdlib.definitely_not_a_real_step

    def test_missing_cmor_variable_raises(self):
        """Calling a step without cmor_variable should raise ValueError."""
        ds = xr.Dataset({"tas": (["time"], [1.0])})
        step = ds.pycmor.stdlib.show_data
        with pytest.raises(ValueError, match="cmor_variable is required"):
            step()

    def test_dunder_raises_attribute_error(self):
        """Accessing dunder attributes should not recurse into std_lib."""
        ds = xr.Dataset({"tas": (["time"], [1.0])})
        with pytest.raises(AttributeError):
            ds.pycmor.stdlib.__nonexistent__


class TestProcessMethod:
    """Test the .process() method on PycmorAccessor."""

    @pytest.fixture(autouse=True)
    def _enable(self):
        pycmor.enable_xarray_accessor()

    def test_method_exists(self):
        """ds.pycmor.process should be a callable."""
        ds = xr.Dataset({"tas": (["time"], [1.0, 2.0])})
        assert hasattr(ds.pycmor, "process")
        assert callable(ds.pycmor.process)

    def test_requires_cmor_variable(self):
        """process() without cmor_variable should raise TypeError (missing kwarg)."""
        ds = xr.Dataset({"tas": (["time"], [1.0])})
        with pytest.raises(TypeError):
            ds.pycmor.process()

    def test_process_on_dataarray(self):
        """process() should also be available on DataArrays."""
        da = xr.DataArray([1.0, 2.0], dims=["time"], name="tas")
        assert hasattr(da.pycmor, "process")
        assert callable(da.pycmor.process)


class TestBuildRule:
    """Test the _build_rule() helper function."""

    def test_basic_construction(self):
        """_build_rule should return a Rule with the given cmor_variable."""
        rule = _build_rule(cmor_variable="tas")
        assert rule.cmor_variable == "tas"

    def test_pycmor_cfg_attached(self):
        """The rule should have _pycmor_cfg attached for std_lib steps."""
        rule = _build_rule(cmor_variable="tas")
        assert hasattr(rule, "_pycmor_cfg")
        # Should be callable (ConfigManager)
        assert callable(rule._pycmor_cfg)

    def test_native_backend(self):
        """The pipeline should use native workflow backend."""
        rule = _build_rule(cmor_variable="tas")
        assert len(rule.pipelines) == 1
        assert rule.pipelines[0]._workflow_backend == "native"

    def test_extra_kwargs_become_attrs(self):
        """Additional kwargs should be set as attributes on the Rule."""
        rule = _build_rule(cmor_variable="tas", model_variable="temp", experiment_id="historical")
        assert rule.model_variable == "temp"
        assert rule.experiment_id == "historical"

    def test_missing_cmor_variable_raises(self):
        """_build_rule without cmor_variable should raise ValueError."""
        with pytest.raises(ValueError, match="cmor_variable is required"):
            _build_rule()

    def test_data_request_variables_empty_without_table(self):
        """Without table info, data_request_variables should be empty."""
        rule = _build_rule(cmor_variable="tas")
        assert rule.data_request_variables == [] or rule.data_request_variables == [None]
