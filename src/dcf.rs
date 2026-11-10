use crate::model::{DcfInputs, DcfOutput, Flags};

pub fn compute(input: &DcfInputs) -> DcfOutput {
    let mut flags = Flags::default();
    let beta = if !(0.3..=3.0).contains(&input.beta) {
        flags.0 |= Flags::BETA_CLAMPED;
        input.beta.clamp(0.3, 3.0)
    } else {
        input.beta
    };

    let e = input.price * input.shares;
    let d = input.total_debt.max(0.0);
    let v = e + d;
    let cost_equity = input.rf + beta * input.erp;
    let cost_debt = input.rf + 0.02;
    let wacc = if v.abs() < f64::EPSILON {
        cost_equity
    } else {
        (e / v) * cost_equity + (d / v) * cost_debt * (1.0 - input.tax_rate)
    };

    let nopat = input.ebit * (1.0 - input.tax_rate);
    let fcff = nopat + input.da - input.capex - input.change_nwc;
    if !fcff.is_finite() || fcff <= 0.0 {
        flags.0 |= Flags::NEGATIVE_FCFF;
    }

    let mut pv_sum = 0.0;
    for t in 1..=5 {
        let projected = fcff * (1.0 + input.growth_5y).powi(t);
        if projected <= 0.0 {
            flags.0 |= Flags::NEGATIVE_FCFF;
        }
        pv_sum += projected / (1.0 + wacc).powi(t);
    }

    let mut terminal_growth = input.terminal_growth;
    if terminal_growth >= wacc {
        flags.0 |= Flags::TERMINAL_GT_WACC;
        terminal_growth = wacc - 0.01;
    }
    let fcff_6 = fcff * (1.0 + input.growth_5y).powi(5) * (1.0 + terminal_growth);
    let spread = (wacc - terminal_growth).max(0.0001);
    let tv = fcff_6 / spread;
    let pv_tv = tv / (1.0 + wacc).powi(5);
    let ev = pv_sum + pv_tv;
    let equity = ev - input.total_debt + input.cash;
    if equity < 0.0 {
        flags.0 |= Flags::NEGATIVE_EQUITY;
    }
    let fvps = if input.shares > 0.0 {
        equity / input.shares
    } else {
        f64::NAN
    };

    DcfOutput {
        wacc,
        terminal_growth,
        enterprise_value: ev,
        equity_value: equity,
        fair_value_per_share: fvps,
        flags,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> DcfInputs {
        DcfInputs {
            ebit: 100.0,
            tax_rate: 0.25,
            da: 10.0,
            capex: 15.0,
            change_nwc: 5.0,
            total_debt: 100.0,
            cash: 20.0,
            shares: 10.0,
            price: 20.0,
            beta: 1.0,
            rf: 0.04,
            erp: 0.05,
            growth_5y: 0.08,
            terminal_growth: 0.03,
        }
    }

    #[test]
    fn computes_finite_positive_value() {
        let out = compute(&sample());
        assert!(out.wacc.is_finite() && out.wacc > 0.0);
        assert!(out.fair_value_per_share.is_finite());
        assert!(!out.flags.contains(Flags::NEGATIVE_FCFF));
    }

    #[test]
    fn flags_and_clamps_bad_beta_and_terminal_growth() {
        let mut x = sample();
        x.beta = 9.0;
        x.terminal_growth = 0.9;
        let out = compute(&x);
        assert!(out.flags.contains(Flags::BETA_CLAMPED));
        assert!(out.flags.contains(Flags::TERMINAL_GT_WACC));
        assert!(out.terminal_growth < out.wacc);
    }

    #[test]
    fn flags_negative_fcff() {
        let mut x = sample();
        x.capex = 500.0;
        assert!(compute(&x).flags.contains(Flags::NEGATIVE_FCFF));
    }
}
