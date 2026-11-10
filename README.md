# valuation

A Rust FCFF discounted-cash-flow engine exposed through a Python package and an HTTP API. The Rust calculation kernel is shared by both interfaces.

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

The install/distribution name is `valuation`; the Python import namespace is `valuation_api`.

## Run the HTTP API

Requires a validated Parquet snapshot and adjacent `fundamentals.manifest.json`.

```bash
cargo run --release -- --data data/fundamentals.parquet
```

The service listens on `0.0.0.0:8080` by default. Override with `HOST` and `PORT`, and set `DATA_PATH` when not using `--data`.

- `GET /health`: liveness
- `GET /ready`: readiness and row count
- `GET /meta`: snapshot timestamp and freshness
- `GET /value/{ticker}?fmt=json|arrow`
- `GET /value/batch?fmt=json|arrow`
- `POST /admin/reload`: authenticated, atomic snapshot reload

The reload endpoint requires `API_ADMIN_TOKEN` (minimum 32 characters) and an `x-admin-token` request header. If the replacement snapshot fails validation, the active snapshot is retained. See [deployment and operations](docs/deployment.md).

## Container

```bash
docker compose build
API_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" docker compose up -d
curl http://localhost:8080/ready
```

Mount the data directory read-only. The image runs as a non-root user. See [deployment and operations](docs/deployment.md) for production requirements.

## Data ingestion

Install `ingestion/requirements.txt`, create a newline-delimited ticker file, then run:

```bash
python ingestion/fetch.py --tickers tickers.txt --out data/fundamentals.parquet
```

The current yfinance adapter is an experimental starter, not a licensed or audited financial-data service. Field availability and statement labels vary by market and issuer. Do not redistribute its output commercially without confirming source terms. The current adapter also uses illustrative defaults for risk-free rate, ERP, tax, growth and terminal growth; configure and validate these by market. Missing fields are recorded in the manifest.

## Model

FCFF = EBIT × (1 − tax rate) + D&A − CapEx − change in NWC.

Cost of equity uses CAPM; cost of debt is risk-free rate + 2% in v1. The five-year explicit forecast grows the latest FCFF at the configured growth rate, followed by a Gordon-growth terminal value. Values and assumptions are in the row's reporting currency.

## Development

```bash
cargo fmt --all -- --check
cargo test --all-targets
cargo clippy --all-targets -- -D warnings
pip install maturin pytest
maturin develop --release
pytest -q
```

## Publishing to PyPI

A release workflow automatically builds and publishes a new version after a meaningful, versioned product change is merged to `main`, the main CI/performance gate passes, and Vercel reports a successful production deployment.

The workflow requires the `pypi` GitHub Actions environment and its `PYPI_TOKEN` secret. Prefer a project-scoped PyPI token, or migrate to PyPI Trusted Publishing before the first public release. Never commit credentials.

Both `Cargo.toml` and `pyproject.toml` must use the same higher stable SemVer version. PyPI releases are immutable; increment the version for each release.

**First publication is not yet verified.** Confirm that the intended PyPI project name `valuation` is available and that the `pypi` environment secret is configured before the first publication attempt.

## Limitations

- The API serves a snapshot; it does not fetch market data on request.
- The current ingestion adapter is not production-grade and no licensed market-data universe is bundled.
- The service is container-ready but this repository's Vercel project has not yet been validated as a live Rust API deployment.
- No public API rate limiting or end-user API-key system is included. Put the service behind a trusted gateway before exposing it.
- DCF output is model output, not investment advice or a guaranteed fair value.

MIT License.
