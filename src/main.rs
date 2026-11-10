use axum::{extract::{Path, Query, State}, http::{header, StatusCode}, response::{IntoResponse, Response}, routing::get, Json, Router};
use arrow::{array::{ArrayRef, Float64Array, StringArray}, datatypes::{DataType, Field, Schema}, record_batch::RecordBatch, ipc::writer::StreamWriter};
use serde::Deserialize;
use std::{path::PathBuf, sync::Arc};
use tokio::sync::Semaphore;
use valuation_api::{compute, model::{DcfInputs, Valuation}, store::Store};

#[derive(Clone)]
struct AppState { store: Arc<Store>, batch_gate: Arc<Semaphore> }
#[derive(Deserialize)] struct Format { fmt: Option<String> }
#[derive(serde::Serialize)] struct ApiError { error: &'static str, detail: String }
fn err(status: StatusCode, code: &'static str, detail: impl Into<String>) -> Response {
    (status, Json(ApiError { error:code, detail:detail.into() })).into_response()
}
fn value(c: &valuation_api::Company) -> Valuation {
    let o = compute(&DcfInputs::from(c));
    let mos = if c.price.abs() > f64::EPSILON { o.fair_value_per_share / c.price - 1.0 } else { f64::NAN };
    Valuation { ticker:c.ticker.clone(), as_of_date:c.as_of_date, currency:c.currency.clone(), wacc:o.wacc,
        terminal_growth:c.terminal_growth, enterprise_value:o.enterprise_value, equity_value:o.equity_value,
        fair_value_per_share:o.fair_value_per_share, market_price:c.price, margin_of_safety:mos, flags:o.flags.names().into_iter().map(str::to_owned).collect() }
}
async fn health(State(s):State<AppState>) -> Json<serde_json::Value> {
    Json(serde_json::json!({"status":"ok","rows":s.store.len(),"generated_at":s.store.manifest.generated_at}))
}
async fn single(Path(ticker):Path<String>, Query(q):Query<Format>, State(s):State<AppState>) -> Response {
    if !matches!(q.fmt.as_deref(),None|Some("json")|Some("arrow")) { return err(StatusCode::BAD_REQUEST,"INVALID_FORMAT","fmt must be json or arrow"); }
    let Some(c) = s.store.get(&ticker) else { return err(StatusCode::NOT_FOUND,"TICKER_NOT_FOUND",format!("{ticker} is not in the loaded universe")); };
    let v = value(c);
    if q.fmt.as_deref() == Some("arrow") { return arrow_response(vec![v]); }
    Json(v).into_response()
}
async fn batch(Query(q):Query<Format>, State(s):State<AppState>) -> Response {
    if !matches!(q.fmt.as_deref(),None|Some("json")|Some("arrow")) { return err(StatusCode::BAD_REQUEST,"INVALID_FORMAT","fmt must be json or arrow"); }
    let Ok(_permit) = s.batch_gate.clone().try_acquire_owned() else { return err(StatusCode::TOO_MANY_REQUESTS,"OVERLOADED","batch capacity is busy; retry shortly"); };
    let results: Vec<Valuation> = s.store.rows().iter().map(value).collect();
    if q.fmt.as_deref() == Some("arrow") { arrow_response(results) }
    else { Json(serde_json::json!({"results":results})).into_response() }
}
fn arrow_response(rows: Vec<Valuation>) -> Response {
    let schema = Arc::new(Schema::new(vec![
        Field::new("ticker",DataType::Utf8,false), Field::new("fair_value_per_share",DataType::Float64,false),
        Field::new("wacc",DataType::Float64,false), Field::new("margin_of_safety",DataType::Float64,false),
        Field::new("flags",DataType::Utf8,false)]));
    let cols: Vec<ArrayRef> = vec![
        Arc::new(StringArray::from(rows.iter().map(|r|r.ticker.as_str()).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|r|r.fair_value_per_share).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|r|r.wacc).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|r|r.margin_of_safety).collect::<Vec<_>>())),
        Arc::new(StringArray::from(rows.iter().map(|r|r.flags.join(",")).collect::<Vec<_>>())),
    ];
    let Ok(batch) = RecordBatch::try_new(schema.clone(),cols) else { return err(StatusCode::INTERNAL_SERVER_ERROR,"ARROW_ENCODING","could not build Arrow record batch"); };
    let mut bytes = Vec::new();
    let result = StreamWriter::try_new(&mut bytes,&schema).and_then(|mut w| { w.write(&batch)?; w.finish() });
    if result.is_err() { return err(StatusCode::INTERNAL_SERVER_ERROR,"ARROW_ENCODING","could not encode Arrow stream"); }
    ([(header::CONTENT_TYPE,"application/vnd.apache.arrow.stream")],bytes).into_response()
}
#[tokio::main]
async fn main() {
    let path = std::env::args().skip_while(|a|a!="--data").nth(1).map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/data/fundamentals.parquet"));
    let store = Store::load(&path).unwrap_or_else(|e| { eprintln!("DATA_UNAVAILABLE: {e}"); std::process::exit(1); });
    let state = AppState { store:Arc::new(store), batch_gate:Arc::new(Semaphore::new(1)) };
    let app = Router::new().route("/health",get(health)).route("/value/{ticker}",get(single))
        .route("/value/batch",get(batch)).with_state(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:8080").await.expect("bind 127.0.0.1:8080");
    axum::serve(listener,app).await.expect("server");
}
