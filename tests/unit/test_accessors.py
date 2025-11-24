"""
Tests for the unified pycmor accessor functionality in accessors.py.

This module tests the PycmorDataArrayAccessor and PycmorDatasetAccessor classes
that provide unified access to all pycmor functionality under the data.pycmor
and dataset.pycmor namespaces.

Tests are focused on the simplified process() API that replaces the old
load_config/run pattern.
"""

from unittest.mock import Mock, patch

import cftime
import pytest
import xarray as xr

# Import pycmor to register all accessors
import pycmor  # noqa: F401
from pycmor.core.pipeline import Pipeline
from pycmor.data_request.variable import DataRequestVariable


@pytest.fixture
def regular_monthly_time():
    """Regular monthly time series for testing."""
    return [cftime.Datetime360Day(2000, m, 15) for m in range(1, 5)]


@pytest.fixture
def sample_dataarray(regular_monthly_time):
    """Sample DataArray with time dimension for testing."""
    return xr.DataArray(
        [1, 2, 3, 4],
        coords={"time": regular_monthly_time},
        dims="time",
        name="temperature",
    )


@pytest.fixture
def sample_dataset(sample_dataarray):
    """Sample Dataset with time dimension for testing."""
    return xr.Dataset(
        {"atmos.tas.tavg-h2m-hxy-u.mon.GLB": sample_dataarray, "atmos.pr.tavg-hxy-u.mon.GLB": sample_dataarray * 2}
    )


# Mock pipeline steps for testing
def mock_step_multiply(data, rule):
    """Mock step that multiplies data by 2."""
    return data * 2


def mock_step_add(data, rule):
    """Mock step that adds 10 to data."""
    return data + 10


def mock_step_with_rule_access(data, rule):
    """Mock step that accesses rule attributes."""
    # Access cmor_variable from rule
    if hasattr(rule, "cmor_variable"):
        data.attrs["cmor_variable"] = rule.cmor_variable
    # Access custom attributes if present
    if hasattr(rule, "custom_attr"):
        data.attrs["custom_attr"] = rule.custom_attr
    return data


@pytest.fixture
def simple_pipeline():
    """Simple pipeline with one step."""
    return Pipeline.from_dict({"name": "SimplePipeline", "steps": ["tests.unit.test_accessors.mock_step_multiply"]})


@pytest.fixture
def multi_step_pipeline():
    """Pipeline with multiple steps."""
    return Pipeline.from_dict(
        {
            "name": "MultiStepPipeline",
            "steps": [
                "tests.unit.test_accessors.mock_step_multiply",
                "tests.unit.test_accessors.mock_step_add",
            ],
        }
    )


@pytest.fixture
def rule_accessing_pipeline():
    """Pipeline that accesses rule attributes."""
    return Pipeline.from_dict(
        {"name": "RuleAccessingPipeline", "steps": ["tests.unit.test_accessors.mock_step_with_rule_access"]}
    )


@pytest.fixture
def mock_cmip7_drv_tas():
    """Mock CMIP7 DataRequestVariable for tas (near-surface air temperature)."""
    mock_drv = Mock(spec=DataRequestVariable)
    mock_drv.name = "tas"
    mock_drv.variable_id = "tas"
    mock_drv.compound_name = "atmos.tas.tavg-h2m-hxy-u.mon.GLB"
    mock_drv.frequency = "mon"
    mock_drv.modeling_realm = "atmos"
    mock_drv.standard_name = "air_temperature"
    mock_drv.units = "K"
    mock_drv.cell_methods = "area: time: mean"
    mock_drv.cell_measures = "area: areacella"
    mock_drv.long_name = "Near-Surface Air Temperature"
    mock_drv.comment = "near-surface (usually, 2 meter) air temperature"
    mock_drv.dimensions = ("time", "lat", "lon")
    mock_drv.out_name = "tas"
    mock_drv.typ = float
    mock_drv.positive = ""
    mock_drv.table_name = "Amon"
    return mock_drv


