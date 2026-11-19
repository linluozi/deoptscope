"""Command line interface: census and counterfactual benchmarks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .bench import cold_vs_warm
from .census import profile_workload
from .kernels import KERNELS


def _json_dump(obj: Any, path: str | None) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {path}")
    else:
        print(text)


def cmd_census(args: argparse.Namespace) -> int:
    from . import workloads

    names = sorted(workloads.WORKLOADS) if args.workload == "all" else [args.workload]
    payload: dict[str, Any] = {"python": sys.version.split()[0], "warmup": args.warmup, "results": {}}
    for name in names:
        fn = workloads.get(name)
        result = profile_workload(fn, warmup=args.warmup)
        payload["results"][name] = result
        print(
            f"{name}: calls={result['profiled_calls']} code_objects={result['code_objects']} "
            f"quickened(unique)={result['quickened_ratio_unique']} "
            f"quickened(call-weighted)={result['quickened_ratio_call_weighted']}",
            file=sys.stderr,
        )
    _json_dump(payload, args.out)
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    names = sorted(KERNELS) if args.kernel == "all" else [args.kernel]
    payload: dict[str, Any] = {"python": sys.version.split()[0], "results": {}}
    for name in names:
        fn, fargs, fkwargs = KERNELS[name]
        result = cold_vs_warm(
            fn, *fargs, samples=args.samples, blocks=args.blocks, warmup=args.warmup, **fkwargs
        )
        payload["results"][name] = result
        print(
            f"{name}: warm={result['warm']['median_ns']:.0f}ns cold={result['cold']['median_ns']:.0f}ns "
            f"slowdown={result['slowdown_without_quickening']:.3f}x "
            f"mismatches={result['correctness']['mismatches']}",
            file=sys.stderr,
        )
    _json_dump(payload, args.out)
    return 0


def cmd_kernels(_args: argparse.Namespace) -> int:
    for name in sorted(KERNELS):
        print(name)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deoptscope", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    census = sub.add_parser("census", help="census specialisation of real workloads")
    census.add_argument("--workload", default="all")
    census.add_argument("--warmup", type=int, default=20)
    census.add_argument("--out")
    census.set_defaults(func=cmd_census)

    bench = sub.add_parser("bench", help="fresh-code-object counterfactual on kernels")
    bench.add_argument("--kernel", default="all")
    bench.add_argument("--samples", type=int, default=1200)
    bench.add_argument("--blocks", type=int, default=6)
    bench.add_argument("--warmup", type=int, default=200)
    bench.add_argument("--out")
    bench.set_defaults(func=cmd_bench)

    kernels = sub.add_parser("kernels", help="list available kernels")
    kernels.set_defaults(func=cmd_kernels)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
