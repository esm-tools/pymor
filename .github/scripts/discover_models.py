#!/usr/bin/env python
"""Discover registered model runs from entry points for GitHub Actions matrix.

This script outputs a JSON array of model names that can be used in a GitHub
Actions matrix strategy.

This script only reads entry point names without loading the classes, so it
doesn't require test dependencies to be installed.
"""

import importlib.metadata
import json
import sys


def discover_model_names():
    """Discover registered model run names from entry points.

    Returns just the entry point names without loading the actual classes,
    so this works even without test dependencies installed.
    """
    # Python 3.9 vs 3.10+ compatibility
    try:
        # Try Python 3.10+ API first
        eps = importlib.metadata.entry_points(group="pycmor.fixtures.model_runs")
    except TypeError:
        # Fall back to Python 3.9 API
        all_eps = importlib.metadata.entry_points()
        eps = all_eps.get("pycmor.fixtures.model_runs", [])

    # Just get the names, don't load the classes
    model_names = [ep.name for ep in eps]

    return model_names


def main():
    """Discover models and output as JSON for GitHub Actions matrix."""
    try:
        model_names = discover_model_names()
        model_names = sorted(model_names)

        # Output as JSON array for GitHub Actions matrix
        print(json.dumps(model_names))

        # Also print human-readable for debugging
        print(f"# Discovered {len(model_names)} models: {', '.join(model_names)}", file=sys.stderr)

        return 0
    except Exception as e:
        print(f"# Error discovering models: {e}", file=sys.stderr)
        # Return empty array on error so workflow doesn't fail
        print("[]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
