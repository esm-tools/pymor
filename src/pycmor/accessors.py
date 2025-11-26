"""
Xarray accessor registration module for pycmor.

This module imports and registers all xarray accessors used throughout the pycmor project.
By importing this module, all accessors become available on xarray DataArrays and Datasets.
"""

from xarray import register_dataarray_accessor, register_dataset_accessor

# Import modules that register specialized xarray accessors
from .core.infer_freq import DatasetFrequencyAccessor, TimeFrequencyAccessor
from .core.rule import Rule

# Future accessor imports can be added here as the project grows
# from .other_module import other_accessor  # noqa: F401


@register_dataarray_accessor("pycmor")
class PycmorDataArrayAccessor:
    """
    Unified pycmor accessor for xarray DataArrays.

    This accessor provides access to all pycmor functionality under a single namespace.
    It delegates to specialized accessors like timefreq while providing a unified interface.

    Examples
    --------
    # Time frequency operations
    data.pycmor.resample_safe(target_approx_interval=30.0)  # ~monthly
    data.pycmor.resample_safe(freq_str='3M')  # 3-monthly
    data.pycmor.check_resolution(target_approx_interval=1.0)  # daily
    data.pycmor.infer_frequency()  # infer frequency from data

    # Pipeline operations - simple stateless processing with CMIP7 (default)
    result = data.pycmor.process('atmos.tas.tavg-h2m-hxy-u.mon.GLB')

    # CMIP6 usage with simple variable name
    result = data.pycmor.process('tas', cmor_version='CMIP6')

    # With custom pipeline
    from pycmor.pipeline import DefaultPipeline
    result = data.pycmor.process(
        'ocean.tos.tavg-hxy-u.mon.GLB',
        pipeline=DefaultPipeline
    )

    # Inherit defaults from config file
    # In ~/.pycmor.yaml or ${XDG_CONFIG_HOME}/pycmor/pycmor.yaml:
    #   inherit:
    #     source_id: "FESOM2"
    #     experiment_id: "historical"
    #     variant_label: "r1i1p1f1"
    #     grid_label: "gn"
    #
    # These values are automatically applied to all process() calls
    result = data.pycmor.process('atmos.tas.tavg-h2m-hxy-u.mon.GLB')
    # source_id, experiment_id, etc. come from config file
    """

    def __init__(self, xarray_obj):
        self._obj = xarray_obj
        # Initialize specialized accessors
        self._timefreq = TimeFrequencyAccessor(xarray_obj)

    # Time frequency methods - delegate to TimeFrequencyAccessor
    def resample_safe(self, *args, **kwargs):
        """Resample data safely with temporal resolution validation.

        See TimeFrequencyAccessor.resample_safe for full documentation.
        """
        return self._timefreq.resample_safe(*args, **kwargs)

    def check_resolution(self, *args, **kwargs):
        """Check if temporal resolution is sufficient for resampling.

        See TimeFrequencyAccessor.check_resolution for full documentation.
        """
        return self._timefreq.check_resolution(*args, **kwargs)

    def infer_frequency(self, *args, **kwargs):
        """Infer frequency from time series data.

        See TimeFrequencyAccessor.infer_frequency for full documentation.
        """
        return self._timefreq.infer_frequency(*args, **kwargs)

    # Pipeline methods
    def process(
        self,
        variable=None,
        cmor_version="CMIP7",
        pipeline=None,
        compound_name=None,
        cmor_variable=None,
        data_request_variable=None,
        **rule_kwargs,
    ):
        """Process this data through a pycmor pipeline.

        Parameters
        ----------
        variable : str
            Variable identifier to process. How this is interpreted depends on cmor_version:
            - For CMIP6: interpreted as cmor_variable (e.g., 'tas', 'pr')
            - For CMIP7+: interpreted as compound_name (e.g., 'atmos.tas.tavg-h2m-hxy-u.mon.GLB')
            Cannot be used together with compound_name, cmor_variable, or data_request_variable kwargs.
        cmor_version : str, optional
            CMIP version to use for variable lookup (e.g., 'CMIP6', 'CMIP7').
            Defaults to 'CMIP7'. Determines how the positional variable arg is interpreted.
        pipeline : Pipeline instance, class, string, or None, optional
            Pipeline to use. If None, uses DefaultPipeline.
            If string, looks for pipeline class in pycmor.pipeline module.
            If class, instantiates it.
            If instance, uses it directly.
        compound_name : str, optional
            CMIP7 compound name for explicit lookup (e.g., 'atmos.tas.tavg-h2m-hxy-u.mon.GLB').
            Cannot be used with positional variable arg.
        cmor_variable : str, optional
            CMOR variable name for explicit lookup (e.g., 'tas').
            Cannot be used with positional variable arg.
        data_request_variable : DataRequestVariable, optional
            Explicit DataRequestVariable instance to use.
            If provided, variable lookup is skipped.
            Cannot be used with positional variable arg.
        **rule_kwargs
            Additional arguments for Rule constructor (units, etc.)

        Returns
        -------
        xr.DataArray
            Processed data

        Examples
        --------
        # CMIP7 usage with compound name (default)
        result = data.pycmor.process('atmos.tas.tavg-h2m-hxy-u.mon.GLB')

        # CMIP6 usage with simple variable name
        result = data.pycmor.process('tas', cmor_version='CMIP6')

        # Explicit compound_name kwarg
        result = data.pycmor.process(
            compound_name='atmos.tas.tavg-h2m-hxy-u.mon.GLB',
            cmor_version='CMIP7'
        )

        # Explicit cmor_variable kwarg
        result = data.pycmor.process(
            cmor_variable='tas',
            cmor_version='CMIP6'
        )

        # Use with custom pipeline
        from pycmor.pipeline import DefaultPipeline
        result = data.pycmor.process(
            'atmos.pr.tavg-hxy-u.mon.GLB',
            pipeline=DefaultPipeline
        )

        # Use explicit DataRequestVariable instance
        from pycmor.data_request.collection import CMIP7DataRequest
        dr = CMIP7DataRequest.from_vendored_json()
        drv = dr.variables['atmos.tas.tavg-h2m-hxy-u.mon.GLB']
        result = data.pycmor.process(
            'atmos.tas.tavg-h2m-hxy-u.mon.GLB',
            data_request_variable=drv
        )

        # Use with additional rule kwargs
        result = data.pycmor.process(
            'ocean.tos.tavg-hxy-u.mon.GLB',
            units='degC'
        )
        """
        # Conflict checks
        if variable and data_request_variable:
            raise ValueError("Cannot specify both positional variable and data_request_variable")
        if variable and compound_name:
            raise ValueError("Cannot specify both positional variable and compound_name kwarg")
        if variable and cmor_variable:
            raise ValueError("Cannot specify both positional variable and cmor_variable kwarg")

        # Interpret the positional variable arg based on CMIP version
        if variable:
            if cmor_version == "CMIP6":
                cmor_variable = variable
            else:  # CMIP7+ defaults to compound_name
                compound_name = variable

        # Get or create DataRequestVariable
        if data_request_variable is not None:
            drv = data_request_variable
        elif compound_name or cmor_variable:
            # Look up variable in DataRequest using TableLocator priority chain
            from .core.factory import create_factory
            from .core.resource_locator import TableLocator
            from .data_request.collection import DataRequest

            # Get the versioned classes using factory pattern
            DataRequestFactory = create_factory(DataRequest)
            DataRequestClass = DataRequestFactory.get(cmor_version)

            TableLocatorFactory = create_factory(TableLocator)
            TableLocatorClass = TableLocatorFactory.get(cmor_version)

            # Use TableLocator to find tables with 5-level priority chain:
            # 1. User-specified path (none here)
            # 2. XDG cache
            # 3. Remote git (with caching)
            # 4. Packaged resources
            # 5. Vendored submodules
            locator = TableLocatorClass(version=None, user_path=None)
            table_dir = locator.locate()

            # Create DataRequest from located directory
            dr = DataRequestClass.from_directory(table_dir)

            # Look up the variable by compound_name or cmor_variable
            lookup_key = compound_name if compound_name else cmor_variable
            if lookup_key not in dr.variables:
                raise ValueError(
                    f"Variable '{lookup_key}' not found in {cmor_version} DataRequest. "
                    f"Available variables: {sorted(dr.variables.keys())[:10]}..."
                )
            drv = dr.variables[lookup_key]
        else:
            raise ValueError(
                "Must provide a variable identifier. "
                "Examples:\n"
                "  CMIP7: process('atmos.tas.tavg-h2m-hxy-u.mon.GLB')\n"
                "  CMIP6: process('tas', cmor_version='CMIP6')"
            )

        # Get inherit defaults from config file
        from .core.config import PycmorConfigManager

        config = PycmorConfigManager.from_pycmor_cfg()
        inherit_defaults = config.get_inherit_section()

        # Merge: inherit < rule_kwargs (explicit args override defaults)
        merged_kwargs = {**inherit_defaults, **rule_kwargs}

        # Build rule from kwargs - no inputs needed since we have data
        if "inputs" not in merged_kwargs:
            merged_kwargs["inputs"] = []

        # Attach DataRequestVariable to rule
        # Rule.from_dict requires cmor_variable, so extract it from DRV if needed
        if not cmor_variable:
            # For CMIP7, extract cmor_variable from DataRequestVariable
            cmor_variable = getattr(drv, "variable_id", None) or getattr(drv, "name", None)
            if not cmor_variable:
                raise ValueError(f"Cannot determine cmor_variable from DataRequestVariable: {drv}")

        merged_kwargs["cmor_variable"] = cmor_variable

        # Also attach compound_name if available (CMIP7)
        if compound_name:
            merged_kwargs["compound_name"] = compound_name

        merged_kwargs["data_request_variables"] = [drv]

        rule = Rule.from_dict(merged_kwargs)

        # Handle pipeline - default to DefaultPipeline
        if pipeline is None:
            from .core.pipeline import DefaultPipeline

            pipeline = DefaultPipeline()
        elif isinstance(pipeline, str):
            from .core.utils import get_callable_by_name

            pipeline = get_callable_by_name(f"pycmor.pipeline.{pipeline}")()
        elif isinstance(pipeline, type):
            pipeline = pipeline()

        return pipeline.run(self._obj, rule)


