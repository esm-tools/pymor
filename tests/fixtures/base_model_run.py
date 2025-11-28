"""Base class for model-specific test run fixtures.

DEPRECATED: This module is kept for backward compatibility.
New code should import from pycmor.tutorial.base_model_run instead.
"""

# Re-export from new location for backward compatibility
from pycmor.tutorial.base_model_run import BaseModelRun  # noqa: F401

__all__ = ["BaseModelRun"]
