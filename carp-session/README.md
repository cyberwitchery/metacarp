# carp-session

Warm, transactional compiler state for notebook and editor hosts. The library
checks Core once, then reuses its expansion, resolution, and inference state
for transient cells and committed definition updates.

Read the [session integration guide](../docs/carp-session.md) for a runnable
example, the current API, source spans, input ownership, rollback behavior,
editor queries, and code generation.

Load `carp-session/carp-session.carp` from the repository root. The library
exposes `CompilerSession` through operations in the `Session` module. API
version 1 includes:

- `create`, `create-from-module`, and `reset` for session lifecycle.
- `infer-cell` for checking transient source.
- `upsert`, `remove`, and `definitions` for name-based definition editing.
- `upsert-input` and `remove-input` for whole source buffers.
- `ownership`, `expand`, `expand-1`, `trace-expand`, `complete`, and `doc` for
  editor queries.
- `prepare-emit`, `emit-cell`, `lower-cell`, and `lower-cell-plain` for code
  generation.

The host owns transport, source buffers, executable storage, and runtime
values. Persistent native execution is provided separately by
[`SessionJit`](../carp-llvm-backend/README.md) in the LLVM backend.

## Verification

Run from the repository root with `CARP_DIR` pointing to the reference Carp
checkout:

```sh
carp -x carp-session/test/carp-session.carp
carp -x carp-session/test/core.carp
carp -x --log-memory carp-session/test/memory.carp
carp -x carp-session/test/benchmark.carp
```

The benchmark records cold creation and repeated warm checks against real
Core. Its timings depend on the machine, compiler build, and submitted cells.
