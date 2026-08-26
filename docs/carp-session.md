# carp-session

Status: API version 2 implemented; this document retains the original design rationale

API version: 2

Primary client: incremental notebook environments such as Lepiter and GT

## Purpose

`carp-session` is a library API for running the compiler as a long-lived,
incremental service. It loads, expands, resolves, derives, and infers Carp's
core once. Notebook cells then operate against that warm base instead of
rechecking core after every edit.

The library owns compiler state and structured reports. It does not own a
transport, wire format, editor protocol, value host, or long-running server
binary. Those belong in a thin host linked against this library. The existing
CLI remains supported and is the fallback path.

## Goals

- Make repeated cell inference warm and suitable for interactive editing.
- Preserve the meaning of the normal compiler pipeline.
- Let callers identify every source buffer with a stable ID.
- Attach source-relative spans to all diagnostics and reported entities.
- Support transactional definition updates and dependency invalidation.
- Never corrupt or poison a session after an unsuccessful operation.
- Expose a versioned, transport-independent Carp API.

The initial performance target is a warm `infer-cell` latency below 100 ms for
representative notebook cells on the development machine. Benchmarks must
report cell size and machine details rather than treating this number as a
portable guarantee.

## Non-goals

- Defining an RPC protocol or JSON schema.
- Managing notebook values or evaluating compiled cell results.
- Choosing how a host identifies users, images, or notebooks.
- Making one `Session` concurrently mutable from multiple threads.
- Replacing the CLI.

## Original compiler boundary

Before `carp-session`, the compiler already had useful tooling entry points:

- `CarpCompiler.infer-module-with` returns `AnnotatedModule`.
- `CarpCompiler.plan-module-checked` returns `PlannedModule`.
- `InferredModule` records schemes, expression types, call sites, node types,
  and the final substitution.
- surface nodes carry `SurfaceSpan` values.

Those entry points alone were not an incremental API:

- every call expands, resolves, derives, and infers a complete module;
- `CoreExpr` stores an integer node ID but no source provenance;
- node IDs are only meaningful in the module that minted them;
- `InferredNodeType` needs an owner to disambiguate IDs;
- inference errors have only a message;
- `CompileError` has a phase and message but no span;
- the CLI's annotation and ownership payloads reconstruct names and omit
  source ranges.

The implemented `carp-session` reuses the compiler packages rather than
wrapping the CLI or concatenating source text.

## Public data model

Names below describe the stable semantic API. See the library README and source
for the exact exported Carp field spelling.

```clojure
(deftype SourceInput [id String source String])
(deftype SourceSpan [source-id String start Int end Int])

(deftype Diagnostic [phase String message String span (Maybe SourceSpan)])

(deftype DefKind
  (Function []) (Value []) (Type []) (Macro []) (Interface [])
  (Implementation []) (Template []) (External []) (Other [String]))

(deftype DefInfo
  [name String kind DefKind scheme String source SourceInput span SourceSpan])

(deftype TypedEntity
  [kind String name (Maybe String) type String span SourceSpan])

(deftype CellReport
  [forms (Array TypedEntity)
   definitions (Array DefInfo)
   locals (Array TypedEntity)
   expressions (Array TypedEntity)])

(deftype UpsertReport
  [definition DefInfo invalidated (Array String)])
```

Types and schemes are exposed as rendered strings in API version 2. This keeps
the boundary stable while the compiler's internal `MonoType`, `TypeScheme`,
and substitution representation evolves. A future API version may add a
structured type tree without removing the display form.

`SourceSpan` uses half-open byte offsets into the exact `SourceInput.source`
provided by the caller. A report never points into a concatenated replay file.
The host can convert byte offsets to line and column positions.

The caller supplies stable source IDs. A source ID may identify a notebook
cell, a saved definition, or another editor buffer. Reusing an ID means “new
contents of the same logical source”; it does not imply that node identities
inside the new contents are retained.

## Public API

Mutation is explicit through `(Ref Session)`. The session itself is opaque to
clients; its internal compiler representations are not API.

```clojure
(Session.api-version) -> Int

(Session.create core-dir) -> (Result Session Diagnostic)
(Session.fork (Ref Session)) -> Session
(Session.reset (Ref Session)) -> ()

(Session.upsert (Ref Session) SourceInput)
  -> (Result UpsertReport Diagnostic)
(Session.remove (Ref Session) String)
  -> (Result (Array String) Diagnostic)
(Session.definitions (Ref Session)) -> (Array DefInfo)

(Session.infer-cell (Ref Session) SourceInput)
  -> (Result CellReport Diagnostic)
(Session.ownership (Ref Session) String)
  -> (Result OwnershipReport Diagnostic)
(Session.expand (Ref Session) SourceInput)
  -> (Result (Maybe String) Diagnostic)
(Session.expand-1 (Ref Session) SourceInput)
  -> (Result (Maybe String) Diagnostic)
(Session.complete (Ref Session) String)
  -> (Array Candidate)
(Session.doc (Ref Session) String) -> (Maybe DocInfo)

(Session.prepare-emit (Ref Session)) -> ()
(Session.emit-cell (Ref Session) SourceInput)
  -> (Result String Diagnostic)
(Session.emit-library (Ref Session) SourceInput (Ref (Array String)))
  -> (Result String Diagnostic)
(Session.build-cell (Ref Session) SourceInput String)
  -> (Result BuildReport Diagnostic)
```

