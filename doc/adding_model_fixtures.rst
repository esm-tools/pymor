====================================
Adding Model Fixtures to pycmor
====================================

This guide explains how to create an external test data package that integrates with pycmor's testing infrastructure.

Overview
========

pycmor uses a **plugin-based architecture** for test data, allowing climate models to provide their own test datasets as separate packages. Each model package provides:

1. **Model run classes** that handle data fetching and management
2. **CMIP configuration files** for CMIP6/CMIP7 processing
3. **Entry points** for automatic discovery by pycmor

This approach enables:

- **Decoupled maintenance**: Model teams maintain their own test data
- **Progressive implementation**: Start with minimal implementation, add features over time
- **Self-healing tests**: Tests automatically adapt as configs become available
- **Shared infrastructure**: All models benefit from common test infrastructure

Architecture
============

Entry Point Discovery
---------------------

pycmor discovers model fixtures through Python entry points defined in ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points."pycmor.fixtures.model_runs"]
   fesom_2p6 = "pycmor_test_data_fesom.fesom_2p6:Fesom2p6ModelRun"
   fesom_dev = "pycmor_test_data_fesom.fesom_dev:FesomDevModelRun"

Integration Test Matrix
------------------------

pycmor's integration tests create a test matrix across all discovered models:

.. list-table:: Integration Test Matrix
   :header-rows: 1
   :widths: 30 20 25 25

   * - Test
     - Scope
     - Runs For
     - Validates
   * - ``test_library_initialization``
     - Basic setup
     - Each model × CMIP6/7
     - CMORizer can load config
   * - ``test_library_process``
     - Full pipeline
     - Each model × CMIP6/7 × 3 orchestrators
     - End-to-end processing
   * - ``test_library_accessor``
     - Accessor API
     - Each model × CMIP6/7
     - In-memory processing

Self-Healing Test Behavior
---------------------------

Tests use the ``configs`` property for conditional xfail:

.. code-block:: python

   def test_library_initialization(model_run_instance, cmip_version):
       # Conditionally xfail if config not available
       if cmip_version not in model_run_instance.configs:
           pytest.xfail(f"{cmip_version.upper()} config not available")

       # Test proceeds only when config exists
       config_path = model_run_instance.configs[cmip_version]
       cmorizer = CMORizer.from_dict(load_config(config_path))
       assert cmorizer is not None

This creates a **progressive workflow**:

1. **No configs**: Tests show ``XFAIL`` (expected failure) - not a problem
2. **Add CMIP6 config**: CMIP6 tests pass, CMIP7 still ``XFAIL``
3. **Add CMIP7 config**: All tests pass

Step-by-Step Implementation Guide
==================================

This guide walks through creating a complete model fixture package using FESOM 2.6 as an example.

Step 1: Create Package Structure
---------------------------------

Create a new Python package with this structure:

.. code-block:: text

   pycmor_test_data_<model>/
   ├── README.md
   ├── pyproject.toml
   └── src/
       └── pycmor_test_data_<model>/
           ├── __init__.py
           ├── <model>_2p6.py              # ModelRun class
           ├── <model>_2p6_registry.yaml   # Pooch registry
           ├── <model>_2p6_stub_manifest.yaml  # Stub data spec
           └── fixtures/                   # CMIP configs (create later)

**Example for FESOM:**

.. code-block:: text

   pycmor_test_data_fesom/
   └── src/
       └── pycmor_test_data_fesom/
           ├── __init__.py
           ├── fesom_2p6.py
           ├── fesom_2p6_registry.yaml
           └── fesom_2p6_stub_manifest.yaml

Step 2: Create pyproject.toml
------------------------------

Define your package with entry points for model discovery:

.. code-block:: toml

   [build-system]
   requires = ["setuptools>=61.0", "wheel"]
   build-backend = "setuptools.build_meta"

   [project]
   name = "pycmor-test-data-fesom"
   version = "0.1.0"
   description = "FESOM test datasets for pycmor"
   readme = "README.md"
   requires-python = ">=3.9"
   dependencies = [
       "pycmor",
   ]

   # Register model runs for automatic discovery
   [project.entry-points."pycmor.fixtures.model_runs"]
   fesom_2p6 = "pycmor_test_data_fesom.fesom_2p6:Fesom2p6ModelRun"

   [tool.setuptools]
   zip-safe = false
   include-package-data = true

   [tool.setuptools.packages.find]
   where = ["src"]

   [tool.setuptools.package-dir]
   "" = "src"

   # Include YAML files in package distribution
   [tool.setuptools.package-data]
   pycmor_test_data_fesom = ["*.yaml", "fixtures/*.yaml"]

