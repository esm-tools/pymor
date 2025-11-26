"""Data directory fixtures for FESOM 2.6 PI mesh model.

This module provides fixtures for locating test data, either by:
- Downloading real data from remote storage (fesom_2p6_pimesh_esm_tools_real_datadir)
- Generating lightweight stub data (fesom_2p6_pimesh_esm_tools_stub_datadir)
- Routing between them based on environment (fesom_2p6_pimesh_esm_tools_datadir)
"""

import logging
import os
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_real_datadir():
    """
    Download and extract real FESOM 2.6 PI mesh data using pooch.

    Returns
    -------
    Path
        Path to the extracted data directory
    """
    # Lazy import to avoid loading pooch during test collection
    from tests.fixtures.example_data.data_fetcher import fetch_and_extract

    # Get registry path for this model
    registry_path = Path(__file__).parent / "registry.yaml"

    data_dir = fetch_and_extract("fesom_2p6_pimesh.tar", registry_path=registry_path)

    # The tarball extracts to fesom_2p6_pimesh/fesom_2p6_pimesh
    # Return the inner directory for consistency
    inner_dir = data_dir / "fesom_2p6_pimesh"
    if inner_dir.exists():
        return inner_dir
    return data_dir


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_real_data(fesom_2p6_pimesh_esm_tools_real_datadir):
    """Deprecated: Use fesom_2p6_pimesh_esm_tools_real_datadir instead."""
    import warnings

    warnings.warn(
        "fesom_2p6_pimesh_esm_tools_real_data is deprecated, use fesom_2p6_pimesh_esm_tools_real_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_2p6_pimesh_esm_tools_real_datadir


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_stub_datadir(tmp_path_factory):
    """Generate stub data from YAML manifest."""
    # Lazy import to avoid loading numpy/xarray during test collection
    from tests.fixtures.stub_generator import generate_stub_files

    manifest_file = Path(__file__).parent / "stub_manifest.yaml"
    output_dir = tmp_path_factory.mktemp("fesom_2p6_pimesh")

    # Generate stub files
    stub_dir = generate_stub_files(manifest_file, output_dir)

    # Create mesh files (always generate them even if not all tests need them)
    mesh_dir = stub_dir / "input" / "fesom" / "mesh" / "pi"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    _create_minimal_mesh_files(mesh_dir)

    # Return the equivalent path structure that real data returns
    # (should match what fesom_2p6_pimesh_esm_tools_real_datadir returns)
    return stub_dir


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_stub_data(fesom_2p6_pimesh_esm_tools_stub_datadir):
    """Deprecated: Use fesom_2p6_pimesh_esm_tools_stub_datadir instead."""
    import warnings

    warnings.warn(
        "fesom_2p6_pimesh_esm_tools_stub_data is deprecated, use fesom_2p6_pimesh_esm_tools_stub_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_2p6_pimesh_esm_tools_stub_datadir


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
def fesom_2p6_pimesh_esm_tools_datadir(request):
    """Router fixture: return stub or real data based on marker/env var."""
    # Check for environment variable
    use_real = os.getenv("PYCMOR_USE_REAL_TEST_DATA", "").lower() in ("1", "true", "yes")

    # Check for pytest marker
    if hasattr(request, "node") and request.node.get_closest_marker("real_data"):
        use_real = True

    if use_real:
        logger.info("Using real downloaded test data for fesom_2p6_pimesh")
        return request.getfixturevalue("fesom_2p6_pimesh_esm_tools_real_datadir")
    else:
        logger.info("Using stub test data for fesom_2p6_pimesh")
        return request.getfixturevalue("fesom_2p6_pimesh_esm_tools_stub_datadir")


@pytest.fixture(scope="session")
def fesom_2p6_pimesh_esm_tools_data(fesom_2p6_pimesh_esm_tools_datadir):
    """Deprecated: Use fesom_2p6_pimesh_esm_tools_datadir instead."""
    import warnings

    warnings.warn(
        "fesom_2p6_pimesh_esm_tools_data is deprecated, use fesom_2p6_pimesh_esm_tools_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return fesom_2p6_pimesh_esm_tools_datadir