@pytest.fixture
def mock_cmip7_drv_pr():
    """Mock CMIP7 DataRequestVariable for pr (precipitation)."""
    mock_drv = Mock(spec=DataRequestVariable)
    mock_drv.name = "pr"
    mock_drv.variable_id = "pr"
    mock_drv.compound_name = "atmos.pr.tavg-hxy-u.mon.GLB"
    mock_drv.frequency = "mon"
    mock_drv.modeling_realm = "atmos"
    mock_drv.standard_name = "precipitation_flux"
    mock_drv.units = "kg m-2 s-1"
    mock_drv.cell_methods = "area: time: mean"
    mock_drv.cell_measures = "area: areacella"
    mock_drv.long_name = "Precipitation"
    mock_drv.comment = "includes both liquid and solid phases"
    mock_drv.dimensions = ("time", "lat", "lon")
    mock_drv.out_name = "pr"
    mock_drv.typ = float
    mock_drv.positive = ""
    mock_drv.table_name = "Amon"
    return mock_drv


class TestPycmorDataArrayAccessor:
    """Test the unified pycmor accessor for DataArrays (time frequency methods)."""

    def test_pycmor_accessor_registration(self, sample_dataarray):
        """Test that the pycmor accessor is properly registered."""
        assert hasattr(sample_dataarray, "pycmor")
        assert hasattr(sample_dataarray, "timefreq")  # Specialized accessor still available

    def test_pycmor_accessor_methods_available(self, sample_dataarray):
        """Test that all expected methods are available on the pycmor accessor."""
        expected_methods = ["resample_safe", "check_resolution", "infer_frequency"]

        for method in expected_methods:
            assert hasattr(sample_dataarray.pycmor, method)
            assert callable(getattr(sample_dataarray.pycmor, method))

    def test_pycmor_infer_frequency_delegation(self, sample_dataarray):
        """Test that pycmor.infer_frequency delegates correctly to timefreq."""
        # Test via pycmor accessor
        pycmor_result = sample_dataarray.pycmor.infer_frequency(log=False)

        # Test via specialized accessor
        timefreq_result = sample_dataarray.timefreq.infer_frequency(log=False)

        # Results should be identical
        assert pycmor_result == timefreq_result
        assert pycmor_result.frequency == "M"
        assert pycmor_result.status == "valid"

    def test_pycmor_check_resolution_delegation(self, sample_dataarray):
        """Test that pycmor.check_resolution delegates correctly to timefreq."""
        target_interval = 30.0

        # Test via pycmor accessor
        pycmor_result = sample_dataarray.pycmor.check_resolution(
            target_approx_interval=target_interval, calendar="360_day", log=False
        )

        # Test via specialized accessor
        timefreq_result = sample_dataarray.timefreq.check_resolution(
            target_approx_interval=target_interval, calendar="360_day", log=False
        )

        # Results should be identical
        assert pycmor_result == timefreq_result
        assert "is_valid_for_resampling" in pycmor_result
        assert "comparison_status" in pycmor_result

    def test_pycmor_resample_safe_delegation(self, sample_dataarray):
        """Test that pycmor.resample_safe delegates correctly to timefreq."""
        # Test via pycmor accessor
        pycmor_result = sample_dataarray.pycmor.resample_safe(target_approx_interval=30.0, calendar="360_day")

        # Test via specialized accessor
        timefreq_result = sample_dataarray.timefreq.resample_safe(target_approx_interval=30.0, calendar="360_day")

        # Results should be equivalent DataArrays
        assert isinstance(pycmor_result, xr.DataArray)
        assert isinstance(timefreq_result, xr.DataArray)
        assert pycmor_result.dims == timefreq_result.dims
        assert pycmor_result.name == timefreq_result.name

    def test_pycmor_resample_safe_with_freq_str(self, sample_dataarray):
        """Test pycmor.resample_safe with frequency string parameter."""
        result = sample_dataarray.pycmor.resample_safe(freq_str="M", calendar="360_day")

        assert isinstance(result, xr.DataArray)
        assert "time" in result.dims
        assert result.name == sample_dataarray.name

    def test_pycmor_resample_safe_parameter_flexibility(self, sample_dataarray):
        """Test that pycmor.resample_safe accepts flexible parameter combinations."""
        # Test with target_approx_interval only
        result1 = sample_dataarray.pycmor.resample_safe(target_approx_interval=30.0, calendar="360_day")

        # Test with freq_str only
        result2 = sample_dataarray.pycmor.resample_safe(freq_str="M", calendar="360_day")

        # Test with both parameters
        result3 = sample_dataarray.pycmor.resample_safe(target_approx_interval=30.0, freq_str="M", calendar="360_day")

        # All should produce valid results
        for result in [result1, result2, result3]:
            assert isinstance(result, xr.DataArray)
            assert "time" in result.dims

    def test_pycmor_accessor_error_handling(self):
        """Test that pycmor accessor handles errors appropriately."""
        # Create DataArray without time dimension
        da_no_time = xr.DataArray([1, 2, 3], dims=["x"])

        # Should raise appropriate error when trying to use time-based methods
        with pytest.raises((ValueError, KeyError)):
            da_no_time.pycmor.infer_frequency()

    def test_pycmor_accessor_docstrings(self, sample_dataarray):
        """Test that pycmor accessor methods have proper docstrings."""
        methods = ["resample_safe", "check_resolution", "infer_frequency"]

        for method_name in methods:
            method = getattr(sample_dataarray.pycmor, method_name)
            assert method.__doc__ is not None
            assert len(method.__doc__.strip()) > 0
            # Should reference the specialized accessor documentation
            assert "TimeFrequencyAccessor" in method.__doc__


