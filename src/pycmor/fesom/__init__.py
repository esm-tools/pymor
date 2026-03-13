# Lazy import to avoid loading dependencies at startup
def __getattr__(name):
    if name == "regrid_to_regular":
        from ..fesom_2p1.regridding import regrid_to_regular
        return regrid_to_regular
    raise AttributeError(f"module 'pycmor.fesom' has no attribute '{name}'")

__all__ = ["regrid_to_regular"]
