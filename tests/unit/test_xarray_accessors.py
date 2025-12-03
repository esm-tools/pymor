"""
Tests for xarray accessors
"""

import numpy as np
import pytest
import xarray as xr

# Import pycmor to register accessors
import pycmor  # noqa: F401


class TestAccessorRegistration:
    """Test that accessors are properly registered."""

    def test_pycmor_accessor_on_dataset(self):
        """Test that .pycmor accessor is available on Dataset."""
        ds = xr.Dataset()
        assert hasattr(ds, "pycmor")

    def test_pycmor_accessor_on_dataarray(self):
        """Test that .pycmor accessor is available on DataArray."""
        da = xr.DataArray([1, 2, 3])
        assert hasattr(da, "pycmor")

    def test_coords_sub_accessor(self):
        """Test that .pycmor.coords is available."""
        ds = xr.Dataset()
        assert hasattr(ds.pycmor, "coords")

    def test_dims_sub_accessor(self):
        """Test that .pycmor.dims is available."""
        ds = xr.Dataset()
        assert hasattr(ds.pycmor, "dims")

    def test_old_accessor_is_deprecated(self):
        """Tests that old names no longer work"""
        with pytest.raises(AttributeError):
            xr.Dataset().pymor  # Yes, pymor (no C)


class TestCoordinateAccessor:
    """Test coordinate accessor functionality."""

    def test_get_metadata_latitude(self):
        """Test getting metadata for latitude coordinate."""
        ds = xr.Dataset()
        metadata = ds.pycmor.coords.get_metadata("lat")

        assert metadata is not None
        assert metadata["standard_name"] == "latitude"
        assert metadata["units"] == "degrees_north"
        assert metadata["axis"] == "Y"

    def test_get_metadata_longitude(self):
        """Test getting metadata for longitude coordinate."""
        ds = xr.Dataset()
        metadata = ds.pycmor.coords.get_metadata("lon")

        assert metadata is not None
        assert metadata["standard_name"] == "longitude"
        assert metadata["units"] == "degrees_east"
        assert metadata["axis"] == "X"

    def test_get_metadata_unknown(self):
        """Test getting metadata for unknown coordinate."""
        ds = xr.Dataset()
        metadata = ds.pycmor.coords.get_metadata("unknown_coord")
        assert metadata is None

    def test_list_recognized(self):
        """Test listing recognized coordinates."""
        ds = xr.Dataset()
        coords = ds.pycmor.coords.list_recognized()

        assert isinstance(coords, list)
        assert len(coords) > 0
        assert "lat" in coords
        assert "lon" in coords

    def test_set_attributes_basic(self):
        """Test setting coordinate attributes."""
        ds = xr.Dataset(
            coords={
                "lat": (["lat"], np.linspace(-90, 90, 180)),
                "lon": (["lon"], np.linspace(0, 360, 360)),
            }
        )

        ds_with_attrs = ds.pycmor.coords.set_attributes()

        # Check latitude attributes
        assert ds_with_attrs["lat"].attrs["standard_name"] == "latitude"
        assert ds_with_attrs["lat"].attrs["units"] == "degrees_north"
        assert ds_with_attrs["lat"].attrs["axis"] == "Y"

        # Check longitude attributes
        assert ds_with_attrs["lon"].attrs["standard_name"] == "longitude"
        assert ds_with_attrs["lon"].attrs["units"] == "degrees_east"
        assert ds_with_attrs["lon"].attrs["axis"] == "X"

    def test_set_attributes_with_data_variable(self):
        """Test setting attributes with data variable."""
        ds = xr.Dataset(
            {
                "tas": (["time", "lat", "lon"], np.random.random((10, 180, 360))),
            },
            coords={
                "time": np.arange(10),
                "lat": np.linspace(-90, 90, 180),
                "lon": np.linspace(0, 360, 360),
            },
        )

        ds_with_attrs = ds.pycmor.coords.set_attributes()

        assert "standard_name" in ds_with_attrs["lat"].attrs
        assert "standard_name" in ds_with_attrs["lon"].attrs

    def test_validate_correct_attrs(self):
        """Test validation with correct attributes."""
        ds = xr.Dataset(
            coords={
                "lat": (
                    ["lat"],
                    np.linspace(-90, 90, 180),
                    {
                        "standard_name": "latitude",
                        "units": "degrees_north",
                        "axis": "Y",
                    },
                )
            }
        )

        results = ds.pycmor.coords.validate()
        assert results["lat"]["valid"] is True

    def test_validate_incorrect_attrs(self):
        """Test validation with incorrect attributes."""
        ds = xr.Dataset(
            coords={
                "lat": (
                    ["lat"],
                    np.linspace(-90, 90, 180),
                    {"standard_name": "wrong_name"},
                )
            }
        )

        results = ds.pycmor.coords.validate(mode="warn")
        assert results["lat"]["valid"] is False
        assert len(results["lat"]["issues"]) > 0


