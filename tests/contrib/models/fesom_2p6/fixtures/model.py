"""FESOM 2.6 PI mesh model run implementation.

DEPRECATED: This module is kept for backward compatibility.
New code should import from pycmor.tutorial.datasets.fesom_2p6 instead.
"""

# Re-export from new location for backward compatibility
from pycmor.tutorial.datasets.fesom_2p6 import Fesom2p6ModelRun  # noqa: F401

__all__ = ["Fesom2p6ModelRun"]
