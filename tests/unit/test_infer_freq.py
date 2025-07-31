import cftime
import numpy as np
import pytest
import xarray as xr

from pymor.core.infer_freq import infer_frequency, is_resolution_fine_enough


@pytest.fixture
def regular_monthly_time():
    return [cftime.Datetime360Day(2000, m, 15) for m in range(1, 5)]


@pytest.fixture
def irregular_time():
    return [
        cftime.Datetime360Day(2000, 1, 1),
        cftime.Datetime360Day(2000, 1, 20),
        cftime.Datetime360Day(2000, 2, 15),
        cftime.Datetime360Day(2000, 3, 10),
    ]


@pytest.fixture
def short_time():
    return [cftime.Datetime360Day(2000, 1, 1)]


def test_infer_monthly_frequency(regular_monthly_time):
    freq = infer_frequency(regular_monthly_time)
    assert freq == "M"


def test_infer_irregular_time(irregular_time):
    freq, delta, _, exact, status = infer_frequency(
        irregular_time, return_metadata=True
    )
    assert freq is not None
    assert not exact
    assert status in ("irregular", "missing_steps")


def test_short_time_series(short_time):
    freq = infer_frequency(short_time)
    assert freq is None


def test_resolution_check_finer_than_month(regular_monthly_time):
    result = is_resolution_fine_enough(
        regular_monthly_time, target_approx_interval=30.5, calendar="360_day"
    )
    assert result["comparison_status"] == "finer"
    assert result["is_valid_for_resampling"]


def test_resolution_check_equal_to_month(regular_monthly_time):
    result = is_resolution_fine_enough(
        regular_monthly_time, target_approx_interval=30.0, calendar="360_day"
    )
    assert result["comparison_status"] in ("equal", "finer")
    assert result["is_valid_for_resampling"]


def test_resolution_check_too_sparse():
    times = [
        cftime.Datetime360Day(2000, 1, 1),
        cftime.Datetime360Day(2000, 4, 1),
        cftime.Datetime360Day(2000, 7, 1),
    ]
    result = is_resolution_fine_enough(
        times, target_approx_interval=30.4375, calendar="360_day"
    )
    assert result["comparison_status"] == "coarser"
    assert not result["is_valid_for_resampling"]


def test_accessor_on_dataarray(regular_monthly_time):
    da = xr.DataArray([1, 2, 3, 4], coords={"time": regular_monthly_time}, dims="time")
    info = da.timefreq.infer_frequency(log=False)
    assert info["frequency"] == "M"


def test_accessor_on_dataset(regular_monthly_time):
    da = xr.DataArray([1, 2, 3, 4], coords={"time": regular_monthly_time}, dims="time")
    ds = xr.Dataset({"tas": da})
    info = ds.timefreq.infer_frequency(log=False)
    assert info["frequency"] == "M"


def test_strict_mode_detection():
    # Intentionally skip one time step
    times = [cftime.Datetime360Day(2000, m, 15) for m in (1, 2, 4, 5)]
    result = is_resolution_fine_enough(
        times, target_approx_interval=30.0, calendar="360_day", strict=True
    )
    assert result["comparison_status"] == "missing_steps"
    assert not result["is_valid_for_resampling"]


def test_dataarray_resample_safe_pass(regular_monthly_time):
    da = xr.DataArray([1, 2, 3, 4], coords={"time": regular_monthly_time}, dims="time")

    # Should pass and return resampled array
    resampled = da.timefreq.resample_safe(
        freq_str="M", target_approx_interval=30.4375, calendar="360_day"
    )

    assert isinstance(resampled, xr.DataArray)
    assert "time" in resampled.dims


def test_dataset_resample_safe_pass(regular_monthly_time):
    da = xr.DataArray([1, 2, 3, 4], coords={"time": regular_monthly_time}, dims="time")
    ds = xr.Dataset({"pr": da})

    # Should pass and return resampled dataset
    resampled_ds = ds.timefreq.resample_safe(
        freq_str="M", target_approx_interval=30.4375, calendar="360_day"
    )

    assert isinstance(resampled_ds, xr.Dataset)
    assert "time" in resampled_ds.dims
    assert "pr" in resampled_ds.data_vars


def test_resample_safe_fails_on_coarse_resolution():
    # Coarser than monthly (e.g. quarterly)
    times = [
        cftime.Datetime360Day(2000, 1, 1),
        cftime.Datetime360Day(2000, 4, 1),
        cftime.Datetime360Day(2000, 7, 1),
    ]
    da = xr.DataArray([1, 2, 3], coords={"time": times}, dims="time")

    with pytest.raises(ValueError, match="time resolution too coarse"):
        da.timefreq.resample_safe(
            freq_str="M", target_approx_interval=30.4375, calendar="360_day"
        )


def test_resample_safe_with_mean(regular_monthly_time):
    da = xr.DataArray(
        [1.0, 2.0, 3.0, 4.0], coords={"time": regular_monthly_time}, dims="time"
    )

    # Should apply 'mean' over each monthly bin
    resampled = da.timefreq.resample_safe(
        freq_str="M", target_approx_interval=30.0, calendar="360_day", method="mean"
    )

    assert np.allclose(resampled.values, [1.0, 2.0, 3.0, 4.0])


