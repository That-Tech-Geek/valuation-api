use arrow::{
    array::{ArrayRef, Float64Array, StringArray},
    datatypes::{DataType, Field, Schema},
    ipc::writer::StreamWriter,
    record_batch::RecordBatch,
};
use axum::{
    extract::{Path, Query, State},
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::Deserialize;
use std::{path::PathBuf, sync::Arc};
use subtle::ConstantTimeEq;
use tokio::sync::{RwLock, Semaphore};
use valuation_api::{
    compute,
    model::{DcfInputs, Valuation},
    store::Store,
};

#[derive(Clone)]
struct AppState {
    store: Arc<Store>,
    data_path: Arc<PathBuf>,
    admin_token: Option<Arc<String>>,
    batch_gate: Arc<Semaphore>,
}

type SharedState = Arc<RwLock<AppState>>;

#[derive(Deserialize)]
struct Format {
    fmt: Option<String>,
}

#[derive(serde::Serialize)]
struct ApiError {
    error: &'static str,
    detail: String,
}

fn err(status: StatusCode, code: &'static str, detail: impl Into<String>) -> Response {
    (
        status,
        Json(ApiError {
            error: code,
            detail: detail.into(),
        }),
    )
        .into_response()
}

fn value(c: &valuation_api::Company) -> Valuation {
    let o = compute(&DcfInputs::from(c));
    let mos = if c.price.abs() > f64::EPSILON {
        o.fair_value_per_share / c.price - 1.0
    } else {
        f64::NAN
    };
    Valuation {
        ticker: c.ticker.clone(),
        as_of_date: c.as_of_date,
        currency: c.currency.clone(),
        wacc: o.wacc,
        terminal_growth: o.terminal_growth,
        enterprise_value: o.enterprise_value,
        equity_value: o.equity_value,
        fair_value_per_share: o.fair_value_per_share,
        market_price: c.price,
        margin_of_safety: mos,
        flags: o.flags.names().into_iter().map(str::to_owned).collect(),
    }
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({"status": "ok"}))
}

async fn ready(State(state): State<SharedState>) -> Response {
    let store = state.read().await.store.clone();
    if store.is_empty() {
        return err(
            StatusCode::SERVICE_UNAVAILABLE,
            "DATA_UNAVAILABLE",
            "no valuation rows are loaded",
        );
    }
    Json(serde_json::json!({
        "status": "ready",
        "rows": store.len(),
        "generated_at": store.manifest.generated_at,
    }))
    .into_response()
}

async fn metadata(State(state): State<SharedState>) -> Json<serde_json::Value> {
    let store = state.read().await.store.clone();
    let generated_at = store.manifest.generated_at.clone();
    let age_seconds = chrono::DateTime::parse_from_rfc3339(&generated_at)
        .ok()
        .map(|value| {
            (chrono::Utc::now() - value.with_timezone(&chrono::Utc))
                .num_seconds()
                .max(0)
        });
    Json(serde_json::json!({
        "engine": "valuation-api",
        "data": {
            "rows": store.len(),
            "generated_at": generated_at,
            "age_seconds": age_seconds,
            "dropped_tickers": store.manifest.tickers_dropped.len(),
        },
        "formats": ["json", "arrow"],
    }))
}

async fn single(
    Path(ticker): Path<String>,
    Query(q): Query<Format>,
    State(state): State<SharedState>,
) -> Response {
    if !matches!(q.fmt.as_deref(), None | Some("json") | Some("arrow")) {
        return err(
            StatusCode::BAD_REQUEST,
            "INVALID_FORMAT",
            "fmt must be json or arrow",
        );
    }
    let store = state.read().await.store.clone();
    let Some(company) = store.get(&ticker) else {
        return err(
            StatusCode::NOT_FOUND,
            "TICKER_NOT_FOUND",
            format!("{ticker} is not in the loaded universe"),
        );
    };
    let result = value(company);
    if q.fmt.as_deref() == Some("arrow") {
        return arrow_response(vec![result]);
    }
    Json(result).into_response()
}

async fn batch(Query(q): Query<Format>, State(state): State<SharedState>) -> Response {
    if !matches!(q.fmt.as_deref(), None | Some("json") | Some("arrow")) {
        return err(
            StatusCode::BAD_REQUEST,
            "INVALID_FORMAT",
            "fmt must be json or arrow",
        );
    }
    let (store, gate) = {
        let guard = state.read().await;
        (guard.store.clone(), guard.batch_gate.clone())
    };
    let Ok(_permit) = gate.try_acquire_owned() else {
        return err(
            StatusCode::TOO_MANY_REQUESTS,
            "OVERLOADED",
            "batch capacity is busy; retry shortly",
        );
    };
    let results: Vec<Valuation> = store.rows().iter().map(value).collect();
    if q.fmt.as_deref() == Some("arrow") {
        arrow_response(results)
    } else {
        Json(serde_json::json!({"results": results})).into_response()
    }
}

