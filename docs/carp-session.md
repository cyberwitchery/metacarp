# Embedding a compiler session

`carp-session` keeps a checked compiler base resident for notebook and editor
hosts. It owns semantic state and structured reports. Your host owns source
buffers, transport, display, executable storage, and runtime values.

The current API version is 1. Load `carp-session/carp-session.carp`; the session
value is a `CompilerSession`, and operations use a reference to it. Treat its
fields as implementation details. This guide describes the implemented API,
not the original delivery plan.

## Check a cell

Save this program at the repository root as `session-example.carp`:

```clojure
(load "carp-session/carp-session.carp")
(Project.no-echo)

(defn show-diagnostic [diagnostic]
  (IO.errorln (Diagnostic.message diagnostic)))

(defn main []
  (match (IO.getenv "CARP_DIR")
    (Maybe.Nothing) (IO.errorln "Set CARP_DIR to your reference Carp checkout")
    (Maybe.Just root)
      (let [core (String.append &root "/core")]
        (match (Session.create &core)
          (Result.Error diagnostic) (show-diagnostic &diagnostic)
          (Result.Success session)
            (let [input (SourceInput.init @"cell:1" @"(Int.+ 1 2)")]
              (match (Session.infer-cell &session &input)
                (Result.Error diagnostic) (show-diagnostic &diagnostic)
                (Result.Success report)
                  (IO.println
                    (SessionTypedEntity.type
                      (Array.unsafe-nth (CellReport.forms &report) 0)))))))))
```

With `CARP_DIR` pointing to the reference Carp checkout, run:

```sh
carp -x session-example.carp
```

It prints `Int`. Inference checks the cell; it does not execute it or commit
its definitions. Reuse the same session for subsequent operations instead of
creating a session for each cell.

`Session.create` loads, expands, resolves, and infers Core once. Hosts with an
already-loaded `SourcedSurfaceModule` can instead call
`Session.create-from-module` with that base and an `ExpandConfig`.
`Session.reset` discards committed user state and caches while retaining the
warm base.

## Source identity and reports

`SourceInput` has `id` and `source` fields. Supply a stable logical ID for each
buffer and its exact UTF-8 source text. Reuse the ID when replacing the same
input; it does not promise stable syntax-node IDs after an edit.

`SourceSpan` has `source-id`, `start`, and `end`. Offsets are half-open UTF-8
byte ranges into the identified input, not character indexes or positions in
a concatenated replay file. The host converts them to line and column
positions. Macro-generated syntax is anchored to the invocation span.

`Diagnostic` has `phase`, `message`, and an optional `span`. A generated-code
failure may have no source span; some code-generation failures cover the
whole submitted cell rather than one expression.

`CellReport` contains four arrays:

| Field | Contents |
| --- | --- |
| `forms` | Top-level typed entities. |
| `definitions` | `SessionDefInfo` values for definitions in the cell. |
| `locals` | Typed lexical bindings. |
| `expressions` | Typed expressions. |

`SessionTypedEntity` exposes `kind`, optional `name`, rendered `type`, and
`span`. `SessionDefInfo` exposes `name`, `kind`, rendered `scheme`, `source`,
and `span`. Types and schemes are strings, not a public structured type tree.
The kind type is `SessionDefKind`, not the `DefKind` from the original plan.

## Commit and replace source

Choose the operation according to who owns the source text:

| Operation | Identity | Success value |
| --- | --- | --- |
| `Session.upsert` | One definition's name | `UpsertReport` |
| `Session.upsert-input` | `SourceInput.id`, with multiple definitions allowed | Array of `SessionDefInfo` |
| `Session.remove` | One definition's name | `RemoveReport` |
| `Session.remove-input` | Committed input ID | Unit |
| `Session.definitions` | Current user overlay | Array of `SessionDefInfo` |

The four mutation operations return `Result` with `Diagnostic` on failure.
`upsert` accepts one definition. Its report has `definition` and `invalidated`
fields. Runtime definitions, macros, types, interfaces, and implementations
can be committed.

For example, commit a function before checking a cell that calls it:

