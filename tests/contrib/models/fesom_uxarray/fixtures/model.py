"""FESOM UXarray (PI control) model run implementation."""

import logging
import shutil
import subprocess
from pathlib import Path

from tests.fixtures.base_model_run import BaseModelRun

logger = logging.getLogger(__name__)

MESH_GIT_REPO = "https://gitlab.awi.de/fesom/pi"
"""str : Git repository URL for the FESOM PI mesh data."""


class FesomUxarrayModelRun(BaseModelRun):
    """FESOM UXarray PI control model run.

    This model run includes:
    - PI control simulation data (via pooch download)
    - Mesh files (via git-lfs clone from GitLab)
    - UXarray-compatible dataset access
    """

    def fetch_real_datadir(self) -> Path:
        """Download and extract real FESOM UXarray PI control data using pooch.

        Returns
        -------
        Path
            Path to the extracted data directory
        """
        from tests.fixtures.example_data.data_fetcher import fetch_and_extract

        return fetch_and_extract("pi_uxarray.tar", registry_path=self.registry_path)

    def generate_stub_datadir(self, stub_dir: Path) -> Path:
        """Generate stub data for fesom_uxarray from YAML manifest.

        Parameters
        ----------
        stub_dir : Path
            Temporary directory for stub data

        Returns
        -------
        Path
            Path to the stub data directory
        """
        from tests.fixtures.stub_generator import generate_stub_files

        generate_stub_files(self.stub_manifest_path, stub_dir)
        return stub_dir

    def fetch_real_meshdir(self) -> Path:
        """Clone FESOM PI mesh from GitLab using git-lfs.

        Uses persistent cache in $HOME/.cache/pycmor instead of ephemeral /tmp.

        Returns
        -------
        Path
            Path to the cloned mesh repository
        """
        mesh_dir = self.cache_dir / "pi_mesh_git"

        if mesh_dir.exists() and (mesh_dir / ".git").exists():
            logger.info(f"Using cached git mesh repository: {mesh_dir}")
            return mesh_dir

        # Clone the repository with git-lfs
        logger.info(f"Cloning FESOM PI mesh from {MESH_GIT_REPO}...")
        try:
            # Check if git-lfs is available
            result = subprocess.run(
                ["git", "lfs", "version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "git-lfs is not installed. Please install git-lfs to download mesh data.\n"
                    "See: https://git-lfs.github.com/"
                )

            # Remove directory if it exists but is incomplete
            if mesh_dir.exists():
                shutil.rmtree(mesh_dir)

            # Clone with git-lfs
            result = subprocess.run(
                ["git", "clone", MESH_GIT_REPO, str(mesh_dir)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if result.returncode != 0:
                error_msg = (
                    f"Failed to clone mesh repository from {MESH_GIT_REPO}\n"
                    f"Git error: {result.stderr}\n"
                    f"Git output: {result.stdout}\n"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.info(f"Mesh repository cloned to: {mesh_dir}")
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Git clone timed out after {e.timeout} seconds") from e
        except FileNotFoundError as e:
            raise RuntimeError("git command not found. Please install git.") from e

        return mesh_dir

    def generate_stub_meshdir(self, stub_dir: Path) -> Path:
        """Generate stub mesh for fesom_uxarray.

        Creates minimal FESOM mesh files for testing.

        Parameters
        ----------
        stub_dir : Path
            Temporary directory for stub mesh

        Returns
        -------
        Path
            Path to the stub mesh directory
        """
        # Generate stub files from manifest (includes mesh file)
        from tests.fixtures.stub_generator import generate_stub_files

        generate_stub_files(self.stub_manifest_path, stub_dir)

        # Create minimal mesh files
        self._create_minimal_mesh_files(stub_dir)

        return stub_dir

    def open_mfdataset(self, **kwargs):
        """Open FESOM UXarray dataset from data directory.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments for xr.open_mfdataset

        Returns
        -------
        xr.Dataset
            Opened dataset
        """
        import xarray as xr

        nc_files = list(self.datadir.glob("*.nc"))
        if not nc_files:
            raise FileNotFoundError(f"No NetCDF files found in {self.datadir}")
        return xr.open_mfdataset(nc_files, **kwargs)

    @staticmethod
    def _create_minimal_mesh_files(mesh_dir: Path):
        """Create minimal FESOM mesh files for testing.

        Parameters
        ----------
        mesh_dir : Path
            Directory where mesh files will be created
        """
        # nod2d.out: 2D nodes (lon, lat)
        with open(mesh_dir / "nod2d.out", "w") as f:
            f.write("10\n")
            for i in range(1, 11):
                lon = 300.0 + i * 0.1
                lat = 74.0 + i * 0.05
                f.write(f"{i:8d} {lon:14.7f}  {lat:14.7f}        0\n")

        # elem2d.out: 2D element connectivity
        with open(mesh_dir / "elem2d.out", "w") as f:
            f.write("5\n")
            for i in range(1, 6):
                n1, n2, n3 = i, i + 1, i + 2
                f.write(f"{i:8d} {n1:8d} {n2:8d}\n")
                f.write(f"{n2:8d} {n3:8d} {(i % 8) + 1:8d}\n")

        # nod3d.out: 3D nodes (lon, lat, depth)
        with open(mesh_dir / "nod3d.out", "w") as f:
            f.write("30\n")
            for i in range(1, 31):
                lon = 300.0 + (i % 10) * 0.1
                lat = 74.0 + (i % 10) * 0.05
                depth = -100.0 * (i // 10)
                f.write(f"{i:8d} {lon:14.7f}  {lat:14.7f} {depth:14.7f}        0\n")

        # elem3d.out: 3D element connectivity (tetrahedra)
        with open(mesh_dir / "elem3d.out", "w") as f:
            f.write("10\n")  # 10 3D elements
            for i in range(1, 11):
                n1, n2, n3, n4 = i, i + 1, i + 2, i + 10
                f.write(f"{n1:8d} {n2:8d} {n3:8d} {n4:8d}\n")

        # aux3d.out: auxiliary 3D info (layer indices)
        # Format: num_layers \n layer_start_indices...
        with open(mesh_dir / "aux3d.out", "w") as f:
            f.write("3\n")  # 3 vertical layers
            f.write("       1\n")  # Layer 1 starts at node 1
            f.write("      11\n")  # Layer 2 starts at node 11
            f.write("      21\n")  # Layer 3 starts at node 21

        # depth.out: depth values at each node
        with open(mesh_dir / "depth.out", "w") as f:
            for i in range(10):
                f.write(f"   {-100.0 - i * 50:.1f}\n")