@register_dataset_accessor("pycmor")
class PycmorDatasetAccessor:
    """
    Unified pycmor accessor for xarray Datasets.

    This accessor provides access to all pycmor functionality under a single namespace.
    It delegates to specialized accessors like timefreq while providing a unified interface.

    Examples
    --------
    # Time frequency operations
    dataset.pycmor.resample_safe(target_approx_interval=30.0)  # ~monthly
    dataset.pycmor.resample_safe(freq_str='3M')  # 3-monthly
    dataset.pycmor.check_resolution(target_approx_interval=1.0)  # daily
    dataset.pycmor.infer_frequency()  # infer frequency from data

    # Pipeline operations - simple stateless processing with CMIP7 (default)
    result = dataset.pycmor.process('atmos.tas.tavg-h2m-hxy-u.mon.GLB')

    # CMIP6 usage with simple variable name
    result = dataset.pycmor.process('tas', cmor_version='CMIP6')

    # With custom pipeline
    from pycmor.pipeline import DefaultPipeline
    result = dataset.pycmor.process(
        'ocean.tos.tavg-hxy-u.mon.GLB',
        pipeline=DefaultPipeline
    )

    # Inherit defaults from config file
    # In ~/.pycmor.yaml or ${XDG_CONFIG_HOME}/pycmor/pycmor.yaml:
    #   inherit:
    #     source_id: "FESOM2"
    #     experiment_id: "historical"
    #     variant_label: "r1i1p1f1"
    #     grid_label: "gn"
    #
    # These values are automatically applied to all process() calls
    result = dataset.pycmor.process('atmos.tas.tavg-h2m-hxy-u.mon.GLB')
    # source_id, experiment_id, etc. come from config file
    """

    def __init__(self, xarray_obj):
        self._obj = xarray_obj
        # Initialize specialized accessors
        self._timefreq = DatasetFrequencyAccessor(xarray_obj)

    # Time frequency methods - delegate to DatasetFrequencyAccessor
    def resample_safe(self, *args, **kwargs):
        """Resample dataset safely with temporal resolution validation.

        See DatasetFrequencyAccessor.resample_safe for full documentation.
        """
        return self._timefreq.resample_safe(*args, **kwargs)

    def check_resolution(self, *args, **kwargs):
        """Check if temporal resolution is sufficient for resampling.

        See DatasetFrequencyAccessor.check_resolution for full documentation.
        """
        return self._timefreq.check_resolution(*args, **kwargs)

    def infer_frequency(self, *args, **kwargs):
        """Infer frequency from time series data.

        See DatasetFrequencyAccessor.infer_frequency for full documentation.
        """
        return self._timefreq.infer_frequency(*args, **kwargs)

    # Pipeline methods
    def process(
        self,
        variable=None,
        cmor_version="CMIP7",
        pipeline=None,
        compound_name=None,
        cmor_variable=None,
        data_request_variable=None,
        **rule_kwargs,
    ):
        """Process this data through a pycmor pipeline.

        Parameters
        ----------
        variable : str
            Variable identifier to process. How this is interpreted depends on cmor_version:
            - For CMIP6: interpreted as cmor_variable (e.g., 'tas', 'pr')
            - For CMIP7+: interpreted as compound_name (e.g., 'atmos.tas.tavg-h2m-hxy-u.mon.GLB')
            Cannot be used together with compound_name, cmor_variable, or data_request_variable kwargs.
        cmor_version : str, optional
            CMIP version to use for variable lookup (e.g., 'CMIP6', 'CMIP7').
            Defaults to 'CMIP7'. Determines how the positional variable arg is interpreted.
        pipeline : Pipeline instance, class, string, or None, optional
            Pipeline to use. If None, uses DefaultPipeline.
            If string, looks for pipeline class in pycmor.pipeline module.
            If class, instantiates it.
            If instance, uses it directly.
        compound_name : str, optional
            CMIP7 compound name for explicit lookup (e.g., 'atmos.tas.tavg-h2m-hxy-u.mon.GLB').
            Cannot be used with positional variable arg.
        cmor_variable : str, optional
            CMOR variable name for explicit lookup (e.g., 'tas').
            Cannot be used with positional variable arg.
        data_request_variable : DataRequestVariable, optional
            Explicit DataRequestVariable instance to use.
            If provided, variable lookup is skipped.
            Cannot be used with positional variable arg.
        **rule_kwargs
            Additional arguments for Rule constructor (units, etc.)

        Returns
        -------
        xr.Dataset
            Processed data

        Examples
        --------
        # CMIP7 usage with compound name (default)
        result = dataset.pycmor.process('atmos.tas.tavg-h2m-hxy-u.mon.GLB')

        # CMIP6 usage with simple variable name
        result = dataset.pycmor.process('tas', cmor_version='CMIP6')

        # Explicit compound_name kwarg
        result = dataset.pycmor.process(
            compound_name='atmos.tas.tavg-h2m-hxy-u.mon.GLB',
            cmor_version='CMIP7'
        )

        # Explicit cmor_variable kwarg
        result = dataset.pycmor.process(
            cmor_variable='tas',
            cmor_version='CMIP6'
        )

        # Use with custom pipeline
        from pycmor.pipeline import DefaultPipeline
        result = dataset.pycmor.process(
            'atmos.pr.tavg-hxy-u.mon.GLB',
            pipeline=DefaultPipeline
        )

        # Use explicit DataRequestVariable instance
        from pycmor.data_request.collection import CMIP7DataRequest
        dr = CMIP7DataRequest.from_vendored_json()
        drv = dr.variables['atmos.tas.tavg-h2m-hxy-u.mon.GLB']
        result = dataset.pycmor.process(
            'atmos.tas.tavg-h2m-hxy-u.mon.GLB',
            data_request_variable=drv
        )

        # Use with additional rule kwargs
        result = dataset.pycmor.process(
            'ocean.tos.tavg-hxy-u.mon.GLB',
            units='degC'
        )
        """
        # Conflict checks
        if variable and data_request_variable:
            raise ValueError("Cannot specify both positional variable and data_request_variable")
        if variable and compound_name:
            raise ValueError("Cannot specify both positional variable and compound_name kwarg")
        if variable and cmor_variable:
            raise ValueError("Cannot specify both positional variable and cmor_variable kwarg")

        # Interpret the positional variable arg based on CMIP version
        if variable:
            if cmor_version == "CMIP6":
                cmor_variable = variable
            else:  # CMIP7+ defaults to compound_name
                compound_name = variable

        # Get or create DataRequestVariable
        if data_request_variable is not None:
            drv = data_request_variable
        elif compound_name or cmor_variable:
            # Look up variable in DataRequest using TableLocator priority chain
            from .core.factory import create_factory
            from .core.resource_locator import TableLocator
            from .data_request.collection import DataRequest

            # Get the versioned classes using factory pattern
            DataRequestFactory = create_factory(DataRequest)
            DataRequestClass = DataRequestFactory.get(cmor_version)

            TableLocatorFactory = create_factory(TableLocator)
            TableLocatorClass = TableLocatorFactory.get(cmor_version)

            # Use TableLocator to find tables with 5-level priority chain:
            # 1. User-specified path (none here)
            # 2. XDG cache
            # 3. Remote git (with caching)
            # 4. Packaged resources
            # 5. Vendored submodules
            locator = TableLocatorClass(version=None, user_path=None)
            table_dir = locator.locate()

            # Create DataRequest from located directory
            dr = DataRequestClass.from_directory(table_dir)

            # Look up the variable by compound_name or cmor_variable
            lookup_key = compound_name if compound_name else cmor_variable
            if lookup_key not in dr.variables:
                raise ValueError(
                    f"Variable '{lookup_key}' not found in {cmor_version} DataRequest. "
                    f"Available variables: {sorted(dr.variables.keys())[:10]}..."
                )
            drv = dr.variables[lookup_key]
        else:
            raise ValueError(
                "Must provide a variable identifier. "
                "Examples:\n"
                "  CMIP7: process('atmos.tas.tavg-h2m-hxy-u.mon.GLB')\n"
                "  CMIP6: process('tas', cmor_version='CMIP6')"
            )

        # Get inherit defaults from config file
        from .core.config import PycmorConfigManager

        config = PycmorConfigManager.from_pycmor_cfg()
        inherit_defaults = config.get_inherit_section()

        # Merge: inherit < rule_kwargs (explicit args override defaults)
        merged_kwargs = {**inherit_defaults, **rule_kwargs}

        # Build rule from kwargs - no inputs needed since we have data
        if "inputs" not in merged_kwargs:
            merged_kwargs["inputs"] = []

        # Attach DataRequestVariable to rule
        # Rule.from_dict requires cmor_variable, so extract it from DRV if needed
        if not cmor_variable:
            # For CMIP7, extract cmor_variable from DataRequestVariable
            cmor_variable = getattr(drv, "variable_id", None) or getattr(drv, "name", None)
            if not cmor_variable:
                raise ValueError(f"Cannot determine cmor_variable from DataRequestVariable: {drv}")

        merged_kwargs["cmor_variable"] = cmor_variable

        # Also attach compound_name if available (CMIP7)
        if compound_name:
            merged_kwargs["compound_name"] = compound_name

        merged_kwargs["data_request_variables"] = [drv]

        rule = Rule.from_dict(merged_kwargs)

        # Handle pipeline - default to DefaultPipeline
        if pipeline is None:
            from .core.pipeline import DefaultPipeline

            pipeline = DefaultPipeline()
        elif isinstance(pipeline, str):
            from .core.utils import get_callable_by_name

            pipeline = get_callable_by_name(f"pycmor.pipeline.{pipeline}")()
        elif isinstance(pipeline, type):
            pipeline = pipeline()

        return pipeline.run(self._obj, rule)
