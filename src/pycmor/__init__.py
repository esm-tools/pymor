"""pycmor - Makes CMOR Simple"""

# Import module that registers all xarray accessors
try:

    from . import accessors  # noqa: F401

    _XARRAY_ACCESSOR_AVAILABLE = True
except ImportError:
    _XARRAY_ACCESSOR_AVAILABLE = False
from . import _version

__author__ = "Paul Gierz <pgierz@awi.de>"
__all__ = []

__version__ = _version.get_versions()["version"]
