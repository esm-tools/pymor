"""pycmor - Makes CMOR Simple"""

from . import _version

__author__ = "Paul Gierz <pgierz@awi.de>"
__all__ = ["enable_xarray_accessor"]

__version__ = _version.get_versions()["version"]

_accessor_registered = False


def enable_xarray_accessor(log_level="INFO"):
    """Enable the pycmor xarray accessor (ds.pycmor).

    This function lazily registers the pycmor accessor on xarray Dataset
    and DataArray objects. It is idempotent -- calling it multiple times
    has no additional effect.

    Parameters
    ----------
    log_level : str, optional
        Logging level for loguru (default: "INFO").
    """
    global _accessor_registered
    if _accessor_registered:
        return

    from .xarray.accessor import PycmorAccessor, PycmorDataArrayAccessor  # noqa: F401

    # Configure loguru with rich formatting
    try:
        from loguru import logger

        logger.enable("pycmor")
    except ImportError:
        pass

    _accessor_registered = True
