"""Nightly fundamentals snapshot writer. Run with a curated ticker universe."""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


COLUMNS = [
    "ticker", "as_of_date", "currency", "sector", "revenue", "ebit",
    "effective_tax_rate", "da", "capex", "change_nwc", "total_debt",
    "cash", "shares_outstanding", "price", "beta", "risk_free_rate",
    "equity_risk_premium", "growth_5y", "terminal_growth",
]


def first_number(frame, keys, default=None):
    for key in keys:
        if key in frame.index:
            values = frame.loc[key].dropna()
            if len(values):
                return float(values.iloc[0])
    return default


def _latest_two_values(frame, label: str, keys: list[str]) -> tuple[float, float]:
    """Return latest and prior annual values; fail closed on incomplete statements."""
    key = next((candidate for candidate in keys if candidate in frame.index), None)
    if key is None:
        raise ValueError(f"balance sheet missing {label}")

    try:
        periods = sorted(frame.columns, key=lambda period: pd.Timestamp(period), reverse=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("balance sheet period labels must be valid dates") from exc
    if len(periods) < 2:
        raise ValueError(f"two balance sheet periods required for {label}")

    series = frame.loc[key]
    values = []
    for period in periods[:2]:
        value = series.loc[period]
        if pd.isna(value):
            raise ValueError(f"balance sheet missing {label} for {pd.Timestamp(period).date()}")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"balance sheet has non-finite {label}")
        values.append(number)
    return values[0], values[1]


def change_in_nwc(balance_sheet) -> float:
    """Derive ΔNWC = current operating NWC - prior operating NWC.

    Operating NWC excludes cash/short-term investments and current debt from
    current assets/current liabilities. Missing statement components are not
    silently treated as zero: the ticker is rejected instead.
    """
    current_assets = _latest_two_values(balance_sheet, "current assets", ["Current Assets", "Total Current Assets"])
    current_liabilities = _latest_two_values(
        balance_sheet, "current liabilities", ["Current Liabilities", "Total Current Liabilities"]
    )
    current_debt = _latest_two_values(
        balance_sheet,
        "current debt",
        [
            "Current Debt And Lease Obligation",
            "Current Debt",
            "Short Term Debt",
            "Current Portion Of Long Term Debt",
        ],
    )

    aggregate_cash_key = next(
        (
            key
            for key in (
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Cash Equivalents And Short Term Investments",
            )
            if key in balance_sheet.index
        ),
        None,
    )
    if aggregate_cash_key is not None:
        cash_and_short_term_investments = _latest_two_values(
            balance_sheet, "cash and short-term investments", [aggregate_cash_key]
        )
    else:
        cash = _latest_two_values(
            balance_sheet, "cash and cash equivalents", ["Cash And Cash Equivalents"]
        )
        short_term_investments = _latest_two_values(
            balance_sheet,
            "short-term investments",
            ["Other Short Term Investments", "Short Term Investments"],
        )
        cash_and_short_term_investments = (
            cash[0] + short_term_investments[0],
            cash[1] + short_term_investments[1],
        )

    current_nwc = (
        current_assets[0]
        - cash_and_short_term_investments[0]
        - current_liabilities[0]
        + current_debt[0]
    )
    prior_nwc = (
        current_assets[1]
        - cash_and_short_term_investments[1]
        - current_liabilities[1]
        + current_debt[1]
    )
    delta = current_nwc - prior_nwc
    if not math.isfinite(delta):
        raise ValueError("derived change in net working capital is non-finite")
    return delta


