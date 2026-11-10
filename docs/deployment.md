# Deployment and operations

## Runtime contract

The Axum service is a stateless HTTP process over an immutable in-memory snapshot.

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind interface. Keep the service behind a trusted ingress or gateway. |
| `PORT` | `8080` | HTTP listen port. |
| `DATA_PATH` | `/data/fundamentals.parquet` | Snapshot file; the manifest must sit beside it. |
| `API_ADMIN_TOKEN` | unset | Optional 32+ character secret required for snapshot reload. |

The process refuses to start if the snapshot or its manifest is missing or invalid. The container runs as a non-root user and expects the data directory to be mounted read-only.

## Build and run locally

Generate a snapshot first using the ingestion workflow described in the README, then:

```bash
docker compose build
API_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" docker compose up -d
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl http://localhost:8080/meta
curl "http://localhost:8080/value/AAPL"
```

Do not use the example ticker unless it exists in your loaded universe.

## Endpoints

- `GET /health`: process liveness only; it does not claim that data is loaded.
- `GET /ready`: readiness and loaded row count.
- `GET /meta`: snapshot timestamp, age, row count and dropped ticker count.
- `GET /value/{ticker}?fmt=json|arrow`: one valuation.
- `GET /value/batch?fmt=json|arrow`: the loaded universe; a single concurrent batch is admitted.
- `POST /admin/reload`: validates and atomically swaps the mounted snapshot. Requires `x-admin-token: $API_ADMIN_TOKEN`.

Reload is fail-safe: the currently active snapshot remains available if the replacement cannot be loaded. The new Parquet file and its manifest must be written to temporary files and atomically renamed into place before calling reload. Never write into a read-only mount from the API container.

## Production deployment requirements

This repository currently has a Vercel Git project, but its detected framework is null and the project is not yet verified as a live API service. A successful Vercel build status is not proof that this Rust process is running. Deploy this container to a host that supports long-running containers, or deliberately port the HTTP layer to a supported serverless runtime while keeping the Rust kernel shared.

Before exposing the API publicly:

1. Put it behind HTTPS ingress and a rate-limiting gateway.
2. Restrict `POST /admin/reload` to a private network and a secret stored in the deployment platform's secret manager.
3. Configure an explicit data provider and licensed market universe. Do not assume yfinance redistribution rights.
4. Add monitoring for snapshot age, failed refreshes, dropped symbols, 4xx/5xx rates and request latency.
5. Test backup/rollback of both the Parquet file and its manifest.
6. Set resource limits and a deployment health check against `/ready`.

No market-data provider credentials or hosting secrets are included in this repository.
