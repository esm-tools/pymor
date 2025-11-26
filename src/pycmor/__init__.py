"""pycmor - Makes CMOR Simple"""

# Import module that registers all xarray accessors
try:
    from .accessors import *  # noqa: F401, F403

    _XARRAY_ACCESSOR_AVAILABLE = True
except ImportError:
    _XARRAY_ACCESSOR_AVAILABLE = False
from . import _version

__author__ = "Paul Gierz <pgierz@awi.de>"
__all__ = []

__version__ = _version.get_versions()["version"]
