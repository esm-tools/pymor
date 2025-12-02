============================
xarray Accessors for pycmor
============================

Overview
========

The pycmor xarray accessors provide a convenient interface for interactive coordinate and dimension operations without requiring full pipeline configuration. They work seamlessly with both CMIP6 and CMIP7 data request formats.

The accessors are available via the ``.pycmor`` namespace:

- ``.pycmor.coords`` - Coordinate attribute operations
- ``.pycmor.dims`` - Dimension mapping operations

Quick Start
===========

.. code-block:: python

    import xarray as xr
    import pycmor  # Auto-registers the accessors

    # Load your data
    ds = xr.open_dataset("model_output.nc")

    # Detect dimension types
    types = ds.pycmor.dims.detect_types()
    print(types)
    # {'time': 'time', 'lev': 'pressure', 'latitude': 'latitude', 'longitude': 'longitude'}

    # Map dimensions to CMIP6 standards
    ds_mapped = ds.pycmor.dims.map_to_cmip(table="Amon", variable="tas")

    # Set CF-compliant coordinate attributes
    ds_final = ds_mapped.pycmor.coords.set_attributes()

Coordinate Operations (.pycmor.coords)
========================================

Setting Coordinate Attributes
------------------------------

The coordinate accessor automatically applies CF-compliant metadata to coordinate variables:

.. code-block:: python

    # Basic usage
    ds_with_attrs = ds.pycmor.coords.set_attributes()

    # With validation mode
    ds_with_attrs = ds.pycmor.coords.set_attributes(validate='fix')

Configuration Options
~~~~~~~~~~~~~~~~~~~~~

- ``enable`` (bool): Enable/disable coordinate attribute setting (default: True)
- ``validate`` (str): Validation mode - 'ignore', 'warn', 'error', or 'fix' (default: 'warn')
- ``set_coordinates_attr`` (bool): Set 'coordinates' attribute on data variables (default: True)

Getting Coordinate Metadata
----------------------------

Query available metadata for any coordinate:

.. code-block:: python

    # Get metadata for a specific coordinate
    lat_meta = ds.pycmor.coords.get_metadata('lat')
    print(lat_meta)
    # {'standard_name': 'latitude', 'units': 'degrees_north', 'axis': 'Y'}

    # List all recognized coordinates
    all_coords = ds.pycmor.coords.list_recognized()
    print(all_coords[:5])
    # ['lat', 'latitude', 'lon', 'longitude', 'plev19']

Validating Coordinates
----------------------

Check if existing coordinate attributes are correct:

.. code-block:: python

    # Validate all coordinates
    results = ds.pycmor.coords.validate()
    print(results)
    # {
    #     'lat': {'valid': True},
    #     'lon': {'valid': False, 'issues': [...]},
    #     ...
    # }

    # With error mode (raises exception on issues)
    results = ds.pycmor.coords.validate(mode='error')

Dimension Operations (.pycmor.dims)
====================================

Detecting Dimension Types
--------------------------

Automatically detect what each dimension represents:

.. code-block:: python

    # Detect all dimension types
    types = ds.pycmor.dims.detect_types()
    print(types)
    # {
    #     'time': 'time',
    #     'lev': 'pressure',
    #     'latitude': 'latitude',
    #     'longitude': 'longitude'
    # }

The detection uses multiple strategies:

1. Name pattern matching (e.g., 'lat', 'latitude', 'rlat')
2. Standard name attributes
3. Axis attributes (X, Y, Z, T)
4. Value range analysis

CMIP6 Usage
-----------

Map dimensions using CMIP6 table and variable names:

.. code-block:: python

    # Basic CMIP6 mapping
    ds_mapped = ds.pycmor.dims.map_to_cmip(
        table="Amon",
        variable="tas"
    )

    # With user overrides
    ds_mapped = ds.pycmor.dims.map_to_cmip(
        table="Amon",
        variable="tas",
        user_mapping={'lev': 'plev19'}
    )

    # With validation
    ds_mapped = ds.pycmor.dims.map_to_cmip(
        table="Amon",
        variable="tas",
        validate='error',  # Raise on validation failures
        allow_override=False  # Strict CMIP compliance
    )

CMIP7 Usage
-----------

Map dimensions using CMIP7 compound names:

.. code-block:: python

    # Using full CMIP7 compound name
    ds_mapped = ds.pycmor.dims.map_to_cmip(
        compound_name="atmos.tas.tavg-h2m-hxy-u.mon.GLB"
    )

    # Using CMIP6-style for backward compatibility
    ds_mapped = ds.pycmor.dims.map_to_cmip(
        compound_name="Amon.tas",
        cmor_version="CMIP7"
    )

Smart Detection
---------------

Let pycmor auto-detect the format:

.. code-block:: python

    # Auto-detect CMIP6 format
    ds_mapped = ds.pycmor.dims.map_to_cmip(
        variable_spec="Amon.tas"
    )

    # Auto-detect CMIP7 format
    ds_mapped = ds.pycmor.dims.map_to_cmip(
        variable_spec="atmos.tas.tavg-h2m-hxy-u.mon.GLB"
    )

Standalone Mode (No CMIP Tables)
---------------------------------

