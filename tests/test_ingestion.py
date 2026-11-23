import pandas as pd
import pytest

from ingestion.fetch import change_in_nwc


def test_change_in_nwc_uses_two_periods_and_excludes_cash_and_current_debt():
    balance_sheet = pd.DataFrame(
        {
            pd.Timestamp("2024-12-31"): [450.0, 90.0, 280.0, 30.0],
            pd.Timestamp("2025-12-31"): [500.0, 100.0, 300.0, 40.0],
        },
        index=[
            "Current Assets",
            "Cash Cash Equivalents And Short Term Investments",
            "Current Liabilities",
            "Current Debt And Lease Obligation",
        ],
    )

    # Latest NWC = 500 - 100 - 300 + 40 = 140.
    # Prior NWC  = 450 -  90 - 280 + 30 = 110.
    assert change_in_nwc(balance_sheet) == pytest.approx(30.0)


def test_change_in_nwc_supports_separate_cash_and_short_term_investments():
    balance_sheet = pd.DataFrame(
        {
            pd.Timestamp("2024-12-31"): [450.0, 70.0, 20.0, 280.0, 30.0],
            pd.Timestamp("2025-12-31"): [500.0, 75.0, 25.0, 300.0, 40.0],
        },
        index=[
            "Current Assets",
            "Cash And Cash Equivalents",
            "Other Short Term Investments",
            "Current Liabilities",
            "Current Debt",
        ],
    )

    assert change_in_nwc(balance_sheet) == pytest.approx(30.0)


def test_change_in_nwc_rejects_missing_prior_period():
    balance_sheet = pd.DataFrame(
        {pd.Timestamp("2025-12-31"): [500.0, 100.0, 300.0, 40.0]},
        index=[
            "Current Assets",
            "Cash Cash Equivalents And Short Term Investments",
            "Current Liabilities",
            "Current Debt And Lease Obligation",
        ],
    )

    with pytest.raises(ValueError, match="two balance sheet periods"):
        change_in_nwc(balance_sheet)


def test_change_in_nwc_rejects_missing_components_instead_of_zero_filling():
    balance_sheet = pd.DataFrame(
        {
            pd.Timestamp("2024-12-31"): [450.0, 90.0, 280.0],
            pd.Timestamp("2025-12-31"): [500.0, 100.0, 300.0],
        },
        index=["Current Assets", "Cash Cash Equivalents And Short Term Investments", "Current Liabilities"],
    )

    with pytest.raises(ValueError, match="current debt"):
        change_in_nwc(balance_sheet)


def test_fetch_uses_derived_change_in_nwc_and_requires_real_capex_debt_and_cash(monkeypatch):
    from ingestion import fetch as ingestion_module

    periods = [pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31")]
    financials = pd.DataFrame(
        {
            periods[0]: [1000.0, 100.0, 10.0, -15.0, 20.0, 80.0],
        },
        index=[
            "Total Revenue",
            "EBIT",
            "Reconciled Depreciation",
            "Capital Expenditure",
            "Tax Provision",
            "Pretax Income",
        ],
    )
    balance_sheet = pd.DataFrame(
        {
            periods[0]: [500.0, 100.0, 300.0, 40.0, 100.0, 20.0],
            periods[1]: [450.0, 90.0, 280.0, 30.0, 90.0, 15.0],
        },
        index=[
            "Current Assets",
            "Cash Cash Equivalents And Short Term Investments",
            "Current Liabilities",
            "Current Debt And Lease Obligation",
            "Total Debt",
            "Cash And Cash Equivalents",
        ],
    )

    class FakeTicker:
        def get_info(self):
            return {
                "sharesOutstanding": 10.0,
                "currentPrice": 20.0,
                "currency": "USD",
                "beta": 1.0,
                "revenueGrowth": 0.08,
            }

        @property
        def financials(self):
            return financials

        @property
        def balance_sheet(self):
            return balance_sheet

    monkeypatch.setattr(ingestion_module.yf, "Ticker", lambda _: FakeTicker())
    defaults = {
        "currency": "USD",
        "risk_free_rate": 0.04,
        "equity_risk_premium": 0.05,
        "growth_5y": 0.08,
        "terminal_growth": 0.025,
        "tax_rate": 0.25,
    }

    row = ingestion_module.fetch("TEST", defaults)
    assert row["change_nwc"] == pytest.approx(30.0)
    assert row["capex"] == pytest.approx(15.0)
    assert row["total_debt"] == pytest.approx(100.0)
    assert row["cash"] == pytest.approx(100.0)

    # If Yahoo reports cash and short-term investments separately, the equity
    # bridge must use their sum rather than cash alone.
    separate_balance_sheet = balance_sheet.drop(
        index="Cash Cash Equivalents And Short Term Investments"
    ).copy()
    separate_balance_sheet.loc["Other Short Term Investments"] = [80.0, 75.0]

    class SeparateCashTicker(FakeTicker):
        @property
        def balance_sheet(self):
            return separate_balance_sheet

    monkeypatch.setattr(ingestion_module.yf, "Ticker", lambda _: SeparateCashTicker())
    separate_row = ingestion_module.fetch("TEST", defaults)
    assert separate_row["cash"] == pytest.approx(100.0)
    assert separate_row["change_nwc"] == pytest.approx(30.0)

    incomplete_financials = financials.drop(index="Capital Expenditure")
    monkeypatch.setattr(
        ingestion_module.yf,
        "Ticker",
        lambda _: type(
            "NoCapexTicker",
            (),
            {
                "get_info": lambda self: FakeTicker().get_info(),
                "financials": property(lambda self: incomplete_financials),
                "balance_sheet": property(lambda self: balance_sheet),
            },
        )(),
    )
    with pytest.raises(ValueError, match="capital expenditure"):
        ingestion_module.fetch("TEST", defaults)



def test_change_in_nwc_rejects_missing_short_term_investment_component():
    balance_sheet = pd.DataFrame(
        {
            pd.Timestamp("2024-12-31"): [450.0, 70.0, 280.0, 30.0],
            pd.Timestamp("2025-12-31"): [500.0, 75.0, 300.0, 40.0],
        },
        index=[
            "Current Assets",
            "Cash And Cash Equivalents",
            "Current Liabilities",
            "Current Debt",
        ],
    )

    with pytest.raises(ValueError, match="short-term investments"):
        change_in_nwc(balance_sheet)
