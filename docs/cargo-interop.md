# Cargo adapter interoperability

Meta-Carp consumes Rust through a stable C ABI. It never depends on Rust's
unstable native ABI. A Cargo adapter is a `cdylib` or `staticlib` crate whose
public boundary consists of `extern "C"` functions, `#[repr(C)]` values, and
opaque handles with explicit destruction.

This document describes the compiler boundary implemented in Meta-Carp.
Automatic Cargo/rustdoc discovery, adapter generation, dynamic loading, Panama
bindings, and JVM owner objects belong to Carpaccio and are documented and
tested in that repository. Keeping that division explicit makes the compiler
changes suitable for upstream review without making Meta-Carp appear to
contain its Clojure host.

## Implemented compiler boundary

The Carp binding module owns typed declarations and foreign ownership modes:

```clojure
(system-include "example.h")
(defmodule Example
  (register inspect (Fn [(Ref Item)] Double) "example_inspect" [shared])
  (register mutate! (Fn [(Ref Item)] ()) "example_mutate" [unique])
  (register consume (Fn [Item] ()) "example_consume" [take]))
```

Resolution checks that the mode list matches function arity, that `shared` and
`unique` are used only for reference parameters, and that by-value parameters
use `copy` or `take`. The ownership pass:

- preserves these contracts in its structured manifest;
- rejects overlapping strict unique access, including another argument that
  takes the same owner;
- propagates unique requirements through ordinary Carp wrappers;
- marks owned values passed by value to global or dynamic closure calls as
  moved; and
- uses the same move/borrow/delete plan for C emission and session reports.

`Session.emit-library` emits an entry-point-free C translation unit for
explicit roots. `Session.emit-library-with-build` carries caller-resolved
include directories and link libraries alongside that C and the exact
ownership reports used during lowering. The command-line driver exposes the
same build inputs through repeatable `--include` and `--link` options.

Meta-Carp does not execute Cargo implicitly while parsing source. A host may
run Cargo with an argument vector, resolve its artifact, then supply bindings,
include directories, and libraries through these APIs.

## Native fixture

The dependency-free fixture demonstrates that the boundary is native Carp FFI,
not a Carpaccio-only facility:

```sh
cargo build --release --manifest-path examples/rust-cargo/Cargo.toml
out/carp-compiler -b --optimize -c "$CARP_DIR/core" \
  --include examples/rust-cargo/include \
  --link examples/rust-cargo/target/release/libmetacarp_rust_example.so \
  -o /tmp/metacarp-rust-example examples/rust-cargo/main.carp
/tmp/metacarp-rust-example # prints 42
```

`scripts/run-rust-cargo-example.sh` performs the platform-sensitive form of
this smoke test.

## Adapter descriptor boundary

Hosts can describe a resolved adapter with data rather than executable shell
text. The logical first version is shown here as EDN; Carpaccio and the native
session host use canonical CBOR on the wire:

```clojure
{:format 1
 :manifest "rust/example/Cargo.toml"
 :package "example-adapter"
 :profile :release
 :features []
 :library {:linux "target/release/libexample_adapter.so"
           :macos "target/release/libexample_adapter.dylib"
           :windows "target/release/example_adapter.dll"}
 :include-dirs ["include"]
 :bindings ["bindings/Example.carp"]}
```

Paths are resolved relative to the descriptor. The library path is explicit:
Cargo package names, target names, platform suffixes, workspaces, and custom
target directories make guessing it unreliable. Features are individual names,
never shell fragments. Successful artifacts should be copied to an immutable,
content-addressed location before loading; a failed build must not replace the
active generation.

## Safety boundary

- Rust panics must be caught and must not unwind across the C boundary.
- Rust-specific containers, trait objects, futures, and default enums do not
  cross directly; adapters expose stable carriers or opaque handles.
- A dynamic library cannot unload while native handles, callbacks, or returned
  borrows remain live.
- Callback lifetime, thread, and unwind behavior requires an explicit adapter
  contract.
- Tight loops should remain behind a native root rather than crossing the C or
  Panama boundary per element.

`unsafe-sendable` and `requires-send` are currently **unsafe host
attestations**, not compiler-derived Rust `Send`/`Sync` proofs. Meta-Carp
preserves them in the Core IR and ownership artifact. At API revision 4,
`requires-send` verifies that its target name resolves and both forms validate
their syntax, but nominal existence/admissibility, callable arity, duplicate
indices, structural `Send`, and closure captures are not yet enforced. Hosts
must only emit these forms from trusted Rust metadata they have independently
validated. They should remain a separate draft upstream proposal until those
checks land.

## Division of responsibility

Meta-Carp supplies:

1. stable C ABI declarations and reusable library emission;
2. affine foreign parameter contracts and ownership/lifetime reports;
3. transport-neutral resident compiler sessions; and
4. explicit include/link build inputs.

Carpaccio supplies Cargo metadata/rustdoc extraction, conservative wrapper
generation for supported Rust APIs, immutable build generations, dynamic
library loading, Coffi/Panama invocation, JVM lifetime objects, and REPL-facing
`cargo/api`, `cargo/import!`, and `cargo/import-local!` operations. Unsupported
Rust APIs are reported rather than guessed.

The next compiler-side steps are to validate `Send` metadata against nominal
declarations and callable arities, distinguish `Send` from `Sync`, model
closure-capture transfer, and only then consider deriving structural
capabilities. Advanced Rust coverage—traits, callbacks, async, const generics,
and aggregate LTO—should remain host/adapter work unless it reveals a generally
useful affine or ABI primitive that belongs in Carp itself.
