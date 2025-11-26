"""FESOM 2.6 PI mesh model run implementation."""

import logging
from pathlib import Path

from tests.fixtures.base_model_run import BaseModelRun

logger = logging.getLogger(__name__)


class Fesom2p6PimeshModelRun(BaseModelRun):
    """FESOM 2.6 PI mesh model run.

    This model run includes FESOM 2.6 output on the PI mesh configuration.
    """

    def fetch_real_datadir(self) -> Path:
        """Download and extract real FESOM 2.6 PI mesh data using pooch.

        Returns
        -------
        Path
            Path to the extracted data directory
        """
        from tests.fixtures.example_data.data_fetcher import fetch_and_extract

        data_dir = fetch_and_extract("fesom_2p6_pimesh.tar", registry_path=self.registry_path)

        # The tarball extracts to fesom_2p6_pimesh/fesom_2p6_pimesh
        # Return the inner directory for consistency
        inner_dir = data_dir / "fesom_2p6_pimesh"
        if inner_dir.exists():
            return inner_dir
        return data_dir

    def generate_stub_datadir(self, stub_dir: Path) -> Path:
        """Generate stub data for fesom_2p6_pimesh from YAML manifest.

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

        # Generate stub files
        stub_dir = generate_stub_files(self.stub_manifest_path, stub_dir)

        # Create mesh files (always generate them even if not all tests need them)
        mesh_dir = stub_dir / "input" / "fesom" / "mesh" / "pi"
        mesh_dir.mkdir(parents=True, exist_ok=True)
        self._create_minimal_mesh_files(mesh_dir)

        return stub_dir

    def open_mfdataset(self, **kwargs):
        """Open FESOM 2.6 PI mesh dataset from data directory.

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

        # Find FESOM output files
        fesom_output_dir = self.datadir / "outdata" / "fesom"
        matching_files = [f for f in fesom_output_dir.iterdir() if f.name.startswith("temp.fesom")]

        if not matching_files:
            raise FileNotFoundError(f"No temp.fesom* files found in {fesom_output_dir}")

        return xr.open_mfdataset(matching_files, **kwargs)

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
        with open(mesh_dir / "aux3d.out", "w") as f:
            f.write("3\n")  # 3 vertical layers
            f.write("       1\n")  # Layer 1 starts at node 1
            f.write("      11\n")  # Layer 2 starts at node 11
            f.write("      21\n")  # Layer 3 starts at node 21

        # depth.out: depth values at each node
        with open(mesh_dir / "depth.out", "w") as f:
            for i in range(10):
                f.write(f"   {-100.0 - i * 50:.1f}\n")
