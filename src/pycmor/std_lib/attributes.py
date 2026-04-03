from typing import Union

import xarray as xr

from ..core.rule import Rule
from .coordinate_attributes import set_coordinate_attributes
from .global_attributes import set_global_attributes
from .variable_attributes import set_variable_attrs


def set_coordinates(ds: Union[xr.Dataset, xr.DataArray], rule: Rule) -> Union[xr.Dataset, xr.DataArray]:
    """
    Wrapper function for set_coordinate_attributes.

    This function ensures CF-compliant metadata attributes are set on coordinate variables.

    Parameters
    ----------
    ds : Union[xr.Dataset, xr.DataArray]
        Input dataset or data array
    rule : Rule
        Processing rule containing configuration

    Returns
    -------
    Union[xr.Dataset, xr.DataArray]
        Dataset or DataArray with coordinate attributes set according to CF conventions
    """
    return set_coordinate_attributes(ds, rule)


def set_variable(ds: Union[xr.Dataset, xr.DataArray], rule: Rule) -> Union[xr.Dataset, xr.DataArray]:
    """
    Wrapper function for set_variable_attrs.

    This function sets variable attributes according to the CMOR variable definition
    in the processing rule, including units, missing values, and other metadata.

    Parameters
    ----------
    ds : Union[xr.Dataset, xr.DataArray]
        Input dataset or data array containing the variable to process
    rule : Rule
        Processing rule containing variable definitions and configuration

    Returns
    -------
    Union[xr.Dataset, xr.DataArray]
        Dataset or DataArray with variable attributes set according to CMOR standards
    """
    return set_variable_attrs(ds, rule)


def set_global(ds: Union[xr.Dataset, xr.DataArray], rule: Rule) -> Union[xr.Dataset, xr.DataArray]:
    """
    Wrapper function for set_global_attributes.

    This function sets global attributes on the dataset according to the CMOR
    processing rules, including information about the source, experiment,
    and other metadata.

    Parameters
    ----------
    ds : Union[xr.Dataset, xr.DataArray]
        Input dataset or data array to add global attributes to
    rule : Rule
        Processing rule containing global attribute definitions

    Returns
    -------
    Union[xr.Dataset, xr.DataArray]
        Dataset or DataArray with global attributes set according to CMOR standards
    """
    return set_global_attributes(ds, rule)
