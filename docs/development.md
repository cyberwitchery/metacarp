# Development and verification

Run commands from the repository root. Set `CARP_DIR` to the reference Carp
checkout, with its standard library at `$CARP_DIR/core`. The reference `carp`
compiler must be on `PATH`.

The fixed-point check builds the next compiler generation, asks it to emit
the compiler again, and compares the two generated C files byte for byte:

```sh
carp -b --optimize main.carp
scripts/check-fixed-point.sh
```

The script supplies the runtime include path, math library, and the larger
stack required on macOS. It uses a temporary directory and removes it after
the check. A fixed point checks reproducibility of self-compilation; the
reference suite separately checks program behavior and rejection.

The canonical generation benchmark compares reference Carp, gen 1, and gen 2
on the same workload (generating C for `main.carp`):

```sh
CARP_BENCH_RUNS=3 ./bench/compiler-generations.sh
```

It reports wall time, user time, and maximum resident set size, writes the raw
measurements as TSV, and checks that the C emitted by gen 1 and gen 2 reaches a
fixed point. Linking each next-generation compiler is deliberately excluded
from the timed region.

`bench/nbody-codegen.sh` checks exact output parity with reference Carp and
requires the generated hot loop to materialize its stable array data pointer.
It also reports reference/generated executable runtime without imposing a
noise-sensitive CI timing threshold.

## Assurance

The local and CI entry point is `scripts/run-assurance.sh`:

```sh
scripts/run-assurance.sh phase
scripts/run-assurance.sh self
scripts/run-assurance.sh all
```

| Group | Checks |
| --- | --- |
| `phase` | Lint, formatting, compiler-phase tests, and session tests. |
| `self` | Bootstrap, reference suite, fixed point, and expansion parity. |
| `all` | Both groups; also the default when no group is supplied. |

Style checks need `angler` and `carp-fmt`. Set `CARP_SKIP_STYLE=1` only when
intentionally skipping those checks. `CARP_PHASE_JOBS=2` or `3` runs independent
phase tasks concurrently; `CARP_SELF_JOBS=2` or `3` splits the reference suite
across isolated workers. `CARP_REFERENCE` selects the reference compiler
executable instead of `carp`.

The self-host checks can also run individually:

- `scripts/run-carp-suite-self.sh` runs the reference repository's examples,
  output comparisons, runtime tests, error-rejection tests, and bench builds.
  It finds the checkout through `CARP_ROOT` or `CARP_DIR`. `CARP_COMPILER`
  selects the compiler binary, including a self-built generation.
- `scripts/check-fixed-point.sh` compares successive self-emitted C files.
- `scripts/diff-expansion.sh` requires identical observable output for macros,
  quasiquote, gensym, and dynamic evaluation under both compilers.

CI invokes the same assurance groups. The self-host group runs generated
programs on x86-64 Linux and ARM64 macOS. See
[the workflow](../.github/workflows/ci.yml) for the current runner and cache
configuration.

## Working on a phase

Run an individual phase test from its package directory, following that
package's README. The root integration tests run from the repository root:

```sh
carp -x test/carp-compiler.carp
carp -x carp-session/test/carp-session.carp
carp -x carp-session/test/core.carp
carp -x --log-memory carp-session/test/memory.carp
```

The phase harness isolates output directories for concurrent tasks and warms
the package cache before starting them. Avoid compiling two tests into the
same `out/Untitled` concurrently.

LLVM verification is separate from the default assurance groups. Run these
tests from the LLVM package directory:

```sh
cd carp-llvm-backend
carp -x test/carp-llvm-backend.carp
carp -x test/carp-session-jit.carp
```

It requires a linkable `libLLVM` and the runtime headers under `$CARP_DIR/core`.
See the [LLVM backend README](../carp-llvm-backend/README.md) for linking
requirements and the [architecture guide](architecture.md) for phase boundaries.
