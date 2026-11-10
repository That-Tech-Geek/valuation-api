from datetime import date
from pathlib import Path
import json
import pyarrow as pa
import pyarrow.parquet as pq

out = Path("data/fixtures")
out.mkdir(parents=True, exist_ok=True)
schema = pa.schema([
    ("ticker", pa.string()), ("as_of_date", pa.date32()), ("currency", pa.string()), ("sector", pa.string()),
    ("revenue", pa.float64()), ("ebit", pa.float64()), ("effective_tax_rate", pa.float64()),
    ("da", pa.float64()), ("capex", pa.float64()), ("change_nwc", pa.float64()),
    ("total_debt", pa.float64()), ("cash", pa.float64()), ("shares_outstanding", pa.float64()),
    ("price", pa.float64()), ("beta", pa.float64()), ("risk_free_rate", pa.float64()),
    ("equity_risk_premium", pa.float64()), ("growth_5y", pa.float64()), ("terminal_growth", pa.float64()),
])
rows = []
for i in range(10):
    rows.append({
        "ticker": f"FIX{i:02}.X", "as_of_date": date(2026, 9, 30), "currency": "USD", "sector": "Technology",
        "revenue": 1_000_000.0 + i * 100_000, "ebit": 150_000.0 + i * 10_000,
        "effective_tax_rate": 0.25, "da": 20_000.0, "capex": 25_000.0, "change_nwc": 5_000.0,
        "total_debt": 100_000.0, "cash": 50_000.0, "shares_outstanding": 10_000.0 + i * 100,
        "price": 25.0 + i, "beta": 1.0, "risk_free_rate": 0.04, "equity_risk_premium": 0.05,
        "growth_5y": 0.08, "terminal_growth": 0.025,
    })
table = pa.Table.from_pylist(rows, schema=schema)
target = out / "sample.parquet"
tmp = target.with_suffix(".parquet.tmp")
pq.write_table(table, tmp, compression="snappy")
tmp.replace(target)
(out / "fundamentals.manifest.json").write_text(json.dumps({
    "row_count": len(rows), "generated_at": "2026-11-10T00:00:00Z", "tickers_dropped": []
}, indent=2))
print(f"wrote {len(rows)} fixture rows to {target}")
