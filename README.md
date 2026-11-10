# valuation

A Rust FCFF discounted-cash-flow engine distributed as both an HTTP API and a Python package. Both interfaces call the same Rust implementation.

## Install the Python library

```bash
pip install valuation
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

The install/distribution name is `valuation`; the Python import namespace remains `valuation_api`.

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

## Development

```bash
cargo fmt --all
cargo test --all-targets
cargo clippy --all-targets -- -D warnings
pip install maturin pytest
maturin develop --release
pytest -q
```

## Publishing to PyPI

Releases are automated after a meaningful, versioned product change is merged to `main`.

1. Create the `pypi` GitHub Actions environment.
2. Create a PyPI API token for the `valuation` project (prefer a project-scoped token). Do not paste the token into source code, commits, issues, or chat.
3. Add it as the environment secret named exactly `PYPI_TOKEN` under **Settings → Environments → pypi → Environment secrets**.
4. Keep `Cargo.toml` and `pyproject.toml` on the same higher stable SemVer version for each significant release.
5. The release workflow waits for main-branch CI/performance gates and a successful Vercel production deployment, then creates the version tag and dispatches the tag-validated PyPI build.

The PyPI workflow builds wheels for supported OS/Python combinations and an sdist, reruns Rust/Python validation, and publishes the artifacts. A failed or missing CI/Vercel result withholds publication. Publishing a version is irreversible on PyPI; increment the version for every subsequent release.

**PyPI name check required:** the intended distribution name is `valuation`. Its availability has not been conclusively verified, so the first release must not proceed until the project URL is checked and the name is confirmed available. PyPI project names are globally unique.

## Engineering notes

- The Parquet snapshot is loaded into immutable in-memory rows at startup. This first implementation prioritizes correctness and simple ownership; it does not claim zero-copy mmap.
- Batch computation currently shares the scalar reference kernel. SIMD specialization and measured 1,000-row p95/RSS gates are follow-up optimization work, not claimed as already achieved.
- Arrow IPC is emitted as an Arrow stream.
- The API does not fetch external data on request.
- Do not expose the unauthenticated API to the public internet; put it behind a trusted network boundary.

MIT License.
