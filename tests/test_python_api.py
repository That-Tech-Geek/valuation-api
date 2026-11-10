import pytest
native = pytest.importorskip("valuation_api")
def test_compute_dcf_returns_expected_contract():
    result = native.compute_dcf(100, .25, 10, 15, 5, 100, 20, 10, 20, 1, .04, .05, .08, .03)
    assert set(result) == {"wacc","enterprise_value","equity_value","fair_value_per_share","flags"}
    assert result["fair_value_per_share"] > 0