def test_missing_steps_daily_gaps():
    """Test missing_steps detection for daily time series with gaps."""
    # Daily series with missing days 4, 5, 6
    times_with_gaps = [
        cftime.Datetime360Day(2000, 1, 1),  # Day 1
        cftime.Datetime360Day(2000, 1, 2),  # Day 2
        cftime.Datetime360Day(2000, 1, 3),  # Day 3
        # Missing days 4, 5, 6 (3-day gap!)
        cftime.Datetime360Day(2000, 1, 7),  # Day 7
        cftime.Datetime360Day(2000, 1, 8),  # Day 8
    ]

    result = infer_frequency(
        times_with_gaps, return_metadata=True, strict=True, calendar="360_day"
    )

    assert result.frequency == "D"
    assert result.status == "missing_steps"
    assert not result.is_exact
    assert result.step == 1


def test_missing_steps_weekly_gaps():
    """Test missing_steps detection for weekly time series with gaps."""
    # Weekly series with missing week 3
    times_weekly_gaps = [
        cftime.Datetime360Day(2000, 1, 1),  # Week 1
        cftime.Datetime360Day(2000, 1, 8),  # Week 2
        # Missing week 3 (Jan 15)
        cftime.Datetime360Day(2000, 1, 22),  # Week 4
        cftime.Datetime360Day(2000, 1, 29),  # Week 5
    ]

    result = infer_frequency(
        times_weekly_gaps, return_metadata=True, strict=True, calendar="360_day"
    )

    assert result.frequency == "7D"
    assert result.status == "missing_steps"
    assert not result.is_exact
    assert result.step == 7


def test_missing_steps_vs_irregular():
    """Test difference between missing_steps and irregular status."""
    # Irregular: varying intervals but no clear pattern
    times_irregular = [
        cftime.Datetime360Day(2000, 1, 1),
        cftime.Datetime360Day(2000, 1, 20),  # 19 days
        cftime.Datetime360Day(2000, 2, 15),  # 26 days
        cftime.Datetime360Day(2000, 3, 10),  # 24 days
    ]

    result_irregular = infer_frequency(
        times_irregular, return_metadata=True, strict=True, calendar="360_day"
    )

    # Should be irregular, not missing_steps
    assert result_irregular.status == "irregular"
    assert not result_irregular.is_exact

    # Missing steps: clear daily pattern with gaps
    times_missing = [
        cftime.Datetime360Day(2000, 1, 1),  # Day 1
        cftime.Datetime360Day(2000, 1, 2),  # Day 2
        cftime.Datetime360Day(2000, 1, 5),  # Day 5 (missing 3,4)
        cftime.Datetime360Day(2000, 1, 6),  # Day 6
    ]

    result_missing = infer_frequency(
        times_missing, return_metadata=True, strict=True, calendar="360_day"
    )

    # Should be missing_steps
    assert result_missing.status == "missing_steps"
    assert result_missing.frequency == "D"


def test_missing_steps_requires_strict_mode():
    """Test that missing_steps detection requires strict=True."""
    times_with_gaps = [
        cftime.Datetime360Day(2000, 1, 1),
        cftime.Datetime360Day(2000, 1, 2),
        cftime.Datetime360Day(2000, 1, 5),  # Gap: missing days 3,4
        cftime.Datetime360Day(2000, 1, 6),
    ]

    # Without strict mode: should be "irregular"
    result_non_strict = infer_frequency(
        times_with_gaps, return_metadata=True, strict=False, calendar="360_day"
    )

    assert result_non_strict.status == "irregular"

    # With strict mode: should be "missing_steps"
    result_strict = infer_frequency(
        times_with_gaps, return_metadata=True, strict=True, calendar="360_day"
    )

    assert result_strict.status == "missing_steps"


def test_consistent_is_exact_and_status():
    """Test that is_exact and status are consistent when strict=True detects irregularities."""
    # Time series with small offsets that pass std_delta test but fail strict individual delta test
    import numpy as np

    times_with_offsets = np.array(
        [
            "3007-02-01T00:00:00",  # Feb 1
            "3007-03-01T00:00:00",  # Mar 1 (28 days)
            "3007-04-02T00:00:00",  # Apr 2 (32 days) <- 1-day offset
            "3007-05-01T00:00:00",  # May 1 (29 days)
            "3007-06-01T00:00:00",  # Jun 1 (31 days)
            "3007-07-02T00:00:00",  # Jul 2 (31 days) <- 1-day offset
            "3007-08-01T00:00:00",  # Aug 1 (30 days)
        ],
        dtype="datetime64[s]",
    )

    # With strict=True: should detect irregularity and set is_exact=False
    result_strict = infer_frequency(
        times_with_offsets, return_metadata=True, strict=True
    )

    # Both status and is_exact should indicate irregularity
    assert result_strict.status == "irregular"
    assert not result_strict.is_exact  # Should be consistent with status
    assert result_strict.frequency == "M"

    # With strict=False: should be valid (less strict tolerance)
    result_non_strict = infer_frequency(
        times_with_offsets, return_metadata=True, strict=False
    )

    # Should be valid with non-strict mode
    assert result_non_strict.status == "valid"
    assert result_non_strict.is_exact
    assert result_non_strict.frequency == "M"
