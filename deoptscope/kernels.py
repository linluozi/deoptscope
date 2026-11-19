"""Self-contained kernels used by the cold-vs-warm counterfactual.

They are deliberately tiny and dependency-free so the fresh-clone method is
valid: the only code object involved in the measurement is the kernel itself.
Library workloads are measured with the census, not with this counterfactual.
"""

from __future__ import annotations

from typing import Any

import math


class Point:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class Vector:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


def int_loop(n: int = 400) -> int:
    total = 0
    for i in range(n):
        total += i * i
    return total


def builtin_call_loop(n: int = 400) -> int:
    total = 0
    for _ in range(n):
        total += len([1, 2, 3])
    return total


def attr_monomorphic(points: list[Any]) -> float:
    total = 0.0
    for p in points:
        total += p.x + p.y
    return total


def attr_dimorphic(items: list[Any]) -> float:
    total = 0.0
    for item in items:
        total += item.x + item.y
    return total


def math_loop(n: int = 400) -> float:
    total = 0.0
    for i in range(n):
        total += math.sqrt(i)
    return total


KERNELS = {
    "int_loop": (int_loop, (400,), {}),
    "builtin_call_loop": (builtin_call_loop, (600,), {}),
    "attr_monomorphic": (
        attr_monomorphic,
        ([Point(float(i), float(i + 1)) for i in range(200)],),
        {},
    ),
    "attr_dimorphic": (
        attr_dimorphic,
        (
            [
                Point(float(i), 1.0) if i % 2 else Vector(float(i), 1.0)
                for i in range(200)
            ],
        ),
        {},
    ),
    "math_loop": (math_loop, (400,), {}),
}
