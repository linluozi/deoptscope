"""Exact census of CPython 3.12 adaptive-specialisation state.

CPython 3.12 rewrites (``quickens``) individual bytecode instructions in place
with specialised variants (``LOAD_GLOBAL_BUILTIN``) or fused superinstructions
(``LOAD_FAST__LOAD_CONST``).  ``dis.get_instructions(code, adaptive=True)``
exposes the *current* state of a code object's adaptive bytecode, so a census
is a direct observation, not an estimate.

Nothing here clears caches or patches the interpreter; it only reads.
"""

from __future__ import annotations

import dis
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# dis._specializations maps base opname -> list of specialised opnames.
# It is private, so fail loudly instead of silently reporting zeros.
try:  # pragma: no cover - version guard
    _SPECIALIZATIONS: dict[str, list[str]] = dict(dis._specializations)  # type: ignore[attr-defined]
except AttributeError as exc:  # pragma: no cover
    raise RuntimeError(
        "deoptscope needs CPython 3.12 (dis._specializations is missing on "
        f"{sys.version.split()[0]})"
    ) from exc

SPECIALIZED_TO_BASE: dict[str, str] = {
    specialized: base
    for base, specials in _SPECIALIZATIONS.items()
    for specialized in specials
}
# Bases whose specialisation list contains a real variant.  Some bases
# (LOAD_CONST, LOAD_FAST) only appear as halves of fused superinstructions;
# a plain LOAD_CONST can never become "specialised", so counting it as a
# generic adaptive slot would inflate the denominator by a large factor.
ADAPTIVE_BASES = frozenset(
    base
    for base, specials in _SPECIALIZATIONS.items()
    if any("__" not in special for special in specials)
)


@dataclass
class Site:
    offset: int
    opname: str
    base: str | None
    kind: str  # "specialized" | "generic" | "fused" | "fixed"
    line: int | None
    arg: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "opname": self.opname,
            "base": self.base,
            "kind": self.kind,
            "line": self.line,
        }


@dataclass
class CodeCensus:
    module: str
    qualname: str
    firstlineno: int
    slots: int
    specialized: int
    generic: int
    fused: int
    fixed: int
    sites: list[Site] = field(default_factory=list)

    @property
    def adaptive(self) -> int:
        return self.specialized + self.generic

    @property
    def quickened_ratio(self) -> float | None:
        return self.specialized / self.adaptive if self.adaptive else None

    def as_dict(self, include_sites: bool = False) -> dict[str, Any]:
        out = {
            "module": self.module,
            "qualname": self.qualname,
            "firstlineno": self.firstlineno,
            "slots": self.slots,
            "specialized": self.specialized,
            "generic": self.generic,
            "fused": self.fused,
            "fixed": self.fixed,
            "adaptive": self.adaptive,
            "quickened_ratio": self.quickened_ratio,
        }
        if include_sites:
            out["sites"] = [s.as_dict() for s in self.sites]
        return out


def classify(opname: str) -> tuple[str, str | None]:
    """Return (kind, base_opname) for an adaptive opname."""
    if "__" in opname:
        return "fused", None
    base = SPECIALIZED_TO_BASE.get(opname)
    if base is not None:
        return "specialized", base
    if opname in ADAPTIVE_BASES:
        return "generic", opname
    return "fixed", None


def census_code(code: Any) -> CodeCensus:
    """Census one (preferably warmed) code object, without modifying it."""
    counts: Counter[str] = Counter()
    sites: list[Site] = []
    for ins in dis.get_instructions(code, adaptive=True):
        kind, base = classify(ins.opname)
        counts[kind] += 1
        sites.append(
            Site(
                offset=ins.offset,
                opname=ins.opname,
                base=base,
                kind=kind,
                line=ins.starts_line,
            )
        )
    return CodeCensus(
        module=code.co_filename.rsplit("/", 1)[-1],
        qualname=getattr(code, "co_qualname", code.co_name),
        firstlineno=code.co_firstlineno,
        slots=sum(counts.values()),
        specialized=counts["specialized"],
        generic=counts["generic"],
        fused=counts["fused"],
        fixed=counts["fixed"],
        sites=sites,
    )


