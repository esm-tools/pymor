"""Data directory fixtures for AWI-CM 1.0 RECOM biogeochemistry model.

This module provides fixtures for locating test data, either by:
- Downloading real data from remote storage (awicm_1p0_recom_real_datadir)
- Generating lightweight stub data (awicm_1p0_recom_stub_datadir)
- Routing between them based on environment (awicm_1p0_recom_datadir)
"""

import logging
import os
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def awicm_1p0_recom_real_datadir():
    """
    Download and extract real AWI-CM 1.0 RECOM data using pooch.

    Returns
    -------
    Path
        Path to the extracted data directory

    Notes
    -----
    This fixture includes validation to check for corrupted extractions
    by attempting to open a known NetCDF file.
    """
    # Lazy import to avoid loading pooch during test collection
    from tests.fixtures.example_data.data_fetcher import fetch_and_extract

    # Get registry path for this model
    registry_path = Path(__file__).parent / "registry.yaml"

    data_dir = fetch_and_extract("awicm_1p0_recom.tar", registry_path=registry_path)

    # The tarball extracts to awicm_1p0_recom/awicm_1p0_recom
    # Return the inner directory for consistency
    final_data_path = data_dir / "awicm_1p0_recom"

    if final_data_path.exists():
        # Verify one of the known files exists and is valid
        test_file = (
            final_data_path / "awi-esm-1-1-lr_kh800" / "piControl" / "outdata" / "fesom" / "thetao_fesom_2686-01-05.nc"
        )
        if test_file.exists():
            try:
                # Try to open the file to verify it's not corrupted
                import h5py

                with h5py.File(test_file, "r"):
                    logger.info(f"Validated extraction: {final_data_path}")
                    return final_data_path
            except (OSError, IOError) as e:
                logger.warning(f"Test file may be corrupted ({e}), but proceeding anyway")

    return final_data_path if final_data_path.exists() else data_dir


@pytest.fixture(scope="session")
def awicm_1p0_recom_real_data(awicm_1p0_recom_real_datadir):
    """Deprecated: Use awicm_1p0_recom_real_datadir instead."""
    import warnings

    warnings.warn(
        "awicm_1p0_recom_real_data is deprecated, use awicm_1p0_recom_real_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return awicm_1p0_recom_real_datadir


@pytest.fixture(scope="session")
def awicm_1p0_recom_stub_datadir(tmp_path_factory):
    """Generate stub data from YAML manifest."""
    # Lazy import to avoid loading numpy/xarray during test collection
    from tests.fixtures.stub_generator import generate_stub_files

    manifest_file = Path(__file__).parent / "stub_manifest.yaml"
    output_dir = tmp_path_factory.mktemp("awicm_1p0_recom")

    # Generate stub files
    stub_dir = generate_stub_files(manifest_file, output_dir)

    # Create mesh files (always generate them even if not all tests need them)
    mesh_dir = stub_dir / "awi-esm-1-1-lr_kh800" / "piControl" / "input" / "fesom" / "mesh"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    _create_minimal_mesh_files(mesh_dir)

    # Return the equivalent path structure that real data returns
    # (should match what awicm_1p0_recom_real_datadir returns)
    # The stub_dir contains awi-esm-1-1-lr_kh800/piControl/... structure
    return stub_dir


@pytest.fixture(scope="session")
def awicm_1p0_recom_stub_data(awicm_1p0_recom_stub_datadir):
    """Deprecated: Use awicm_1p0_recom_stub_datadir instead."""
    import warnings

    warnings.warn(
        "awicm_1p0_recom_stub_data is deprecated, use awicm_1p0_recom_stub_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return awicm_1p0_recom_stub_datadir


def _create_minimal_mesh_files(mesh_dir: Path):
    """Create minimal FESOM mesh files for testing."""
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


@pytest.fixture(scope="session")
def awicm_1p0_recom_datadir(request):
    """Router fixture: return stub or real data based on marker/env var."""
    # Check for environment variable
    use_real = os.getenv("PYCMOR_USE_REAL_TEST_DATA", "").lower() in ("1", "true", "yes")

    # Check for pytest marker
    if hasattr(request, "node") and request.node.get_closest_marker("real_data"):
        use_real = True

    if use_real:
        logger.info("Using real downloaded test data for awicm_1p0_recom")
        # Request real data fixture lazily
        return request.getfixturevalue("awicm_1p0_recom_real_datadir")
    else:
        logger.info("Using stub test data for awicm_1p0_recom")
        # Request stub data fixture lazily
        return request.getfixturevalue("awicm_1p0_recom_stub_datadir")


@pytest.fixture(scope="session")
def awicm_1p0_recom_data(awicm_1p0_recom_datadir):
    """Deprecated: Use awicm_1p0_recom_datadir instead."""
    import warnings

    warnings.warn(
        "awicm_1p0_recom_data is deprecated, use awicm_1p0_recom_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return awicm_1p0_recom_datadir
