from collections import deque, namedtuple

import cftime
import numpy as np
import pandas as pd
import xarray as xr
from xarray.core.utils import is_scalar


def is_datetime_type(arr: np.ndarray) -> bool:
    "Checks if array elements are datetime objects or cftime objects"
    return isinstance(
        arr.item(0), tuple(cftime._cftime.DATE_TYPES.values())
    ) or np.issubdtype(arr, np.datetime64)


def get_time_label(ds):
    """
    Determines the name of the coordinate in the dataset that can serve as a time label.

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset containing coordinates to check for a time label.

    Returns
    -------
    str or None
        The name of the coordinate that is a datetime type and can serve as a time label,
        or None if no such coordinate is found.

    Example
    -------
    >>> import xarray as xr
    >>> import pandas as pd
    >>> import numpy as np
    >>> ds = xr.Dataset({'time': ('time', pd.date_range('2000-01-01', periods=10))})
    >>> get_time_label(ds)
    'time'
    >>> ds = xr.DataArray(np.ones(10), coords={'T': ('T', pd.date_range('2000-01-01', periods=10))})
    >>> get_time_label(ds)
    'T'
    >>> # The following does have a valid time coordinate, expected to return None
    >>> da = xr.Dataset({'time': ('time', [1,2,3,4,5])})
    >>> get_time_label(da) is None
    True
    """
    label = deque()
    for name, coord in ds.coords.items():
        if not is_datetime_type(coord):
            continue
        if not coord.dims:
            continue
        if name in coord.dims:
            label.appendleft(name)
        else:
            label.append(name)
    label.append(None)
    return label.popleft()


def has_time_axis(ds) -> bool:
    """
    Checks if the given dataset has a time axis.

    Parameters
    ----------
    ds : xarray.Dataset or xarray.DataArray
        The dataset to check.

    Returns
    -------
    bool
        True if the dataset has a time axis, False otherwise.
    """
    return bool(get_time_label(ds))


def needs_resampling(ds, timespan):
    """
    Checks if a given dataset needs resampling based on its time axis.

    Parameters
    ----------
    ds : xr.Dataset or xr.DataArray
        The dataset to check.
    timespan : str
        The time span for which the dataset is to be resampled.
        10YS, 1YS, 6MS, etc.

    Returns
    -------
    bool
        True if the dataset needs resampling, False otherwise.

    Notes:
    ------
    After time-averaging step, this function aids in determining if
    splitting into multiple files is required based on provided
    timespan.
    """
    if (timespan is None) or (not timespan):
        return False
    time_label = get_time_label(ds)
    if time_label is None:
        return False
    if is_scalar(ds[time_label]):
        return False
    # string representation is need to deal with cftime
    start = pd.Timestamp(str(ds[time_label].data[0]))
    end = pd.Timestamp(str(ds[time_label].data[-1]))
    offset = pd.tseries.frequencies.to_offset(timespan)
    return (start + offset) < end


def freq_is_coarser_than_data(
    freq: str,
    ds: xr.Dataset,
    ref_time: pd.Timestamp = pd.Timestamp("1970-01-01"),
) -> bool:
    """
    Checks if the frequency is coarser than the time frequency of the xarray Dataset.

    Parameters
    ----------
    freq : str
        The frequency to compare (e.g. 'M', 'D', '6H').
    ds : xr.Dataset
        The dataset containing a time coordinate.
    ref_time : pd.Timestamp, optional
        Reference timestamp used to convert frequency to a time delta. Defaults to the beginning of
        the Unix Epoch.


    Returns
    -------
    bool
        True if `freq` is coarser (covers a longer duration) than the dataset's frequency.
    """
    time_label = get_time_label(ds)
    if time_label is None:
        raise ValueError("The dataset does not contain a valid time coordinate.")
    time_index = ds.indexes[time_label]

    data_freq = pd.infer_freq(time_index)
    if data_freq is None:
        raise ValueError(
            "Could not infer frequency from the dataset's time coordinate."
        )

    delta1 = (ref_time + pd.tseries.frequencies.to_offset(freq)) - ref_time
    delta2 = (ref_time + pd.tseries.frequencies.to_offset(data_freq)) - ref_time

    return delta1 > delta2

