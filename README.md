# Metacarp

Metacarp is a self-hosting compiler for [Carp](https://github.com/carp-lang/Carp),
written in Carp. It compiles Carp programs to C or, with the optional LLVM
backend, LLVM IR and native executables. Its libraries also support warm
compiler sessions for editors and notebooks.

The C compiler reaches a self-hosted fixed point: successive generations emit
byte-identical C for the compiler itself. The assurance scripts check this,
reference-suite behavior, and macro-expansion parity. Metacarp is still not a
drop-in replacement for reference Carp; see [limitations](#limitations).

## Start here

| Task | Documentation |
| --- | --- |
| Build and run a program | [Quick start](#quick-start) |
| Choose compiler flags | [Command line](#command-line) |
| Embed a notebook or editor session | [Session guide](docs/carp-session.md) |
| Understand the compiler pipeline | [Architecture](docs/architecture.md) |
| Run tests, check self-hosting, or benchmark | [Development](docs/development.md) |
| Use LLVM or its persistent session JIT | [LLVM backend](carp-llvm-backend/README.md) |
| Browse the libraries | [Documentation index](docs/README.md) |

## Quick start

You need the reference Carp compiler on `PATH`, a checkout of its source
repository, and `clang`. Run these commands from the Metacarp repository root.
Set `CARP_DIR` to your reference Carp checkout, not its `core/` directory:

```sh
export CARP_DIR=/path/to/Carp
carp -b --optimize main.carp
./out/carp-compiler -x -c "$CARP_DIR/core" examples/squares.carp
```

The build produces `out/carp-compiler`. The example prints:

```text
sum of squares of the even numbers in 1..10 = 220
```

The build loads pinned Carpentry dependencies into Carp's shared package cache.
The first build needs network access and Git access to those repositories.

To keep an executable instead of running it immediately:

```sh
./out/carp-compiler -b -c "$CARP_DIR/core" -o /tmp/squares examples/squares.carp
/tmp/squares
```

To inspect generated C:

```sh
./out/carp-compiler -c "$CARP_DIR/core" -o /tmp/squares.c examples/squares.carp
```

Without `--core`, the C driver can compile programs that do not need the
standard library. Generated C still needs Carp's runtime headers when linked:

```sh
./out/carp-compiler -o /tmp/hello.c examples/hello.carp
clang -I "$CARP_DIR/core" -o /tmp/hello /tmp/hello.c -lm
/tmp/hello
```

This example prints `OK`.

## Command line

```text
carp-compiler [options] <source.carp>
```

The driver accepts one input file. It emits C to standard output unless you
choose `-o`, `-b`, `-x`, `--annotate`, or `--ownership`. Diagnostics go to
standard error.

| Option | Behavior |
| --- | --- |
| `-c`, `--core <dir>` | Load the standard library; supply runtime headers for linking. |
| `-b`, `--build` | Build an executable, defaulting to `a.out`. Requires `--core`. |
| `-x`, `--execute` | Build and run a temporary executable. Requires `--core`. |
| `-o`, `--output <file>` | Choose the generated C file or, under `-b`, executable path. |
| `--optimize` | Use `clang -O3 -D NDEBUG` for `-b`/`-x`. |
| `-g`, `--debug` | Preserve source mapping; under `-b`, retain generated C beside the executable. |
| `--annotate` | Emit inferred global-definition types as JSON. Requires `--core`. |
| `--ownership` | Emit the move, borrow, and delete plan as JSON. Requires `--core`. |
| `--log-memory` | Enable runtime allocation logging in built executables. |
| `--no-core` | Skip the implicit Core load; explicit loads can still resolve through `--core`. |
| `-h`, `--help` | Show help. |
| `-v`, `--version` | Show the compiler version. |

Choose one action (`-b`, `-x`, `--annotate`, or `--ownership`) per invocation.
`-o` does not select the executable path for `-x`.

The driver resolves `(load ...)` relative to the loading file, then through
the Core directory. Git references use the shared `~/.cache/carp/libs/` cache:

```clojure
(load "git@github.com:carpentry-org/strbuf@0.2.1")
```

### LLVM driver

The optional driver needs a linkable `libLLVM`. The bindings discover its
prefix with `brew --prefix llvm` on macOS and `llvm-config --prefix` elsewhere.
Library hosts can pass an explicit prefix to `LLVM.setup`.

```sh
carp -b --optimize main-llvm.carp
./out/carp-compiler-llvm -c "$CARP_DIR/core" -o /tmp/squares.ll examples/squares.carp
./out/carp-compiler-llvm -x -c "$CARP_DIR/core" examples/squares.carp
```

This driver requires `--core` even for IR output and with `--no-core`. It
supports `-b`, `-x`, `-c`, `-o`, `--no-core`, `-g`, `--log-memory`, `-h`, and
`-v`. It does not accept the C driver's `--optimize`, `--annotate`, or
`--ownership` flags. `-g` attaches DWARF source locations; Darwin builds also
produce a `.dSYM` beside a `-b` executable.

## Examples

| File in `examples/` | Demonstrates |
| --- | --- |
| `hello.carp` | Inline C through `deftemplate`; prints `OK`. |
| `nominal.carp` | Sum types and wildcard fields in `match`. |
| `polymorphic-nominal.carp` | Two concrete instances of a generic type. |
| `nested-pattern.carp` | Nested constructor patterns. |
| `signature-nominal.carp` | Type layout discovered from a signature. |
| `squares.carp` | Arrays, lambdas, and strings from Core. |
| `simple.carp` | Registered external C primitive; linking needs an implementation of `int_inc`. |

The [CLAP experiment](experiments/metacarp-clap/README.md) embeds the warm
session and LLVM JIT in a macOS audio effect. It runs native code in the plugin
host and is an integration experiment, not a release artifact.

## Limitations

- Delete placement is scope-based rather than liveness-based, so peak memory
  can exceed reference Carp's on the same program.
- The conservative ownership plan can leak a reassigned value when its
  binding was consumed on another control-flow path.
- Diagnostics are Metacarp's own. Reference-suite parity checks rejection
  behavior, not identical error text.
- The command-line drivers build for the host; they expose no cross-compilation
  target option.

## Dependencies and license

The compiler loads `carp-reader@0.4.1` and `strbuf@0.2.1`. The session library
also loads `rc@0.3.0`; the LLVM backend loads `llvm@0.1.0`.

MIT. See [LICENSE](LICENSE).
