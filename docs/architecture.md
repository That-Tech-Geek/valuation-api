# Architecture and implementation status

## Shared engine

The crate exposes a pure Rust DCF function. The Axum binary and optional PyO3 extension both call that function. This prevents valuation drift between HTTP and Python clients.

## Data path

The ingestion sidecar creates a complete Parquet snapshot and a manifest. The API loads and validates both at process startup; request handlers perform no network I/O. The first store implementation materializes validated rows in memory rather than claiming a zero-copy memory map.

## v1 boundaries

- No live prices, authentication, hot reload, sector-specific debt spreads, Monte Carlo or comps.
- The API binds to loopback by default. Add a reverse proxy and network boundary before deployment.
- Ingestion defaults are examples only. Configure country-specific assumptions and independently validate source statement mappings.

## Performance work remaining

The current batch endpoint uses the shared scalar kernel and builds JSON/Arrow output per request. It is functionally useful but is not yet certified against the 250 MB RSS, 200 ms batch p95, 5 ms single p95, 15 MB binary, or 500 ms cold-start targets. The next optimization pass should add Criterion benchmarks, process RSS measurement, preallocated output buffers, and an AVX2 implementation only if profiling proves it improves measured p95.
