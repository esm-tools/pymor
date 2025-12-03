from typing import Union

import xarray as xr

from ..core.rule import Rule
from .dimension_mapping import map_dimensions as _map_dimensions


def map_dimensions(data: Union[xr.Dataset, xr.DataArray], rule: Rule) -> Union[xr.Dataset, xr.DataArray]:
    """
    Wrapper function for dimension mapping functionality.

    This function handles the mapping of source dataset dimensions to CMIP-required
    dimension names and formats. It ensures that the input dataset's dimensions
    match the expected CMIP conventions.

    Parameters
    ----------
    data : Union[xr.Dataset, xr.DataArray]
        Input dataset or data array with dimensions to be mapped
    rule : Rule
        Processing rule containing CMOR variable definition and configuration

    Returns
    -------
    Union[xr.Dataset, xr.DataArray]
        Dataset or DataArray with dimensions mapped according to CMIP requirements

    See Also
    --------
    dimension_mapping.map_dimensions : The underlying implementation function
    """
    return _map_dimensions(data, rule)