`upsert` accepts exactly one top-level definition form in API version 2. A
multi-form source is rejected with a parse diagnostic. `infer-cell`, `expand`,
and `emit-cell` may accept multiple forms and never commit them.

`remove` returns the transitive set of definitions invalidated by the removal.
Removing an unknown name is an error rather than a silent no-op.

## Session state

A session has an immutable base and a mutable user overlay.

```text
Session
├── base
│   ├── loaded core sources
│   ├── expanded compile-time environment and macros
│   ├── resolved and derived core module
│   └── inferred global environment
├── user overlay
│   ├── source ID and source text per definition
│   ├── expanded/resolved definition fragments
│   ├── schemes and documentation
│   └── forward and reverse dependency indexes
├── provenance
│   ├── node ID -> SourceSpan
│   └── definition/binding ID -> SourceSpan
└── monotonic allocators
    ├── global and local binding IDs
    └── expression node IDs
```

`Session.create` performs the one expensive core load. `Session.reset` drops
the complete user overlay and its caches while retaining the immutable base.

Core and user state should be stored separately even if an early implementation
occasionally materializes a combined view. This makes reset cheap and prevents
user edits from mutating the warm base accidentally.

## Source provenance and identities

Spans are carried through the pipeline in provenance tables keyed by compiler
identities. This avoids adding a span field to every `CoreExpr`, specialized
expression, and backend variant.

- The parser converts reader positions to byte offsets for one `SourceInput`.
- Expansion preserves source spans for unchanged syntax.
- Macro-generated syntax is anchored to the invocation span. Retaining an
  optional expansion-origin chain is desirable but not required for API 1.
- Resolution records the span of every core expression, binding, and
  definition in the provenance table.
- Inference errors retain the node ID that caused the error; the session turns
  that identity into a `Diagnostic.span`.
- Inferred expression and local reports join their IDs with provenance.
- Ownership actions already refer to expression sites; those sites join with
  the same provenance table.
- Backend errors use the most specific originating node available.

Node and binding IDs are minted by session-owned monotonic allocators. They do
not restart for each definition. Replacing a definition may retain its global
binding identity when its name and kind are compatible, but all new syntax
nodes receive fresh IDs. IDs are internal and are not promised stable across
session restarts; `SourceInput.id` and spans are the external identity.

Generated compiler declarations also receive unique IDs, but have no user
span. Diagnostics originating solely in generated code report no span and
should include the originating user definition in their message when known.

## Transaction and error contract

Every operation begins from a valid snapshot. Read-only operations discard all
temporary compiler state. Mutating operations construct a candidate overlay
and swap it into the session only after the operation and all affected
dependents succeed.

An error therefore has these guarantees:

- the session remains usable;
- committed definitions and their inferred schemes are unchanged;
- identity allocators may advance, but no externally observable definition is
  partially installed;
- temporary macro, resolver, inference, ownership, and codegen state is
  released;
- the error identifies a phase and includes a source span whenever the phase
  operated on caller-provided source.

Panics, process exits, and printing diagnostics are forbidden in the library
boundary. The CLI may continue rendering library diagnostics and choosing its
own exit codes.

## Incremental definitions and invalidation

Each committed definition records its direct dependencies by resolved global
identity. The overlay maintains both forward and reverse indexes.

On `upsert`:

1. Parse and expand the new definition against a snapshot of the current
   compile-time environment.
2. Resolve its name and direct dependencies with session allocators.
3. Find transitive reverse dependents of the previous definition.
4. Re-resolve and re-infer the replacement plus invalidated dependents in
   dependency order.
5. Rebuild derived declarations and dispatch tables affected by type,
   interface, implementation, or macro changes.
6. Commit the candidate overlay atomically and return the invalidated names.

Changing a macro invalidates definitions whose stored expanded syntax depended
on it. Changing a type, interface, or implementation is conservatively allowed
to invalidate all definitions that mention that declaration or dispatch
through the interface. Correct conservative invalidation comes before minimal
invalidation.