```clojure
(let [definition (SourceInput.init @"definition:twice"
                                    @"(defn twice [x] (Int.+ x x))")]
  (match (Session.upsert &session &definition)
    (Result.Error diagnostic) (show-diagnostic &diagnostic)
    (Result.Success _)
      (let [cell (SourceInput.init @"cell:2" @"(twice 21)")]
        (match (Session.infer-cell &session &cell)
          (Result.Error diagnostic) (show-diagnostic &diagnostic)
          (Result.Success _) (IO.println "Cell checks")))))
```

`upsert-input` replaces everything contributed by that input in its replay
position. Definitions omitted from the replacement disappear. Use it for
files and cells containing several definitions. Definitions owned by a
multi-definition input cannot be edited or removed by name.

A replacement rebuilds and checks the candidate overlay before publishing it.
Committed dependents bind to the latest definition of a name, including when
an overlay shadows the base. Failed replacement leaves previous definitions
and schemes intact. Macro, type, interface, and implementation edits
conservatively invalidate later definitions.

`remove` drops the named definition and its transitive dependents, including
whole inputs that own dependent definitions. `RemoveReport.name` identifies
the requested definition; `invalidated` lists the other definitions removed.
Removing an unknown definition returns a diagnostic.

`remove-input` removes that input and rebuilds the remaining overlay. It does
not perform `remove`'s dependency cascade: if remaining inputs no longer
check, the operation fails and preserves the previous overlay.

Transient checks and failed edits may advance internal identity allocators or
populate caches, but they do not partially publish semantic definitions.
A mutable session should have one owning execution context; it is not an API
for concurrent mutation by multiple threads.

## Editor queries

All operations below take `&session`. Source operations also take `&input`;
name and prefix queries take a string reference.

| Operation | Result |
| --- | --- |
| `infer-cell` | `Result CellReport Diagnostic`; check transient source. |
| `ownership` | `Result OwnershipReport Diagnostic`; plan a committed definition. |
| `expand` | `Result (Maybe String) Diagnostic`; fully expanded source text. |
| `expand-1` | Same result type; one outermost step per top-level form, or `Nothing` if none is a macro call. |
| `trace-expand` | Pair of an array of `CtStep` and an optional diagnostic, retaining the trace on failure. |
| `complete` | Array of `Candidate` values matching the prefix. |
| `doc` | Optional `DocInfo` for the requested name. |

Expansion queries discard their temporary compile-time environment changes.
Completion candidates contain name, kind, scheme, and optional documentation;
ranking and fuzzy matching belong to the host. `OwnershipReport` contains the
name, scheme, and spanned ownership actions.

## Generate or execute code

`Session.emit-cell &session &input` returns `Result String Diagnostic`: a
complete C translation unit, including an entry point. The cell's top-level
values are echoed as in the driver. It does not commit cell definitions or
execute the resulting code. The host writes the C and invokes a C compiler
with the runtime headers and any required native dependencies.

`Session.prepare-emit &session` optionally normalizes base inference traces
before the first emission. Emission otherwise initializes that cache lazily.
There is no implemented `Session.build-cell` or `BuildReport` API.

Alternative backends use `Session.lower-cell` or `Session.lower-cell-plain`,
which return `Result BackendModule Diagnostic`. The plain variant suppresses
top-level result echoing. Both share the transient compiler pipeline.

For persistent native execution, load
`carp-llvm-backend/carp-session-jit.carp` and use `SessionJit`. This is a
separate library requiring LLVM; `carp-session` itself does not depend on LLVM.
Native modules and global storage can survive later cells. Use the JIT's own
edit operations to keep semantic and native state synchronized. See the
[LLVM backend README](../carp-llvm-backend/README.md) for entry points,
invalidation, initialization, and linking requirements.

## Verify an integration

Run from the repository root with `CARP_DIR` set:

```sh
carp -x carp-session/test/carp-session.carp
carp -x carp-session/test/core.carp
carp -x --log-memory carp-session/test/memory.carp
```

The tests cover transactions, source provenance, queries, emission, and warm
Core integration. The memory test checks allocation balance across repeated
successful and failed operations. Measure latency for your own base and cells;
`carp-session/test/benchmark.carp` provides a real-Core benchmark rather than
a portable latency guarantee. See [development](development.md) for the full
assurance commands.
