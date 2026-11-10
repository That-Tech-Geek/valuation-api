"""Python interface to the Rust FCFF DCF valuation engine."""
from ._native import compute_dcf

__all__ = ["compute_dcf"]
__version__ = "0.1.0"
