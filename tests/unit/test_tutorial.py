"""Tests for pycmor.tutorial module."""

import pytest


def test_tutorial_available_datasets():
    """Test that tutorial datasets can be discovered."""
    import pycmor.tutorial as tutorial

    datasets = tutorial.available_datasets()
    assert isinstance(datasets, list)
    assert len(datasets) > 0
    # Should have at least the built-in datasets
    assert "fesom_2p6" in datasets
    assert "awicm_recom" in datasets
    assert "fesom_dev" in datasets


def test_tutorial_info():
    """Test that tutorial.info returns dataset information."""
    import pycmor.tutorial as tutorial

    info_text = tutorial.info("fesom_2p6")
    assert isinstance(info_text, str)
    assert len(info_text) > 0


def test_tutorial_info_invalid_dataset():
    """Test that tutorial.info raises KeyError for invalid dataset."""
    import pycmor.tutorial as tutorial

    with pytest.raises(KeyError, match="Dataset 'invalid' not found"):
        tutorial.info("invalid")


def test_tutorial_open_dataset_stub(tmp_path_factory):
    """Test opening a tutorial dataset with stub data."""
    import pycmor.tutorial as tutorial

    ds = tutorial.open_dataset("fesom_2p6", use_real=False)
    assert ds is not None
    # Should be an xarray Dataset
    import xarray as xr

    assert isinstance(ds, xr.Dataset)


@pytest.mark.real_data
def test_tutorial_open_dataset_real():
    """Test opening a tutorial dataset with real data.

    This test requires internet connection and will download data.
    Only runs when marked with real_data marker.
    """
    import pycmor.tutorial as tutorial

    ds = tutorial.open_dataset("fesom_2p6", use_real=True)
    assert ds is not None
    import xarray as xr

    assert isinstance(ds, xr.Dataset)


def test_tutorial_open_dataset_invalid():
    """Test that open_dataset raises KeyError for invalid dataset."""
    import pycmor.tutorial as tutorial

    with pytest.raises(KeyError, match="Dataset 'invalid' not found"):
        tutorial.open_dataset("invalid")


def test_tutorial_open_dataset_with_kwargs():
    """Test that open_dataset passes kwargs to xarray."""
    import pycmor.tutorial as tutorial

    # Pass chunks argument to xarray
    ds = tutorial.open_dataset("fesom_2p6", use_real=False, chunks={"time": 1})
    assert ds is not None
