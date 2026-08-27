# carp-llvm-backend

**Status: reference-suite parity.** An alternative backend that lowers a `BackendModule` (the
same lowered form `CBackend` renders to C) to LLVM IR through the
[carpentry-org/llvm](../../llvm) bindings. It consumes the pipeline after
`BackendLower`; everything upstream — specialization, ownership planning,
lambda lifting — is shared with the C backend unchanged.

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
beyond this records an emission error naming itself — `emit-module` returns
them joined — rather than mis-lowering.

Lowering decisions worth knowing:

- Bool lowers to i8 to match the C backend's `bool`; conditions compare
  against zero at branch sites.
- Sum types mirror the C backend's layout under the module's target data
  layout (`emit-module` takes an `LLVMTargetData`): `{ union-rep, i32 tag }`,
  where union-rep is the strictest-aligned variant struct padded with bytes to
  the union's ABI size, and a nullary variant is `{ i8 }` like the C backend's
  `unsigned char unused`. Variant access goes through memory — opaque-pointer
  typed GEPs overlay the active variant on the union area — so constructors
  spill to an alloca and matches store the scrutinee into a pre-allocated
  entry-block spill slot. Match compiles to tag tests with the C backend's
  `abort()` on fall-through. The test asserts size and tag-offset parity
  against the host C compiler's `sizeof`/`offsetof` (`LLVMBackend.sum-layout`).
- Aggregates cross the LLVM/C call boundary through generated pointer-only
  wrappers: a C-native callee (template or header-backed registered function)
  whose signature moves an aggregate by value gets a `<symbol>_carpabi`
  wrapper in the shim — every parameter arrives by pointer, results leave
  through an out-pointer — so the C compiler performs all aggregate ABI
  coercions on its side. The LLVM side spills arguments to entry-block slots
  and calls the wrapper. LLVM-to-LLVM calls pass aggregates directly.
- Ownership-planned code works: plan-inserted deletes arrive as ordinary
  calls (declared on demand from their own call signature — the C backend
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
  data, yielding a `String*` borrow of static storage. Owned strings (copy,
  delete, `String.append`, ...) are the not-yet-started managed tier.
- The helpers live at top level like the C backend's renderers: mutual
  recursion between defns inside a `defmodule` loses definitions during
  emission under the reference compiler. An ignored recursive call also needs
  its result type pinned (`(ignore (the LLVMValue (llvm-emit-expr ...)))`).

The entry point is `LLVMBackend.emit-module`, which fills a caller-provided
LLVM context/builder/module; verification, JIT execution, and object emission
stay with the caller through the bindings. `LLVMBackend.shim-translation-unit`
renders the C-native declarations (deftemplate sources, primitive templates)
into an entry-point-free C translation unit via the C backend's own renderer;
the test compiles it with clang into a dylib and `dlopen`s it with
`RTLD_GLOBAL`, so MCJIT resolves the template symbols — an AOT build would
link the shim object instead. Since both backends read the same lowered
`BackendModule`, the mangled symbols agree by construction.

```bash
carp -x test/carp-llvm-backend.carp
```

The backend also has a driver: `carp -b --optimize main-llvm.carp` at the
repository root builds `out/carp-compiler-llvm`, which shares the C driver's
whole front half (`driver-load.carp`) and prints LLVM IR by default, or builds
and runs a native executable under `-b`/`-x` (object file through the LLVM
target machine, linked by clang against the C shim plus a generated `main`).
every runnable example — `hello.carp`, `nominal.carp`, `nested-pattern.carp`,
`signature-nominal.carp`, `polymorphic-nominal.carp`, and `squares.carp` (the
full standard library: lambdas, `copy-map`, string formatting) — runs end to
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
