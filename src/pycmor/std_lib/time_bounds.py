"""
Set time bounds for datasets based on time method and approximate interval.

Time bounds represent the start and end of the time interval associated with
each time point. For climate data, these are required for CMIP compliance.

The main function is :func:`time_bounds` which creates appropriate bounds
based on the time method (mean, instantaneous, or climatology) and the
data's temporal frequency.
"""

import numpy as np
import xarray as xr

from ..core.logging import logger
from ..core.rule import Rule
from .dataset_helpers import get_time_label


def time_bounds(ds: xr.Dataset, rule: Rule) -> xr.Dataset:
    """
    Set time bounds for a variable based on time method and approx_interval.

    Time bounds are set according to the following logic:

    - For instantaneous time method: bounds equal the time values (delta = 0)
    - For mean time method: bounds span the averaging interval (delta > 0)
    - For climatology: no bounds are created
    - Uses approx_interval from rule to determine appropriate bounds

    Parameters
    ----------
    ds : xr.Dataset
        The input dataset.
    rule : Rule
        Rule object. Uses ``approx_interval`` (float, days) and
        ``time_method`` (str) attributes if present.

    Returns
    -------
    xr.Dataset
        The output dataset with time bounds information.

    Raises
    ------
    ValueError
        If the input is not a Dataset, has no time coordinate, or has
        insufficient time points for the requested bounds type.
    """
    dataset_name = ds.attrs.get("name", "unnamed_dataset")
    logger.info(f"[Time bounds] {dataset_name}")

    if not isinstance(ds, xr.Dataset):
        raise ValueError("The input is not a dataset.")

    time_label = get_time_label(ds)
    if time_label is None:
        # fx / ofx and other time-invariant outputs have no time coord.
        # set_time_bounds is a no-op for those; skip silently rather than
        # raising so the same DefaultPipeline can be reused for fx rules.
        logger.info("  no time coordinate; skipping (fx-style dataset)")
        return ds

    bounds_dim_label = "bnds"
    time_bounds_label = f"{time_label}_{bounds_dim_label}"

    approx_interval = getattr(rule, "approx_interval", None)
    time_method = getattr(rule, "time_method", None) or ds.attrs.get("time_method", "mean")

    logger.info(f"  time label: {time_label}, approx_interval: {approx_interval} days")
    logger.info(f"  time method: {time_method}")

    # If the source carries a non-canonical XIOS-style ``<time>_bounds``
    # (FESOM convention) but not the CMIP-canonical ``<time>_bnds``,
    # rename it now so the rest of the function (and downstream tools)
    # sees the canonical name. Avoids the wcrp TIME003 month-precision
    # fallback that kicks in when no canonical bnds variable is found.
    noncanonical = f"{time_label}_bounds"
    if noncanonical in ds.variables and time_bounds_label not in ds.variables:
        ds = ds.rename({noncanonical: time_bounds_label})
        ds[time_label].attrs["bounds"] = time_bounds_label
        logger.info(f"  renamed {noncanonical} -> {time_bounds_label}")

    if time_method not in ("mean", "instantaneous", "climatology"):
        logger.warning(f"  Unknown time method '{time_method}', defaulting to 'mean'")
        time_method = "mean"

    if time_method == "climatology":
        logger.info("  skipping bounds creation for climatology data")
        return ds

    time_var = ds[time_label]
    time_values = time_var.values

    if len(time_values) < 1:
        raise ValueError("Cannot create time bounds: no time points found")

    # Single-stamp ``mean``-default rules (fx / ofx that didn't explicitly set
    # ``time_method=instantaneous``) would crash in ``_create_mean_bounds``,
    # and even if they didn't, manufacturing bnds for a time-invariant field
    # is wrong — the file shouldn't carry time_bnds at all. Skip silently.
    if len(time_values) < 2 and time_method != "instantaneous":
        logger.info(
            f"  {len(time_values)} time point(s) with method='{time_method}'; "
            "treating as fx-like, no bounds created"
        )
        _force_canonical_time_encoding(ds, time_label)
        return ds

    # If the source already shipped time_bnds (e.g. FESOM daily files), don't
    # recompute them, but still realign time = midpoint(bnds) so the wcrp
    # TIME001 check passes. FESOM daily output writes bnds = (day_start,
    # next_day_start) but time at day_start (midnight); the cf/CMIP
    # convention is time at the bnds midpoint (noon). The realignment is
    # skipped for instantaneous time (the point IS the value).
    if time_bounds_label in ds.variables:
        logger.info(f"  using existing bounds: {time_bounds_label}")
        if time_method != "instantaneous" and len(time_values) >= 1:
            existing_bnds = ds[time_bounds_label].values
            if existing_bnds.ndim == 2 and existing_bnds.shape[1] == 2:
                try:
                    new_time_values = _midpoint_bounds(existing_bnds)
                except Exception as exc:
                    logger.warning(
                        f"  could not realign {time_label} from existing bnds: {exc}"
                    )
                    new_time_values = None
                if new_time_values is not None:
                    new_time = time_var.copy(data=new_time_values)
                    ds = ds.assign_coords({time_label: new_time})
                    logger.info(
                        f"  realigned {time_label} to midpoint of existing {time_bounds_label}"
                    )
        if "bounds" not in ds[time_label].attrs:
            ds[time_label].attrs["bounds"] = time_bounds_label
        _force_canonical_time_encoding(ds, time_label)
        return ds

    logger.info(f"  {len(time_values)} points from {time_values[0]} to {time_values[-1]}")

    if time_method == "instantaneous":
        bounds_data = np.column_stack([time_values, time_values])
        new_time_values = None
    else:
        bounds_data = _create_mean_bounds(time_values, approx_interval)
        # CF/CMIP and wcrp TIME001 require coord == midpoint(bnds). Source
        # files often write fixed-day-of-month timestamps (e.g. always the
        # 16th at 12:00) that are off by 1-2 days for non-31-day months.
        # Replace time with the bnds midpoint so the check passes. Skipped
        # for instantaneous time (the point IS the value).
        new_time_values = _midpoint_bounds(bounds_data)

    bounds = xr.DataArray(
        data=bounds_data,
        dims=(time_label, bounds_dim_label),
        coords={
            time_label: new_time_values if new_time_values is not None else time_values,
            # Give the bnds aux a long_name so CF §3.3 doesn't flag it
            # as a meta-data-less coord variable. Without this xarray
            # writes ``int64 bnds(bnds) ;`` with no attrs, which the
            # checker reports against every file that has time_bnds.
            bounds_dim_label: xr.DataArray(
                [0, 1], dims=(bounds_dim_label,),
                attrs={"long_name": "bounds index"},
            ),
        },
        # CF §7.1: bounds variables MUST NOT carry boundary-related attrs of
        # their own (long_name, units, standard_name, calendar, axis, ...).
        # They inherit those from the parent coord at read time. Setting a
        # long_name here trips wcrp_cmip7 §7.1 with a "non matching
        # boundary related attributes: ['long_name']" finding.
        attrs={},
    )

    ds = ds.assign_coords({time_bounds_label: bounds})

    if new_time_values is not None:
        # Preserve attrs/encoding from the original time coord while
        # swapping in the midpoint-aligned values.
        new_time = time_var.copy(data=new_time_values)
        ds = ds.assign_coords({time_label: new_time})

    if "bounds" not in ds[time_label].attrs:
        ds[time_label].attrs["bounds"] = time_bounds_label

    _force_canonical_time_encoding(ds, time_label)

    logger.info(f"  set {time_bounds_label}{bounds.shape}, " f"range: {bounds.values[0][0]} to {bounds.values[-1][-1]}")
    return ds