class TestDimensionAccessor:
    """Test dimension accessor functionality."""

    def test_detect_types_basic(self):
        """Test basic dimension type detection."""
        ds = xr.Dataset(
            {
                "temp": (["time", "lat", "lon"], np.random.random((10, 180, 360))),
            },
            coords={
                "time": np.arange(10),
                "lat": np.linspace(-90, 90, 180),
                "lon": np.linspace(0, 360, 360),
            },
        )

        types = ds.pycmor.dims.detect_types()

        assert isinstance(types, dict)
        assert types.get("lat") == "latitude"
        assert types.get("lon") == "longitude"
        # time might be None if values don't look like time
        # but dimension name should still be detected
        assert "time" in types

    def test_detect_types_pressure(self):
        """Test detection of pressure dimension."""
        ds = xr.Dataset(
            coords={
                "lev": (["lev"], [100000, 92500, 85000, 70000, 50000]),
            }
        )

        types = ds.pycmor.dims.detect_types()
        assert types["lev"] == "pressure"

    def test_create_mapping_standalone(self):
        """Test creating mapping without CMIP table."""
        ds = xr.Dataset(
            {
                "temp": (["time", "latitude", "longitude"], np.random.random((10, 180, 360))),
            },
            coords={
                "time": np.arange(10),
                "latitude": np.linspace(-90, 90, 180),
                "longitude": np.linspace(0, 360, 360),
            },
        )

        mapping = ds.pycmor.dims.create_mapping()

        assert isinstance(mapping, dict)
        # Should map latitude/longitude to lat/lon
        assert mapping.get("latitude") in ["lat", "latitude"]
        assert mapping.get("longitude") in ["lon", "longitude"]

    def test_create_mapping_with_target_dims(self):
        """Test creating mapping with manual target dimensions."""
        ds = xr.Dataset(
            {
                "temp": (["time", "latitude", "longitude"], np.random.random((10, 180, 360))),
            },
            coords={
                "time": np.arange(10),
                "latitude": np.linspace(-90, 90, 180),
                "longitude": np.linspace(0, 360, 360),
            },
        )

        mapping = ds.pycmor.dims.create_mapping(target_dimensions=["time", "lat", "lon"])

        assert "latitude" in mapping
        assert "longitude" in mapping
        # Should map to target dimensions
        assert mapping["latitude"] == "lat"
        assert mapping["longitude"] == "lon"

    def test_apply_mapping(self):
        """Test applying a dimension mapping."""
        ds = xr.Dataset(
            {
                "temp": (["time", "latitude", "longitude"], np.random.random((10, 180, 360))),
            },
            coords={
                "time": np.arange(10),
                "latitude": np.linspace(-90, 90, 180),
                "longitude": np.linspace(0, 360, 360),
            },
        )

        mapping = {"latitude": "lat", "longitude": "lon"}
        ds_mapped = ds.pycmor.dims.apply_mapping(mapping)

        assert "lat" in ds_mapped.dims
        assert "lon" in ds_mapped.dims
        assert "latitude" not in ds_mapped.dims
        assert "longitude" not in ds_mapped.dims

    def test_map_to_cmip_standalone(self):
        """Test mapping to CMIP without table specification."""
        ds = xr.Dataset(
            {
                "temp": (["time", "latitude", "longitude"], np.random.random((10, 180, 360))),
            },
            coords={
                "time": np.arange(10),
                "latitude": np.linspace(-90, 90, 180),
                "longitude": np.linspace(0, 360, 360),
            },
        )

        ds_mapped = ds.pycmor.dims.map_to_cmip()

        # Should have applied smart mapping
        assert "lat" in ds_mapped.dims or "latitude" in ds_mapped.dims
        assert "lon" in ds_mapped.dims or "longitude" in ds_mapped.dims

    def test_map_to_cmip_with_user_mapping(self):
        """Test mapping with user-specified overrides."""
        ds = xr.Dataset(
            {
                "temp": (["time", "lev", "latitude", "longitude"], np.random.random((10, 19, 180, 360))),
            },
            coords={
                "time": np.arange(10),
                "lev": np.linspace(100000, 10000, 19),
                "latitude": np.linspace(-90, 90, 180),
                "longitude": np.linspace(0, 360, 360),
            },
        )

        ds_mapped = ds.pycmor.dims.map_to_cmip(user_mapping={"lev": "plev19", "latitude": "lat", "longitude": "lon"})

        assert "plev19" in ds_mapped.dims
        assert "lat" in ds_mapped.dims
        assert "lon" in ds_mapped.dims