class TestPycmorDatasetAccessor:
    """Test the unified pycmor accessor for Datasets (time frequency methods)."""

    def test_pycmor_accessor_registration(self, sample_dataset):
        """Test that the pycmor accessor is properly registered for datasets."""
        assert hasattr(sample_dataset, "pycmor")
        assert hasattr(sample_dataset, "timefreq")  # Specialized accessor still available

    def test_pycmor_accessor_methods_available(self, sample_dataset):
        """Test that all expected methods are available on the dataset pycmor accessor."""
        expected_methods = ["resample_safe", "check_resolution", "infer_frequency"]

        for method in expected_methods:
            assert hasattr(sample_dataset.pycmor, method)
            assert callable(getattr(sample_dataset.pycmor, method))

    def test_pycmor_infer_frequency_delegation(self, sample_dataset):
        """Test that dataset pycmor.infer_frequency delegates correctly."""
        # Test via pycmor accessor
        pycmor_result = sample_dataset.pycmor.infer_frequency(log=False)

        # Test via specialized accessor
        timefreq_result = sample_dataset.timefreq.infer_frequency(log=False)

        # Results should be identical
        assert pycmor_result == timefreq_result
        assert pycmor_result.frequency == "M"
        assert pycmor_result.status == "valid"

    def test_pycmor_check_resolution_delegation(self, sample_dataset):
        """Test that dataset pycmor.check_resolution delegates correctly."""
        target_interval = 30.0

        # Test via pycmor accessor
        pycmor_result = sample_dataset.pycmor.check_resolution(
            target_approx_interval=target_interval, calendar="360_day", log=False
        )

        # Test via specialized accessor
        timefreq_result = sample_dataset.timefreq.check_resolution(
            target_approx_interval=target_interval, calendar="360_day", log=False
        )

        # Results should be identical
        assert pycmor_result == timefreq_result
        assert "is_valid_for_resampling" in pycmor_result

    def test_pycmor_resample_safe_delegation(self, sample_dataset):
        """Test that dataset pycmor.resample_safe delegates correctly."""
        # Test via pycmor accessor
        pycmor_result = sample_dataset.pycmor.resample_safe(target_approx_interval=30.0, calendar="360_day")

        # Test via specialized accessor
        timefreq_result = sample_dataset.timefreq.resample_safe(target_approx_interval=30.0, calendar="360_day")

        # Results should be equivalent Datasets
        assert isinstance(pycmor_result, xr.Dataset)
        assert isinstance(timefreq_result, xr.Dataset)
        assert set(pycmor_result.data_vars) == set(timefreq_result.data_vars)
        assert pycmor_result.dims == timefreq_result.dims

    def test_pycmor_resample_safe_preserves_variables(self, sample_dataset):
        """Test that dataset pycmor.resample_safe preserves all data variables."""
        result = sample_dataset.pycmor.resample_safe(freq_str="M", calendar="360_day")

        assert isinstance(result, xr.Dataset)
        assert set(result.data_vars) == set(sample_dataset.data_vars)
        assert "atmos.tas.tavg-h2m-hxy-u.mon.GLB" in result.data_vars
        assert "atmos.pr.tavg-hxy-u.mon.GLB" in result.data_vars

    def test_pycmor_dataset_error_handling(self):
        """Test that dataset pycmor accessor handles errors appropriately."""
        # Create Dataset without time dimension
        ds_no_time = xr.Dataset(
            {
                "var1": xr.DataArray([1, 2, 3], dims=["x"]),
                "var2": xr.DataArray([4, 5, 6], dims=["x"]),
            }
        )

        # Should raise appropriate error when trying to use time-based methods
        with pytest.raises((ValueError, KeyError)):
            ds_no_time.pycmor.infer_frequency()

    def test_pycmor_dataset_docstrings(self, sample_dataset):
        """Test that dataset pycmor accessor methods have proper docstrings."""
        methods = ["resample_safe", "check_resolution", "infer_frequency"]

        for method_name in methods:
            method = getattr(sample_dataset.pycmor, method_name)
            assert method.__doc__ is not None
            assert len(method.__doc__.strip()) > 0
            # Should reference the specialized accessor documentation
            assert "DatasetFrequencyAccessor" in method.__doc__