def fetch(ticker: str, defaults: dict) -> dict:
    obj = yf.Ticker(ticker)
    info = obj.get_info()
    fin = obj.financials
    bal = obj.balance_sheet
    if fin.empty or bal.empty:
        raise ValueError("financial statements unavailable")

    revenue = first_number(fin, ["Total Revenue"])
    ebit = first_number(fin, ["EBIT", "Operating Income"])
    da = first_number(fin, ["Reconciled Depreciation", "Depreciation And Amortization"])
    capex_raw = first_number(fin, ["Capital Expenditure", "Capital Expenditures"])
    if capex_raw is None:
        raise ValueError("missing capital expenditure; refusing to assume zero")
    capex = abs(capex_raw)

    tax_exp = first_number(fin, ["Tax Provision"])
    pretax = first_number(fin, ["Pretax Income"])
    tax = (
        min(0.5, max(0.0, tax_exp / pretax))
        if tax_exp is not None and pretax is not None and pretax > 0
        else defaults["tax_rate"]
    )

    debt = first_number(bal, ["Total Debt"])
    cash = first_number(
        bal,
        ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"],
    )
    if cash is None:
        cash_equivalents = first_number(bal, ["Cash And Cash Equivalents"])
        short_term_investments = first_number(
            bal, ["Other Short Term Investments", "Short Term Investments"]
        )
        if cash_equivalents is None or short_term_investments is None:
            raise ValueError("missing cash or short-term investments; refusing to assume zero")
        cash = cash_equivalents + short_term_investments
    if debt is None:
        raise ValueError("missing total debt; refusing to assume zero")

    change_nwc = change_in_nwc(bal)
    shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    required = [revenue, ebit, da, shares, price]
    if any(value is None for value in required):
        raise ValueError("missing required financial field")

    return dict(
        ticker=ticker,
        as_of_date=pd.Timestamp.now(tz="UTC").date(),
        currency=info.get("currency") or defaults["currency"],
        sector=info.get("sector") or "UNKNOWN",
        revenue=revenue,
        ebit=ebit,
        effective_tax_rate=tax,
        da=da,
        capex=capex,
        change_nwc=change_nwc,
        total_debt=debt,
        cash=cash,
        shares_outstanding=float(shares),
        price=float(price),
        beta=min(3.0, max(0.3, float(info.get("beta") or 1.0))),
        risk_free_rate=defaults["risk_free_rate"],
        equity_risk_premium=defaults["equity_risk_premium"],
        growth_5y=min(
            0.5, max(-0.1, float(info.get("revenueGrowth") or defaults["growth_5y"]))
        ),
        terminal_growth=defaults["terminal_growth"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", required=True, help="newline-delimited ticker file")
    parser.add_argument("--out", default="data/fundamentals.parquet")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--risk-free-rate", type=float, default=0.04)
    parser.add_argument("--erp", type=float, default=0.05)
    parser.add_argument("--terminal-growth", type=float, default=0.025)
    parser.add_argument("--growth", type=float, default=0.08)
    parser.add_argument("--tax-rate", type=float, default=0.25)
    args = parser.parse_args()
    defaults = dict(
        currency=args.currency,
        risk_free_rate=args.risk_free_rate,
        equity_risk_premium=args.erp,
        terminal_growth=args.terminal_growth,
        growth_5y=args.growth,
        tax_rate=args.tax_rate,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    dropped = []
    for ticker in Path(args.tickers).read_text().splitlines():
        ticker = ticker.strip()
        if not ticker or ticker.startswith("#"):
            continue
        try:
            for attempt in range(2):
                try:
                    row = fetch(ticker, defaults)
                    break
                except yf.exceptions.YFRateLimitError:
                    if attempt == 1:
                        raise
                    time.sleep(60)
            if (
                not all(pd.notna(row[column]) for column in COLUMNS)
                or row["shares_outstanding"] <= 0
                or row["price"] <= 0
            ):
                raise ValueError("null or invalid required value")
            rows.append(row)
        except Exception as exc:
            dropped.append({"ticker": ticker, "reason": str(exc)})
        time.sleep(0.2)

    if not rows:
        raise SystemExit("No valid rows; refusing to replace existing dataset")

    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"])
    frame.to_parquet(tmp, index=False, compression="snappy")
    with open(tmp, "rb") as file:
        os.fsync(file.fileno())
    os.replace(tmp, out)

    manifest = {
        "row_count": len(rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickers_dropped": dropped,
    }
    manifest_tmp = out.with_name("fundamentals.manifest.json.tmp")
    manifest_tmp.write_text(json.dumps(manifest, indent=2))
    os.replace(manifest_tmp, out.with_name("fundamentals.manifest.json"))
    print(json.dumps({"rows": len(rows), "dropped": len(dropped), "output": str(out)}))


if __name__ == "__main__":
    main()
