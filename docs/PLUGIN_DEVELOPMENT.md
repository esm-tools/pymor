# Developing pycmor Model Plugins

This guide explains how to create external model plugins for pycmor that integrate seamlessly with the test suite.

## Overview

pycmor uses a plugin system that allows external developers to:
1. Add support for their climate models
2. Automatically integrate with pycmor's test suite
3. Share model-specific fixtures and test data

When you install a plugin with `pip install pycmor-plugin-yourmodel[test]`, the plugin's model will automatically be tested alongside pycmor's built-in models.

## Creating a Plugin

### 1. Package Structure

Create a package with the following structure:

```
pycmor-plugin-cesm/
├── pyproject.toml
├── README.md
├── src/
│   └── pycmor_plugin_cesm/
│       ├── __init__.py
│       ├── model.py          # Your ModelRun class
│       └── fixtures/
│           ├── registry.yaml       # Pooch registry for real data
│           └── stub_manifest.yaml  # Stub data specification
└── tests/
    └── test_cesm_specific.py  # Model-specific tests
```

### 2. Implement Your ModelRun Class

In `src/pycmor_plugin_cesm/model.py`:

```python
"""CESM model run implementation."""

from pathlib import Path
from pycmor.tests.fixtures.base_model_run import BaseModelRun


class CESMModelRun(BaseModelRun):
    """CESM model run with atmosphere and ocean output."""

    def fetch_real_datadir(self) -> Path:
        """Download real CESM data using pooch.

        Returns
        -------
        Path
            Path to the extracted data directory
        """
        from tests.fixtures.example_data.data_fetcher import fetch_and_extract

        return fetch_and_extract("cesm_data.tar", registry_path=self.registry_path)

    def generate_stub_datadir(self, stub_dir: Path) -> Path:
        """Generate stub CESM data from YAML manifest.

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
        """Open CESM dataset from data directory.

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

        # CESM-specific file pattern
        nc_files = list(self.datadir.glob("*.cam.h0.*.nc"))

        if not nc_files:
            raise FileNotFoundError(f"No CESM files found in {self.datadir}")

        return xr.open_mfdataset(nc_files, **kwargs)
```

### 3. Create Fixture Files

**registry.yaml** - Pooch configuration for downloading real test data:

```yaml
# fixtures/registry.yaml
cesm_data.tar:
  url: https://example.com/cesm_test_data.tar
  sha256: null  # Add SHA256 hash for verification
  description: CESM test data
  extract_dir: cesm_data
```

**stub_manifest.yaml** - Specification for generating lightweight stub data:

```yaml
# fixtures/stub_manifest.yaml
files:
  - path: cesm_output.cam.h0.0001-01.nc
    dimensions:
      time: 12
      lat: 96
      lon: 144
      lev: 32
    variables:
      T:
        dims: [time, lev, lat, lon]
        attrs:
          long_name: Temperature
          units: K
      PS:
        dims: [time, lat, lon]
        attrs:
          long_name: Surface pressure
          units: Pa
```

### 4. Register Your Plugin

In `pyproject.toml`:

```toml
[project]
name = "pycmor-plugin-cesm"
version = "0.1.0"
description = "CESM model plugin for pycmor"
dependencies = [
    "pycmor>=1.0.0",
]

[project.optional-dependencies]
test = [
    "pycmor[test]",  # Include pycmor's test dependencies
    "pytest>=7.0",
]

# Register your model via entry points
[project.entry-points."pycmor.models"]
cesm = "pycmor_plugin_cesm.model:CESMModelRun"
```

## Using Your Plugin

### Installation

Users install your plugin with the test extra:

```bash
pip install pycmor-plugin-cesm[test]
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
tests/test_generic_models.py::test_model_run_has_datadir[cesm] PASSED  ← Your model!
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

You can also add tests specific to your model in `tests/test_cesm_specific.py`:

```python
import pytest


def test_cesm_has_atmosphere_variables(cesm_model_run):
    """Test CESM-specific atmosphere variables."""
    ds = cesm_model_run.ds
    assert 'T' in ds.data_vars
    assert 'PS' in ds.data_vars
```

To make your model_run fixture available, create `conftest.py`:

```python
import pytest
from pycmor_plugin_cesm.model import CESMModelRun


@pytest.fixture(scope="session")
def cesm_model_run(request, tmp_path_factory):
    """CESM model run fixture for tests."""
    use_real = CESMModelRun.should_use_real_data(request)
    # Provide fixtures_dir pointing to your package's fixtures/
    from pathlib import Path
    fixtures_dir = Path(__file__).parent.parent / "src" / "pycmor_plugin_cesm" / "fixtures"

    return CESMModelRun(
        model_name="cesm",
        fixtures_dir=fixtures_dir,
        use_real=use_real,
        tmp_path_factory=tmp_path_factory,
    )
```

## Best Practices

1. **Use descriptive model names** - Name your ModelRun class clearly (e.g., `CESMModelRun`, not `ModelRun`)

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
