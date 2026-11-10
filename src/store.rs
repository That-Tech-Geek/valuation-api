use crate::model::Company;
use arrow::array::{Array, Date32Array, Float64Array, StringArray};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use std::{collections::HashMap, fs::File, path::Path};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum LoadError {
    #[error("data file error: {0}")] Io(#[from] std::io::Error),
    #[error("parquet error: {0}")] Parquet(#[from] parquet::errors::ParquetError),
    #[error("missing or invalid column: {0}")] Column(String),
    #[error("manifest missing, invalid, or empty")] Manifest,
    #[error("invalid row: {0}")] Row(String),
}

#[derive(Clone, Debug, serde::Deserialize)]
pub struct Manifest {
    pub row_count: usize,
    pub generated_at: String,
    #[serde(default)] pub tickers_dropped: Vec<String>,
}

pub struct Store {
    rows: Vec<Company>,
    index: HashMap<Box<str>, usize>,
    pub manifest: Manifest,
}

impl Store {
    pub fn load(path: &Path) -> Result<Self, LoadError> {
        let manifest_path = path.with_file_name("fundamentals.manifest.json");
        let manifest: Manifest = serde_json::from_reader(File::open(manifest_path).map_err(|_| LoadError::Manifest)?)
            .map_err(|_| LoadError::Manifest)?;
        if manifest.row_count == 0 { return Err(LoadError::Manifest); }
        let file = File::open(path)?;
        let mut reader = ParquetRecordBatchReaderBuilder::try_new(file)?.build()?;
        let mut rows = Vec::with_capacity(manifest.row_count);
        while let Some(batch) = reader.next() {
            let batch = batch?;
            let col = |name: &str| batch.schema().index_of(name).map_err(|_| LoadError::Column(name.into()));
            let strings = |name: &str| -> Result<&StringArray, LoadError> {
                batch.column(col(name)?).as_any().downcast_ref().ok_or_else(|| LoadError::Column(name.into()))
            };
            let floats = |name: &str| -> Result<&Float64Array, LoadError> {
                batch.column(col(name)?).as_any().downcast_ref().ok_or_else(|| LoadError::Column(name.into()))
            };
            let dates = batch.column(col("as_of_date")?).as_any().downcast_ref::<Date32Array>()
                .ok_or_else(|| LoadError::Column("as_of_date".into()))?;
            for i in 0..batch.num_rows() {
                let s = |a: &StringArray| if a.is_null(i) { None } else { Some(a.value(i).to_owned()) };
                let f = |a: &Float64Array| if a.is_null(i) { None } else { Some(a.value(i)) };
                let ticker = s(strings("ticker")?).ok_or_else(|| LoadError::Row("ticker null".into()))?;
                let date = chrono::NaiveDate::from_num_days_from_ce_opt(dates.value(i) + 719163)
                    .ok_or_else(|| LoadError::Row("invalid date".into()))?;
                let getf = |name: &str| -> Result<f64, LoadError> {
                    let v = f(floats(name)?).ok_or_else(|| LoadError::Row(format!("{name} null")))?;
                    if !v.is_finite() { return Err(LoadError::Row(format!("{name} non-finite"))); } Ok(v)
                };
                rows.push(Company {
                    ticker, as_of_date: date,
                    currency: s(strings("currency")?).ok_or_else(|| LoadError::Row("currency null".into()))?,
                    sector: s(strings("sector")?).unwrap_or_else(|| "UNKNOWN".into()),
                    revenue:getf("revenue")?, ebit:getf("ebit")?, effective_tax_rate:getf("effective_tax_rate")?,
                    da:getf("da")?, capex:getf("capex")?, change_nwc:getf("change_nwc")?,
                    total_debt:getf("total_debt")?, cash:getf("cash")?, shares_outstanding:getf("shares_outstanding")?,
                    price:getf("price")?, beta:getf("beta")?, risk_free_rate:getf("risk_free_rate")?,
                    equity_risk_premium:getf("equity_risk_premium")?, growth_5y:getf("growth_5y")?,
                    terminal_growth:getf("terminal_growth")?,
                });
            }
        }
        if rows.len() != manifest.row_count { return Err(LoadError::Manifest); }
        let index = rows.iter().enumerate().map(|(i,r)| (r.ticker.clone().into_boxed_str(), i)).collect();
        Ok(Self { rows, index, manifest })
    }
    pub fn len(&self) -> usize { self.rows.len() }
    pub fn is_empty(&self) -> bool { self.rows.is_empty() }
    pub fn get(&self, ticker: &str) -> Option<&Company> { self.index.get(ticker).map(|i| &self.rows[*i]) }
    pub fn rows(&self) -> &[Company] { &self.rows }
}