class TestIntegration:
    """Integration tests combining multiple accessor features."""

    def test_full_workflow_standalone(self):
        """Test complete workflow without CMIP tables."""
        # Create test dataset
        ds = xr.Dataset(
            {
                "tas": (["time", "latitude", "longitude"], np.random.random((12, 180, 360))),
            },
            coords={
                "time": np.arange(12),
                "latitude": np.linspace(-90, 90, 180),
                "longitude": np.linspace(0, 360, 360),
            },
        )

        # Detect dimension types
        dim_types = ds.pycmor.dims.detect_types()
        assert dim_types["latitude"] == "latitude"
        assert dim_types["longitude"] == "longitude"

        # Map dimensions
        ds = ds.pycmor.dims.map_to_cmip(target_dimensions=["time", "lat", "lon"])
        assert "lat" in ds.dims
        assert "lon" in ds.dims

        # Set coordinate attributes
        ds = ds.pycmor.coords.set_attributes()
        assert ds["lat"].attrs["standard_name"] == "latitude"
        assert ds["lon"].attrs["standard_name"] == "longitude"

        # Validate
        validation = ds.pycmor.coords.validate()
        assert validation["lat"]["valid"] is True
        assert validation["lon"]["valid"] is True

    def test_dataarray_support(self):
        """Test that accessors work on DataArrays."""
        da = xr.DataArray(
            np.random.random((180, 360)),
            dims=["latitude", "longitude"],
            coords={
                "latitude": np.linspace(-90, 90, 180),
                "longitude": np.linspace(0, 360, 360),
            },
            name="tas",
        )

        # Test dimension detection
        dim_types = da.pycmor.dims.detect_types()
        assert "latitude" in dim_types
        assert "longitude" in dim_types

        # Test dimension mapping
        da_mapped = da.pycmor.dims.map_to_cmip(target_dimensions=["lat", "lon"])
        assert "lat" in da_mapped.dims
        assert "lon" in da_mapped.dims

        # Test coordinate attributes
        da_final = da_mapped.pycmor.coords.set_attributes()
        assert "standard_name" in da_final.coords["lat"].attrs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
