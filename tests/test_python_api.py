import pytest
native = pytest.importorskip("valuation_api")

def sample():
    return dict(ebit=100, tax_rate=.25, da=10, capex=15, change_nwc=5,
        total_debt=100, cash=20, shares=10, price=20, beta=1,
        rf=.04, erp=.05, growth_5y=.08, terminal_growth=.03)

def test_compute_dcf_returns_expected_contract():
    result = native.compute_dcf(**sample())
    assert set(result) == {"wacc","enterprise_value","equity_value","fair_value_per_share","flags"}
    assert result["fair_value_per_share"] > 0

def test_compute_batch_uses_same_kernel():
    results = native.compute_batch([sample(), sample()])
    assert len(results) == 2
    assert results[0] == results[1]

def test_compute_batch_rejects_incomplete_rows():
    with pytest.raises(ValueError, match="missing required fields"):
        native.compute_batch([{"ebit": 1}])
