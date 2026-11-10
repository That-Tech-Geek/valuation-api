use std::path::Path;
use valuation_api::store::Store;

#[test]
fn loads_ten_row_parquet_fixture_and_indexes_tickers() {
    let store = Store::load(Path::new("data/fixtures/sample.parquet")).expect("fixture loads");
    assert_eq!(store.len(), 10);
    assert!(store.get("FIX00000.X").is_some());
    assert!(store.get("MISSING").is_none());
}
