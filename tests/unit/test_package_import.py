"""Unit tests for the application package layout."""

import campaignnarrator


def test_package_exposes_module_name() -> None:
    """The package should remain importable from the app layout."""

    assert campaignnarrator.__name__ == "campaignnarrator"