**Key sections:**

- ``project.entry-points``: Registers your model with pycmor
- ``package-data``: Ensures YAML files are included in the package

Step 3: Implement the ModelRun Class
-------------------------------------

Create a class inheriting from ``BaseModelRun``:

.. code-block:: python

   """FESOM 2.6 PI mesh model run implementation."""

   import logging
   from pathlib import Path

   from pycmor.tutorial.base_model_run import BaseModelRun

   logger = logging.getLogger(__name__)


   class Fesom2p6ModelRun(BaseModelRun):
       """FESOM 2.6 PI mesh model run.

       This model run includes FESOM 2.6 output on the PI mesh configuration.
       """

       @property
       def configs(self) -> dict:
           """Return available CMIP config files.

           Returns
           -------
           dict[str, Path]
               Mapping of CMIP version ("cmip6", "cmip7") to config file paths.
               Empty dict if no configs available.
           """
           configs = {}
           fixtures_dir = Path(__file__).parent / "fixtures"

           # Check for CMIP6 config
           cmip6_config = fixtures_dir / "config_cmip6_fesom_2p6.yaml"
           if cmip6_config.exists():
               configs["cmip6"] = cmip6_config

           # Check for CMIP7 config
           cmip7_config = fixtures_dir / "config_cmip7_fesom_2p6.yaml"
           if cmip7_config.exists():
               configs["cmip7"] = cmip7_config

           return configs

       def fetch_real_datadir(self) -> Path:
           """Download and extract real FESOM 2.6 data using pooch.

           Returns
           -------
           Path
               Path to the extracted data directory
           """
           from pycmor.tutorial.data_fetcher import fetch_and_extract

           data_dir = fetch_and_extract(
               "fesom_2p6_pimesh.tar",
               registry_path=self.registry_path
           )
           return data_dir

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
           from pycmor.tutorial.stub_generator import generate_stub_files

           return generate_stub_files(self.stub_manifest_path, stub_dir)

       def open_mfdataset(self, **kwargs):
           """Open FESOM 2.6 dataset with xarray.

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

           fesom_output_dir = self.datadir / "outdata" / "fesom"
           matching_files = [
               f for f in fesom_output_dir.iterdir()
               if f.name.startswith("temp.fesom")
           ]

           if not matching_files:
               raise FileNotFoundError(
                   f"No temp.fesom* files found in {fesom_output_dir}"
               )

           return xr.open_mfdataset(matching_files, **kwargs)

**Required Methods:**

1. ``configs`` property - Returns available CMIP configs (initially returns ``{}``)
2. ``fetch_real_datadir()`` - Downloads real data via pooch
3. ``generate_stub_datadir()`` - Creates lightweight test data
4. ``open_mfdataset()`` - Opens data with xarray

**Inherited Properties:**

BaseModelRun automatically provides:

- ``registry_path`` - Generated from class name (``fesom_2p6_registry.yaml``)
- ``stub_manifest_path`` - Generated from class name (``fesom_2p6_stub_manifest.yaml``)
- ``datadir`` - Lazy-loaded data directory
- ``ds`` - Lazy-loaded xarray dataset

Step 4: Create Registry and Stub Manifest
------------------------------------------

Create two YAML files for data management:

**fesom_2p6_registry.yaml** (Pooch registry for real data):

.. code-block:: yaml

   fesom_2p6_pimesh.tar:
     url: https://zenodo.org/record/12345/files/fesom_2p6_pimesh.tar
     sha256: abc123def456...

**fesom_2p6_stub_manifest.yaml** (Specification for stub data):

.. code-block:: yaml

   files:
     - path: outdata/fesom/temp.fesom.1850.nc
       variables:
         temp:
           dims: [time, nz1, nod2]
           shape: [12, 10, 100]
           dtype: float32

See pycmor documentation for complete manifest specification.

Step 5: Create CMIP Configuration Files
----------------------------------------

Create ``fixtures/`` directory and add CMIP configs. Start with CMIP6:

**fixtures/config_cmip6_fesom_2p6.yaml:**

.. code-block:: yaml

   pycmor:
     version: "unreleased"
     use_xarray_backend: True
     warn_on_no_rule: False

   general:
     name: "fesom_2p6_pimesh"
     description: "FESOM 2.6 PI mesh configuration for CMIP6"
     maintainer: "your_name"
     email: "your.email@example.com"
     cmor_version: "CMIP6"
     mip: "CMIP"
     frequency: "mon"
     CMIP_Tables_Dir: "./cmip6-cmor-tables/Tables"
     CV_Dir: "./cmip6-cmor-tables/CMIP6_CVs"

   rules:
     - name: "thetao_with_levels"
       experiment_id: "piControl"
       activity_id: "CMIP"
       output_directory: "./output"
       source_id: "FESOM"
       grid_label: gn
       variant_label: "r1i1p1f1"
       model_component: "ocean"
       inputs:
         - path: "{{ datadir }}/outdata/fesom"
           pattern: "temp.fesom..*\\.nc"  # REGEX pattern
       cmor_variable: "thetao"
       model_variable: "temp"
       pipelines:
         - level_regridder

   pipelines:
     - name: level_regridder
       steps:
         - pycmor.core.gather_inputs.load_mfdataset
         - pycmor.std_lib.generic.get_variable
         - pycmor.std_lib.generic.trigger_compute

**Important Notes:**

- Use ``{{ datadir }}`` template variable (NOT ``REPLACE_ME``)
- ``pattern`` expects **regex**, not glob (``.*\\.nc`` not ``*.nc``)
- Escape literal dots: ``\\.nc``
- Include complete pipeline steps for your model

**CMIP7 config** (optional, add when ready):

.. code-block:: yaml

   general:
     cmor_version: "CMIP7"  # Changed from CMIP6
     # CMIP_Tables_Dir not needed (uses packaged data)
     # CV_Dir is optional

   rules:
     - name: "thetao_with_levels"
       institution_id: "AWI"  # Required for CMIP7
       compound_name: "ocean.thetao.mean.mon.gn"  # CMIP7 identifier
       # ... rest similar to CMIP6

Step 6: Test Your Implementation
---------------------------------

Install your package in development mode:

.. code-block:: bash

   cd pycmor_test_data_fesom
   pip install -e .

Verify entry point registration:

.. code-block:: bash

   python -c "from pycmor.tutorial.base_model_run import BaseModelRun; \
              from tests.utils.entry_points import discover_model_runs; \
              print(discover_model_runs())"

Expected output should include your model:

.. code-block:: python

   {
       'fesom_2p6': <class 'pycmor_test_data_fesom.fesom_2p6.Fesom2p6ModelRun'>,
       # ... other models
   }

Test the ModelRun class:

.. code-block:: python

   from pycmor_test_data_fesom.fesom_2p6 import Fesom2p6ModelRun

   # Create instance
   model_run = Fesom2p6ModelRun.from_module(
       "pycmor_test_data_fesom/fesom_2p6.py"
   )

   # Check configs (should be empty initially)
   print(model_run.configs)  # {}

   # Check data paths work
   print(model_run.datadir)  # Should generate stub data

Step 7: Run Integration Tests
------------------------------

From the pycmor repository:

.. code-block:: bash

   # Run tests for your model
   pytest tests/integration/test_model_runs.py -k fesom_2p6 -v

Expected behavior **without configs**:

.. code-block:: text

   test_model_runs.py::test_library_initialization[fesom_2p6-cmip6] XFAIL
   test_model_runs.py::test_library_initialization[fesom_2p6-cmip7] XFAIL

Expected behavior **with CMIP6 config**:

.. code-block:: text

   test_model_runs.py::test_library_initialization[fesom_2p6-cmip6] PASSED
   test_model_runs.py::test_library_initialization[fesom_2p6-cmip7] XFAIL

Expected behavior **with both configs**:

.. code-block:: text

   test_model_runs.py::test_library_initialization[fesom_2p6-cmip6] PASSED
   test_model_runs.py::test_library_initialization[fesom_2p6-cmip7] PASSED

Common Issues and Solutions
============================

Registry Files Not Found
-------------------------

**Error:**

.. code-block:: text

   FileNotFoundError: [Errno 2] No such file or directory:
   '.../pycmor_test_data_fesom/registry.yaml'

**Solution:**

The ``BaseModelRun`` class automatically generates filenames from your class name. Ensure your files match the expected pattern:

- ``Fesom2p6ModelRun`` → ``fesom_2p6_registry.yaml``
- ``AwicmRecomModelRun`` → ``awicm_recom_registry.yaml``

The conversion uses this pattern:

.. code-block:: python

   class_name = "Fesom2p6ModelRun".replace("ModelRun", "")  # "Fesom2p6"
   prefix = re.sub(r'(?<!^)(?=[A-Z])', '_', class_name).lower()  # "fesom_2p6"
   filename = f"{prefix}_registry.yaml"  # "fesom_2p6_registry.yaml"

Invalid Regex Pattern
---------------------

**Error:**

.. code-block:: text

   re.error: nothing to repeat at position 0

**Cause:**

Using glob patterns instead of regex:

.. code-block:: yaml

   # WRONG - this is a glob pattern
   pattern: "*.nc"

   # CORRECT - this is a regex pattern
   pattern: ".*\\.nc"

**Solution:**

- Use ``.*`` for "any characters" (not ``*``)
- Escape literal dots: ``\\.`` (not ``.``)
- Common patterns:

  - Any .nc file: ``".*\\.nc"``
  - Specific prefix: ``"temp.fesom..*\\.nc"``
  - Date pattern: ``"data.\\d{4}-\\d{2}\\.nc"``

Configs Not Discovered
-----------------------

**Symptom:** Tests still show XFAIL even after adding config files.

**Checklist:**

1. **File location correct?**

   .. code-block:: bash

      ls src/pycmor_test_data_fesom/fixtures/config_cmip6_*.yaml

2. **Filenames match pattern?**

   - For ``Fesom2p6ModelRun``: ``config_cmip6_fesom_2p6.yaml``
   - Pattern: ``config_{cmip_version}_{model_prefix}.yaml``

3. **configs property implemented?**

   .. code-block:: python

      @property
      def configs(self) -> dict:
          configs = {}
          fixtures_dir = Path(__file__).parent / "fixtures"
          cmip6_config = fixtures_dir / "config_cmip6_fesom_2p6.yaml"
          if cmip6_config.exists():
              configs["cmip6"] = cmip6_config
          return configs

4. **Package data registered in pyproject.toml?**

   .. code-block:: toml

      [tool.setuptools.package-data]
      pycmor_test_data_fesom = ["*.yaml", "fixtures/*.yaml"]

5. **Package reinstalled after adding configs?**

   .. code-block:: bash

      pip install -e . --force-reinstall --no-deps

Template Variables Not Rendered
--------------------------------

**Error:**

.. code-block:: text

   FileNotFoundError: {{ datadir }}/outdata/fesom

**Cause:**

Tests render the config template, but you're using it directly.

**Solution:**

When using configs in tests, always render Jinja2 templates:

.. code-block:: python

   from jinja2 import Template
   import yaml

   # Load and render config
   with open(config_path) as f:
       template = Template(f.read())

   rendered_config = template.render(datadir=str(model_run.datadir))
   cfg = yaml.safe_load(rendered_config)

Progressive Implementation Workflow
====================================

You don't need to implement everything at once. Here's a recommended progression:

Phase 1: Minimal Viable Package
--------------------------------

**Goal:** Get your model discovered by pycmor tests

**Implement:**

1. Package structure with ``pyproject.toml``
2. Basic ``ModelRun`` class with:

   - ``fetch_real_datadir()``
   - ``generate_stub_datadir()``
   - ``open_mfdataset()``
   - ``configs`` property returning ``{}``

3. Registry and stub manifest files

**Result:** Tests discover your model but show XFAIL (expected, not a problem)

Phase 2: CMIP6 Integration
---------------------------

**Goal:** Enable CMIP6 processing tests

**Implement:**

1. Create ``fixtures/`` directory
2. Add ``config_cmip6_<model>.yaml``
3. Update ``configs`` property to return CMIP6 config

**Result:** CMIP6 tests pass, CMIP7 tests still XFAIL

Phase 3: CMIP7 Integration
---------------------------

**Goal:** Full CMIP6/7 support

**Implement:**

1. Add ``config_cmip7_<model>.yaml``
2. ``configs`` property now returns both configs

**Result:** All tests pass

Phase 4: Optional Enhancements
-------------------------------

**Consider adding:**

- Pytest fixture modules (``config.py``, ``datadir.py``, ``datasets.py``)
- Additional model variants
- Mesh-specific fixtures
- Custom processing steps

Best Practices
==============

Class Naming
------------

Use descriptive names that convert cleanly to filenames:

.. code-block:: python

   # GOOD - converts to fesom_2p6
   class Fesom2p6ModelRun(BaseModelRun):
       pass

   # GOOD - converts to awicm_recom
   class AwicmRecomModelRun(BaseModelRun):
       pass

   # AVOID - creates awkward filenames
   class FESOMRun(BaseModelRun):  # -> f_e_s_o_m_run.yaml
       pass

Config Organization
-------------------

Organize configs by version and model:

.. code-block:: text

   fixtures/
   ├── config_cmip6_fesom_2p6.yaml
   ├── config_cmip7_fesom_2p6.yaml
   ├── config_cmip6_fesom_dev.yaml
   └── config_cmip7_fesom_dev.yaml

Stub Data Design
----------------

Keep stub data minimal but representative:

- Use small dimensions (time=12, lev=10, lat/lon=20)
- Include all required coordinates
- Match real data structure
- Use realistic variable names

Documentation
-------------

Document your ModelRun class clearly:

.. code-block:: python

   class Fesom2p6ModelRun(BaseModelRun):
       """FESOM 2.6 PI mesh model run.

       This model run includes FESOM 2.6 output on the PI mesh configuration
       with monthly mean ocean temperature data.

       Data Structure
       --------------
       - Input path: ``{datadir}/outdata/fesom/``
       - File pattern: ``temp.fesom.*.nc``
       - Mesh path: ``{datadir}/input/fesom/mesh/pi/``

       Variables
       ---------
       - temp: 3D ocean potential temperature

       CMIP Variables
       --------------
       - CMIP6: thetao (sea_water_potential_temperature)
       - CMIP7: ocean.thetao.mean.mon.gn
       """

Testing Strategy
----------------

Test at multiple levels:

1. **Unit tests**: Test ModelRun methods in your package
2. **Integration tests**: Let pycmor's test suite validate integration
3. **CI/CD**: Run both on every commit

Example unit test:

.. code-block:: python

   # In your package's test suite
   def test_fesom_2p6_data_structure():
       """Test FESOM 2.6 data has expected structure."""
       model_run = Fesom2p6ModelRun.from_module(__file__)
       ds = model_run.ds

       assert "temp" in ds.variables
       assert "time" in ds.dims
       assert len(ds.time) > 0

Example References
==================

Complete implementations to study:

**FESOM Package:**

- Package: ``pycmor_test_data_fesom``
- Location: ``https://github.com/fesom/pycmor_test_data``
- Models: FESOM 2.6, FESOM dev

**AWI-CM RECOM Package:**

- Package: ``pycmor_test_data_awiesm``
- Location: ``https://github.com/AWI-ESM/pycmor_test_data``
- Models: AWI-CM RECOM

**Built-in Example:**

- Location: ``tests/contrib/models/awicm_recom/`` in pycmor repo
- Complete reference implementation

Related Documentation
=====================

* :doc:`test_infrastructure` - Test infrastructure overview
* :doc:`developer_guide` - General developer guide
* :doc:`pycmor_configuration` - Configuration file format
* :doc:`pycmor_building_blocks` - Pipeline and rule concepts

External Resources
------------------

* `Entry Points Guide <https://setuptools.pypa.io/en/latest/userguide/entry_point.html>`_
* `Pooch Documentation <https://www.fatiando.org/pooch/>`_
* `Jinja2 Templates <https://jinja.palletsprojects.com/>`_