async fn reload(headers: HeaderMap, State(state): State<SharedState>) -> Response {
    let (expected, data_path) = {
        let guard = state.read().await;
        (guard.admin_token.clone(), guard.data_path.as_ref().clone())
    };
    let Some(expected) = expected else {
        return err(
            StatusCode::SERVICE_UNAVAILABLE,
            "RELOAD_DISABLED",
            "API_ADMIN_TOKEN is not configured",
        );
    };
    let supplied = headers
        .get("x-admin-token")
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    let authorized = expected.len() == supplied.len()
        && expected.as_bytes().ct_eq(supplied.as_bytes()).unwrap_u8() == 1;
    if !authorized {
        return err(
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            "a valid x-admin-token header is required",
        );
    }

    let loaded = match tokio::task::spawn_blocking(move || Store::load(&data_path)).await {
        Ok(Ok(store)) => store,
        Ok(Err(error)) => {
            return err(
                StatusCode::UNPROCESSABLE_ENTITY,
                "SNAPSHOT_INVALID",
                error.to_string(),
            );
        }
        Err(error) => {
            return err(
                StatusCode::INTERNAL_SERVER_ERROR,
                "RELOAD_FAILED",
                error.to_string(),
            );
        }
    };
    let rows = loaded.len();
    let generated_at = loaded.manifest.generated_at.clone();
    state.write().await.store = Arc::new(loaded);
    Json(serde_json::json!({
        "status": "reloaded",
        "rows": rows,
        "generated_at": generated_at,
    }))
    .into_response()
}

fn arrow_response(rows: Vec<Valuation>) -> Response {
    let schema = Arc::new(Schema::new(vec![
        Field::new("ticker", DataType::Utf8, false),
        Field::new("fair_value_per_share", DataType::Float64, false),
        Field::new("wacc", DataType::Float64, false),
        Field::new("margin_of_safety", DataType::Float64, false),
        Field::new("flags", DataType::Utf8, false),
    ]));
    let cols: Vec<ArrayRef> = vec![
        Arc::new(StringArray::from(
            rows.iter().map(|r| r.ticker.as_str()).collect::<Vec<_>>(),
        )),
        Arc::new(Float64Array::from(
            rows.iter()
                .map(|r| r.fair_value_per_share)
                .collect::<Vec<_>>(),
        )),
        Arc::new(Float64Array::from(
            rows.iter().map(|r| r.wacc).collect::<Vec<_>>(),
        )),
        Arc::new(Float64Array::from(
            rows.iter().map(|r| r.margin_of_safety).collect::<Vec<_>>(),
        )),
        Arc::new(StringArray::from(
            rows.iter().map(|r| r.flags.join(",")).collect::<Vec<_>>(),
        )),
    ];
    let Ok(batch) = RecordBatch::try_new(schema.clone(), cols) else {
        return err(
            StatusCode::INTERNAL_SERVER_ERROR,
            "ARROW_ENCODING",
            "could not build Arrow record batch",
        );
    };
    let mut bytes = Vec::new();
    let result = StreamWriter::try_new(&mut bytes, &schema).and_then(|mut writer| {
        writer.write(&batch)?;
        writer.finish()
    });
    if result.is_err() {
        return err(
            StatusCode::INTERNAL_SERVER_ERROR,
            "ARROW_ENCODING",
            "could not encode Arrow stream",
        );
    }
    (
        [(header::CONTENT_TYPE, "application/vnd.apache.arrow.stream")],
        bytes,
    )
        .into_response()
}

fn data_path() -> PathBuf {
    let cli_path = std::env::args()
        .skip_while(|arg| arg != "--data")
        .nth(1)
        .map(PathBuf::from);
    cli_path
        .or_else(|| std::env::var_os("DATA_PATH").map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("/data/fundamentals.parquet"))
}

#[tokio::main]
async fn main() {
    let path = data_path();
    let store = Store::load(&path).unwrap_or_else(|error| {
        eprintln!("DATA_UNAVAILABLE: {error}");
        std::process::exit(1);
    });
    let admin_token = std::env::var("API_ADMIN_TOKEN")
        .ok()
        .filter(|value| !value.is_empty());
    if admin_token.as_ref().is_some_and(|value| value.len() < 32) {
        eprintln!("CONFIGURATION_ERROR: API_ADMIN_TOKEN must contain at least 32 characters");
        std::process::exit(1);
    }
    let state: SharedState = Arc::new(RwLock::new(AppState {
        store: Arc::new(store),
        data_path: Arc::new(path),
        admin_token: admin_token.map(Arc::new),
        batch_gate: Arc::new(Semaphore::new(1)),
    }));
    let app = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/meta", get(metadata))
        .route("/value/{ticker}", get(single))
        .route("/value/batch", get(batch))
        .route("/admin/reload", post(reload))
        .with_state(state);

    let host = std::env::var("HOST").unwrap_or_else(|_| "0.0.0.0".into());
    let port = std::env::var("PORT")
        .unwrap_or_else(|_| "8080".into())
        .parse::<u16>()
        .unwrap_or_else(|_| {
            eprintln!("CONFIGURATION_ERROR: PORT must be a valid TCP port");
            std::process::exit(1);
        });
    let address = format!("{host}:{port}");
    let listener = tokio::net::TcpListener::bind(&address)
        .await
        .unwrap_or_else(|error| {
            eprintln!("BIND_ERROR: {address}: {error}");
            std::process::exit(1);
        });
    println!("valuation-api listening on {address}");
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await
        .expect("server");
}