def _claim_tool_id(mon: Any) -> int:
    for candidate in (2, 3, 4, 5):
        try:
            mon.use_tool_id(candidate, "deoptscope")
            return candidate
        except ValueError:
            continue
    raise RuntimeError("no free sys.monitoring tool id")


def profile_workload(
    fn: Callable[..., Any],
    *args: Any,
    warmup: int = 20,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run ``fn`` ``warmup`` times, then count calls and census every code object.

    The last run is the profiled one.  Census happens after it, so instructions
    have had a chance to specialise.
    """
    if warmup < 1:
        raise ValueError("warmup must be >= 1")
    for _ in range(warmup):
        fn(*args, **kwargs)

    calls: Counter[Any] = Counter()
    mon = sys.monitoring
    tool = _claim_tool_id(mon)
    events = mon.events

    def on_start(code: Any, _offset: int) -> None:
        calls[code] += 1

    try:
        mon.register_callback(tool, events.PY_START, on_start)
        mon.set_events(tool, events.PY_START)
        try:
            fn(*args, **kwargs)
        finally:
            mon.set_events(tool, 0)
            mon.register_callback(tool, events.PY_START, None)
    finally:
        mon.free_tool_id(tool)

    censuses = {code: census_code(code) for code in calls}
    return summarise(censuses, calls, workload=getattr(fn, "__name__", str(fn)))


def summarise(
    censuses: dict[Any, CodeCensus],
    calls: dict[Any, int],
    workload: str,
) -> dict[str, Any]:
    total_calls = sum(calls.values())
    adaptive = sum(c.specialized + c.generic for c in censuses.values())
    specialized = sum(c.specialized for c in censuses.values())
    generic = sum(c.generic for c in censuses.values())
    fused = sum(c.fused for c in censuses.values())
    fixed = sum(c.fixed for c in censuses.values())

    weighted_adaptive = sum(
        calls[code] * c.adaptive for code, c in censuses.items()
    )
    weighted_specialized = sum(
        calls[code] * c.specialized for code, c in censuses.items()
    )

    hot = sorted(
        (
            {
                "module": c.module,
                "qualname": c.qualname,
                "firstlineno": c.firstlineno,
                "calls": calls[code],
                "adaptive": c.adaptive,
                "specialized": c.specialized,
                "generic": c.generic,
                "quickened_ratio": c.quickened_ratio,
            }
            for code, c in censuses.items()
        ),
        key=lambda row: (-row["calls"], -(row["adaptive"] or 0)),
    )

    # Generic sites weighted by how often their code object ran.  This is the
    # list that says *which* hot instructions failed to specialise.
    generic_weight: Counter[tuple[str, str, int, str]] = Counter()
    examples: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    for code, c in censuses.items():
        for site in c.sites:
            if site.kind != "generic":
                continue
            key = (c.module, c.qualname, site.offset, site.opname)
            generic_weight[key] += calls[code]
            examples.setdefault(
                key,
                {
                    "module": c.module,
                    "qualname": c.qualname,
                    "offset": site.offset,
                    "opname": site.opname,
                    "base": site.base,
                    "firstlineno": c.firstlineno,
                    "calls": calls[code],
                },
            )
    generic_sites = [
        {**examples[key], "weighted_calls": weight}
        for key, weight in generic_weight.most_common(30)
    ]

    return {
        "workload": workload,
        "python": sys.version.split()[0],
        "profiled_calls": total_calls,
        "code_objects": len(censuses),
        "slots": {
            "adaptive": adaptive,
            "specialized": specialized,
            "generic": generic,
            "fused": fused,
            "fixed": fixed,
        },
        "quickened_ratio_unique": round(specialized / adaptive, 6) if adaptive else None,
        "quickened_ratio_call_weighted": (
            round(weighted_specialized / weighted_adaptive, 6)
            if weighted_adaptive
            else None
        ),
        "hot_functions": hot[:15],
        "code_objects_detail": hot,
        "generic_sites": generic_sites,
    }


def quickened_ratio(code: Any) -> float | None:
    """Convenience: specialised / adaptive slots for one warmed code object."""
    return census_code(code).quickened_ratio
