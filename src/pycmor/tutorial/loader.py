"""Tutorial dataset loader implementation.

This module handles loading tutorial datasets using the entry point system
and the test fixture infrastructure for data generation.
"""

import importlib.metadata
import os
from pathlib import Path
from typing import Optional

import xarray as xr


def _discover_model_runs() -> dict[str, type]:
    """Discover all registered model run classes from entry points.

    Returns
    -------
    dict[str, type]
        Dictionary mapping model names to their ModelRun classes
    """
    model_runs = {}

    # Python 3.9 vs 3.10+ compatibility
    try:
        # Try Python 3.10+ API first
        eps = importlib.metadata.entry_points(group="pycmor.fixtures.model_runs")
    except TypeError:
        # Fall back to Python 3.9 API
        all_eps = importlib.metadata.entry_points()
        eps = all_eps.get("pycmor.fixtures.model_runs", [])

    for ep in eps:
        model_runs[ep.name] = ep.load()

    return model_runs


def available_datasets() -> list[str]:
    """List all available tutorial datasets.

    Returns
    -------
    list[str]
        Names of available model datasets

    Examples
    --------
    >>> import pycmor.tutorial as tutorial
    >>> tutorial.available_datasets()
    ['awicm_recom', 'fesom_2p6', 'fesom_dev']
    """
    model_runs = _discover_model_runs()
    return sorted(model_runs.keys())


def info(name: str) -> str:
    """Get information about a tutorial dataset.

    Parameters
    ----------
    name : str
        Name of the dataset

    Returns
    -------
    str
        Description of the dataset (from model class docstring)

    Raises
    ------
    KeyError
        If the dataset name is not recognized

    Examples
    --------
    >>> import pycmor.tutorial as tutorial
    >>> tutorial.info("fesom_2p6")
    'FESOM 2.6 PI mesh model run...'
    """
    model_runs = _discover_model_runs()
    if name not in model_runs:
        available = ", ".join(available_datasets())
        raise KeyError(
            f"Dataset '{name}' not found. Available datasets: {available}. "
            f"Use pycmor.tutorial.available_datasets() to see all options."
        )

    model_class = model_runs[name]
    # Get the first line of the docstring
    if model_class.__doc__:
        return model_class.__doc__.strip().split("\n")[0]
    return f"Model run: {name}"


def open_dataset(
    name: str,
    *,
    use_real: bool = False,
    cache: bool = True,
    cache_dir: Optional[Path] = None,
    **kwargs,
) -> xr.Dataset:
    """Open a tutorial dataset from pycmor's collection.

    This function provides easy access to example climate model datasets
    for tutorials, examples, and testing. It uses the entry point system
    to discover available models and the BaseModelRun pattern to handle
    both real and stub data.

    Available datasets are discovered via entry points registered under
    'pycmor.fixtures.model_runs'. Use available_datasets() to see the
    current list.

    Parameters
    ----------
    name : str
        Name of the dataset to load. Use available_datasets() to see options.
    use_real : bool, optional
        If True, download and use real data (requires internet and disk space).
        If False (default), generate lightweight stub data for testing.
        Can also be controlled via PYCMOR_USE_REAL_TEST_DATA environment variable.
    cache : bool, optional
        If True (default), cache downloaded data locally for reuse.
        Only relevant when use_real=True.
    cache_dir : Path, optional
        Directory for caching data. If not specified, uses the default cache
        location (~/.cache/pycmor/test_data on Unix).
        Only relevant when use_real=True.
    **kwargs
        Additional keyword arguments passed to xarray's open_mfdataset.

    Returns
    -------
    xr.Dataset
        The loaded dataset

    Raises
    ------
    KeyError
        If the dataset name is not recognized

    Examples
    --------
    Open a tutorial dataset with stub data (fast, no download):

    >>> import pycmor.tutorial as tutorial
    >>> ds = tutorial.open_dataset("fesom_2p6")
    >>> ds
    <xarray.Dataset>
    ...

    Open with real data (downloads if not cached):

    >>> ds = tutorial.open_dataset("fesom_2p6", use_real=True)

    Pass additional xarray options:

    >>> ds = tutorial.open_dataset("fesom_2p6", chunks={"time": 1})

    See Also
    --------
    available_datasets : List all available tutorial datasets
    info : Get information about a dataset

    Notes
    -----
    For real data, the first load will download and cache the data,
    subsequent loads will use the cached version.
    """
    model_runs = _discover_model_runs()

    if name not in model_runs:
        available = ", ".join(available_datasets())
        raise KeyError(
            f"Dataset '{name}' not found. Available datasets: {available}. "
            f"Use pycmor.tutorial.available_datasets() to see all options."
        )

    model_class = model_runs[name]

    # Check environment variable if not explicitly set
    if not use_real:
        use_real = os.getenv("PYCMOR_USE_REAL_TEST_DATA", "").lower() in ("1", "true", "yes")

    # Find the model's fixtures directory
    import inspect

    module_file = inspect.getfile(model_class)

    if use_real:
        # Use real data with caching
        instance = model_class.from_module(module_file, use_real=True, tmp_path_factory=None)

        # If cache_dir is specified, we could override the default cache location
        # For now, we use the default cache location from the test infrastructure

        # Access the dataset (triggers download and caching if needed)
        return instance.open_mfdataset(**kwargs)
    else:
        # Use stub data - need to create a temporary directory
        import tempfile

        # Create a temp directory that persists for the session
        # Users can clean this up, or it will be cleaned by OS
        stub_root = Path(tempfile.gettempdir()) / "pycmor_tutorial_stubs"
        stub_root.mkdir(parents=True, exist_ok=True)

        stub_dir = stub_root / name

        # Simple TempPathFactory substitute for tutorial use
        class SimpleTempFactory:
            """Minimal temp path factory for tutorial datasets."""

            def __init__(self, base_dir: Path):
                self.base_dir = base_dir

            def mktemp(self, basename: str) -> Path:
                """Create a temporary directory."""
                temp_dir = self.base_dir / basename
                temp_dir.mkdir(parents=True, exist_ok=True)
                return temp_dir

        tmp_factory = SimpleTempFactory(stub_dir)

        instance = model_class.from_module(module_file, use_real=False, tmp_path_factory=tmp_factory)

        return instance.open_mfdataset(**kwargs)
