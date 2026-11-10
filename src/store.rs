use crate::model::Company;
use arrow::array::{Array, Date32Array, Float64Array, StringArray};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use std::{collections::HashMap, fs::File, path::Path};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum LoadError {
    #[error("data file error: {0}")]
    Io(#[from] std::io::Error),
    #[error("parquet error: {0}")]
    Parquet(#[from] parquet::errors::ParquetError),
    #[error("arrow error: {0}")]
    Arrow(#[from] arrow::error::ArrowError),
    #[error("missing or invalid column: {0}")]
    Column(String),
    #[error("manifest missing, invalid, or empty")]
    Manifest,
    #[error("invalid row: {0}")]
    Row(String),
}

#[derive(Clone, Debug, serde::Deserialize)]
pub struct Manifest {
    pub row_count: usize,
    pub generated_at: String,
    #[serde(default)]
    pub tickers_dropped: Vec<serde_json::Value>,
}

pub struct Store {
    rows: Vec<Company>,
    index: HashMap<Box<str>, usize>,
    pub manifest: Manifest,
}

impl Store {
    pub fn load(path: &Path) -> Result<Self, LoadError> {
        let manifest_path = path.with_file_name("fundamentals.manifest.json");
        let manifest: Manifest =
            serde_json::from_reader(File::open(manifest_path).map_err(|_| LoadError::Manifest)?)
                .map_err(|_| LoadError::Manifest)?;
        if manifest.row_count == 0 || manifest.generated_at.is_empty() {
            return Err(LoadError::Manifest);
        }
        let file = File::open(path)?;
        let reader = ParquetRecordBatchReaderBuilder::try_new(file)?.build()?;
        let mut rows = Vec::with_capacity(manifest.row_count);
        for batch in reader {
            let batch = batch?;
            let col = |name: &str| {
                batch
                    .schema()
                    .index_of(name)
                    .map_err(|_| LoadError::Column(name.into()))
            };
            let strings = |name: &str| -> Result<&StringArray, LoadError> {
                batch
                    .column(col(name)?)
                    .as_any()
                    .downcast_ref()
                    .ok_or_else(|| LoadError::Column(name.into()))
            };
            let floats = |name: &str| -> Result<&Float64Array, LoadError> {
                batch
                    .column(col(name)?)
                    .as_any()
                    .downcast_ref()
                    .ok_or_else(|| LoadError::Column(name.into()))
            };
            let dates = batch
                .column(col("as_of_date")?)
                .as_any()
                .downcast_ref::<Date32Array>()
                .ok_or_else(|| LoadError::Column("as_of_date".into()))?;
            for i in 0..batch.num_rows() {
                let s = |array: &StringArray| {
                    if array.is_null(i) {
                        None
                    } else {
                        Some(array.value(i).trim().to_owned())
                    }
                };
                let f = |array: &Float64Array| {
                    if array.is_null(i) {
                        None
                    } else {
                        Some(array.value(i))
                    }
                };
                let ticker = s(strings("ticker")?)
                    .filter(|value| !value.is_empty())
                    .ok_or_else(|| LoadError::Row("ticker null or empty".into()))?;
                let date = chrono::NaiveDate::from_num_days_from_ce_opt(dates.value(i) + 719163)
                    .ok_or_else(|| LoadError::Row("invalid date".into()))?;
                let getf = |name: &str| -> Result<f64, LoadError> {
                    let value = f(floats(name)?)
                        .ok_or_else(|| LoadError::Row(format!("{name} null")))?;
                    if !value.is_finite() {
                        return Err(LoadError::Row(format!("{name} non-finite")));
                    }
                    Ok(value)
                };
                let shares_outstanding = getf("shares_outstanding")?;
                let price = getf("price")?;
                if shares_outstanding <= 0.0 || price <= 0.0 {
                    return Err(LoadError::Row(
                        "shares_outstanding and price must be positive".into(),
                    ));
                }
                let currency = s(strings("currency")?)
                    .filter(|value| !value.is_empty())
                    .ok_or_else(|| LoadError::Row("currency null or empty".into()))?;
                rows.push(Company {
                    ticker,
                    as_of_date: date,
                    currency,
                    sector: s(strings("sector")?).unwrap_or_else(|| "UNKNOWN".into()),
                    revenue: getf("revenue")?,
                    ebit: getf("ebit")?,
                    effective_tax_rate: getf("effective_tax_rate")?,
                    da: getf("da")?,
                    capex: getf("capex")?,
                    change_nwc: getf("change_nwc")?,
                    total_debt: getf("total_debt")?,
                    cash: getf("cash")?,
                    shares_outstanding,
                    price,
                    beta: getf("beta")?,
                    risk_free_rate: getf("risk_free_rate")?,
                    equity_risk_premium: getf("equity_risk_premium")?,
                    growth_5y: getf("growth_5y")?,
                    terminal_growth: getf("terminal_growth")?,
                });
            }
        }
        if rows.len() != manifest.row_count {
            return Err(LoadError::Manifest);
        }
        let mut index = HashMap::with_capacity(rows.len());
        for (position, row) in rows.iter().enumerate() {
            let key = row.ticker.to_ascii_uppercase().into_boxed_str();
            if index.insert(key, position).is_some() {
                return Err(LoadError::Row(format!(
                    "duplicate ticker after case normalization: {}",
                    row.ticker
                )));
            }
        }
        Ok(Self {
            rows,
            index,
            manifest,
        })
    }

    pub fn len(&self) -> usize {
        self.rows.len()
    }

    pub fn is_empty(&self) -> bool {
        self.rows.is_empty()
    }

    pub fn get(&self, ticker: &str) -> Option<&Company> {
        self.index
            .get(ticker.trim().to_ascii_uppercase().as_str())
            .map(|index| &self.rows[*index])
    }

    pub fn rows(&self) -> &[Company] {
        &self.rows
    }
}

#[cfg(test)]
mod tests {
    use super::Manifest;

    #[test]
    fn manifest_accepts_structured_dropped_ticker_records() {
        let manifest: Manifest = serde_json::from_str(
            r#"{"row_count":1,"generated_at":"2026-11-10T00:00:00Z","tickers_dropped":[{"ticker":"BAD","reason":"missing fields"}]}"#,
        )
        .expect("manifest with structured dropped-ticker details should deserialize");
        assert_eq!(manifest.tickers_dropped.len(), 1);
        assert_eq!(manifest.tickers_dropped[0]["ticker"], "BAD");
    }

    #[test]
    fn manifest_accepts_legacy_string_dropped_ticker_records() {
        let manifest: Manifest = serde_json::from_str(
            r#"{"row_count":1,"generated_at":"2026-11-10T00:00:00Z","tickers_dropped":["BAD"]}"#,
        )
        .expect("legacy string records remain compatible");
        assert_eq!(manifest.tickers_dropped.len(), 1);
    }
}
