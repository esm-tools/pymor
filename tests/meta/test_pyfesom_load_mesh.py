import logging
import os

import pytest

from pycmor.fesom_1p4 import load_mesh_data

logger = logging.getLogger(__name__)

# Meta tests validate environment setup
# Skip when using stub data since mesh loading requires real mesh files
pytestmark = pytest.mark.skipif(
    not os.getenv("PYCMOR_USE_REAL_TEST_DATA"),
    reason="Meta tests require real data for environment validation (set PYCMOR_USE_REAL_TEST_DATA=1)",
)


def test_load_mesh_awicm_1p0_recom(awicm_1p0_recom_datadir):
    try:
        mesh = load_mesh_data.load_mesh(f"{awicm_1p0_recom_datadir}/awi-esm-1-1-lr_kh800/piControl/input/fesom/mesh/")
    except Exception as e:
        logger.error("Failed to load mesh. Mesh directory contents:")
        for path in (awicm_1p0_recom_datadir / "awi-esm-1-1-lr_kh800/piControl/input/fesom/mesh/").iterdir():
            logger.error(f"  {path}")
        raise e
    assert mesh is not None
