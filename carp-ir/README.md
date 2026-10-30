# carp-ir

`carp-ir` defines the resolved, compiler-owned core representation shared by
resolution, inference, and specialization. `CoreRef.id` is the stable binding
identity; names remain only for diagnostics and generated symbols.

`CoreExpr` covers literals, resolved references, calls, `if`, `do`, lexical
`let`, `set!`, `while`, `break`, `match`, lambdas, array and static-array
literals, and explicit type annotations. `CoreModule` carries function
definitions, values, builtins and builtin sources, type and constructor
declarations, interface signatures, implementation registrations, and requested
system includes. It has no dependency on the reader, macro expander, or type
implementation.

`CoreIR.append-module!` appends a module's complete payload in place;
`CoreIR.append-modules` copies the left module and uses the same append path.
Sessions additionally load `module-transactions.carp` for `mark-module` and
`retract-module!`. A mark records array boundaries for append-only rollback
on the same module, including nested checkpoints. It does not restore edits
to entries that existed before the mark. These helpers cover all 13 fields,
including recursive type names and overloads.

`index-call-sites` consumes its module. It replaces functions, values, and
roots while retaining storage for the ten declaration fields it does not
rewrite. Borrowing callers must explicitly copy before calling it.
