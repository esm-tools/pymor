"""FESOM dev model run implementation.

DEPRECATED: This module is kept for backward compatibility.
New code should import from pycmor.tutorial.datasets.fesom_dev instead.
"""

# Re-export from new location for backward compatibility
from pycmor.tutorial.datasets.fesom_dev import FesomDevModelRun  # noqa: F401

__all__ = ["FesomDevModelRun"]
