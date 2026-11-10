# valuation-api

A Rust FCFF discounted-cash-flow engine distributed as both an HTTP API and a Python package. Both interfaces call the same Rust implementation.

## Install the Python library

```bash
pip install valuation-api
```

```python
from valuation_api import compute_dcf

result = compute_dcf(
    ebit=100.0, tax_rate=0.25, da=10.0, capex=15.0,
    change_nwc=5.0, total_debt=100.0, cash=20.0,
    shares=10.0, price=20.0, beta=1.0, rf=0.04,
    erp=0.05, growth_5y=0.08, terminal_growth=0.03,
)
print(result["fair_value_per_share"])
```

## Run the HTTP API

Requires a valid Parquet snapshot and adjacent `fundamentals.manifest.json`.

```bash
cargo run --release -- --data data/fundamentals.parquet
```

- `GET /health`
- `GET /value/{ticker}?fmt=json|arrow`
- `GET /value/batch?fmt=json|arrow`

The server binds to `127.0.0.1:8080`. Batch requests are guarded by a single-permit semaphore. The v1 refresh endpoint is intentionally not exposed.

## Data ingestion

Install `ingestion/requirements.txt`, create a newline-delimited ticker file, then run:

```bash
python ingestion/fetch.py --tickers tickers.txt --out data/fundamentals.parquet
```

The ingestion script is a starter adapter, not an audited financial-data pipeline. yfinance field availability and statement labels vary by market. Configure local risk-free rate, ERP, currency, terminal growth and growth assumptions deliberately; do not treat generic defaults as investment advice. Missing required fields cause the ticker to be dropped and recorded in the manifest.

## Model

FCFF = EBIT × (1 − tax rate) + D&A − CapEx − change in NWC.

Cost of equity uses CAPM; cost of debt is risk-free rate + 2% in v1. The five-year explicit forecast grows the latest FCFF at the configured growth rate, followed by a Gordon-growth terminal value. Values and assumptions are in the row's reporting currency.

## Engineering notes

- The Parquet snapshot is loaded into immutable in-memory rows at startup. This first implementation prioritizes correctness and simple ownership; it does not claim zero-copy mmap.
- Batch computation currently shares the scalar reference kernel. SIMD specialization and measured 1,000-row p95/RSS gates are follow-up optimization work, not claimed as already achieved.
- Arrow IPC is emitted as an Arrow stream.
- The API does not fetch external data on request.
- Do not expose the unauthenticated API to the public internet; put it behind a trusted network boundary.

## Development

```bash
cargo fmt --all
cargo test --all-targets
cargo clippy --all-targets -- -D warnings
pip install maturin pytest
maturin develop --release
pytest -q
```

MIT License.