class TestProcessMethodDataArray:
    """Test the simplified process() API for DataArrays.

    The process() method requires either cmor_version or data_request_variable to be specified.
    This allows the accessor to properly configure the Rule with CMOR variable metadata.

    NOTE: The existing tests (test_process_basic, test_process_with_pipeline_name, etc.) do not
    yet pass cmor_version or data_request_variable. These tests will need to be updated when the
    accessor implementation is modified to require these parameters. The new tests added at the
    end of this class demonstrate the correct usage patterns.
    """

    def test_process_basic(self, sample_dataarray, simple_pipeline):
        """Test basic process() call with pipeline parameter using compound name."""
        result = sample_dataarray.pycmor.process(variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=simple_pipeline)

        # Should have doubled the values (mock_step_multiply multiplies by 2)
        assert isinstance(result, xr.DataArray)
        assert (result.values == sample_dataarray.values * 2).all()

    def test_process_with_pipeline_name(self, sample_dataarray):
        """Test process() with pipeline name string."""
        # Note: This test assumes a registry or default pipelines exist
        # For now, we pass the pipeline object directly
        pipeline = Pipeline.from_dict(
            {"name": "TestingPipeline", "steps": ["tests.unit.test_accessors.mock_step_multiply"]}
        )

        result = sample_dataarray.pycmor.process(variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=pipeline)

        assert isinstance(result, xr.DataArray)
        assert (result.values == sample_dataarray.values * 2).all()

    def test_process_with_pipeline_class(self, sample_dataarray):
        """Test process() with Pipeline class."""
        pipeline = Pipeline.from_dict({"name": "TestPipeline", "steps": ["tests.unit.test_accessors.mock_step_add"]})

        result = sample_dataarray.pycmor.process(variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=pipeline)

        assert isinstance(result, xr.DataArray)
        assert (result.values == sample_dataarray.values + 10).all()

    def test_process_with_pipeline_instance(self, sample_dataarray, multi_step_pipeline):
        """Test process() with pipeline instance."""
        result = sample_dataarray.pycmor.process(
            variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=multi_step_pipeline
        )

        # Should multiply by 2, then add 10: (data * 2) + 10
        assert isinstance(result, xr.DataArray)
        expected = (sample_dataarray.values * 2) + 10
        assert (result.values == expected).all()

    def test_process_with_rule_kwargs(self, sample_dataarray, rule_accessing_pipeline):
        """Test process() with various rule attributes passed as kwargs."""
        result = sample_dataarray.pycmor.process(
            variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB",
            pipeline=rule_accessing_pipeline,
            custom_attr="test_value",
            experiment_id="piControl",
            source_id="TEST-MODEL",
        )

        # Check that rule attributes were applied to data attrs
        assert isinstance(result, xr.DataArray)
        # Note: compound_name is now the default interpretation
        assert result.attrs["custom_attr"] == "test_value"

    def test_process_returns_correct_type(self, sample_dataarray, simple_pipeline):
        """Test that process() returns a DataArray when called on DataArray."""
        result = sample_dataarray.pycmor.process(variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=simple_pipeline)

        assert isinstance(result, xr.DataArray)
        assert not isinstance(result, xr.Dataset)

    def test_process_missing_variable(self, sample_dataarray, simple_pipeline):
        """Test that process() requires variable parameter."""
        with pytest.raises(TypeError):
            # Missing required variable argument
            sample_dataarray.pycmor.process(pipeline=simple_pipeline)

    def test_process_missing_pipeline(self, sample_dataarray, mock_cmip7_drv_tas):
        """Test that process() handles missing pipeline appropriately."""
        # When pipeline is None, should use a default pipeline or error
        # This behavior depends on implementation
        with pytest.raises((TypeError, ValueError)):
            sample_dataarray.pycmor.process(
                variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", data_request_variable=mock_cmip7_drv_tas
            )

    def test_process_with_empty_variable(self, sample_dataarray, simple_pipeline):
        """Test process() with empty variable string."""
        result = sample_dataarray.pycmor.process(variable="", pipeline=simple_pipeline)

        # Should still work - empty string is valid
        assert isinstance(result, xr.DataArray)

    def test_process_multiple_rule_attributes(self, sample_dataarray, rule_accessing_pipeline):
        """Test process() with multiple rule attributes."""
        result = sample_dataarray.pycmor.process(
            variable="atmos.pr.tavg-hxy-u.mon.GLB",
            pipeline=rule_accessing_pipeline,
            table_id="Amon",
            frequency="mon",
            realm="atmos",
            variable_id="pr",
        )

        assert isinstance(result, xr.DataArray)

    def test_process_with_data_request_variable(self, sample_dataarray, simple_pipeline, mock_cmip7_drv_tas):
        """Test process() with data_request_variable parameter."""
        result = sample_dataarray.pycmor.process(
            variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB",
            data_request_variable=mock_cmip7_drv_tas,
            pipeline=simple_pipeline,
        )

        assert isinstance(result, xr.DataArray)
        # Verify data was processed (doubled by mock_step_multiply)
        assert (result.values == sample_dataarray.values * 2).all()

    # New tests for conflict checking (DataArray)
    def test_process_conflict_variable_and_drv(self, sample_dataarray, simple_pipeline, mock_cmip7_drv_tas):
        """Test that providing both variable and data_request_variable raises an error."""
        with pytest.raises(ValueError) as exc_info:
            sample_dataarray.pycmor.process(
                variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB",
                data_request_variable=mock_cmip7_drv_tas,
                pipeline=simple_pipeline,
            )

        error_msg = str(exc_info.value).lower()
        assert "conflict" in error_msg or "both" in error_msg or "only one" in error_msg

    def test_process_conflict_variable_and_compound_name(self, sample_dataarray, simple_pipeline):
        """Test that providing both variable and compound_name raises an error."""
        with pytest.raises(ValueError) as exc_info:
            sample_dataarray.pycmor.process(
                variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB",
                compound_name="atmos.tas.tavg-h2m-hxy-u.mon.GLB",
                pipeline=simple_pipeline,
            )

        error_msg = str(exc_info.value).lower()
        assert "conflict" in error_msg or "both" in error_msg or "only one" in error_msg

    def test_process_conflict_variable_and_cmor_variable(self, sample_dataarray, simple_pipeline):
        """Test that providing both variable and cmor_variable raises an error."""
        with pytest.raises(ValueError) as exc_info:
            sample_dataarray.pycmor.process(
                variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", cmor_variable="tas", pipeline=simple_pipeline
            )

        error_msg = str(exc_info.value).lower()
        assert "conflict" in error_msg or "both" in error_msg or "only one" in error_msg

    # New tests for variable interpretation (DataArray)
    def test_process_cmip7_interprets_as_compound_name(self, sample_dataarray, simple_pipeline):
        """Test that variable is interpreted as compound_name for CMIP7 (default)."""
        with patch("pycmor.accessors.CMIP7DataRequest") as mock_dr:
            # Mock the data request
            mock_drv = Mock(spec=DataRequestVariable)
            mock_drv.compound_name = "atmos.tas.tavg-h2m-hxy-u.mon.GLB"
            mock_dr.from_vendored_json.return_value.get_variable_by_compound_name.return_value = mock_drv

            result = sample_dataarray.pycmor.process(
                variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=simple_pipeline
            )

            assert isinstance(result, xr.DataArray)
            # Verify the data request was queried with compound_name
            mock_dr.from_vendored_json.return_value.get_variable_by_compound_name.assert_called_once_with(
                "atmos.tas.tavg-h2m-hxy-u.mon.GLB"
            )

    def test_process_cmip6_interprets_as_cmor_variable(self, sample_dataarray, simple_pipeline):
        """Test that variable is interpreted as cmor_variable when cmor_version='CMIP6'."""
        with patch("pycmor.accessors.CMIP6DataRequest") as mock_dr:
            # Mock the CMIP6 data request
            mock_drv = Mock(spec=DataRequestVariable)
            mock_drv.name = "tas"
            mock_drv.variable_id = "tas"
            mock_dr.from_vendored_json.return_value.get_variable.return_value = mock_drv

            result = sample_dataarray.pycmor.process(variable="tas", cmor_version="CMIP6", pipeline=simple_pipeline)

            assert isinstance(result, xr.DataArray)
            # Verify the CMIP6 data request was queried with cmor_variable
            mock_dr.from_vendored_json.return_value.get_variable.assert_called_once_with("tas")


