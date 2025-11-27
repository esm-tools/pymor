#!/usr/bin/env python
"""Discover registered model runs from entry points for GitHub Actions matrix.

This script outputs a JSON array of model names that can be used in a GitHub
Actions matrix strategy.
"""

import json
import sys

# Add src to path so we can import without installing
sys.path.insert(0, "src")

from tests.utils.entry_points import discover_model_runs  # noqa: E402


def main():
    """Discover models and output as JSON for GitHub Actions matrix."""
    try:
        models = discover_model_runs()
        model_names = sorted(models.keys())

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
