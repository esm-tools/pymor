"""pycmor - Makes CMOR Simple"""

from . import _version

# Import accessors to trigger xarray registration
# This makes ds.pycmor.coords and ds.pycmor.dims available
from .xarray import accessor  # noqa: F401

__author__ = "Paul Gierz <pgierz@awi.de>"
__all__ = []

__version__ = _version.get_versions()["version"]
