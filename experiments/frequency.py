"""Does specialisation grow with call count, or is it decided on call #1?

Buckets every code object by how often it ran during the profiled workload and
reports median coverage per bucket, plus a Spearman rank correlation between
log2(calls) and coverage.  Code objects with no adaptive slots are excluded.
"""

import json
import math
import statistics
from pathlib import Path

CENSUS = Path(__file__).resolve().parent.parent / "results" / "census.json"
OUT = Path(__file__).resolve().parent.parent / "results" / "frequency.json"
BUCKETS = [(1, 1), (2, 3), (4, 7), (8, 15), (16, 10**9)]


def rank(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0] * len(values)
    for position, index in enumerate(order):
        ranks[index] = position + 1
    return ranks


def spearman(xs, ys):
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return cov / (sx * sy)


def main() -> None:
    payload = json.loads(CENSUS.read_text())
    rows = [
        row
        for result in payload["results"].values()
        for row in result["code_objects_detail"]
        if row["quickened_ratio"] is not None
    ]
    buckets = []
    for lo, hi in BUCKETS:
        sel = [row for row in rows if lo <= row["calls"] <= hi]
        ratios = [row["quickened_ratio"] for row in sel]
        buckets.append(
            {
                "calls_lo": lo,
                "calls_hi": None if hi == 10**9 else hi,
                "code_objects": len(sel),
                "median_coverage": statistics.median(ratios) if ratios else None,
                "mean_coverage": statistics.fmean(ratios) if ratios else None,
                "fully_specialised": sum(1 for r in ratios if r == 1.0),
                "zero_specialised": sum(1 for r in ratios if r == 0.0),
            }
        )
    result = {
        "code_objects_with_adaptive_slots": len(rows),
        "spearman_log2calls_coverage": spearman(
            [math.log2(row["calls"]) for row in rows],
            [row["quickened_ratio"] for row in rows],
        ),
        "buckets": buckets,
        "totals_by_workload": {
            name: {
                "code_objects": value["code_objects"],
                "unique": value["quickened_ratio_unique"],
                "call_weighted": value["quickened_ratio_call_weighted"],
            }
            for name, value in payload["results"].items()
        },
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
