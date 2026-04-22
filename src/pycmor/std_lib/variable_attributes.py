"""
Pipeline steps to attach metadata attributes to the xarrays
"""

from typing import Union

import xarray as xr

from ..core.logging import logger
from ..core.rule import Rule


def set_variable_attrs(ds: Union[xr.Dataset, xr.DataArray], rule: Rule) -> Union[xr.Dataset, xr.DataArray]:
    if isinstance(ds, xr.Dataset):
        given_dtype = xr.Dataset
        da = ds[rule.model_variable]
        if rule.model_variable != rule.cmor_variable:
            ds = ds.rename({rule.model_variable: rule.cmor_variable})
            da = ds[rule.cmor_variable]
    elif isinstance(ds, xr.DataArray):
        given_dtype = xr.DataArray
        da = ds
        if da.name != rule.cmor_variable:
            da = da.rename(rule.cmor_variable)
    else:
        raise TypeError("Input must be an xarray Dataset or DataArray")

    # Use the associated data_request_variable to set the variable attributes
    missing_value = rule._pycmor_cfg("xarray_default_dataarray_attrs_missing_value")
    attrs = rule.data_request_variable.attrs.copy()  # avoid modifying original

    # Flag variables (CF flag-type) must not carry missing_value/_FillValue.
    is_flag = ("flag_values" in attrs) or ("flag_meanings" in attrs) \
        or ("flag_values" in da.attrs) or ("flag_meanings" in da.attrs)

    # Set missing value in attrs if not present (skip flag variables)
    if not is_flag:
        for attr in ["missing_value", "_FillValue"]:
            if attrs.get(attr) is None:
                attrs[attr] = missing_value

    skip_setting_unit_attr = rule._pycmor_cfg("xarray_default_dataarray_processing_skip_unit_attr_from_drv")
    if skip_setting_unit_attr:
        attrs.pop("units", None)

    # Remove _FillValue and missing_value from attrs before setting .attrs
    attrs_for_encoding = {}
    for enc_attr in ["_FillValue", "missing_value"]:
        if enc_attr in attrs:
            attrs_for_encoding[enc_attr] = attrs.pop(enc_attr)

    logger.info("Setting the following attributes:")
    for k, v in attrs.items():
        logger.info(f"{k}: {v}")
    da.attrs.update(attrs)

    # CMIP/CF requires `_FillValue` via encoding and `missing_value` as a CF attribute
    # with matching dtype. xarray casts encoded _FillValue to the variable dtype; we must
    # match that manually for the attribute to avoid dtype-mismatch warnings.
    import numpy as np
    for k, v in attrs_for_encoding.items():
        if k == "_FillValue":
            da.encoding["_FillValue"] = v
        if k == "missing_value":
            try:
                if da.dtype.kind == "i":
                    info = np.iinfo(da.dtype)
                    if not (info.min <= v <= info.max):
                        continue  # value doesn't fit integer dtype; skip attr
                    cast = da.dtype.type(v)
                elif da.dtype.kind == "f":
                    cast = da.dtype.type(v)
                else:
                    cast = np.float32(v)
            except Exception:
                cast = np.float32(v)
            da.attrs["missing_value"] = cast

    if given_dtype == xr.Dataset:
        return ds
    elif given_dtype == xr.DataArray:
        return da
    else:
        raise TypeError("Given data type is not an xarray Dataset or DataArray, refusing to continue!")


# Alias name for the function
set_variable_attributes = set_variable_attrs
