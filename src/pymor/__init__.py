"""pymor - Makes CMOR Simple"""

from . import _version

# Import module that registers all xarray accessors
from . import accessors  # noqa: F401

__author__ = "Paul Gierz <pgierz@awi.de>"
__all__ = []

__version__ = _version.get_versions()["version"]
