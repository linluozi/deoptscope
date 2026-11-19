"""Fresh-code-object counterfactual for CPython 3.12 specialisation.

CPython 3.13 has ``sys._clear_internal_caches()``; 3.12 does not.  But a new
code object produced by ``code.replace()`` starts with unquickened adaptive
bytecode (verified by ``dis.get_instructions(..., adaptive=True)``), so calling
a *fresh clone* once measures the same function without specialised
instructions.  The clone is created outside the timed region.

This is only valid for self-contained kernels: cloning resets the entry code
object, not the library code it calls.
"""

from __future__ import annotations

import statistics
import sys
import time
import types
from typing import Any, Callable


def make_fresh_function(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Return a function with a new, unquickened code object and same semantics."""
    if not hasattr(fn, "__code__"):
        raise TypeError("cold_vs_warm needs a plain Python function")
    code = fn.__code__.replace()
    clone = types.FunctionType(
        code,
        fn.__globals__,
        fn.__name__,
        fn.__defaults__,
        fn.__closure__,
    )
    clone.__kwdefaults__ = fn.__kwdefaults__
    clone.__module__ = fn.__module__
    clone.__qualname__ = fn.__qualname__
    return clone


def _percentile(sorted_values: list[int], q: float) -> float:
    if not sorted_values:
        raise ValueError("empty sample")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _stats(samples: list[int]) -> dict[str, float]:
    ordered = sorted(samples)
    mean = statistics.fmean(ordered)
    sd = statistics.stdev(ordered) if len(ordered) > 1 else 0.0
    return {
        "n": len(ordered),
        "median_ns": _percentile(ordered, 0.5),
        "p25_ns": _percentile(ordered, 0.25),
        "p75_ns": _percentile(ordered, 0.75),
        "mean_ns": mean,
        "rsd": sd / mean if mean else 0.0,
        "min_ns": float(ordered[0]),
        "max_ns": float(ordered[-1]),
    }


def cold_vs_warm(
    fn: Callable[..., Any],
    *args: Any,
    samples: int = 1200,
    blocks: int = 6,
    warmup: int = 200,
    **kwargs: Any,
) -> dict[str, Any]:
    """Interleave warm and fresh-code calls; report per-call ns distributions."""
    if samples < blocks or blocks < 1:
        raise ValueError("samples must be >= blocks >= 1")
    for _ in range(warmup):
        fn(*args, **kwargs)

    reference = fn(*args, **kwargs)
    clone_pool = [make_fresh_function(fn) for _ in range(samples)]

    warm: list[int] = []
    cold: list[int] = []
    raw: list[dict[str, Any]] = []
    per_block = samples // blocks

    for block in range(blocks):
        for _ in range(per_block):
            t0 = time.perf_counter_ns()
            fn(*args, **kwargs)
            dt = time.perf_counter_ns() - t0
            warm.append(dt)
            raw.append({"block": block, "mode": "warm", "ns": dt})
        for _ in range(per_block):
            clone = clone_pool.pop()
            t0 = time.perf_counter_ns()
            clone(*args, **kwargs)
            dt = time.perf_counter_ns() - t0
            cold.append(dt)
            raw.append({"block": block, "mode": "cold", "ns": dt})

    # Correctness is checked outside the timed loop for the *cold* path only:
    # each clone was called once already, so clone anew to keep it unquickened.
    checked = 0
    mismatches = 0
    for _ in range(min(200, max(20, samples // 10))):
        clone = make_fresh_function(fn)
        checked += 1
        if clone(*args, **kwargs) != reference:
            mismatches += 1

    warm_stats = _stats(warm)
    cold_stats = _stats(cold)
    return {
        "function": f"{fn.__module__}.{fn.__qualname__}",
        "python": sys.version.split()[0],
        "args_repr": repr(args)[:200],
        "samples_per_mode": len(warm),
        "blocks": blocks,
        "warmup": warmup,
        "warm": warm_stats,
        "cold": cold_stats,
        "slowdown_without_quickening": cold_stats["median_ns"] / warm_stats["median_ns"],
        "quickening_benefit": 1.0 - warm_stats["median_ns"] / cold_stats["median_ns"],
        "correctness": {"checked": checked, "mismatches": mismatches},
        "raw": raw,
    }
