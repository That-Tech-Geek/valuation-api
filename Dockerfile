FROM rust:1.89-bookworm AS builder
WORKDIR /app

COPY Cargo.toml ./
COPY src ./src
RUN cargo build --release --bin valuation-api

FROM debian:bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 valuation \
    && useradd --system --uid 10001 --gid valuation --no-create-home valuation
COPY --from=builder /app/target/release/valuation-api /usr/local/bin/valuation-api

ENV HOST=0.0.0.0 \
    PORT=8080 \
    DATA_PATH=/data/fundamentals.parquet
WORKDIR /app
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["valuation-api"]