On `remove`, the named definition and its transitive reverse dependents leave
the committed overlay together. The report returns the affected names so the
host can mark notebook cells stale.

## `infer-cell`

`infer-cell` is the first end-to-end milestone. It parses and checks a
`SourceInput` against the warm base plus the current user overlay without
committing any definitions or compile-time effects.

The report contains:

- the inferred type and span of each top-level form;
- the name, kind, scheme, and span of definitions in the cell;
- every lexical binding's name, inferred type, owner definition, and span;
- expression types with the final substitution applied;
- cell-relative structured diagnostics on failure.

The library must not expose inference variables that the final substitution
can resolve. Multiple expressions with the same display name remain distinct
because reports are span-based rather than reconstructed by name.

The first implementation may infer the complete user overlay plus candidate
cell as long as it never re-expands, re-resolves, or re-infers the immutable
core. Later work can make inference itself definition-incremental.

## Queries

- `ownership` specializes and plans the requested committed definition and
  reports moves, borrows, and deletes with source spans.
- `expand` performs full macro expansion against the session's compile-time
  environment.
- `expand-1` performs one macro-expansion step and is the basis of a notebook
  macro stepper.
- `complete` searches visible globals, interfaces, members, macros, types, and
  current lexical context when supplied by a future API. Candidates include a
  display name, kind, scheme, and documentation.
- `doc` returns structured documentation for one resolved name.

Completion ranking and fuzzy matching remain host concerns in API version 2;
the library returns deterministic candidates matching the supplied prefix.

## Code generation and build caching

`emit-cell` compiles a transient cell program against the committed session and
returns a C translation unit. It must not mutate the session — beyond the
memoized base analysis described below, which no caller can observe.

Emitting needs every inference trace in the session normalized with the
substitution that produced it. The base half of that work is proportional to
the size of the loaded program and is invariant, since the base is fixed when
the session is created: it is done once and kept, and each emission normalizes
only the overlay. On a compiler-sized project this is the difference between
thirty seconds and two hundred milliseconds per cell. `prepare-emit` does the
base half up front for callers that would rather pay it while loading.

`build-cell` is a later milestone. It splits reusable core output from
cell-specific output, compiles core object code once per compatible cache key,
then compiles and links only user code for subsequent cells.

The cache key must include at least:

- `Session.api-version` and compiler build identity;
- core source identity/content;
- target platform and architecture;
- compiler flags that affect ABI or generated code;
- memory-logging and optimization modes.

The caller supplies the output path. Cache storage policy and eviction should
be configurable rather than embedded in the notebook protocol.

## Delivery plan

### Milestone 1: provenance and warm inference

- Introduce `SourceInput`, `SourceSpan`, `Diagnostic`, and provenance tables.
- Thread session-owned binding and node allocators through resolution.
- Attach spans to inference errors and typed reports.
- Load and infer core once in `Session.create`.
- Implement transactional, non-committing `Session.infer-cell`.
- Add warm/cold benchmarks and prove core is not rechecked per cell.

### Milestone 2: committed definitions

- Implement `upsert`, `remove`, `definitions`, and `reset`.
- Add dependency and reverse-dependency indexes.
- Make macro and interface invalidation correct, initially conservatively.
- Add rollback tests for every failing phase.

### Milestone 3: editor queries

- Implement ownership reports with spans.
- Add full and single-step expansion.
- Add completion and documentation queries.

### Milestone 4: code generation

- [x] Implement `emit-cell`.
- Define a separable core/user codegen boundary.
- Implement cached core objects and `build-cell`.

### Milestone 5: notebook blockers and hardening

- Reproduce and fix the listed closure, array-lowering, dispatch, derived-copy,
  and compile-time evaluation deviations.
- Run failed operations repeatedly under memory instrumentation.
- Version and document the supported public API.

## Acceptance criteria for the first vertical slice

- Creating a session against a valid core succeeds and exposes API version 2.
- Two sequential `infer-cell` calls do not parse, expand, resolve, derive, or
  infer core a second time.
- A caller-provided source ID appears unchanged in every returned span.
- Top-level forms, definitions, locals, and expression types have half-open
  byte spans into the submitted source.
- Returned types have the final inference substitution applied.
- Parse, expansion, resolution, validation, and inference failures return
  structured diagnostics and leave the session usable.
- Node IDs do not collide between core, committed definitions, or transient
  cells during a session.
- Existing CLI behavior and compiler tests remain unchanged.
- A benchmark records cold creation and at least 100 repeated warm inferences.

## Related current issues

- Interface specificity overlaps existing issue #8.
- Diagnostic quality and spans overlap existing issue #13, but session
  provenance is broader than diagnostic wording.
- Overall compiler performance remains tracked by issue #14; notebook latency
  needs separate warm-session measurements.
