"""deoptscope: measure CPython 3.12 adaptive specialisation on real workloads.

Public API:
    census_code(code)          -> per-code-object specialisation census
    profile_workload(fn, ...)  -> call counts + census for every executed code object
    cold_vs_warm(fn, ...)      -> fresh-code-object counterfactual for self-contained kernels
"""

from .census import (
    ADAPTIVE_BASES,
    SPECIALIZED_TO_BASE,
    census_code,
    profile_workload,
    quickened_ratio,
)
from .bench import cold_vs_warm, make_fresh_function

__all__ = [
    "ADAPTIVE_BASES",
    "SPECIALIZED_TO_BASE",
    "census_code",
    "profile_workload",
    "quickened_ratio",
    "cold_vs_warm",
    "make_fresh_function",
]
__version__ = "0.1.0"
