"""Utilities for working with entry points in tests."""

import importlib.metadata
from typing import Type

from tests.fixtures.base_model_run import BaseModelRun


def discover_model_runs() -> dict[str, Type[BaseModelRun]]:
    """Discover all registered model run classes from entry points.

    Returns
    -------
    dict[str, Type[BaseModelRun]]
        Dictionary mapping model names to their ModelRun classes
    """
    model_runs = {}

    # Python 3.9 vs 3.10+ compatibility
    # In 3.9: entry_points() returns dict[str, list[EntryPoint]]
    # In 3.10+: entry_points() returns EntryPoints object with select() method
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


def get_model_run_class(model_name: str) -> Type[BaseModelRun]:
    """Get a specific model run class by name.

    Parameters
    ----------
    model_name : str
        Name of the model run (entry point name)

    Returns
    -------
    Type[BaseModelRun]
        The model run class

    Raises
    ------
    KeyError
        If the model name is not found in registered entry points
    """
    model_runs = discover_model_runs()
    if model_name not in model_runs:
        available = ", ".join(model_runs.keys())
        raise KeyError(f"Model '{model_name}' not found. Available models: {available}")
    return model_runs[model_name]
