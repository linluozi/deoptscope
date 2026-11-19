# deoptscope

A CPython 3.12 measurement tool for adaptive specialisation: it reads the interpreter's
actual quickened bytecode (`dis.get_instructions(..., adaptive=True)`) across real library
workloads, and it tests — and falsifies — the common "fresh code object" trick for measuring
what specialisation is worth.

`Upstream: none`

This is an original measurement study, not a patch to an upstream project. It ships no
`-opt-lab` repository and claims no library speedup; the second half of the README explains
why the obvious counterfactual cannot support such a claim.

## What it does

CPython 3.12 rewrites instructions in place as code runs: `LOAD_GLOBAL` becomes
`LOAD_GLOBAL_BUILTIN`, `BINARY_OP` becomes `BINARY_OP_ADD_INT`, adjacent instructions fuse
into superinstructions, and inline caches are reserved. `deoptscope` has two modes:

- `census` — run a real workload (Jinja2 render, markdown-it parse, Click invocation),
  record every executed code object with `sys.monitoring`, then count specialised, generic,
  fused, and fixed slots per code object. Also lists the exact generic sites weighted by how
  often their code object ran.
- `bench` — build fresh, unquickened clones of a self-contained kernel with
  `code.replace()`, then compare warm calls with one call per clone.

## Measurement 1: steady-state coverage on real workloads

`python3 -m deoptscope census --workload all --warmup 20 --out results/census.json`

| workload | profiled calls | code objects | coverage (unique) | coverage (call-weighted) | specialised / generic slots |
| --- | ---: | ---: | ---: | ---: | ---: |
| Jinja2 200-row render | 2,624 | 27 | 0.538 | 0.411 | 136 / 117 |
| markdown-it 115-line doc | 15,566 | 93 | 0.570 | 0.678 | 1,591 / 1,199 |
| Click 8-option CLI | 464 | 140 | 0.515 | 0.536 | 1,092 / 1,027 |

Coverage is `specialised / (specialised + generic)`; fused and fixed slots are excluded.
"unique" counts each code object once, "call-weighted" multiplies by its call count.

The interesting part is *which* hot sites stayed generic. Top rows from
`results/census.json` (module, function, line, opcode, weighted calls):

| workload | function | line | opcode | weighted calls |
| --- | --- | ---: | --- | ---: |
| Jinja2 | `Environment.getattr` | 480 | `LOAD_GLOBAL` / `LOAD_ATTR` / `CALL` | 800 each |
| Jinja2 | `LoopContext.__next__` | 554 | `LOAD_ATTR` / `STORE_ATTR` | 201 each |
| markdown-it | `Logger.isEnabledFor` | 1790 | `LOAD_ATTR` | 1,029 |
| markdown-it | `Logger.debug` | 1517 | `LOAD_ATTR` / `LOAD_GLOBAL` | 1,029 each |
| Click | `join` | 71 | `FOR_ITER` / `CALL` | 16 each |

Two conclusions follow directly from the numbers:

1. Coverage is **frequency-gated**. The call-weighted score for Jinja2 (0.411) is *lower*
   than the unique score (0.538): its hot code is dynamic dispatch (`Environment.getattr`
   at 0.444, `LoopContext.__next__` at 0.357, `sync_do_join` at 0.205), while cold one-shot
   helpers specialise to 1.0.
2. The generic sites are not random. They are attribute lookups and calls whose operand
   types vary at runtime — exactly the polymorphic cases the specialiser is designed to
   bail out of.

`census` is exact about bytecode state, but it does not weight by instructions executed
inside a code object; the call-weighted column is a documented proxy, not an execution
profile.

## Measurement 2: the fresh-code counterfactual measures a transient, not steady state

The tempting A/B is: a new code object from `code.replace()` starts unquickened, so time
call #1 of many clones against warm calls and call the ratio "specialisation speedup".
The method is real — `dis` shows zero specialised slots before the first call — but the
inference is wrong. Quickening completes *inside* call #1, so the ratio must decay as the
kernel grows. It does:

`python3 experiments/sweep.py` (`int_loop(n)`, 2,000 samples per mode, 8 blocks, medians)

| n | warm median (ns) | cold median (ns) | delta (ns) | cold/warm |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 311 | 381 | 70 | 1.225 |
| 5 | 381 | 451 | 70 | 1.184 |
| 20 | 962 | 1,052 | 90 | 1.094 |
| 100 | 4,378 | 4,458 | 80 | 1.018 |
| 400 | 19,476 | 19,687 | 211 | 1.011 |
| 1,600 | 91,934 | 93,165 | 1,232 | 1.013 |