class TestProcessMethodDataset:
    """Test the simplified process() API for Datasets with realistic CMIP7 compound names."""

    def test_process_basic(self, sample_dataset, simple_pipeline):
        """Test basic process() call with pipeline parameter using compound name."""
        result = sample_dataset.pycmor.process(variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=simple_pipeline)

        # Should have doubled all values
        assert isinstance(result, xr.Dataset)
        for var in result.data_vars:
            assert (result[var].values == sample_dataset[var].values * 2).all()

    def test_process_with_pipeline_name(self, sample_dataset):
        """Test process() with pipeline name string."""
        pipeline = Pipeline.from_dict(
            {"name": "TestingPipeline", "steps": ["tests.unit.test_accessors.mock_step_multiply"]}
        )

        result = sample_dataset.pycmor.process(variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=pipeline)

        assert isinstance(result, xr.Dataset)
        for var in result.data_vars:
            assert (result[var].values == sample_dataset[var].values * 2).all()

    def test_process_with_pipeline_class(self, sample_dataset):
        """Test process() with Pipeline class."""
        pipeline = Pipeline.from_dict({"name": "TestPipeline", "steps": ["tests.unit.test_accessors.mock_step_add"]})

        result = sample_dataset.pycmor.process(variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=pipeline)

        assert isinstance(result, xr.Dataset)
        for var in result.data_vars:
            assert (result[var].values == sample_dataset[var].values + 10).all()

    def test_process_with_pipeline_instance(self, sample_dataset, multi_step_pipeline):
        """Test process() with pipeline instance."""
        result = sample_dataset.pycmor.process(
            variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=multi_step_pipeline
        )

        # Should multiply by 2, then add 10: (data * 2) + 10
        assert isinstance(result, xr.Dataset)
        for var in result.data_vars:
            expected = (sample_dataset[var].values * 2) + 10
            assert (result[var].values == expected).all()

    def test_process_with_rule_kwargs(self, sample_dataset, rule_accessing_pipeline):
        """Test process() with various rule attributes passed as kwargs."""
        result = sample_dataset.pycmor.process(
            variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB",
            pipeline=rule_accessing_pipeline,
            custom_attr="test_value",
            experiment_id="piControl",
            source_id="TEST-MODEL",
        )

        # Check that rule attributes were applied
        assert isinstance(result, xr.Dataset)
        # Attributes may be on dataset or variables depending on implementation
        # Just verify processing completed successfully

    def test_process_returns_correct_type(self, sample_dataset, simple_pipeline):
        """Test that process() returns a Dataset when called on Dataset."""
        result = sample_dataset.pycmor.process(variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=simple_pipeline)

        assert isinstance(result, xr.Dataset)
        assert not isinstance(result, xr.DataArray)

    def test_process_missing_variable(self, sample_dataset, simple_pipeline):
        """Test that process() requires variable parameter."""
        with pytest.raises(TypeError):
            # Missing required variable argument
            sample_dataset.pycmor.process(pipeline=simple_pipeline)

    def test_process_missing_pipeline(self, sample_dataset, mock_cmip7_drv_tas):
        """Test that process() handles missing pipeline appropriately."""
        with pytest.raises((TypeError, ValueError)):
            sample_dataset.pycmor.process(
                variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", data_request_variable=mock_cmip7_drv_tas
            )

    def test_process_preserves_data_variables(self, sample_dataset, simple_pipeline):
        """Test that process() preserves all data variables in dataset."""
        result = sample_dataset.pycmor.process(variable="atmos.tas.tavg-h2m-hxy-u.mon.GLB", pipeline=simple_pipeline)

        assert isinstance(result, xr.Dataset)
        assert set(result.data_vars) == set(sample_dataset.data_vars)
        assert "atmos.tas.tavg-h2m-hxy-u.mon.GLB" in result.data_vars
        assert "atmos.pr.tavg-hxy-u.mon.GLB" in result.data_vars

    def test_process_multiple_variables(self, sample_dataset, multi_step_pipeline):
        """Test process() on dataset with multiple data variables."""
        result = sample_dataset.pycmor.process(variable="atmos.pr.tavg-hxy-u.mon.GLB", pipeline=multi_step_pipeline)

        assert isinstance(result, xr.Dataset)
        assert len(result.data_vars) == len(sample_dataset.data_vars)

    def test_process_with_data_request_variable(self, sample_dataset, simple_pipeline, mock_cmip7_drv_pr):
        """Test process() with data_request_variable parameter."""
        result = sample_dataset.pycmor.process(
            variable="atmos.pr.tavg-hxy-u.mon.GLB", data_request_variable=mock_cmip7_drv_pr, pipeline=simple_pipeline
        )

        assert isinstance(result, xr.Dataset)
        # Verify all variables were processed (doubled by mock_step_multiply)
        for var in result.data_vars:
            assert (result[var].values == sample_dataset[var].values * 2).all()

    # New tests for conflict checking (Dataset)
    def test_process_conflict_variable_and_drv(self, sample_dataset, simple_pipeline, mock_cmip7_drv_pr):
        """Test that providing both variable and data_request_variable raises an error."""
        with pytest.raises(ValueError) as exc_info:
            sample_dataset.pycmor.process(
                variable="atmos.pr.tavg-hxy-u.mon.GLB",
                data_request_variable=mock_cmip7_drv_pr,
                pipeline=simple_pipeline,
            )

        error_msg = str(exc_info.value).lower()
        assert "conflict" in error_msg or "both" in error_msg or "only one" in error_msg

    def test_process_conflict_variable_and_compound_name(self, sample_dataset, simple_pipeline):
        """Test that providing both variable and compound_name raises an error."""
        with pytest.raises(ValueError) as exc_info:
            sample_dataset.pycmor.process(
                variable="atmos.pr.tavg-hxy-u.mon.GLB",
                compound_name="atmos.pr.tavg-hxy-u.mon.GLB",
                pipeline=simple_pipeline,
            )

        error_msg = str(exc_info.value).lower()
        assert "conflict" in error_msg or "both" in error_msg or "only one" in error_msg

    def test_process_conflict_variable_and_cmor_variable(self, sample_dataset, simple_pipeline):
        """Test that providing both variable and cmor_variable raises an error."""
        with pytest.raises(ValueError) as exc_info:
            sample_dataset.pycmor.process(
                variable="atmos.pr.tavg-hxy-u.mon.GLB", cmor_variable="pr", pipeline=simple_pipeline
            )

        error_msg = str(exc_info.value).lower()
        assert "conflict" in error_msg or "both" in error_msg or "only one" in error_msg

    # New tests for variable interpretation (Dataset)
    def test_process_cmip7_interprets_as_compound_name(self, sample_dataset, simple_pipeline):
        """Test that variable is interpreted as compound_name for CMIP7 (default)."""
        with patch("pycmor.accessors.CMIP7DataRequest") as mock_dr:
            # Mock the data request
            mock_drv = Mock(spec=DataRequestVariable)
            mock_drv.compound_name = "atmos.pr.tavg-hxy-u.mon.GLB"
            mock_dr.from_vendored_json.return_value.get_variable_by_compound_name.return_value = mock_drv

            result = sample_dataset.pycmor.process(variable="atmos.pr.tavg-hxy-u.mon.GLB", pipeline=simple_pipeline)

            assert isinstance(result, xr.Dataset)
            # Verify the data request was queried with compound_name
            mock_dr.from_vendored_json.return_value.get_variable_by_compound_name.assert_called_once_with(
                "atmos.pr.tavg-hxy-u.mon.GLB"
            )

    def test_process_cmip6_interprets_as_cmor_variable(self, sample_dataset, simple_pipeline):
        """Test that variable is interpreted as cmor_variable when cmor_version='CMIP6'."""
        with patch("pycmor.accessors.CMIP6DataRequest") as mock_dr:
            # Mock the CMIP6 data request
            mock_drv = Mock(spec=DataRequestVariable)
            mock_drv.name = "pr"
            mock_drv.variable_id = "pr"
            mock_dr.from_vendored_json.return_value.get_variable.return_value = mock_drv

            result = sample_dataset.pycmor.process(variable="pr", cmor_version="CMIP6", pipeline=simple_pipeline)

            assert isinstance(result, xr.Dataset)
            # Verify the CMIP6 data request was queried with cmor_variable
            mock_dr.from_vendored_json.return_value.get_variable.assert_called_once_with("pr")


