# carp-llvm-backend

**Status: reference-suite parity.** An alternative backend that lowers a `BackendModule` (the
same lowered form `CBackend` renders to C) to LLVM IR through the
[carpentry-org/llvm](https://github.com/carpentry-org/llvm) bindings. It
consumes the pipeline after `BackendLower`. Specialization, ownership
planning, and lambda lifting are shared with the C backend.

## Build and use the driver

Run from the repository root with `CARP_DIR` pointing to the reference Carp
checkout. A linkable `libLLVM` is required; the bindings use Homebrew on macOS
and `llvm-config` elsewhere to discover the installation prefix.

```sh
carp -b --optimize main-llvm.carp
./out/carp-compiler-llvm -c "$CARP_DIR/core" -o /tmp/squares.ll examples/squares.carp
./out/carp-compiler-llvm -x -c "$CARP_DIR/core" examples/squares.carp
```

The driver requires `--core` for every compilation, including IR output and
`--no-core`. See the [command-line guide](../README.md#llvm-driver) for flags.
For embedding, start with the [session guide](../docs/carp-session.md).

- [Supported lowering](#supported-lowering)
- [Representation and C ABI](#representation-and-c-abi)
- [Library entry point](#library-entry-point)
- [Persistent session JIT](#persistent-session-jit)
- [Verification](#verification)
- [Native driver and debugging](#native-driver-and-debugging)

## Supported lowering

Scope covers every example tier plus owned strings, arrays, closures, and
generic sum-type instances, with ownership-planned deletes: concrete
functions over Int, Bool, Long, Double, Float, Char, Byte, the fixed-width
registered types, and Unit; array literals and the allocate/aset-uninitialized!
builtins; lambdas (non-capturing wrapped over their lifted function, capturing
constructed over a heap environment with generated env delete/copy) and calls
through Lambda values (env-first when an environment is present, the C
backend's convention); string and pattern literals (borrowed static storage); `if`, `let`,
`do`, `set!`, `while`, and `break`; direct global calls; `def` globals with
runtime initializers, global reads (`Reference`/`GlobalValue`, including the
NULL builtin), and global `set!`; concrete sum types with constructors and
by-value `match` (nested patterns included); registered intrinsics (declared
in the module, resolved by the JIT from the process symbol table or by the
linker); and `deftemplate` C sources through the shim below. Top-level
expressions collect into one synthesized function (`LLVMBackend.roots-symbol`)
which first calls the synthesized global-initializer function
(`LLVMBackend.init-symbol`, this backend's `carp_init_globals`; JIT clients
calling individual functions must call it once themselves). Every construct
outside the supported set records a named emission error. `emit-module`
returns the collected errors.

## Representation and C ABI

Lowering decisions:

- Bool lowers to i8 to match the C backend's `bool`; conditions compare
  against zero at branch sites.
- Sum types mirror the C backend's layout under the module's target data
  layout (`emit-module` takes an `LLVMTargetData`): `{ union-rep, i32 tag }`,
  where union-rep is the strictest-aligned variant struct padded with bytes to
  the union's ABI size, and a nullary variant is `{ i8 }` like the C backend's
  `unsigned char unused`. Variant access goes through memory. Opaque-pointer
  typed GEPs overlay the active variant on the union area. Constructors
  spill to an alloca and matches store the scrutinee into a pre-allocated
  entry-block spill slot. Match compiles to tag tests with the C backend's
  `abort()` on fall-through. The test asserts size and tag-offset parity
  against the host C compiler's `sizeof`/`offsetof` (`LLVMBackend.sum-layout`).
- Aggregates cross the LLVM/C call boundary through generated pointer-only
  wrappers: a C-native callee (template or header-backed registered function)
  whose signature moves an aggregate by value gets a `<symbol>_carpabi`
  wrapper in the shim. Every parameter arrives by pointer and results leave
  through an out-pointer. The C compiler performs all aggregate ABI
  coercions on its side. The LLVM side spills arguments to entry-block slots
  and calls the wrapper. LLVM-to-LLVM calls pass aggregates directly.
- Ownership-planned code works: plan-inserted deletes arrive as ordinary
  calls (declared on demand from their own call signature, the C backend
  leans on header declarations there), the `ref`/`deref` builtins (ids 5/6)
  lower to address-of (with pre-scanned slots for addressable locals) and
  loads, and the `__carp_array_free` sentinel lowers to `free` of the backing
  data. Array literals malloc their data and build `{ len, capacity, data }`;
  `Array.unsafe-nth` and `Array.length` lower inline.
- `set!`-targeted binders get entry-block alloca slots (found by a pre-scan),
  so mem2reg can promote them; every other binder stays SSA. Global reads and
  writes go through the mangled global (`CAbi.mangle` + `CAbi.identifier`,
  exactly the C backend's derivation), declared as zero-initialized LLVM
  globals and filled by the init function in declaration order.
- A string literal mirrors the C backend's `({ static String v = "..."; &v; })`:
  a private global pointer variable initialized with the interned literal
  data, yielding a `String*` borrow of static storage. Owned strings cross the
  generated C shim for copy, delete, and other runtime operations, with their
  lifetimes governed by the shared ownership plan.
- The helpers live at top level like the C backend's renderers: mutual
  recursion between defns inside a `defmodule` loses definitions during
  emission under the reference compiler. An ignored recursive call also needs
  its result type pinned (`(ignore (the LLVMValue (llvm-emit-expr ...)))`).

## Library entry point

The entry point is `LLVMBackend.emit-module`, which fills a caller-provided
LLVM context/builder/module; verification, JIT execution, and object emission
stay with the caller through the bindings. `LLVMBackend.shim-translation-unit`
renders the C-native declarations (deftemplate sources, primitive templates)
into an entry-point-free C translation unit via the C backend's own renderer;
the test compiles it with clang into a dylib and `dlopen`s it with
`RTLD_GLOBAL` so MCJIT resolves the template symbols. An AOT build links
the shim object instead. Since both backends read the same lowered
`BackendModule`, the mangled symbols agree by construction. A `BackendModule`
also carries its backend-neutral `BackendLineMap`; when populated, the LLVM
emitter builds compile units, subprograms, file-specific lexical scopes, and
instruction locations from expression identities.

## Persistent session JIT

The backend also powers a session JIT (`carp-session-jit.carp`): a
notebook/editor host loads it beside carp-session and calls
`SessionJit.run-cell`. The transactional cell pipeline stops at the lowered
`BackendModule` (`Session.lower-cell-plain`), which is emitted as an incremental
module into one persistent ORC LLJIT and thread-safe LLVM context. Definitions,
closures, globals, and their storage stay published across cells; later modules
declare rather than redefine those symbols and carry uniquely named roots and
global-init functions. Per-cell resource trackers roll back a module if roots
lookup fails. A committed definition edit conservatively clears published
native code while retaining the LLJIT, context, target state, and template
shim. The semantic session likewise retains one merged Core/inference view;
each transient cell appends and retracts only its own IR and inference traces.
Concrete specializations are cached across successful cells, so a later cell
materializes and lowers only newly reached definitions. Template
specializations live in one shim dylib compiled on the first cell and reused
until a cell introduces a new specialization; a warm cell pays no clang at
all. `run-cell` returns the cell's last integer-typed top-level value;
`run-cell-echoed` prints the result the way a driver-built binary would.
Measured on an Apple arm64 host against the real Core: first cell 1.07 s
(includes the one shim clang), warm cells 62.8 ms, and the emit-C → clang → run
path 382.0 ms per cell (`test/jit-benchmark.carp`). Before the resident semantic
view and specialization cache, the same persistent-ORC path took 99.5 ms per
warm cell.

## Verification

Run from this package directory, with `CARP_DIR` set to an absolute path:

```bash
carp -x test/carp-llvm-backend.carp
carp -x test/carp-session-jit.carp
```

## Native driver and debugging

The backend also has a driver: `carp -b --optimize main-llvm.carp` at the
repository root builds `out/carp-compiler-llvm`, which shares the C driver's
whole front half (`driver-load.carp`) and prints LLVM IR by default, or builds
and runs a native executable under `-b`/`-x` (object file through the LLVM
target machine, linked by clang against the C shim plus a generated `main`).
`-g`/`--debug` preserves the loader's source texts and provenance, attaches
DWARF line and byte-column locations to LLVM IR, and emits a `.dSYM` beside a
Darwin `-b` executable before its temporary object is removed. ELF targets
retain the object DWARF in the linked executable.
Every runnable example, `hello.carp`, `nominal.carp`, `nested-pattern.carp`,
`signature-nominal.carp`, `polymorphic-nominal.carp`, and `squares.carp` (the
full standard library: lambdas, `copy-map`, string formatting), runs end to
end and prints what the C driver's build prints. A Carp `(defn main ...)`
becomes the executable's entry through the shim (roots first, then main, like
the C backend). `simple.carp` fails at link on its deliberately undefined
`int_inc` in both drivers alike.

The driver passes the reference test suite at parity with the C driver:
`CARP_COMPILER=$PWD/out/carp-compiler-llvm scripts/run-carp-suite-self.sh`
reports the same score as the C driver (every test and example, with the one
suite-sanctioned `memory.carp` gap both drivers share). The driver is also
self-hosting: gen-1 metacarp builds `main-llvm.carp` (compile-time
`system-include`/`add-cflag` from `LLVM.setup` flow through expansion into
the resolver and the clang command), and the self-built driver reproduces
the same suite score.

The test lowers `examples/simple.carp`, `examples/hello.carp`,
`examples/nominal.carp`, and two inline programs end to end, verifies every
module, JIT-executes functions covering every supported construct (template
calls cross into the compiled shim), asserts sum-layout parity against the
host C compiler, and checks the same `BackendModule` still renders through
the C backend. Requires `CARP_DIR` for the shim's `-I` include. Note the
front half only specializes what is reachable from top-level expressions, so
a function must be called from a root to exist in the module. Requires LLVM
with a linkable `libLLVM` (Homebrew keg by default, see `LLVM.setup`). On
Linux the test binary needs its symbols exported (`-rdynamic`) for the JIT to
resolve the support primitives; macOS exports them by default.
