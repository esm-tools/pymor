import pytest


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
