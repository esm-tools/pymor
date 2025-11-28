"""Base class for model-specific test run fixtures.

This module provides a base class that standardizes the interface for
model-contributed test fixtures. Each model can inherit from this base
class and implement model-specific logic for:
- Downloading/extracting real data
- Generating stub data
- Accessing mesh files (if applicable)
- Opening datasets with xarray

The base class handles:
- Registry and manifest path resolution via properties
- Cache directory management
- Routing between real and stub data based on environment/markers
- Lazy-loading of data directories, mesh directories, and datasets
- Common fixture patterns
"""

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseModelRun(ABC):
    """Base class for model-specific test run fixtures.

    This class provides a standard interface for handling test data
    across different climate model runs. Subclasses should implement
    model-specific logic for fetching, generating, and opening data.

    A model run represents a specific execution of a climate model with
    associated data files, mesh files, and configuration.

    Parameters
    ----------
    model_name : str
        Name of the model (e.g., 'fesom_uxarray', 'awicm_recom')
    fixtures_dir : Path
        Path to the model's fixtures directory
    use_real : bool, optional
        Whether to use real or stub data (default: False)
    tmp_path_factory : pytest.TempPathFactory, optional
        Pytest fixture for creating temporary directories (required for stub data)

    Attributes
    ----------
    model_name : str
        Name of the model
    fixtures_dir : Path
        Path to the fixtures directory
    use_real : bool
        Whether to use real or stub data
    tmp_path_factory : pytest.TempPathFactory
        Pytest fixture for creating temporary directories
    """

    def __init__(
        self,
        model_name: str,
        fixtures_dir: Path,
        use_real: bool = False,
        tmp_path_factory=None,
    ):
        self.model_name = model_name
        self.fixtures_dir = Path(fixtures_dir)
        self.use_real = use_real
        self.tmp_path_factory = tmp_path_factory
        # Lazy-loaded cached values
        self._datadir = None
        self._meshdir = None
        self._ds = None

    @classmethod
    def from_module(cls, module_path: str, use_real: bool = False, tmp_path_factory=None):
        """Create instance from a module's __file__ path.

        Parameters
        ----------
        module_path : str
            The __file__ attribute of the calling module
        use_real : bool, optional
            Whether to use real or stub data
        tmp_path_factory : pytest.TempPathFactory, optional
            Pytest fixture for creating temporary directories

        Returns
        -------
        BaseModelRun
            Instance configured for the calling module's model
        """
        fixtures_dir = Path(module_path).parent
        model_name = fixtures_dir.parent.name
        return cls(
            model_name=model_name,
            fixtures_dir=fixtures_dir,
            use_real=use_real,
            tmp_path_factory=tmp_path_factory,
        )

    @property
    def registry_path(self) -> Path:
        """Path to the pooch registry YAML file."""
        return self.fixtures_dir / "registry.yaml"

    @property
    def stub_manifest_path(self) -> Path:
        """Path to the stub data manifest YAML file."""
        return self.fixtures_dir / "stub_manifest.yaml"

    @property
    def cache_dir(self) -> Path:
        """Get the persistent cache directory for test data.

        Returns
        -------
        Path
            Cache directory path (usually ~/.cache/pycmor/test_data)
        """
        # Default cache directory
        cache_home = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
        cache_dir = Path(cache_home) / "pycmor" / "tutorial_data"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    @property
    def config_path_cmip6(self) -> Path:
        """Path to the CMIP6 configuration file for this model.

        Returns
        -------
        Path
            Path to config_cmip6.yaml in the model's fixtures directory
        """
        return self.fixtures_dir / "config_cmip6.yaml"

    @property
    def config_path_cmip7(self) -> Path:
        """Path to the CMIP7 configuration file for this model.

        Returns
        -------
        Path
            Path to config_cmip7.yaml in the model's fixtures directory
        """
        return self.fixtures_dir / "config_cmip7.yaml"

    @staticmethod
    def should_use_real_data(request=None) -> bool:
        """Determine whether to use real or stub data.

        Checks:
        1. PYCMOR_USE_REAL_TEST_DATA environment variable
        2. pytest 'real_data' marker (if request provided)

        Parameters
        ----------
        request : pytest.FixtureRequest, optional
            Pytest request object for checking markers

        Returns
        -------
        bool
            True if real data should be used, False for stub data
        """
        # Check environment variable
        use_real = os.getenv("PYCMOR_USE_REAL_TEST_DATA", "").lower() in ("1", "true", "yes")

        # Check pytest marker
        if request is not None and hasattr(request, "node"):
            if request.node.get_closest_marker("real_data"):
                use_real = True

        return use_real

    # Properties for lazy-loaded resources

    @property
    def datadir(self) -> Path:
        """Lazy-loaded data directory (real or stub).

        Returns
        -------
        Path
            Path to the data directory
        """
        if self._datadir is None:
            if self.use_real:
                logger.info(f"Using real data for {self.model_name}")
                self._datadir = self.fetch_real_datadir()
            else:
                logger.info(f"Using stub data for {self.model_name}")
                if self.tmp_path_factory is None:
                    raise ValueError("tmp_path_factory required for stub data generation")
                stub_dir = self.tmp_path_factory.mktemp(f"{self.model_name}_stub_data")
                self._datadir = self.generate_stub_datadir(stub_dir)
        return self._datadir

    @property
    def meshdir(self) -> Path:
        """Lazy-loaded mesh directory (real or stub).

        Returns
        -------
        Path
            Path to the mesh directory

        Raises
        ------
        NotImplementedError
            If the model does not implement mesh handling
        """
        if self._meshdir is None:
            if self.use_real:
                logger.info(f"Using real mesh for {self.model_name}")
                self._meshdir = self.fetch_real_meshdir()
            else:
                logger.info(f"Using stub mesh for {self.model_name}")
                if self.tmp_path_factory is None:
                    raise ValueError("tmp_path_factory required for stub mesh generation")
                stub_dir = self.tmp_path_factory.mktemp(f"{self.model_name}_stub_mesh")
                self._meshdir = self.generate_stub_meshdir(stub_dir)
        return self._meshdir

    @property
    def ds(self):
        """Lazy-loaded xarray dataset.

        Returns
        -------
        xr.Dataset
            Opened dataset from the data directory
        """
        if self._ds is None:
            self._ds = self.open_mfdataset()
        return self._ds

    # Abstract methods for data handling

    @abstractmethod
    def fetch_real_datadir(self) -> Path:
        """Download and extract real data using pooch.

        Returns
        -------
        Path
            Path to the extracted data directory
        """
        pass

    @abstractmethod
    def generate_stub_datadir(self, stub_dir: Path) -> Path:
        """Generate stub data from YAML manifest.

        Parameters
        ----------
        stub_dir : Path
            Temporary directory for stub data

        Returns
        -------
        Path
            Path to the stub data directory
        """
        pass

    @abstractmethod
    def open_mfdataset(self, **kwargs):
        """Open xarray dataset from data directory.

        Subclasses should implement this method to define specific
        file patterns and dataset opening logic.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments for xr.open_mfdataset

        Returns
        -------
        xr.Dataset
            Opened dataset
        """
        pass

    # Optional methods for mesh handling (override if model has mesh files)

    def fetch_real_meshdir(self) -> Path:
        """Download or clone real mesh files.

        Override this method if the model requires separate mesh files.
        Default implementation raises NotImplementedError.

        Returns
        -------
        Path
            Path to the mesh directory

        Raises
        ------
        NotImplementedError
            If the model does not implement mesh fetching
        """
        raise NotImplementedError(f"Model {self.model_name} does not implement mesh fetching")

    def generate_stub_meshdir(self, stub_dir: Path) -> Path:
        """Generate stub mesh files.

        Override this method if the model requires separate mesh files.
        Default implementation raises NotImplementedError.

        Parameters
        ----------
        stub_dir : Path
            Temporary directory for stub mesh

        Returns
        -------
        Path
            Path to the stub mesh directory

        Raises
        ------
        NotImplementedError
            If the model does not implement stub mesh generation
        """
        raise NotImplementedError(f"Model {self.model_name} does not implement stub mesh generation")
