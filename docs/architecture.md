# Architecture and implementation status

## Shared engine

The crate exposes a pure Rust DCF function. The Axum binary and optional PyO3 extension both call that function. This prevents valuation drift between HTTP and Python clients.

## Data path

The ingestion sidecar creates a complete Parquet snapshot and a manifest. The API loads and validates both at process startup; request handlers perform no network I/O. The first store implementation materializes validated rows in memory rather than claiming a zero-copy memory map.

## v1 boundaries

- No live prices, authentication, hot reload, sector-specific debt spreads, Monte Carlo or comps.
- The API binds to loopback by default. Add a reverse proxy and network boundary before deployment.
- Ingestion defaults are examples only. Configure country-specific assumptions and independently validate source statement mappings.

## Continuous performance gate

GitHub Actions runs the same quality and performance gate on every pull request, every push to `main`, and daily at 02:17 UTC (07:47 Asia/Kolkata). It builds the release binary, runs Rust tests and Clippy, builds and tests the Python wheel, then launches the actual Axum server against a deterministic 1,000-company Parquet snapshot.

The current CI budgets are:

| Measurement | Gate |
|---|---:|
| API startup and snapshot load | ≤ 2,000 ms |
| Single valuation HTTP p95 | ≤ 5 ms |
| 1,000-company JSON batch HTTP p95 | ≤ 200 ms |
| API process peak RSS | ≤ 250 MiB |
| Release binary | < 15 MiB |

Latency includes loopback HTTP and response serialization. Peak RSS is measured for the API process, including a kernel-reported child-process high-water mark. The benchmark report is retained as a workflow artifact for 30 days.

These are repeatable GitHub-runner regression gates, not a production SLA or proof of performance on every host, network, dataset, or deployment region. A failing, missing, or out-of-scope check blocks automated merging.

## Release policy

Only in-scope changes to the Rust engine, Python SDK, ingestion layer, or package manifests are considered meaningful releases. Both Cargo and Python package versions must be bumped to the same higher stable SemVer version. Documentation-only, test-only, and housekeeping changes remain open for maintainer handling and do not trigger PyPI publication.

Eligible pull requests require an approval from the repository maintainer on the exact head commit, passing CI/performance gates, and a successful Vercel preview. After merge, the release workflow waits for the main-branch CI gate and Vercel production deployment to succeed before creating the version tag and dispatching the tag-validated PyPI workflow. Any failed, missing, or out-of-scope condition withholds the release.