# Result object for frequency inference with metadata
FrequencyResult = namedtuple(
    "FrequencyResult",
    [
        "frequency",  # str or None: inferred frequency string (e.g., 'M', '2D')
        "delta_days",  # float or None: median time delta in days
        "step",  # int or None: step multiplier for the frequency
        "is_exact",  # bool: whether the time series has exact regular spacing
        "status",  # str: status message ('valid', 'irregular', 'no_match', etc.)
    ],
)


# Core frequency inference
def infer_frequency_core(
    times, tol=0.05, return_metadata=False, strict=False, calendar="standard", log=False
):
    """
    Infer time frequency from datetime-like array, returning pandas-style frequency strings.

    Parameters
    ----------
    times : array-like
        List of datetime-like objects (cftime or datetime64).
    tol : float, optional
        Tolerance for delta comparisons (in days). Defaults to 0.05.
    return_metadata : bool, optional
        If True, returns (frequency, median_delta, step, is_exact, status) instead of just the frequency string.
        Defaults to False.
    strict : bool, optional
        If True, performs additional checks for irregular time series and returns a status message.
        Defaults to False.
    calendar : str, optional
        Calendar type to use for cftime objects. Defaults to "standard".
    log : bool, optional
        If True, logs the results of the frequency check. Defaults to False.

    Returns
    -------
    str or FrequencyResult
        Inferred frequency string (e.g., 'M') or (freq, delta, step, is_exact, status) if return_metadata=True.
    """
    if len(times) < 2:
        if log:
            log_frequency_check(
                "Time Series", None, None, None, False, "too_short", strict
            )
        return (
            FrequencyResult(None, None, None, False, "too_short")
            if return_metadata
            else None
        )

    # Handle both pandas-like objects (with .values) and plain lists/arrays
    try:
        times_values = times.values if hasattr(times, "values") else times

        # Handle both datetime-like objects and numeric timestamps
        if hasattr(times_values[0], "toordinal"):
            # For cftime objects, use a different approach for ordinal calculation
            if hasattr(times_values[0], "calendar"):
                # cftime objects - convert to days since a reference date
                ref_date = times_values[0]
                ordinals = np.array(
                    [
                        (t - ref_date).days
                        + (t.hour / 24 + t.minute / 1440 + t.second / 86400)
                        for t in times_values
                    ]
                )
                # Adjust to make ordinals absolute (add reference ordinal)
                try:
                    ref_ordinal = ref_date.toordinal()
                    ordinals = ordinals + ref_ordinal
                except (AttributeError, ValueError):
                    # If toordinal fails, use a simpler approach
                    ordinals = np.array(
                        [
                            t.year * 365.25
                            + t.month * 30.4375
                            + t.day
                            + t.hour / 24
                            + t.minute / 1440
                            + t.second / 86400
                            for t in times_values
                        ]
                    )
            else:
                # Standard datetime objects
                ordinals = np.array(
                    [
                        t.toordinal() + t.hour / 24 + t.minute / 1440 + t.second / 86400
                        for t in times_values
                    ]
                )
        else:
            # Assume numeric timestamps (e.g., numpy.datetime64)
            ordinals = np.array(
                [pd.Timestamp(t).to_julian_date() for t in times_values]
            )

    except (AttributeError, TypeError, ValueError) as e:
        error_status = f"invalid_input: {str(e)}"
        if log:
            log_frequency_check(
                "Time Series", None, None, None, False, error_status, strict
            )
        if return_metadata:
            return FrequencyResult(None, None, None, False, error_status)
        return None
    deltas = np.diff(ordinals)
    median_delta = np.median(deltas)
    std_delta = np.std(deltas)

    year_days = {
        "standard": 365.25,
        "gregorian": 365.25,
        "noleap": 365.0,
        "360_day": 360.0,
    }.get(calendar, 365.25)

    base_freqs = {
        "H": 1 / 24,
        "D": 1,
        "W": 7,
        "M": year_days / 12,
        "Q": year_days / 4,
        "A": year_days,
        "10A": year_days * 10,
    }

    matched_freq = None
    matched_step = None
    for freq, base_days in base_freqs.items():
        for step in range(1, 13):
            test_delta = base_days * step
            if abs(median_delta - test_delta) <= tol * test_delta:
                matched_freq = freq
                matched_step = step
                break
        if matched_freq:
            break

    if matched_freq is None:
        # For irregular time series, try to find the closest match with relaxed tolerance
        relaxed_tol = 0.5  # Much more relaxed tolerance for irregular data
        for freq, base_days in base_freqs.items():
            for step in range(1, 13):
                test_delta = base_days * step
                if abs(median_delta - test_delta) <= relaxed_tol * test_delta:
                    matched_freq = freq
                    matched_step = step
                    break
            if matched_freq:
                break

        if matched_freq is None:
            if log:
                log_frequency_check(
                    "Time Series", None, median_delta, None, False, "no_match", strict
                )
            return (
                FrequencyResult(None, median_delta, None, False, "no_match")
                if return_metadata
                else None
            )

    is_exact = std_delta < tol * (base_freqs[matched_freq] * matched_step)
    status = "valid" if is_exact else "irregular"

    if strict:
        expected_steps = (ordinals[-1] - ordinals[0]) / (
            base_freqs[matched_freq] * matched_step
        )
        actual_steps = len(times) - 1
        if not np.all(np.abs(deltas - median_delta) <= tol * median_delta):
            status = "irregular"
            is_exact = False  # Fix: Update is_exact to be consistent
        if abs(expected_steps - actual_steps) >= 1:
            status = "missing_steps"
            is_exact = False  # Fix: Update is_exact to be consistent

    freq_str = f"{matched_step}{matched_freq}" if matched_step > 1 else matched_freq

    # Log the results if requested
    if log:
        log_frequency_check(
            "Time Series",
            freq_str,
            median_delta,
            matched_step,
            is_exact,
            status,
            strict,
        )

    return (
        FrequencyResult(freq_str, median_delta, matched_step, is_exact, status)
        if return_metadata
        else freq_str
    )


