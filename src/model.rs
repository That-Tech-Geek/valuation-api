use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Company {
    pub ticker: String,
    pub as_of_date: NaiveDate,
    pub currency: String,
    pub sector: String,
    pub revenue: f64,
    pub ebit: f64,
    pub effective_tax_rate: f64,
    pub da: f64,
    pub capex: f64,
    pub change_nwc: f64,
    pub total_debt: f64,
    pub cash: f64,
    pub shares_outstanding: f64,
    pub price: f64,
    pub beta: f64,
    pub risk_free_rate: f64,
    pub equity_risk_premium: f64,
    pub growth_5y: f64,
    pub terminal_growth: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct DcfInputs {
    pub ebit: f64, pub tax_rate: f64, pub da: f64, pub capex: f64,
    pub change_nwc: f64, pub total_debt: f64, pub cash: f64,
    pub shares: f64, pub price: f64, pub beta: f64, pub rf: f64,
    pub erp: f64, pub growth_5y: f64, pub terminal_growth: f64,
}

impl From<&Company> for DcfInputs {
    fn from(c: &Company) -> Self {
        Self { ebit:c.ebit, tax_rate:c.effective_tax_rate, da:c.da, capex:c.capex,
            change_nwc:c.change_nwc, total_debt:c.total_debt, cash:c.cash,
            shares:c.shares_outstanding, price:c.price, beta:c.beta, rf:c.risk_free_rate,
            erp:c.equity_risk_premium, growth_5y:c.growth_5y, terminal_growth:c.terminal_growth }
    }
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct Flags(pub u16);

impl Flags {
    pub const TERMINAL_GT_WACC: u16 = 1;
    pub const NEGATIVE_FCFF: u16 = 2;
    pub const BETA_CLAMPED: u16 = 4;
    pub const NEGATIVE_EQUITY: u16 = 8;
    pub fn contains(self, flag: u16) -> bool { self.0 & flag != 0 }
    pub fn names(self) -> Vec<&'static str> {
        [(1,"TERMINAL_GT_WACC"),(2,"NEGATIVE_FCFF"),(4,"BETA_CLAMPED"),(8,"NEGATIVE_EQUITY")]
            .into_iter().filter_map(|(bit,name)| self.contains(bit).then_some(name)).collect()
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DcfOutput {
    pub wacc: f64,
    pub terminal_growth: f64,
    pub enterprise_value: f64,
    pub equity_value: f64,
    pub fair_value_per_share: f64,
    pub flags: Flags,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Valuation {
    pub ticker: String,
    pub as_of_date: NaiveDate,
    pub currency: String,
    pub wacc: f64,
    pub terminal_growth: f64,
    pub enterprise_value: f64,
    pub equity_value: f64,
    pub fair_value_per_share: f64,
    pub market_price: f64,
    pub margin_of_safety: f64,
    pub flags: Vec<String>,
}
