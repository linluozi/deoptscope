# Measuring adaptive specialisation in CPython 3.12

This document is the input corpus for the Markdown workload.  It is ordinary
prose with the structures a real technical note contains: headings, lists,
tables, inline code, fenced code, links, and block quotes.  Nothing here is
generated randomly; the parse cost therefore reflects a real document rather
than a stress pattern.

## Why a census instead of an estimate

CPython 3.12 replaces individual bytecode instructions with specialised
variants as functions run.  `LOAD_GLOBAL` becomes `LOAD_GLOBAL_BUILTIN` when
the name resolves to a builtin, `BINARY_OP` becomes `BINARY_OP_ADD_INT` when
both operands are small integers, and two adjacent instructions can be fused
into a superinstruction such as `LOAD_FAST__LOAD_CONST`.  The interpreter also
reserves inline cache entries next to each instruction.

The important property for measurement is that the replacement is *in place*
on the code object.  `dis.get_instructions(code, adaptive=True)` reads the
current adaptive bytecode, so we can observe the state directly instead of
inferring it from timing.  A census is therefore exact: every slot is either a
specialised variant, a generic form that has a specialised variant available,
a fused superinstruction, or an instruction with no specialisation at all.

| category | example | counted in ratio |
| --- | --- | --- |
| specialised | `LOAD_GLOBAL_BUILTIN` | yes, numerator |
| generic | `LOAD_GLOBAL` | yes, denominator only |
| fused | `LOAD_FAST__LOAD_CONST` | no, reported separately |
| fixed | `RETURN_VALUE` | no |

## The counterfactual problem

To know what specialisation is worth we need the same function without it.
CPython 3.13 added `sys._clear_internal_caches()`; on 3.12 there is no public
way to undo quickening in place.  There is, however, a structural trick: a
code object created by `code.replace()` starts unquickened.  A freshly built
function from that code runs the generic bytecode on its first call, and
`dis` confirms there are zero specialised slots before the call.

That gives a clean A/B design for *self-contained* kernels:

1. Warm one function and time repeated calls on the hot code object.
2. Pre-build N fresh clones outside the timed region.
3. Time one call per clone.
4. Compare medians and check that every clone returns the same value.

The method has a hard boundary.  Cloning resets only the entry code object,
not the library functions it calls.  Applying it to a Jinja2 render would
measure the wrapper, not the template engine, so this repository does not
claim library-level speedups from it.

## Reading the numbers

The ratio `cold_median / warm_median` is the slowdown you would pay if the
interpreter never specialised the kernel.  A ratio of 1.0 means the kernel is
dominated by work the specialiser cannot touch, for example a C function call
or an operation whose operand types vary at runtime.  A ratio well above 1.0
means generic dispatch was a real cost.

Two cautions apply to every number in this repository:

- The host is a shared four-core virtual machine.  Relative standard
  deviation above ten percent is reported rather than hidden, and medians with
  quartiles are used instead of means.
- Timings are per call in nanoseconds from `time.perf_counter_ns()`.  Warmup
  calls are never included in the samples.

> A measurement that cannot fail is not a measurement.  The kernels include a
> deliberately dimorphic attribute access whose expected result is "almost no
> benefit"; if that kernel reported a large speedup, the harness would be
> wrong.

## What the census reports

For every code object executed during one profiled run the tool records the
number of specialised, generic, fused, and fixed slots, the call count, and
the qualified name.  Aggregates are published two ways:

- **unique**: each code object contributes its slots once, regardless of how
  often it ran.  This weights small helper functions as much as hot loops.
- **call-weighted**: each code object's slots are multiplied by its call
  count.  This approximates where the interpreter actually spent its
  dispatch budget.

The generic-site table lists the individual instructions that stayed generic,
weighted by the call count of their code object.  That table is the useful
part for a maintainer: it names the exact function, line, and offset where
specialisation did not happen.

## Reproducing

```bash
python3 -m unittest discover -s tests -v
python3 -m deoptscope census --workload all --out results/census.json
python3 -m deoptscope bench --kernel all --out results/bench.json
```

The first command needs no third-party packages.  The census workloads use
Jinja2, markdown-it-py, and Click; those are experiment dependencies, not
runtime dependencies of the tool.

## Limitations

The census observes one interpreter build, one operating system, and one
workload per library.  It says nothing about other Python versions, about
free-threaded builds, or about JIT compilers.  The tool refuses to run when
`dis._specializations` is absent rather than reporting zeros, because a silent
zero would look like a finding.

Finally, a note on naming: this repository is a measurement study, not an
optimisation patch.  It does not modify any upstream project, and it makes no
claim that a particular library can be sped up.  What it provides is a
reproducible way to see which instructions the specialiser reached and which
ones it did not.
