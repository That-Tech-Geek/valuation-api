use crate::{compute, model::DcfInputs};
use pyo3::{prelude::*, types::PyDict};

#[pyfunction]
#[pyo3(signature=(ebit, tax_rate, da, capex, change_nwc, total_debt, cash, shares, price, beta, rf, erp, growth_5y, terminal_growth))]
fn compute_dcf(py: Python<'_>, ebit:f64, tax_rate:f64, da:f64, capex:f64, change_nwc:f64,
    total_debt:f64, cash:f64, shares:f64, price:f64, beta:f64, rf:f64, erp:f64,
    growth_5y:f64, terminal_growth:f64) -> PyResult<Py<PyDict>> {
    let out = compute(&DcfInputs { ebit,tax_rate,da,capex,change_nwc,total_debt,cash,shares,price,beta,rf,erp,growth_5y,terminal_growth });
    let d = PyDict::new(py);
    d.set_item("wacc", out.wacc)?;
    d.set_item("enterprise_value", out.enterprise_value)?;
    d.set_item("equity_value", out.equity_value)?;
    d.set_item("fair_value_per_share", out.fair_value_per_share)?;
    d.set_item("flags", out.flags.names())?;
    Ok(d.unbind())
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compute_dcf, m)?)?;
    Ok(())
}
