"""Sweep call length to show that quickening happens *inside* the first call.

If specialisation were a per-call cost, the cold/warm ratio would stay flat as
the kernel grows.  It does not: the ratio decays to 1.0 once the loop is long
enough, which pins the effect to the unquickened entry, not to steady state.
"""

import json
from pathlib import Path

from deoptscope.bench import cold_vs_warm
from deoptscope.kernels import int_loop

OUT = Path(__file__).resolve().parent.parent / "results" / "transient_sweep.json"
SIZES = [2, 5, 20, 100, 400, 1600]


def main() -> None:
    results = {}
    for n in SIZES:
        r = cold_vs_warm(int_loop, n, samples=2000, blocks=8, warmup=300)
        results[str(n)] = {
            "warm_median_ns": r["warm"]["median_ns"],
            "cold_median_ns": r["cold"]["median_ns"],
            "slowdown": r["slowdown_without_quickening"],
            "warm_rsd": r["warm"]["rsd"],
            "cold_rsd": r["cold"]["rsd"],
            "warm_p25_ns": r["warm"]["p25_ns"],
            "warm_p75_ns": r["warm"]["p75_ns"],
            "cold_p25_ns": r["cold"]["p25_ns"],
            "cold_p75_ns": r["cold"]["p75_ns"],
            "delta_median_ns": r["cold"]["median_ns"] - r["warm"]["median_ns"],
            "mismatches": r["correctness"]["mismatches"],
        }
        print(n, results[str(n)])
    OUT.write_text(json.dumps({"python": __import__("sys").version.split()[0], "sizes": results}, indent=2, sort_keys=True) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