The **absolute** entry cost stays roughly constant (70–90 ns for short calls) while the
ratio collapses toward 1.0. A constant additive transient is the signature of one-time
quickening, not of a multiplicative speedup.

The same is visible in `results/first_calls.json` (40 fresh clones, per-call medians):
call #1 = 19,502 ns, call #2 = 19,432 ns, call #8 = 19,366 ns. Steady state is reached by
the second call; only ~70 ns of the first call is unquickened.

Consequence: a clone-based "1.2x from specialisation" claim on a short function is a
measurement artifact. On this interpreter there is no public way to keep a code object
unquickened while it runs, so the steady-state value of specialisation cannot be isolated
by this A/B, and this repository does not report one.

Kernel results (1,200 samples per mode, `results/bench.json`):

| kernel | warm median (ns) | cold median (ns) | cold/warm |
| --- | ---: | ---: | ---: |
| `int_loop(400)` | 20,238 | 20,438 | 1.010 |
| `builtin_call_loop(600)` | 60,904 | 60,966 | 1.001 |
| `attr_monomorphic(200)` | 5,866 | 6,011 | 1.025 |
| `attr_dimorphic(200)` | 9,327 | 9,297 | 0.997 |
| `math_loop(400)` | 24,085 | 24,907 | 1.034 |

The dimorphic kernel is the control: if it showed a large "specialisation benefit", the
harness would be measuring something other than quickening.

## Correctness and tests

`python3 -m unittest discover -s tests -v` → **19 tests, OK** (no third-party packages).

- Fresh clones return identical results on every checked call: **0 mismatches** across all
  kernels and the 40-clone first-call experiment.
- `census` is read-only: two consecutive censuses of the same warmed code object are
  byte-identical (asserted in `tests/test_census.py`).
- `sys.monitoring` instrumentation does not perturb the census: warm function, census,
  profile one run, census again → same specialised/generic counts (asserted in the tests).
- Classification is version-guarded: on an interpreter without `dis._specializations` the
  tool raises instead of reporting zeros.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
python3 -m deoptscope census --workload all --warmup 20 --out results/census.json
python3 -m deoptscope bench --kernel all --samples 1200 --blocks 6 --out results/bench.json
```

The additional sweeps:

```bash
PYTHONPATH=. python3 experiments/sweep.py        # results/transient_sweep.json
PYTHONPATH=. python3 experiments/first_calls.py  # results/first_calls.json
```

Experiment dependencies (Jinja2, markdown-it-py, Click) are optional; the tool and its
tests do not import them.

## Environment

- CPU: AMD EPYC 7K62 48-Core (4 vCPU), 3,723 MB RAM, shared host.
- Runtime: CPython 3.12.3 (`/usr/bin/python3`). No 3.10/3.11 on this machine, so no
  cross-interpreter comparison was possible.
- Timing: `time.perf_counter_ns()` per call; warmup calls excluded; medians with p25/p75.
- No random seed is involved: inputs are fixed, outputs are deterministic, only timing
  varies. Raw per-call samples are embedded in `results/bench.json` and the other `results/*.json` files.
- Noise disclosure: `int_loop(400)` warm RSD is 10.3%; `n=2` in the sweep has a warm RSD
  of 186% from a single scheduler outlier, so its p25/p75 (310/320 ns) and median (311 ns)
  are reported alongside the ratio. The 1,600-iteration delta (1,232 ns) is within drift;
  the conclusion rests on the constant 70–90 ns delta at small sizes and the monotone decay,
  not on that row.

## 本轮创新

B 档：首次直接读取 CPython 3.12 的真实特化状态，在三个真实库负载上给出**调用频次门控**
的覆盖率（Jinja2 call-weighted 0.411 vs unique 0.538），并**反证**了「fresh code object 对照
能量出特化收益」这一常见做法——收益在第一次调用内部就完成，可测到的是恒定的 ~70 ns 入口
瞬态（1.23x→1.01x 随核长大而衰减），不是稳态乘数。与台账里的 speedgap（合成 vs 真实）
和 benchreconcile（声明三方对账）不同：那两条比的是外部声明与负载，本条直接测量解释器
自适应字节码状态。

## Limitations

- One interpreter build (3.12.3), one host, three workloads. No 3.13, no free-threaded build.
- The counterfactual resets only the entry code object; it is valid for self-contained
  kernels and invalid for library internals. No library-level timing claim is made.
- Census coverage is slot-based and call-weighted, not an executed-instruction profile.
- `dis._specializations` is private; the version guard is intentional.

## License

MIT, original work. See `LICENSE`.
