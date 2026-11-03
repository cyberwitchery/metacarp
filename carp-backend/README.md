# carp-backend

`carp-backend` lowers the specialized module and its ownership plan to one C
translation unit. It is two stages in one library:

`BackendLower` rewrites specialized bodies into emission shape: array literals
are hoisted out of value positions (ANF-style, freed after use unless
consumed), the ownership plan's deletes are inserted at the expression that
consumes each one — let scopes, `set!` sites (evaluate the new value, delete
the old, assign), by-value match branch exits, function exits for parameters —
wildcard pattern slots with a deleter are bound to fresh locals so their
payloads can be freed, capturing lambdas are lifted into closure functions
with heap-allocated environments, and top-level results are echoed through
their `str` implementations when the driver asks.

`CBackend` renders the result: struct/sum-type layouts with unit members
elided, pattern-binding extraction, the parameterized primitive templates
(array/box copy, delete, and str loops over their element dependency), and the
final translation unit with `carp_init_globals` and `main`. C names come from
`carp-c-abi`'s mangling.

Cleanup uses one body rewrite for ordinary functions and lifted callbacks,
preserving context-specific deleters and the distinction between parameter-exit
and assignment-site deletes. It resolves binding deletes once, then uses a
shared `PositionBuckets` index to select each context without rescanning the
ownership action list. Resolution handles missing-deleter errors; body, root,
and closure rewriting then use the same resolved plan. Negative contexts
retain the complete action order. The plan is released before backend
materialization.

Cleanup consumes the lifted module and closure array. Each body expression is
replaced in its existing record, releasing its old tree before the next body.
Signatures, parameters, capture descriptions, specialization metadata, and the
body and closure arrays retain their storage. Root rewriting replaces only the
root array. Public lowering entry points still borrow their inputs.

The optional `symbols.carp` pass selects native copier, deleter, and echo
symbols from a closed specialization module. It indexes implementation roles
once, preserving full reference identity, then walks concrete instances in
order. Echo demands carry accepted type keys; the selected `str` signature
determines the calling convention.

Expression rendering borrows its `BackendModule`, including the constructor,
copier, and deleter tables. Lowering does not prime C-emission symbol state.
Full translation units and standalone function sections use the same module
tables, so lowering another module cannot replace a deferred module's capture
copiers or field deleters.

C source directives also read that module's `BackendLineMap` directly, without
installing or copying it into process state. Shared line, column, and file
lookups preserve independent bounds and missing-location defaults for C and
LLVM. An unmapped module emits no source directives or reset marks, including
when rendered after a mapped module.

Deletes name their concrete deleter symbol (resolved from the ownership
plan's requirements) — the shallow `__carp_array_free` sentinel is only a
fallback for arrays whose element type is unmanaged.

```bash
carp -x test/carp-backend.carp
```
