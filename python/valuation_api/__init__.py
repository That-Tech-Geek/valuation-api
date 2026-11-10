"""Python interface to the Rust FCFF DCF valuation engine."""
from collections.abc import Iterable, Mapping
from ._native import compute_dcf

_REQUIRED = (
    "ebit", "tax_rate", "da", "capex", "change_nwc", "total_debt",
    "cash", "shares", "price", "beta", "rf", "erp", "growth_5y",
    "terminal_growth",
)

def compute_batch(rows: Iterable[Mapping[str, float]]) -> list[dict]:
    """Value a sequence of company assumption mappings using the Rust kernel."""
    results = []
    for index, row in enumerate(rows):
        missing = [key for key in _REQUIRED if key not in row]
        if missing:
            raise ValueError(f"row {index} is missing required fields: {', '.join(missing)}")
        results.append(compute_dcf(**{key: float(row[key]) for key in _REQUIRED}))
    return results

__all__ = ["compute_dcf", "compute_batch"]
__version__ = "0.1.1"