def _force_canonical_time_encoding(ds, time_label):
    """Normalise the encoded ``time`` (and ``time_bnds``) attributes:

    - calendar: promote ``standard``/``gregorian`` to ``proleptic_gregorian``
      (wcrp_cmip7 TIME003a recommendation; semantically identical for any
      date after 1582-10-15).
    - units: rewrite ``seconds since`` to ``days since`` (CMIP convention;
      xarray re-encodes the same cftime objects at the new unit, no data
      mutation needed). Leaves the reference date unchanged.
    - dtype: force ``float64`` (CMIP cmor-tables specify ``type=double`` for
      time; FESOM/XIOS sometimes ships ``int64`` and writes seconds, which
      then trips wcrp_cmip7 VAR005 ``time dtype int64 (expected float)``).
    - Propagate the same encoding to ``time_bnds`` so its units / dtype /
      calendar match.
    """
    if time_label not in ds.variables:
        return
    coord = ds[time_label]
    enc = coord.encoding

    cal_enc = enc.get("calendar")
    cal_attr = coord.attrs.get("calendar")
    if (cal_enc in (None, "standard", "gregorian")) and (cal_attr in (None, "standard", "gregorian")):
        enc["calendar"] = "proleptic_gregorian"
        coord.attrs.pop("calendar", None)

    units = enc.get("units") or coord.attrs.get("units")
    if isinstance(units, str) and units.startswith("seconds since"):
        enc["units"] = "days since" + units[len("seconds since"):]
        coord.attrs.pop("units", None)

    enc["dtype"] = "float64"

    bnds_label = f"{time_label}_bnds"
    if bnds_label in ds.variables:
        b_enc = ds[bnds_label].encoding
        if "calendar" in enc:
            b_enc["calendar"] = enc["calendar"]
        if "units" in enc:
            b_enc["units"] = enc["units"]
        b_enc["dtype"] = "float64"
        # time_bnds inherits the parent coord's units/calendar at write time;
        # keep its own attrs empty (cf §7.1).
        ds[bnds_label].attrs.pop("units", None)
        ds[bnds_label].attrs.pop("calendar", None)


