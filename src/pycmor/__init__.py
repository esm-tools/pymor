"""pycmor - Makes CMOR Simple"""

from . import _version

# Import unified accessor to trigger xarray registration
# This makes ds.pycmor.coords, ds.pycmor.dims, and time frequency methods available
from .xarray import accessor  # noqa: F401

__author__ = "Paul Gierz <pgierz@awi.de>"
__all__ = []

__version__ = _version.get_versions()["version"]
