# Developing pycmor Model Plugins

This guide explains how to create external model plugins for pycmor that integrate seamlessly with the test suite.

## Overview

pycmor uses a plugin system that allows external developers to:
1. Add support for their climate models
2. Automatically integrate with pycmor's test suite
3. Share model-specific fixtures and test data

When you install a plugin with `pip install pycmor-plugin-yourmodel[test]`, the plugin's model will automatically be tested alongside pycmor's built-in models.

## Example Plugins

This guide uses two realistic examples:
1. **FOCI** - Flexible Ocean Climate Infrastructure (GEOMAR)
2. **ICON** - Icosahedral Nonhydrostatic model (MPI-M)

## Creating a Plugin

### 1. Package Structure

**Example: FOCI plugin at GEOMAR**

```
pycmor-plugin-foci/
├── pyproject.toml
├── README.md
├── src/
│   └── pycmor_plugin_foci/
│       ├── __init__.py
│       ├── model.py          # FOCIModelRun class
│       └── fixtures/
│           ├── registry.yaml       # Pooch registry for real data
│           └── stub_manifest.yaml  # Stub data specification
└── tests/
    └── test_foci_specific.py  # Model-specific tests
```

**Example: ICON plugin at MPI-M**

```
pycmor-plugin-icon/
├── pyproject.toml
├── README.md
├── src/
│   └── pycmor_plugin_icon/
│       ├── __init__.py
│       ├── model.py          # ICONModelRun class
│       └── fixtures/
│           ├── registry.yaml
│           └── stub_manifest.yaml
└── tests/
    └── test_icon_specific.py
```

### 2. Implement Your ModelRun Class

**Example 1: FOCI at GEOMAR**

In `src/pycmor_plugin_foci/model.py`:

```python
"""FOCI model run implementation for GEOMAR."""

from pathlib import Path
from pycmor.tests.fixtures.base_model_run import BaseModelRun


class FOCIModelRun(BaseModelRun):
    """FOCI (Flexible Ocean Climate Infrastructure) model run.

    FOCI couples NEMO ocean model with ECHAM atmosphere model.
    Developed and maintained at GEOMAR Helmholtz Centre for Ocean Research.
    """

    def fetch_real_datadir(self) -> Path:
        """Download real FOCI data using pooch.

        Returns
        -------
        Path
            Path to the extracted data directory
        """
        from tests.fixtures.example_data.data_fetcher import fetch_and_extract

        return fetch_and_extract("foci_test_data.tar", registry_path=self.registry_path)

    def generate_stub_datadir(self, stub_dir: Path) -> Path:
        """Generate stub FOCI data from YAML manifest.

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

    def open_mfdataset(self, **kwargs):
        """Open FOCI dataset from data directory.

        FOCI uses NEMO ocean output with specific file naming patterns.

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

        # FOCI/NEMO file pattern: FOCI_*_1m_*.nc
        nc_files = list(self.datadir.glob("FOCI_*_1m_*.nc"))

        if not nc_files:
            raise FileNotFoundError(f"No FOCI files found in {self.datadir}")

        return xr.open_mfdataset(nc_files, **kwargs)
```

**Example 2: ICON at MPI-M**

In `src/pycmor_plugin_icon/model.py`:

```python
"""ICON model run implementation for MPI-M."""

from pathlib import Path
from pycmor.tests.fixtures.base_model_run import BaseModelRun


class ICONModelRun(BaseModelRun):
    """ICON (Icosahedral Nonhydrostatic) model run.

    ICON is a unified modeling framework for atmosphere, ocean, and land.
    Developed at MPI-M and DWD.
    """

    def fetch_real_datadir(self) -> Path:
        """Download real ICON data using pooch.

        Returns
        -------
        Path
            Path to the extracted data directory
        """
        from tests.fixtures.example_data.data_fetcher import fetch_and_extract

        return fetch_and_extract("icon_test_data.tar", registry_path=self.registry_path)

    def generate_stub_datadir(self, stub_dir: Path) -> Path:
        """Generate stub ICON data from YAML manifest.

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

    def open_mfdataset(self, **kwargs):
        """Open ICON dataset from data directory.

        ICON uses unstructured icosahedral grids with specific conventions.

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

        # ICON file pattern: icon_atm_*.nc
        nc_files = list(self.datadir.glob("icon_atm_*.nc"))

        if not nc_files:
            raise FileNotFoundError(f"No ICON files found in {self.datadir}")

        return xr.open_mfdataset(nc_files, **kwargs)
```