def _midpoint_bounds(bounds_data):
    """Per-row midpoint of a (n, 2) time-bounds array.

    Handles both numpy ``datetime64`` and ``cftime`` object arrays. The
    midpoint is computed as ``b0 + (b1 - b0) / 2`` rather than
    ``np.mean(axis=1)`` so that cftime calendars (proleptic_gregorian,
    noleap, 360_day, ...) round-trip correctly — ``np.mean`` doesn't
    know how to average cftime objects.
    """
    if np.issubdtype(bounds_data.dtype, np.datetime64):
        return bounds_data[:, 0] + (bounds_data[:, 1] - bounds_data[:, 0]) / 2
    return np.array(
        [b0 + (b1 - b0) / 2 for b0, b1 in bounds_data],
        dtype=object,
    )


def _create_mean_bounds(time_values, approx_interval):
    """Create bounds for mean time method.

    Parameters
    ----------
    time_values : np.ndarray
        Array of time coordinate values.
    approx_interval : float or None
        Approximate interval in days from the CMIP table.

    Returns
    -------
    np.ndarray
        Array of shape (n, 2) with start/end bounds per time point.
    """
    if len(time_values) < 2:
        raise ValueError("Cannot create mean time bounds: need at least 2 time points")

    # For numpy datetime64 we can cast directly; cftime objects need
    # date2num via their own calendar to land in a numeric space.
    if np.issubdtype(time_values.dtype, np.datetime64):
        time_diff_seconds = np.median(np.diff(time_values.astype("datetime64[s]").astype(float)))
    else:
        import cftime
        cal = getattr(time_values[0], "calendar", "standard")
        nums = cftime.date2num(time_values, units="seconds since 1970-01-01", calendar=cal)
        time_diff_seconds = float(np.median(np.diff(np.asarray(nums, dtype=float))))
    data_freq_days = time_diff_seconds / (24 * 3600)

    # Use month-aware bounds when the data spacing IS monthly. approx_interval
    # is an optional sanity check; if set, it must also indicate monthly,
    # otherwise we fall through to consecutive-step bounds. The previous
    # logic required approx_interval to be set, which silently degraded
    # broadcast-style pipelines (cfc11, ch4, ...) where the rule doesn't
    # carry a DReq-derived interval.
    data_looks_monthly = 27 <= data_freq_days <= 32
    approx_disagrees = approx_interval is not None and not (28 <= approx_interval <= 32)
    if data_looks_monthly and not approx_disagrees:
        logger.info("  detected monthly data, using month-start bounds")
        return _create_monthly_bounds(time_values)

    # Daily data: align bnds to midnight-to-midnight rather than using the
    # raw input timestamps. FESOM/XIOS writes daily stamps at noon; raw
    # consecutive bnds = (noon, next_noon) would produce midnight midpoints,
    # which wcrp TIME001 then flags as off by 0.5 against the canonical
    # (midnight, next_midnight, midpoint=noon) convention.
    data_looks_daily = 0.9 <= data_freq_days <= 1.1
    approx_disagrees_daily = (
        approx_interval is not None
        and not (0.9 <= approx_interval <= 1.1)
    )
    if data_looks_daily and not approx_disagrees_daily:
        logger.info("  detected daily data, using day-start bounds")
        return _create_daily_bounds(time_values)

    # Default: consecutive time points as bounds
    time_diff = np.median(np.diff(time_values))
    time_values_extended = np.append(time_values, time_values[-1] + time_diff)
    return np.column_stack([time_values_extended[:-1], time_values_extended[1:]])