Perform intelligent dimension mapping without CMIP table requirements:

.. code-block:: python

    # Smart mapping to standard names
    ds_mapped = ds.pycmor.dims.map_to_cmip()
    # Automatically maps: latitude→lat, longitude→lon, etc.

    # Manual target dimensions
    ds_mapped = ds.pycmor.dims.map_to_cmip(
        target_dimensions=['time', 'plev19', 'lat', 'lon']
    )

    # With custom user mapping
    ds_mapped = ds.pycmor.dims.map_to_cmip(
        target_dimensions=['time', 'plev19', 'lat', 'lon'],
        user_mapping={'lev': 'plev19', 'latitude': 'lat'}
    )

Advanced: Low-Level Operations
-------------------------------

For expert users, create and apply mappings separately:

.. code-block:: python

    # Create mapping without applying
    mapping = ds.pycmor.dims.create_mapping(
        table="Amon",
        variable="tas"
    )
    print(mapping)
    # {'time': 'time', 'latitude': 'lat', 'longitude': 'lon'}

    # Apply existing mapping
    ds_mapped = ds.pycmor.dims.apply_mapping(mapping)

Complete Example Workflow
==========================

CMIP6 Example
-------------

.. code-block:: python

    import xarray as xr
    import pycmor

    # Load model output
    ds = xr.open_dataset("awicm_output.nc")

    # Inspect dimensions
    print(ds.dims)
    # Dimensions: (time: 120, lev: 19, latitude: 180, longitude: 360)

    # Detect what dimensions represent
    dim_types = ds.pycmor.dims.detect_types()
    print(dim_types)
    # {'time': 'time', 'lev': 'pressure', 'latitude': 'latitude', 'longitude': 'longitude'}

    # Map to CMIP6 Amon table for tas variable
    ds = ds.pycmor.dims.map_to_cmip(
        table="Amon",
        variable="tas"
    )
    print(ds.dims)
    # Dimensions: (time: 120, lat: 180, lon: 360)

    # Set CF-compliant coordinate attributes
    ds = ds.pycmor.coords.set_attributes()

    # Check attributes were set correctly
    print(ds['lat'].attrs)
    # {'standard_name': 'latitude', 'units': 'degrees_north', 'axis': 'Y'}

    # Save CMIP-compliant output
    ds.to_netcdf("cmip6_tas.nc")

CMIP7 Example
-------------

.. code-block:: python

    import xarray as xr
    import pycmor

    # Load model output
    ds = xr.open_dataset("model_output.nc")

    # Map using CMIP7 compound name
    ds = ds.pycmor.dims.map_to_cmip(
        compound_name="atmos.tas.tavg-h2m-hxy-u.mon.GLB"
    )

    # Set coordinate attributes
    ds = ds.pycmor.coords.set_attributes()

    # Validate everything is correct
    coord_validation = ds.pycmor.coords.validate()
    print(coord_validation)

    # Save output
    ds.to_netcdf("cmip7_tas.nc")

Integration with Pipelines
===========================

The accessors complement pipeline processing but don't replace it. Use them for:

**Interactive Exploration**
  - Quick testing in Jupyter notebooks
  - Debugging dimension/coordinate issues
  - Prototyping processing steps

**Pipeline Processing**
  - Use full CMORizer with configuration files
  - Benefit from Prefect workflows and Dask parallelization
  - Handle large datasets and complex multi-variable processing

Pipeline code continues to work unchanged:

.. code-block:: python

    from pycmor.std_lib import map_dimensions, set_coordinate_attributes

    def my_pipeline_step(data, rule):
        data = map_dimensions(data, rule)
        data = set_coordinate_attributes(data, rule)
        return data

Configuration Reference
========================

Coordinate Attributes
---------------------

.. list-table::
   :header-rows: 1
   :widths: 20 15 50

   * - Parameter
     - Default
     - Description
   * - ``enable``
     - ``True``
     - Enable coordinate attribute setting
   * - ``validate``
     - ``'warn'``
     - Validation mode: 'ignore', 'warn', 'error', 'fix'
   * - ``set_coordinates_attr``
     - ``True``
     - Set 'coordinates' attribute on data variables

Dimension Mapping
-----------------

.. list-table::
   :header-rows: 1
   :widths: 20 15 50

   * - Parameter
     - Default
     - Description
   * - ``enable``
     - ``True``
     - Enable dimension mapping
   * - ``validate``
     - ``'warn'``
     - Validation mode: 'ignore', 'warn', 'error'
   * - ``allow_override``
     - ``True``
     - Allow user mappings to override CMIP table dimensions
   * - ``user_mapping``
     - ``{}``
     - Dictionary of {source_dim: target_dim} overrides

API Reference
=============

For detailed API documentation, see:

.. autosummary::
   :toctree: generated/

   pycmor.core.accessor.PycmorAccessor
   pycmor.core.accessor.CoordinateAccessor
   pycmor.core.accessor.DimensionAccessor

See Also
========

- :doc:`coordinate_attributes` - Detailed coordinate attribute documentation
- :doc:`dimension_mapping` - Detailed dimension mapping documentation
- :doc:`pycmor_building_blocks` - Core pycmor concepts
- :doc:`standard_library` - Standard processing steps
