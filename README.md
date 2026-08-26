# carp-compiler

A self-hosting compiler for [Carp](https://github.com/carp-lang/Carp), written
in Carp. It reads Carp source and emits a C translation unit, driving the whole
pipeline — module loading, macro expansion, name resolution, type inference,
interface specialization, ownership and borrow checking, and C code generation —
in Carp itself.

> **Status: self-hosting.** The compiler compiles itself, and the result
> compiles the compiler again to byte-identical C — a fixed point. Both
> generations pass the reference compiler's test suite (154 entries: examples,
> output tests, error-rejection tests, benches). It is still not a drop-in
> replacement for the reference compiler (see [Limitations](#limitations)).

## Build

Requires the reference [Carp](https://github.com/carp-lang/Carp) compiler and a
C compiler (`clang`). Building bootstraps the roughly 42,000 lines of compiler
source through reference Carp:

```sh
carp -b --optimize main.carp
```

This produces `./out/carp-compiler` and `./out/main.c`. The entire `out/`
directory is generated and ignored; neither file is a trusted bootstrap seed.
Always rebuild generation 1 after changing compiler source, then validate it:

```sh
CARP_FIXED_POINT_OUT=/tmp/metacarp-fixed \
  ./scripts/check-fixed-point.sh
```

After fixed-point validation, produce the source-only end-user bootstrap asset:

```sh
CARP_FIXED_POINT_OUT=out/fixed-point scripts/build-bootstrap-bundle.sh
```

The deterministic `.tar.gz` contains generation-2 compiler C, generated CBOR
session-host C, the exact Carp Core source/runtime headers, and a hash manifest.
It also carries Meta-Carp's MIT license and Carp/Core's Apache-2.0 and Lua
license notices. It contains no platform-native executable. Carpaccio can therefore verify one
GitHub release asset, compile both programs with the user's Clang, and cache
them without requiring Haskell Stack; Stack remains part of the independent
from-source assurance chain.

The harness emits generation 2 and generation 3, links with `-O3 -D NDEBUG`,
requires byte-identical C, compiles and runs `examples/hello.carp`, and records
source/compiler hashes in `bootstrap-provenance.txt`. Only promote a compiler
after those checks succeed. At revision `7aee762`, reference Carp built
generation 1 in 527.04 seconds at about 1.09 GiB; optimized Meta-Carp emitted
the next generation in 99.49 seconds at about 0.91 GiB. This is a bootstrap
operation, not the latency of resident incremental compilation.

## Usage

```
carp-compiler [options] <source.carp>

  -b, --build           compile to an executable instead of C (needs --core)
  -x, --execute         compile to an executable and run it (needs --core)
  -c, --core <dir>      compile against the Carp standard library in <dir>
  -o, --output <file>   output path — the C file, or the executable under -b
  --optimize            build -b/-x executables with clang -O3 -D NDEBUG
  --library             emit C without a process entry point (needs --core)
  --no-core             skip the implicit Core load; the source's own
                        (load "X.carp") directives still resolve in --core
  -h, --help            show this help and exit
  -v, --version         show version and exit
```

With no `-b`/`-x`, the C translation unit is written to standard output (or
`-o`). Diagnostics go to standard error and name the rejecting compiler phase.
`-b`/`-x` require `--core`, because linking needs the runtime headers the
standard library ships with.

`--library` selects the backend's reusable translation unit: named roots and
global initialization remain available, but the platform
`int main(int, char**)` entry point is omitted. Embedders are responsible for
stable exported wrappers and for calling `carp_init_globals` when the module
contains runtime-initialized globals.

`(load ...)` resolves like the reference compiler's: relative to the loading
file, then the Core directory — and git references install into the shared
cache (`~/.cache/carp/libs/...`) on first use:

```clojure
(load "git@github.com:carpentry-org/strbuf@0.2.0")
```

The examples below assume `CARP_DIR` points at a checkout of the reference
Carp repository (its `core/` is the standard library and runtime headers).

The bootstrap baseline must include Carp's recursive value-type `Box`
refactor (carp-lang/Carp#1571). Meta-Carp emits `Box a` as the aggregate
`Box__a { a* data; }`, while `Ptr a` remains the raw `a*` ABI. CI pins Carp at
`d718653fb82a62f667bf2117f30222267c5fbb27`; the Core revision is therefore
part of the compiler ABI and should be recorded in binary/cache provenance.

Compile a standalone program (no standard library) to C:

```sh
./out/carp-compiler examples/hello.carp \
  | clang -x c -I "$CARP_DIR/core" -o /tmp/carp-hello -
/tmp/carp-hello        # prints: OK
```

Compile and run a program that uses the standard library:

```sh
./out/carp-compiler -x -c "$CARP_DIR/core" examples/squares.carp
# sum of squares of the even numbers in 1..10 = 220
```

## Self-hosting

The bootstrap chain, from the repository root, is automated by the assurance
harness:

```sh
./scripts/run-assurance.sh self
```

It freshly builds generation 1 with reference Carp before running the
reference suite, fixed-point/provenance/smoke checks, and expansion parity.
`scripts/check-fixed-point.sh` alone deliberately consumes
`CARP_COMPILER` (default `out/carp-compiler`); do not point it at an old local
artifact.

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

The assurance harness keeps the self-host honest:

CircleCI is the primary Linux topology in `.circleci/config.yml`: one cached
bootstrap job supplies the pinned reference Carp checkout and style tools;
the reference phase suite and self-host assurance then run in parallel; the
fixed-point generation-2 compiler is passed through a workspace into the final
phase-suite job. GitHub Actions retains the same Linux gates during the CI
transition and the independent ARM64 macOS self-host lane.

- `scripts/run-assurance.sh phase` runs lint and formatting before every
  phase/session suite. Set `CARP_SKIP_STYLE=1` when the two style tools are
  unavailable. Set `CARP_PHASE_JOBS=2` or `3` to run independent test groups
  concurrently; CI runs this architecture-neutral group once on two Linux
  workers.
- `scripts/run-assurance.sh phase-self` runs the same compiler-phase and
  session suites through `CARP_PHASE_COMPILER` (default
  `out/carp-compiler`). CI retains the fixed-point generation-2 executable and
  points this lane at it, catching both compiler-source regressions and
  generation-specific miscompilations that the reference-compiler phase lane
  cannot expose. The reference-only memory-log test remains in `phase`,
  because the self-hosted CLI does not implement Carp's `--log-memory`
  instrumentation.
- `scripts/run-assurance.sh self` builds gen 1, runs the reference suite,
  checks the self-hosted fixed point, and compares expansion behavior. Set
  `CARP_SELF_JOBS=2` or `3` to split the reference suite across isolated
  workers; CI uses all two Linux or three macOS runner cores.
- `scripts/run-assurance.sh all` runs both groups and is the default. CI calls
  the same phase and self groups rather than maintaining its own command list.
  The self-host group executes generated programs on both x86-64 Linux and
  ARM64 macOS for every commit. CI caches the versioned Carp library checkouts
  on both architectures and the pinned Ubuntu style-tool binaries; generated
  compiler and test outputs are deliberately never cached.

- `scripts/run-carp-suite-self.sh` runs the reference repository's own test
  suite (examples, produces-output diffs, `test/*.carp`, error-rejection
  tests, bench builds) through this compiler. It finds the reference checkout
  through `CARP_ROOT` or `CARP_DIR`, and `CARP_COMPILER` can point it at a
  gen-2 binary.
- `scripts/diff-expansion.sh` compiles and runs a front-end corpus (macros,
  quasiquote, gensym, dynamic evaluation) under both the reference compiler
  and this one and requires identical observable output.

## Examples

The programs in `examples/` double as checkpoints. The standalone ones need no
standard library:

| example                    | shows                                                        |
| -------------------------- | ------------------------------------------------------------ |
| `simple.carp`              | functions, `if`, a registered C primitive                    |
| `hello.carp`               | `deftemplate` inline C; prints `OK`                          |
| `nominal.carp`             | `deftype` sum type, `match` with a wildcard field            |
| `polymorphic-nominal.carp` | one polymorphic type specialized at two instances            |
| `nested-pattern.carp`      | nested constructor patterns                                  |
| `signature-nominal.carp`   | layout discovery from a signature, no reachable constructor  |
| `squares.carp`             | the full standard library (needs `--core`)                   |

## How it works

Source flows through fifteen phase libraries, each with its own directory,
data model, and tests:

```
source registry
  -> carp-module      module loading, load-order and git-reference resolution
  -> carp-surface     lossless surface parsing
  -> carp-expand      macro expansion (with carp-ct-env / carp-ct-eval)
  -> carp-resolve     name resolution into the core IR (carp-ir)
  -> carp-infer       Hindley–Milner type inference (carp-types)
  -> carp-specialize  interface selection and monomorphization
  -> carp-ownership   ownership planning and flow-sensitive borrow checking
  -> carp-backend     lowering and C emission (carp-c-abi for mangling)
  -> one C translation unit
```

Supporting libraries: `carp-primitives` (the declarative primitive registry) and
`carp-graph` (strongly-connected-component ordering), plus `carp-source`
(caller-owned source identities and byte spans) and `carp-session` (warm,
transactional notebook inference). Each phase reports failures tagged with its
own name.

Ownership is real: the compiler derives `delete`/`copy` for managed `deftype`s
(concrete and generic), runs a sound flow-sensitive borrow check (escape, move,
borrow-after-move, branch joins), and emits the corresponding C cleanup. The
delete plan covers let scopes, unconsumed parameters, discarded intermediates,
`set!` overwrites, by-value `match` bindings (used or not), and the payloads a
wildcard pattern drops — with deep deleters and copiers for nested containers.
Escaping closures heap-allocate their environments.

The reusable entry point is `CarpCompiler.compile-source`, or
`CarpCompiler.compile-sources` when the caller already holds an in-memory source
registry.

## Session library

[`carp-session`](carp-session/README.md) keeps an inferred core resident for
notebook and editor clients, then provides transactional definition updates,
cell-relative typed reports, ownership queries, completion, and incremental
code generation. Its API remains transport-neutral. The optional
[`hosts/cbor`](hosts/cbor/README.md) adapter provides the compact machine
protocol used by Carpaccio. The separately loadable
[`replikativ/carp-nrepl`](https://github.com/replikativ/carp-nrepl) package
provides a JVM-free nREPL server for existing editor and command-line tools
without making editor transport part of this compiler.
[`docs/carp-session.md`](docs/carp-session.md) records the original design and
implementation history.

[`docs/semantic-delta.md`](docs/semantic-delta.md) separates the branch's
language changes from compiler-correctness and hosting work, maps its affine
contracts to Rust, and records the deliberately weaker parts of that mapping.
[`docs/rust-affine-interop.md`](docs/rust-affine-interop.md) contains the
lower-level ownership design.

## Limitations

- Target configuration is detected from the build host; an explicit
  cross-compilation target override is not implemented yet.
- Delete placement is scope-based, not liveness-based: values die at scope or
  branch exit rather than after their last use, so peak memory can exceed the
  reference compiler's on the same program.
- A binding consumed on one control-flow path and reassigned later leaks the
  reassigned value (the plan is any-path conservative; it never double-frees).
- Error messages are deliberately this compiler's own; only rejection behavior
  matches the reference, not diagnostic text.

## Dependencies

Two pinned Carpentry packages, loaded as git references:

```clojure
(load "git@github.com:carpentry-org/carp-reader@0.3.8")
(load "git@github.com:carpentry-org/strbuf@0.2.0")
```

## License

MIT. See [LICENSE](LICENSE).