### 3. Create Fixture Files

**Example: FOCI registry.yaml**

```yaml
# src/pycmor_plugin_foci/fixtures/registry.yaml
foci_test_data.tar:
  url: https://data.geomar.de/foci/test_data/foci_cmip6_test.tar
  sha256: null  # Add SHA256 hash for verification
  description: FOCI CMIP6 test data from GEOMAR
  extract_dir: foci_test_data
```

**Example: ICON registry.yaml**

```yaml
# src/pycmor_plugin_icon/fixtures/registry.yaml
icon_test_data.tar:
  url: https://mpimet.mpg.de/icon/test_data/icon_cmip6_test.tar
  sha256: null  # Add SHA256 hash for verification
  description: ICON CMIP6 test data from MPI-M
  extract_dir: icon_test_data
```

**Example: FOCI stub_manifest.yaml**

```yaml
# src/pycmor_plugin_foci/fixtures/stub_manifest.yaml
files:
  - path: FOCI_ocean_1m_2000-01.nc
    dimensions:
      time: 12
      y: 180
      x: 360
      depth: 50
    variables:
      thetao:
        dims: [time, depth, y, x]
        attrs:
          long_name: Sea Water Potential Temperature
          units: degC
          standard_name: sea_water_potential_temperature
      so:
        dims: [time, depth, y, x]
        attrs:
          long_name: Sea Water Salinity
          units: psu
          standard_name: sea_water_salinity
```

**Example: ICON stub_manifest.yaml**

```yaml
# src/pycmor_plugin_icon/fixtures/stub_manifest.yaml
files:
  - path: icon_atm_2d_ml_2000-01.nc
    dimensions:
      time: 12
      ncells: 20480  # R2B04 resolution
      nlevels: 90
    variables:
      tas:
        dims: [time, ncells]
        attrs:
          long_name: Near-Surface Air Temperature
          units: K
          standard_name: air_temperature
      ps:
        dims: [time, ncells]
        attrs:
          long_name: Surface Air Pressure
          units: Pa
          standard_name: surface_air_pressure
```

### 4. Register Your Plugin

**Example: FOCI pyproject.toml (GEOMAR)**

```toml
[project]
name = "pycmor-plugin-foci"
version = "0.1.0"
description = "FOCI model plugin for pycmor (GEOMAR)"
dependencies = [
    "pycmor>=1.0.0",
]

[project.optional-dependencies]
test = [
    "pycmor[test]",  # Include pycmor's test dependencies
    "pytest>=7.0",
]

# Register your model via entry points
[project.entry-points."pycmor.fixtures.model_runs"]
foci = "pycmor_plugin_foci.model:FOCIModelRun"
```

**Example: ICON pyproject.toml (MPI-M)**

```toml
[project]
name = "pycmor-plugin-icon"
version = "0.1.0"
description = "ICON model plugin for pycmor (MPI-M)"
dependencies = [
    "pycmor>=1.0.0",
]

[project.optional-dependencies]
test = [
    "pycmor[test]",  # Include pycmor's test dependencies
    "pytest>=7.0",
]

# Register your model via entry points
[project.entry-points."pycmor.fixtures.model_runs"]
icon = "pycmor_plugin_icon.model:ICONModelRun"
```

## Using Your Plugin

### Installation

Users install your plugin with the test extra:

```bash
# At GEOMAR
pip install pycmor-plugin-foci[test]

# At MPI-M
pip install pycmor-plugin-icon[test]
```

### Running Tests

When users run pycmor's test suite, your model is automatically included:

```bash
cd /path/to/pycmor
pytest tests/test_generic_models.py
```

Output:
```
tests/test_generic_models.py::test_model_run_has_datadir[awicmrecom] PASSED
tests/test_generic_models.py::test_model_run_has_datadir[fesom2p6pimesh] PASSED
tests/test_generic_models.py::test_model_run_has_datadir[fesomuxarray] PASSED
tests/test_generic_models.py::test_model_run_has_datadir[foci] PASSED  ← GEOMAR's FOCI!
tests/test_generic_models.py::test_model_run_has_datadir[icon] PASSED  ← MPI-M's ICON!
...
```

## Generic Tests

Your model will automatically be tested against:

1. **Data directory access** - Can provide a valid data directory
2. **Dataset opening** - Can open an xarray dataset
3. **Registry configuration** - Has proper registry.yaml
4. **Stub manifest** - Has proper stub_manifest.yaml
5. **Lazy loading** - Properties are lazy-loaded
6. **Attribute presence** - Has required attributes (model_name, etc.)

## Adding Model-Specific Tests

You can also add tests specific to your model.

**Example: FOCI-specific tests** (`tests/test_foci_specific.py`):

```python
import pytest


def test_foci_has_ocean_variables(foci_model_run):
    """Test FOCI-specific ocean variables from NEMO."""
    ds = foci_model_run.ds
    assert 'thetao' in ds.data_vars, "Missing potential temperature"
    assert 'so' in ds.data_vars, "Missing salinity"


def test_foci_nemo_grid_structure(foci_model_run):
    """Test that FOCI uses expected NEMO grid dimensions."""
    ds = foci_model_run.ds
    assert 'x' in ds.dims or 'i' in ds.dims, "Missing NEMO x/i dimension"
    assert 'y' in ds.dims or 'j' in ds.dims, "Missing NEMO y/j dimension"
```

**Example: ICON-specific tests** (`tests/test_icon_specific.py`):

```python
import pytest


def test_icon_has_unstructured_grid(icon_model_run):
    """Test ICON uses icosahedral unstructured grid."""
    ds = icon_model_run.ds
    assert 'ncells' in ds.dims, "Missing ncells dimension for unstructured grid"


def test_icon_atmosphere_variables(icon_model_run):
    """Test ICON-specific atmosphere variables."""
    ds = icon_model_run.ds
    assert 'tas' in ds.data_vars, "Missing near-surface air temperature"
    assert 'ps' in ds.data_vars, "Missing surface pressure"
```

To make your model_run fixture available, create `conftest.py`:

**Example: FOCI conftest.py**

```python
import pytest
from pycmor_plugin_foci.model import FOCIModelRun


@pytest.fixture(scope="session")
def foci_model_run(request, tmp_path_factory):
    """FOCI model run fixture for tests."""
    use_real = FOCIModelRun.should_use_real_data(request)
    from pathlib import Path
    fixtures_dir = Path(__file__).parent.parent / "src" / "pycmor_plugin_foci" / "fixtures"

    return FOCIModelRun(
        model_name="foci",
        fixtures_dir=fixtures_dir,
        use_real=use_real,
        tmp_path_factory=tmp_path_factory,
    )
```

**Example: ICON conftest.py**

```python
import pytest
from pycmor_plugin_icon.model import ICONModelRun



@pytest.fixture(scope="session")
def icon_model_run(request, tmp_path_factory):
    """ICON model run fixture for tests."""
    use_real = ICONModelRun.should_use_real_data(request)
    from pathlib import Path
    fixtures_dir = Path(__file__).parent.parent / "src" / "pycmor_plugin_icon" / "fixtures"

    return ICONModelRun(
        model_name="icon",
        fixtures_dir=fixtures_dir,
        use_real=use_real,
        tmp_path_factory=tmp_path_factory,
    )
```

## Best Practices

1. **Use descriptive model names** - Name your ModelRun class clearly (e.g., `FOCIModelRun`, `ICONModelRun`, not `ModelRun`)

2. **Provide both real and stub data** - Implement both `fetch_real_datadir()` and `generate_stub_datadir()`

3. **Document your data requirements** - Clearly document what data files are expected

4. **Include SHA256 hashes** - Add SHA256 hashes to registry.yaml for data integrity

5. **Test locally first** - Run pycmor's test suite locally before publishing

6. **Version constraints** - Pin compatible pycmor versions in your dependencies

## Advanced: Optional Methods

If your model has mesh files, override the mesh methods:

```python
def fetch_real_meshdir(self) -> Path:
    """Download real mesh files."""
    # Implementation
    pass

def generate_stub_meshdir(self, stub_dir: Path) -> Path:
    """Generate stub mesh files."""
    # Implementation
    pass
```

Then users can access:
```python
mesh_path = cesm_model_run.meshdir
```

## Support

For questions or issues:
- pycmor documentation: https://pycmor.readthedocs.io/
- pycmor issues: https://github.com/esm-tools/pycmor/issues
- Example plugin: See `tests/contrib/models/` for built-in model examples

## License

Plugins can use any license, but must be compatible with pycmor's license.
