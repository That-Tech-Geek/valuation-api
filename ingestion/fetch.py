"""Nightly fundamentals snapshot writer. Run with a curated ticker universe."""
from __future__ import annotations
import argparse, json, os, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import yfinance as yf

COLUMNS = ["ticker","as_of_date","currency","sector","revenue","ebit","effective_tax_rate","da",
"capex","change_nwc","total_debt","cash","shares_outstanding","price","beta","risk_free_rate",
"equity_risk_premium","growth_5y","terminal_growth"]

def first_number(frame, keys, default=None):
    for key in keys:
        if key in frame.index:
            values = frame.loc[key].dropna()
            if len(values): return float(values.iloc[0])
    return default

def fetch(ticker: str, defaults: dict) -> dict:
    obj = yf.Ticker(ticker)
    info = obj.get_info()
    fin = obj.financials
    bal = obj.balance_sheet
    if fin.empty or bal.empty: raise ValueError("financial statements unavailable")
    revenue = first_number(fin, ["Total Revenue"])
    ebit = first_number(fin, ["EBIT","Operating Income"])
    da = first_number(fin, ["Reconciled Depreciation","Depreciation And Amortization"])
    capex = abs(first_number(fin, ["Capital Expenditure","Capital Expenditures"], 0.0))
    tax_exp = first_number(fin, ["Tax Provision"], 0.0)
    pretax = first_number(fin, ["Pretax Income"], 0.0)
    tax = min(0.5,max(0.0,tax_exp/pretax)) if pretax > 0 else defaults["tax_rate"]
    debt = first_number(bal, ["Total Debt","Long Term Debt"], 0.0)
    cash = first_number(bal, ["Cash And Cash Equivalents","Cash Cash Equivalents And Short Term Investments"], 0.0)
    shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    required = [revenue,ebit,da,shares,price]
    if any(v is None for v in required): raise ValueError("missing required financial field")
    return dict(ticker=ticker,as_of_date=pd.Timestamp.now(tz="UTC").date(),currency=info.get("currency") or defaults["currency"],
      sector=info.get("sector") or "UNKNOWN",revenue=revenue,ebit=ebit,effective_tax_rate=tax,da=da,capex=capex,
      change_nwc=0.0,total_debt=debt,cash=cash,shares_outstanding=float(shares),price=float(price),
      beta=min(3.0,max(0.3,float(info.get("beta") or 1.0))),risk_free_rate=defaults["risk_free_rate"],
      equity_risk_premium=defaults["equity_risk_premium"],growth_5y=min(.5,max(-.1,float(info.get("revenueGrowth") or defaults["growth_5y"]))),
      terminal_growth=defaults["terminal_growth"])

def main():
    p=argparse.ArgumentParser(); p.add_argument("--tickers",required=True,help="newline-delimited ticker file")
    p.add_argument("--out",default="data/fundamentals.parquet"); p.add_argument("--currency",default="USD")
    p.add_argument("--risk-free-rate",type=float,default=.04); p.add_argument("--erp",type=float,default=.05)
    p.add_argument("--terminal-growth",type=float,default=.025); p.add_argument("--growth",type=float,default=.08)
    p.add_argument("--tax-rate",type=float,default=.25); a=p.parse_args()
    defaults=dict(currency=a.currency,risk_free_rate=a.risk_free_rate,equity_risk_premium=a.erp,
                  terminal_growth=a.terminal_growth,growth_5y=a.growth,tax_rate=a.tax_rate)
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); tmp=out.with_suffix(out.suffix+".tmp")
    rows=[]; dropped=[]
    for ticker in Path(a.tickers).read_text().splitlines():
        ticker=ticker.strip()
        if not ticker or ticker.startswith("#"): continue
        try:
            for attempt in range(2):
                try:
                    row=fetch(ticker,defaults)
                    break
                except yf.exceptions.YFRateLimitError:
                    if attempt == 1: raise
                    time.sleep(60)
            if not all(pd.notna(row[c]) for c in COLUMNS) or row["shares_outstanding"] <= 0 or row["price"] <= 0:
                raise ValueError("null or invalid required value")
            rows.append(row)
        except Exception as exc:
            dropped.append({"ticker":ticker,"reason":str(exc)})
        time.sleep(.2)
    if not rows: raise SystemExit("No valid rows; refusing to replace existing dataset")
    frame=pd.DataFrame(rows,columns=COLUMNS)
    frame["as_of_date"]=pd.to_datetime(frame["as_of_date"])
    frame.to_parquet(tmp,index=False,compression="snappy")
    with open(tmp,"rb") as f: os.fsync(f.fileno())
    os.replace(tmp,out)
    manifest={"row_count":len(rows),"generated_at":datetime.now(timezone.utc).isoformat(),
              "tickers_dropped":dropped}
    mt=out.with_name("fundamentals.manifest.json.tmp")
    mt.write_text(json.dumps(manifest,indent=2)); os.replace(mt,out.with_name("fundamentals.manifest.json"))
    print(json.dumps({"rows":len(rows),"dropped":len(dropped),"output":str(out)}))
if __name__=="__main__": main()
