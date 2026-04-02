import pytest

from pycmor.data_request.variable import CMIP7DataRequestVariable


@pytest.fixture
def dr_sos():
    """Fixture for ocean salinity DataRequestVariable.

    Import is done inside the fixture to avoid pulling in heavy dependencies
    during pytest collection phase.
    """
    from pycmor.data_request.variable import DataRequestVariable

    return DataRequestVariable(
        variable_id="sos",
        unit="0.001",
        description="Salinity of the ocean",
        time_method="MEAN",
        table="Omon",
        frequency="Monthly",
        realms="Ocean",
        standard_name="salinity_ocean",
        cell_methods="area: mean where sea",
        cell_measures="area: areacello",
    )


@pytest.fixture
def dr_cmip7_tas():
    """CMIP7 DataRequestVariable for tas (near-surface air temperature).

    Loaded from the vendored all_var_info.json using the CMIP6-style
    compound name key 'Amon.tas'.
    """
    return CMIP7DataRequestVariable.from_all_var_info_json("Amon.tas")


@pytest.fixture
def dr_cmip7_thetao():
    """CMIP7 DataRequestVariable for thetao (sea water potential temperature).

    Loaded from the vendored all_var_info.json using the CMIP6-style
    compound name key 'Omon.thetao'.
    """
    return CMIP7DataRequestVariable.from_all_var_info_json("Omon.thetao")