# xarray fallback
def infer_frequency(
    times, return_metadata=False, strict=False, calendar="standard", log=False
):
    """
    Infer time frequency from datetime-like array, returning pandas-style frequency strings.

    Parameters
    ----------
    times : array-like
        List of datetime-like objects (cftime or datetime64).
    return_metadata : bool, optional
        If True, returns (frequency, median_delta, step, is_exact, status) instead of just the frequency string.
        Defaults to False.
    strict : bool, optional
        If True, performs additional checks for irregular time series and returns a status message.
        Defaults to False.
    calendar : str, optional
        Calendar type to use for cftime objects. Defaults to "standard".
    log : bool, optional
        If True, logs the results of the frequency check. Defaults to False.

    Returns
    -------
    str or FrequencyResult
        Inferred frequency string (e.g., 'M') or (freq, delta, step, is_exact, status) if return_metadata=True.
    """
    try:
        freq = xr.infer_freq(times)
        if freq is not None:
            if log:
                log_frequency_check("Time Series", freq, None, 1, True, "valid", strict)
            return (
                FrequencyResult(freq, None, 1, True, "valid")
                if return_metadata
                else freq
            )
    except Exception:
        pass
    return infer_frequency_core(
        times,
        return_metadata=return_metadata,
        strict=strict,
        calendar=calendar,
        log=log,
    )


# Logger
def log_frequency_check(name, freq, delta, step, exact, status, strict=False):
    """
    Log the results of the frequency check.
    """
    print(f"[Freq Check] {name}")
    print(f"  → Inferred Frequency : {freq or 'None'}")
    print(f"  → Step Multiple      : {step or 'None'}")

    # Handle None delta values safely
    if delta is not None:
        print(f"  → Median Δ (days)    : {delta:.2f}")
    else:
        print("  → Median Δ (days)    : None")

    print(f"  → Regular Spacing    : {'✅' if exact else '❌'}")
    print(f"  → Strict Mode        : {'✅' if strict else '❌'}")
    print(f"  → Status             : {status}")
    print("-" * 40)