def _create_monthly_bounds(time_values):
    """Create monthly bounds as (month_start, next_month_start).

    Handles both numpy ``datetime64`` and ``cftime`` object arrays.
    cftime is the common case for FESOM/XIOS output (calendar=standard
    or proleptic_gregorian), where ``pd.Timestamp(cftime_obj)`` raises.

    Parameters
    ----------
    time_values : np.ndarray
        Array of time values (datetime64 or cftime objects).

    Returns
    -------
    np.ndarray
        Array of shape (n, 2) with monthly bounds.
    """
    if np.issubdtype(time_values.dtype, np.datetime64):
        import pandas as pd

        bounds_data = []
        for time_val in time_values:
            ts = pd.Timestamp(time_val)
            month_start = ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if ts.month == 12:
                next_month_start = month_start.replace(year=ts.year + 1, month=1)
            else:
                next_month_start = month_start.replace(month=ts.month + 1)
            bounds_data.append([month_start.to_numpy(), next_month_start.to_numpy()])
        return np.array(bounds_data)

    bounds_data = []
    for time_val in time_values:
        month_start = time_val.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if time_val.month == 12:
            next_month_start = month_start.replace(year=time_val.year + 1, month=1)
        else:
            next_month_start = month_start.replace(month=time_val.month + 1)
        bounds_data.append([month_start, next_month_start])
    return np.array(bounds_data, dtype=object)


def _create_daily_bounds(time_values):
    """Create daily bounds as (day_start, next_day_start).

    Snaps the per-cell bnds to midnight regardless of where the input
    timestamp lies within the day. FESOM/XIOS daily output is typically
    at noon, so consecutive-step bnds = (noon, next_noon) would put the
    midpoint at midnight instead of the canonical noon. Snapping to day
    boundaries fixes wcrp TIME001 on every daily file. Handles both
    numpy ``datetime64`` and ``cftime`` object arrays.
    """
    import datetime as _dt

    if np.issubdtype(time_values.dtype, np.datetime64):
        starts = time_values.astype("datetime64[D]").astype("datetime64[ns]")
        nexts = starts + np.timedelta64(1, "D")
        return np.column_stack([starts, nexts])

    one_day = _dt.timedelta(days=1)
    bounds_data = []
    for time_val in time_values:
        day_start = time_val.replace(hour=0, minute=0, second=0, microsecond=0)
        next_day_start = day_start + one_day
        bounds_data.append([day_start, next_day_start])
    return np.array(bounds_data, dtype=object)
