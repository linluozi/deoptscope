"""Time call #1..#N of freshly created code objects.

If quickening happened only between calls, call #1 and call #2 would differ by
a whole function's dispatch cost.  If it happens *inside* call #1, only call #1
is slow and call #2 is already steady state.
"""

import json
import statistics
import time
from pathlib import Path

from deoptscope.bench import make_fresh_function
from deoptscope.kernels import int_loop

OUT = Path(__file__).resolve().parent.parent / "results" / "first_calls.json"
CLONES = 40
CALLS = 8


def main() -> None:
    samples: dict[int, list[int]] = {i: [] for i in range(1, CALLS + 1)}
    for _ in range(CLONES):
        clone = make_fresh_function(int_loop)
        for i in range(1, CALLS + 1):
            t0 = time.perf_counter_ns()
            clone(400)
            samples[i].append(time.perf_counter_ns() - t0)
    medians = {str(i): statistics.median(v) for i, v in samples.items()}
    p25 = {str(i): statistics.quantiles(v, n=4)[0] for i, v in samples.items()}
    p75 = {str(i): statistics.quantiles(v, n=4)[2] for i, v in samples.items()}
    payload = {
        "clones": CLONES,
        "calls": CALLS,
        "kernel": "int_loop(400)",
        "median_ns": medians,
        "p25_ns": p25,
        "p75_ns": p75,
        "raw": {str(i): v for i, v in samples.items()},
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("call  median  p25  p75")
    for i in range(1, CALLS + 1):
        print(i, medians[str(i)], p25[str(i)], p75[str(i)])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
