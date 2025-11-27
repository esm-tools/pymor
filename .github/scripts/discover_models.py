#!/usr/bin/env python
"""Discover registered model runs and orchestrator configs for GitHub Actions matrix.

This script outputs JSON for both models and orchestrator configurations that
can be used in a GitHub Actions matrix strategy.

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


def get_orchestrator_configs():
    """Get orchestrator configurations for the test matrix.

    Returns the standard orchestrator configurations used in integration tests.
    This is the single source of truth for orchestrator combinations.
    """
    return [
        {
            "id": "prefect-dask",
            "pipeline_workflow_orchestrator": "prefect",
            "enable_dask": "yes",
        },
        {
            "id": "native-dask",
            "pipeline_workflow_orchestrator": "native",
            "enable_dask": "yes",
        },
        {
            "id": "native-nodask",
            "pipeline_workflow_orchestrator": "native",
            "enable_dask": "no",
        },
    ]


def main():
    """Discover models and orchestrators, output as JSON for GitHub Actions matrix."""
    import argparse

    parser = argparse.ArgumentParser(description="Discover models and orchestrators for CI matrix")
    parser.add_argument(
        "--output",
        choices=["models", "orchestrators", "both"],
        default="models",
        help="What to output",
    )
    args = parser.parse_args()

    try:
        if args.output == "models":
            model_names = discover_model_names()
            model_names = sorted(model_names)
            print(json.dumps(model_names))
            print(
                f"# Discovered {len(model_names)} models: {', '.join(model_names)}",
                file=sys.stderr,
            )
        elif args.output == "orchestrators":
            orchestrators = get_orchestrator_configs()
            print(json.dumps(orchestrators))
            orchestrator_ids = [o["id"] for o in orchestrators]
            print(
                f"# Orchestrators: {', '.join(orchestrator_ids)}",
                file=sys.stderr,
            )
        elif args.output == "both":
            result = {
                "models": sorted(discover_model_names()),
                "orchestrators": get_orchestrator_configs(),
            }
            print(json.dumps(result))
            print(
                f"# Discovered {len(result['models'])} models and {len(result['orchestrators'])} orchestrator configs",
                file=sys.stderr,
            )

        return 0
    except Exception as e:
        print(f"# Error discovering CI matrix config: {e}", file=sys.stderr)
        # Return empty array/object on error so workflow doesn't fail
        if args.output == "both":
            print('{"models": [], "orchestrators": []}')
        else:
            print("[]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
