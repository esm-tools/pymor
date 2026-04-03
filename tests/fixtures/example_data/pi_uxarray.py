"""Example data for PI control UXarray tests.

This module provides fixtures for both real downloaded data and lightweight
stub data for testing, including both data files and mesh files.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)

MESH_GIT_REPO = "https://gitlab.awi.de/fesom/pi"
"""str : Git repository URL for the FESOM PI mesh data."""


@pytest.fixture(scope="session")
def pi_uxarray_real_datadir():
    """
    Download and extract real PI control UXarray data using pooch.

    Returns
    -------
    Path
        Path to the extracted data directory
    """
    # Lazy import to avoid loading pooch during test collection
    from tests.fixtures.example_data.data_fetcher import fetch_and_extract

    return fetch_and_extract("pi_uxarray.tar")


@pytest.fixture(scope="session")
def pi_uxarray_real_data(pi_uxarray_real_datadir):
    """Deprecated: Use pi_uxarray_real_datadir instead."""
    import warnings

    warnings.warn(
        "pi_uxarray_real_data is deprecated, use pi_uxarray_real_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return pi_uxarray_real_datadir


@pytest.fixture(scope="session")
def pi_uxarray_stub_datadir(tmp_path_factory):
    """
    Generate stub data for pi_uxarray from YAML manifest.
    Returns the data directory containing generated NetCDF files.
    """
    # Lazy import to avoid loading numpy/xarray during test collection
    from tests.fixtures.stub_generator import generate_stub_files

    # Create temporary directory for stub data
    stub_dir = tmp_path_factory.mktemp("pi_uxarray_stub")

    # Path to the YAML manifest
    manifest_file = Path(__file__).parent.parent / "stub_data" / "pi_uxarray.yaml"

    # Generate stub files from manifest
    generate_stub_files(manifest_file, stub_dir)

    return stub_dir


@pytest.fixture(scope="session")
def pi_uxarray_stub_data(pi_uxarray_stub_datadir):
    """Deprecated: Use pi_uxarray_stub_datadir instead."""
    import warnings

    warnings.warn(
        "pi_uxarray_stub_data is deprecated, use pi_uxarray_stub_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return pi_uxarray_stub_datadir


@pytest.fixture(scope="session")
def pi_uxarray_datadir(request):
    """
    Router fixture that returns stub data by default, or real data if:
    1. The PYCMOR_USE_REAL_TEST_DATA environment variable is set
    2. The real_data pytest marker is present
    """
    # Check for environment variable
    use_real = os.getenv("PYCMOR_USE_REAL_TEST_DATA", "").lower() in ("1", "true", "yes")

    # Check for pytest marker
    if hasattr(request, "node") and request.node.get_closest_marker("real_data"):
        use_real = True

    if use_real:
        logger.info("Using real data for pi_uxarray")
        return request.getfixturevalue("pi_uxarray_real_datadir")
    else:
        logger.info("Using stub data for pi_uxarray")
        return request.getfixturevalue("pi_uxarray_stub_datadir")


@pytest.fixture(scope="session")
def pi_uxarray_data(pi_uxarray_datadir):
    """Deprecated: Use pi_uxarray_datadir instead."""
    import warnings

    warnings.warn(
        "pi_uxarray_data is deprecated, use pi_uxarray_datadir",
        DeprecationWarning,
        stacklevel=2,
    )
    return pi_uxarray_datadir


@pytest.fixture(scope="session")
def pi_uxarray_download_mesh(tmp_path_factory):
    """
    Clone FESOM PI mesh from GitLab using git-lfs.
    Uses persistent cache in $HOME/.cache/pycmor instead of ephemeral /tmp.
    """
    from tests.fixtures.example_data.data_fetcher import get_cache_dir

    # Use persistent cache in $HOME/.cache/pycmor instead of ephemeral /tmp
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    mesh_dir = cache_dir / "pi_mesh_git"

    if mesh_dir.exists() and (mesh_dir / ".git").exists():
        logger.info(f"Using cached git mesh repository: {mesh_dir}")
        return mesh_dir

    # Clone the repository with git-lfs
    logger.info(f"Cloning FESOM PI mesh from {MESH_GIT_REPO}...")
    try:
        # Check if git-lfs is available
        result = subprocess.run(["git", "lfs", "version"], capture_output=True, text=True, timeout=10, check=False)
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


@pytest.fixture(scope="session")
def pi_uxarray_real_meshdir(pi_uxarray_download_mesh):
    """Return the cloned git repository directory containing FESOM PI mesh files."""
    return pi_uxarray_download_mesh


@pytest.fixture(scope="session")
def pi_uxarray_real_mesh(pi_uxarray_real_meshdir):
    """Deprecated: Use pi_uxarray_real_meshdir instead."""
    import warnings

    warnings.warn(
        "pi_uxarray_real_mesh is deprecated, use pi_uxarray_real_meshdir",
        DeprecationWarning,
        stacklevel=2,
    )
    return pi_uxarray_real_meshdir


@pytest.fixture(scope="session")
def pi_uxarray_stub_meshdir(tmp_path_factory):
    """
    Generate stub mesh for pi_uxarray from YAML manifest.
    Returns the mesh directory containing fesom.mesh.diag.nc.
    """
    # Lazy import to avoid loading numpy/xarray during test collection
    from tests.fixtures.stub_generator import generate_stub_files

    # Create temporary directory for stub mesh
    stub_dir = tmp_path_factory.mktemp("pi_uxarray_stub_mesh")

    # Path to the YAML manifest
    manifest_file = Path(__file__).parent.parent / "stub_data" / "pi_uxarray.yaml"

    # Generate stub files from manifest
    # Note: This generates all files from the manifest, including the mesh file
    generate_stub_files(manifest_file, stub_dir)

    # Create mesh files directly in stub_dir (not in a subdirectory)
    _create_minimal_mesh_files(stub_dir)

    return stub_dir


@pytest.fixture(scope="session")
def pi_uxarray_stub_mesh(pi_uxarray_stub_meshdir):
    """Deprecated: Use pi_uxarray_stub_meshdir instead."""
    import warnings

    warnings.warn(
        "pi_uxarray_stub_mesh is deprecated, use pi_uxarray_stub_meshdir",
        DeprecationWarning,
        stacklevel=2,
    )
    return pi_uxarray_stub_meshdir


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
def pi_uxarray_meshdir(request):
    """
    Router fixture that returns stub mesh by default, or real mesh if:
    1. The PYCMOR_USE_REAL_TEST_DATA environment variable is set
    2. The real_data pytest marker is present
    """
    # Check for environment variable
    use_real = os.getenv("PYCMOR_USE_REAL_TEST_DATA", "").lower() in ("1", "true", "yes")

    # Check for pytest marker
    if hasattr(request, "node") and request.node.get_closest_marker("real_data"):
        use_real = True

    if use_real:
        logger.info("Using real mesh for pi_uxarray")
        return request.getfixturevalue("pi_uxarray_real_meshdir")
    else:
        logger.info("Using stub mesh for pi_uxarray")
        return request.getfixturevalue("pi_uxarray_stub_meshdir")


@pytest.fixture(scope="session")
def pi_uxarray_mesh(pi_uxarray_meshdir):
    """Deprecated: Use pi_uxarray_meshdir instead."""
    import warnings

    warnings.warn(
        "pi_uxarray_mesh is deprecated, use pi_uxarray_meshdir",
        DeprecationWarning,
        stacklevel=2,
    )
    return pi_uxarray_meshdir