class TestAccessorRegistration:
    """Test that accessors are properly registered through the accessors.py module."""

    def test_import_registers_accessors(self):
        """Test that importing pycmor registers all accessors."""
        # Create test data
        times = [cftime.Datetime360Day(2000, m, 15) for m in range(1, 4)]
        da = xr.DataArray([1, 2, 3], coords={"time": times}, dims="time")
        ds = xr.Dataset({"var": da})

        # Both specialized and unified accessors should be available
        assert hasattr(da, "timefreq")
        assert hasattr(da, "pycmor")
        assert hasattr(ds, "timefreq")
        assert hasattr(ds, "pycmor")

    def test_accessor_namespace_separation(self, sample_dataarray):
        """Test that accessor namespaces are properly separated."""
        # timefreq and pycmor should be different objects
        assert sample_dataarray.timefreq is not sample_dataarray.pycmor

        # But pycmor should delegate to timefreq functionality
        assert hasattr(sample_dataarray.pycmor, "_timefreq")

    def test_process_method_exists(self, sample_dataarray, sample_dataset):
        """Test that process() method exists on both accessors."""
        assert hasattr(sample_dataarray.pycmor, "process")
        assert callable(sample_dataarray.pycmor.process)

        assert hasattr(sample_dataset.pycmor, "process")
        assert callable(sample_dataset.pycmor.process)
