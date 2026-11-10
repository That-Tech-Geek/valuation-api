# Architecture and implementation status

## Shared engine

The crate exposes a pure Rust FCFF DCF function. The Axum HTTP API and optional PyO3 extension both call that function, preventing calculation drift between interfaces.

## Data path

The ingestion sidecar writes a Parquet snapshot and a JSON manifest. The API validates both at startup and loads rows into an immutable in-memory store. The manifest accepts structured dropped-ticker records emitted by the ingestion adapter. Duplicate tickers, invalid numbers, non-positive share counts and prices are rejected.

The API supports an authenticated atomic reload of a new local snapshot. It validates the replacement off the async executor and swaps the active store only after validation succeeds. A failed reload leaves the active snapshot untouched.

## Runtime contract

- `HOST` defaults to `0.0.0.0`; `PORT` defaults to `8080`; `DATA_PATH` defaults to `/data/fundamentals.parquet`.
- `API_ADMIN_TOKEN` enables `POST /admin/reload`; it must be at least 32 characters.
- `GET /health` is liveness, `GET /ready` is readiness, and `GET /meta` reports snapshot freshness and row counts.
- The Docker image runs as a non-root user and expects a read-only data mount.

## Data and deployment boundaries

- The current yfinance adapter is experimental. It does not establish redistribution rights, reliable statement normalization, or country-specific assumptions.
- The API does not fetch external data on request. The updater must publish a complete, validated snapshot before triggering reload.
- This repository has a linked Vercel project, but the project currently has no detected framework and is not yet verified as a running Rust API. The Docker image is portable to a container host; production hosting and ingress are separate deployment work.
- Public deployment requires HTTPS, rate limiting, private administration, monitoring and a licensed market-data source.

## Continuous performance gate

GitHub Actions runs quality and performance gates on pull requests, pushes to `main`, and daily at 02:17 UTC. It builds the release binary, runs Rust tests and Clippy, builds and tests the Python wheel, then benchmarks the actual Axum server against a deterministic 1,000-company Parquet snapshot.

| Measurement | Gate |
|---|---:|
| API startup and snapshot load | ≤ 2,000 ms |
| Single valuation HTTP p95 | ≤ 5 ms |
| 1,000-company JSON batch HTTP p95 | ≤ 200 ms |
| API process peak RSS | ≤ 250 MiB |
| Release binary | < 15 MiB |

These are repeatable GitHub-runner regression gates, not a production SLA. They do not measure external network latency or a deployed hosting environment.

## Release policy

Only in-scope changes to the Rust engine, Python SDK, ingestion layer, or package manifests are considered meaningful releases. Cargo and Python package versions must match and increase together. Eligible pull requests require maintainer authorization, automated diff review, passing CI/performance gates and a successful Vercel preview. After merge, the release workflow waits for main CI and Vercel production status before tagging and publishing to PyPI.
