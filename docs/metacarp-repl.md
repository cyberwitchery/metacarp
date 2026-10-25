# Metacarp terminal REPL

Status: the prototype implements all six milestones in part. Language editing
now uses the shared lossless reader, compiler-owned scope facts, and a bounded
worker. Type-namespace queries and native inspection now use compiler-owned
identities and layouts.

## Purpose and priorities

Build a terminal REPL on the existing session and LLVM JIT. Prioritize a
reliable interaction loop, editing, language support, introspection, editable
history, and rich inspection, in that order. The prototype drives one umbrella
RFC rather than a second compiler architecture.

The [user guide](../carp-repl/README.md) documents keys, commands, build
instructions, and current limits.

## Architecture

The combined executable is built from `main-metacarp.carp`. Bare `metacarp`
opens the REPL, `metacarp repl [options]` selects it explicitly, and file
arguments use the C compiler. `driver.carp` and `carp-repl/cli.carp` expose
callable entry points to the combined executable and the standalone drivers.
The C-only `main.carp` bootstrap does not load LLVM or the terminal editor.

The boundary is one language service shared by highlighting,
completion, documentation, and diagnostics. The terminal owns text editing
and presentation. It receives facts about source ranges and never recognizes
Carp tokens or binding forms.

The reader's editing document retains all source bytes, trivia, delimiters,
reader prefixes, incomplete forms, and invalid input. Strict parsing lowers
that same tree only when it has no issues. Reader recovery cannot turn
invented syntax into accepted compiler input.

Surface syntax carries two locations: diagnostic blame and written origin.
Macro expansion may blame an invocation while retaining the exact origin of
an argument substituted into the expansion. Syntax introduced by a macro
cannot impersonate a written occurrence in the caller. Resolver observations
record binding identities and lexical environments from the ordinary compiler
operations; the editor does not implement another binding walker.

Each analysis belongs to an exact document revision and session revision.
Cursor movement queries the existing analysis. A text change requests a new
analysis; replies for superseded revisions are discarded. Lexical facts remain
available when resolution or inference fails. Missing knowledge has an
explicit pending or unavailable state.

`paint.carp` holds provisional presentation separately from those analysis
facts. On an edit, it projects whole spans outside the changed byte range onto
the new source, respecting UTF-8 boundaries. A reader-only reply retains cached
semantic formatting only where an exact symbol range still exists. A final
semantic reply replaces it, including partial and unavailable results. The
cache contains ranges and presentation categories, with no binding identities,
types, or scopes. Completion, docs, and diagnostics cannot query it.

Automatic analysis runs on one serialized compiler worker. The editor sends
requests and polls structured replies through a narrow protocol. A wakeup pipe
integrates with terminal input; only the service's own pipe is nonblocking.
The worker has one pending request and bounded reply slots. A newer source
revision cancels work; stale source, session, cursor, and request IDs cannot
alter the current buffer. Cursor-only queries reuse the cached analysis.

```text
terminal.carp + terminal-language.carp + display.carp
    | protocol.carp: requests, ranges, pairs, diagnostics, editing replies
service.carp: serialized worker, cancellation barrier, wakeup pipe
    | language.carp: cached revision-specific compiler adapter
Reader.read-syntax -> Surface editing tree -> expansion
    -> runtime resolver / compile-time lowering observations -> inference
```

The terminal imports neither the reader nor Session or JIT APIs. The reader
owns token boundaries and delimiter structure. The compiler records actual
binding identities, environments, and selected syntax during its normal work.
Runtime names use CoreRef identities. Compile-time queries retain compact
immutable environment snapshots and use the evaluator's own lookup kernel,
including module parents, imports, ambiguity, and static-definition filtering.
They do not retain mutable evaluator values or preview code pointers.

The host also supplies a synchronous newline-edit callback. `indentation.carp`
uses the shared reader's recovered tree to return a replacement range and text
at the exact cursor. The terminal applies that edit through the same range
replacement path as completion; it contains no indentation rules.

The host pauses and drains the service before accessing its engine. Each
semantic preview restores compile-time metadata, build flags, load state,
prototype/code boundaries, and caches after success, error, or cancellation.
Environment epoch allocation stays monotonic so divergent temporary states
cannot reuse cache keys. Accepted source, result handles, and native code are
not changed by analysis.

The compiler checks a two-million-unit work budget at expansion, resolution,
inference, type solving, compile-time lowering, and every VM instruction.
Size-growing VM builtins also charge for produced data. A 500 ms monotonic
deadline uses those cooperative cancellation points. Automatic previews refuse
compile-time file reads; explicit F2 permits them under the same work limits.
These bounds do not interrupt blocking filesystem operations or arbitrary
native execution. Buffers over 256 KiB report analysis unavailable.

Reader facts are published first. Semantic results distinguish ready, partial,
and unavailable states; diagnostics appear after 450 ms of quiet. Incomplete
input stays quiet until explicitly queried. Missing bodies have explicit
invalid placeholders for observation and remain compiler errors. No recovered
syntax is executable input.

The host owns command dispatch. One command registry supplies help and command
completion. Source-taking commands analyze their original argument ranges in
the same source document; name-taking commands query namespace metadata.
Text and path arguments do not enter Carp multiline continuation.

`journal.carp` separates accepted source from chronological attempts.
`values.carp` transports actual typed values through native callback slots.
System libedit supplies editing and recall. All editor, service, and compiler
adapter code is Carp, using direct OS registrations without a hand-written C
shim or an added dependency.

## Milestone 1: persistent evaluation and recovery

Implemented:

- Warm Core loading, persistent definitions and native expression cells.
- Reader-backed continuation, located diagnostics, and prompt-free pipe mode.
- Atomic source updates; failed replacements preserve the accepted definition.
- Mixed submissions stage declarations and native publication before once-only
  execution. ABI boundary changes use a separate JIT while preparing their
  transaction; ordinary revisions restore their binding policy on failure.
- Ordinary function and value revisions retain unrelated globals and results.
- Invalidation follows resolved body changes and emitted LLVM/C dependencies,
  including concrete interface implementations and ABI helpers.
- Retained scalar, string, array, record, and closure results.
- Recovery after returned compiler and native-publication diagnostics.
- Borrow checks on top-level roots as well as function bodies, including moves,
  escaping local references, and borrowed closure captures.

Source acceptance and compilation of polymorphic instances remain separate.
Type, interface, foreign, and compile-time definition changes reset native state,
with a notice. Ordinary revisions keep old code for historical values. Editing
an input preserves its unchanged initializers; a new value declaration explicitly
initializes its binding again.
Runtime I/O and mutations begin after preparation and cannot be rolled back.
Native crashes, nontermination, and execution interrupts remain outside the
compiler-error recovery contract. The current terminal integration targets macOS.

## Milestone 2: terminal editing

Implemented:

- Immediate arrows, word/cursor movement, Home/End, deletion, kill/yank, undo,
  reverse search, draft restoration, and multiline recall.
- Persistent, bounded, unique history with an explicit path and opt-out.
- Bracketed paste, explicit newlines, forced submission, cancel, and empty EOF.
- UTF-8 decoding, display width, wrapped input, a caret-centered viewport,
  terminal resize, color opt-out, and terminal restoration.

PTY tests exercise actual input before Enter, paste, Unicode, search,
cancellation, EOF, resize, and signal cleanup. History loading never evaluates
source. Persistence stores submitted text, including failed compiler inputs.

Continuation prompts are part of the display projection. The primary prompt's
terminal width determines the continuation margin, including history-editing
prompts. Display characters and source styles are projected together, and the
source cursor maps through that projection. Logical newlines add `·> `; soft
wraps retain ordinary terminal wrapping. Prompt text never enters source,
history, or compiler byte ranges.

Frames contain independently styled cells and rows with their terminal widths.
The terminal caches the preceding rows and emits one batch containing changed
suffixes, cleared retired rows, and cursor movement. Prefix comparison includes
glyphs, widths, and styles; combining-mark edits repaint their base glyph. A row
is erased to its end only when it shrinks, after writing its replacement suffix.
New rows use line feeds to allow terminal scrolling. Ordinary editing does not
clear the frame; terminal resize invalidates its cached layout.

Newline indentation follows the deepest open reader group at the cursor.
Ordinary calls align with their first argument, collections and quoted lists
with their first element, and the established body-form layout nests two columns
from the opener. Immediate closing delimiters align with their opener. Nested
quasiquotes track unquote depth. This is a formatting convention, not semantic
classification of a binding by its spelling. Unfinished strings, raw strings,
patterns, and characters receive no inserted whitespace. Display and
indentation share terminal column measurement; source edits retain byte ranges.

## Milestone 3: language-aware editing

Implemented:

- Lossless tolerant reader facts for literals, comments, whitespace, reader
  macros, invalid input, and missing or mismatched delimiters. Strict parsing
  lowers this same tree.
- Semantic styles from actual expansion, binding resolution, and inference,
  including shadowed syntax names and caller arguments substituted by macros.
- Function-declaration roles take precedence over inferred binding types.
  An incomplete function body does not erase the function name's known role.
- Tab completion in actual runtime and compile-time scopes, including local
  parameters, sequential bindings, imports, qualified names, and result aliases.
- Exact symbol replacement ranges, including text to the right of the cursor.
- F1 uses the resolved occurrence identity, including at binding declarations.
  Quoted data suppresses value queries. Type annotations have an explicit
  context and cannot accidentally query a same-named value.
- Background diagnostics and explicit F2 semantic/ownership checks without
  source commitment or native execution.
- Revisioned asynchronous replies, bounded feedback, compiler cancellation,
  checkpoint restoration, and cached cursor queries.

Type completion uses a compiler-owned catalogue of primitive, structural, and
nominal type heads, plus parameters observed by the ordinary type resolver.
Pending declarations participate before submission. Type generation mapping
selects the source spelling visible at the cursor and excludes retired internal
identities. Type documentation uses the language's normal metadata; standalone
`doc` and `sig` inputs retain their expansion state without inventing a value
definition.

Observation-only expansion recovery retains verified parent forms and the
expanded prefix. Failed nodes become Invalid, and no later compile-time code is
evaluated. The normal resolver can therefore retain an outer function or let
scope after a nested macro fails. Strict compilation still rejects that source.
Failed resolution or inference can leave local types unknown even when a
binding identity is known. Those states are explicit.

## Milestone 4: introspection

Implemented `:type`, `:doc`, `:complete`, `:expand`, `:expand-1`, `:ownership`,
`:c`, `:c-render`, and `:llvm`. Ownership reports preserve action ranges.
`:llvm` selects artifacts of successful native publications. `:c` selects
retained generated C support for those same published identities. Fresh C
backend rendering requires `:c-render <source>` and labels its output as an
alternate compilation that the REPL did not execute.

Bare `:llvm` selects the last executed cell, and `:llvm name` selects concrete
published instances of a committed binding. `--deps` follows captured LLVM
operand edges; `--full` prints the complete original modules. Default views
omit unrelated Core and support entities. Unmaterialized definitions report
that no code has been compiled for them.

Backend declarations retain specialization-to-CoreRef associations. Session
lowering marks membership in the committed resolver snapshot, keeping
publication-local identities separate from resident identities. The LLVM
emitter associates each global initializer with its owning binding. Each
initializer has its own emitted function, called by the dispatcher in original
declaration order.

The JIT copies module text, entity text, and operand edges before transferring
the module to ORC. It commits that artifact only after publication and symbol
lookup succeed. Artifacts retain owned data and no LLVM handles. The host
attaches exact source snapshots and journal revisions after its semantic
transaction succeeds. Source revisions, publication serials, and native
generations remain distinct.

The C renderer returns the exact translation unit and template fragments from
one rendering. ABI wrappers, callbacks, invoke helpers, and allocation helpers
record their fragments and declared symbol edges as they are appended. The
JIT retains the unit only after publication and lookup succeed. Focused `:c` views
follow LLVM operands, initializer ownership, and those explicit C edges;
`:c --full [name]` includes complete units. No generated C is available for
LLVM-only or header-provided implementations, and inspection reports that
state. Raw C bodies and included headers remain opaque to dependency selection.

C support is compiled to LLVM IR by Clang from the same installation selected
by `LLVM.setup`, with the JIT's target triple. The C-derived module and the cell's
LLVM module enter ORC under one resource tracker before symbol lookup. This
allows C and LLVM definitions to resolve each other in the same transaction.
Publication commits artifacts, materialization caches, and instance caches only
after lookup succeeds. Any add or lookup failure removes both modules. C
compilation and verification happen before publication and cannot leak native
definitions from a rejected staged session.

The C renderer annotates included runtime definitions and driver initialization
separately from generated support. The JIT reads Clang's `llvm.global.annotations`
through LLVM APIs to identify these definitions. Runtime symbols already present
in the host become external declarations. Previously published support is also
imported; native template definitions remain owned by the session. Function
imports preserve their type, calling convention, and ABI attributes.

ABI boundary changes and reset retire C and LLVM code, materialization caches,
and their artifacts together. Ordinary revisions publish new binding symbols;
current inspection selects active specializations while historical values keep
their original publications. View queries are renewed when their emitted
dependencies change. Independent JIT sessions can publish the same native symbol
with different bodies and retire them independently. Source origins still come
from the active compiler declaration's provenance; shadowed definitions cannot
relabel emitted code. Inspection reads retained data without compiling,
executing, or reading scratch files. `:c-render` restores transient compiler
state on both success and failure.

Inspection does not enter expansion or lowering. Prepared cells, inspection
helpers, and failed submissions do not replace the last executed cell.
Native reset releases the retired generation's artifacts. Retained IR is the
emitter output before ORC optimization; it is not a dump of mutable globals.
Native templates expose their LLVM declarations, with implementation in the
existing C backend. Focused excerpts may refer to types or metadata available
in the full module.

Long command and result output uses a bounded terminal pager with scrolling,
literal search, and source anchors that survive reflow. It shares the editor's
frame patching and libedit's input lifecycle, including signal restoration.
Simple terminals and pipes retain plain output. Structured value navigation
uses the same frame patching and input lifecycle through `:browse`.

## Milestone 5: editable history and export

Implemented:

- Stable journal numbers and owning source identities.
- `:edit N` seeds the terminal without submission; failed edits preserve active
  source and remain in the transcript.
- Resolved-reference dependencies and transitive stale marking. Generation
  changes conservatively invalidate earlier status.
- Explicit `:replay N`; edits never replay past expression effects.
- Revision-bound removal previews and atomic removal of the affected input set.
  Compile-time dependencies use conservative invalidation.
- Active declaration export in session replay order and separate chronological
  transcript export, including earlier revisions and failures.

Inputs containing several declarations are replaced together. Active source
exports omit past expression roots. Transcript exports include them as source
and may deliberately include invalid attempts; they are an audit artifact,
not an automatically replayed program.

## Milestone 6: rich inspection

Implemented typed, owned handles. A native slot holds storage and a release
callback; inferred types are retained as structured MonoType values. Values and
callbacks are released before invalidating their JIT generation.

There are 32 retained slots. Additional owned results use temporary slots and
are released after display. Result numbers are monotonic; `_` is the latest.
Aliases copy scalars and borrow owners. Dropping N also drops newer results
conservatively so retained borrows cannot outlive earlier owners.

The LLVM backend exports owned layout descriptions from its actual lowering:
field offsets, generic substitutions, unit-field elision, optional sum tags,
array strides, and closure capture types. Each successful native publication
retains its layout environment. On-demand layout queries use that environment
and the generating target data in a private LLVM context. Failed publications
retain no schema, and reset retires schemas, callback addresses, and caches.
Foreign values without compiler-recorded layouts remain opaque.

`:inspect N [selectors]` follows checked array indices, product fields, active
sum payloads, and closure capture names. Positional sum selectors name logical
payload fields, including unit fields. Views borrow the original live result;
navigation neither reexecutes source nor moves a payload or capture. Closures
remain callable after inspection.

Both automatic display and explicit inspection use the bounded structural
renderer. They do not compile an eager `str` callback. Defaults are 32 children,
six compound levels, and 4,096 output bytes. `--offset`, `--count`, `--depth`, and
`--bytes` select a bounded view. Arrays and fields use child offsets; strings
use UTF-8 byte offsets, advancing to a character boundary. String traversal
copies only the requested bounded slice. Request caps are offset 1,048,576,
count 1,024, depth 32, and bytes 65,536. Byte clipping preserves UTF-8 boundaries;
a truncation marker may add a few bytes. Native strings require scanning up to
the requested offset because the runtime representation has no length field.

Custom views use the same `defview` mechanism as gt4carp:

```carp
(deftype Point [x Int y Int])

(defview show-point [point Point]
  (=> (View.text)
      (View.title @"Coordinates")
      (View.content (fmt "point(%d, %d)" @(Point.x point) @(Point.y point)))))
```

`:inspect N --views` lists applicable selectors. `:inspect N --view show-point`
selects one. `--raw` or `--view gtRawFor` uses the compiler's native structural
view. Custom views use their declared priorities; the terminal's Raw view has
priority 90. Text, listing, and columned views render as terminal text. Bitmap
views report their dimensions. Native field and index selectors still navigate
borrowed storage.

The [shared view runtime](../carp-views/README.md) supplies declarations, bounded
requests, item providers, and object ownership. Source-aware callbacks receive
`ViewRequest` bounds without copying the source collection. The REPL invokes
providers through ordinary interface dispatch and caches typed queries for the
current native generation. Custom callbacks remain native user code and must
bound their own work and allocations. This API belongs to the warm base and
survives reset.

`:browse N [selectors]` opens a structured viewer over a retained result.
Up/Down or j/k move through rows, Space/Page Down and b/Page Up change pages,
and Home/End jump within counted collections. Enter or Right opens the selected
item; Left, Backspace, or h returns to the parent with its prior selection and
page. Tab cycles declared views. `[` and `]` scroll wide tables horizontally.
q, Escape, Ctrl-C, and Ctrl-D close the viewer. Pipes and simple terminals
receive a bounded plain snapshot.

Text views scroll and request further UTF-8 byte windows at their boundaries.
Trees retain the displayed child leases until their window changes or the
handle closes. Bitmap views sample RGBA pixels to the viewport and byte budget;
color terminals display blocks, and `NO_COLOR` selects a monochrome rendering.
Partial alpha is composited over black. Native Raw views use recorded fields,
active sum payloads, sequence elements, and closure captures.

The viewer receives owned pages and opaque generation-checked handles through
`ReplViewClient`. Native pointers and callbacks stay inside the engine. Closing
a parent does not invalidate a selected child; dropping its source result or
retiring the runtime invalidates both. Provider windows are bounded before
rendering, and an idle viewer does not repaint or invoke providers.

A macro can emit declarations and runtime expressions in one top-level
sequence. The compiler prepares one expanded syntax tree, commits its declaration
projection, then executes its runtime roots once. Type, ownership, or native
publication errors leave the previous session intact. Rebuilding accepted
source restores declarations without executing its runtime roots. History and
export retain the original invocation.

```clojure
(defmacro define-and-call [name value]
  `(do (defn %name [] %value) (%name)))

(define-and-call answer 42)
; 42, retained as _1
(answer)
; 42
```

F2 checks the same prepared syntax without committing or executing it. Loading
an exported source sequence in the REPL explicitly executes its runtime parts.
Module-scoped output keeps its namespace, imports, private access, and source
coordinates. The terminal adapter materializes those runtime roots as transient
functions; they never enter the committed source or definition list.

Three alternating optimized PTY runs on the same Mac compared the structured
viewer checkpoint with prepared submissions. Median startup was 791 ms versus
790 ms, first integer evaluation 828 ms versus 824 ms, and warm evaluation
245 ms versus 242 ms. A first invocation that defined and called a function
through a mixed-output macro took 975 ms. These runs show no measurable change
to ordinary evaluation latency at this sample size.

## Platform boundary

The current terminal host has Darwin-specific clock and errno bindings,
an Apple linker stack-size option, and a Darwin-only check-script guard.
libedit and the compiler/session interfaces are not inherently macOS-specific.
The LLVM backend already has non-Darwin support-clang lookup and Linux process
symbol linking. Porting the terminal requires selecting the corresponding
clock, errno, and linker conventions and validating the host on that platform.

## Validation and performance

The dedicated check script builds an optimized executable and runs
reader and lexical tests, native display checks, and complete process and PTY
scenarios. Relevant
session, lowering, C backend, LLVM backend, and incremental JIT suites verify
the underlying changes. AddressSanitizer exercises owned results, callbacks,
inspection, failed publication, and terminal editing.

Performance measurements distinguish startup, first native execution, warm
expression latency, declaration additions/replacements, and editor response.
Use an optimized build, record the machine and sample count, and report
distributions. JIT code, the current process's source journal, and published native
support intentionally accumulates within a generation; result slots and
persisted recall have separate bounds.

Full compiler assurance, sanitizer coverage of generated LLVM instructions,
and cross-platform terminal behavior remain broader validation work. The
dedicated REPL checks do not establish those claims.

Before unified native publication, on 2026-10-19, the rebuilt compiler passed 486 assertions across all 37 phase
suites. The dedicated REPL run passed all 73 process and PTY scenarios,
plus input, syntax, display, wait, and service checks. An additional targeted
regression recorded support loaded by a discarded staged session. The unified
publication checks below replace that retention expectation with rollback. Earlier shared reader validation passed
its 92 existing and 16 recovery assertions; a differential check preserved
forms and every nested location across 198 source files. The LLVM backend
passed 55 assertions, the incremental session JIT passed 27, and the artifact
lifecycle suite passed 28. The latter also passed under AddressSanitizer,
including native publication rollback, generation retirement, exact C source
retention, inspection without scratch files, and support reuse after reset. The LLVM
memory fixture passed under both C and LLVM drivers. Artifact checks now run
in the canonical LLVM assurance group.
Changed Carp files pass balance checks, angler, and carp-fmt.

The earlier AddressSanitizer host run, before retained publication inspection,
passed 50 of 52 scenarios without memory-error
reports. Two F2 checks exceeded the fixed 500 ms preview deadline under
instrumentation and returned an unavailable result; both also timed out on an
idle rerun. Those scenarios pass in the release build. The sanitizer suite is
therefore not fully green, and the complete current process/PTY suite has not been
rerun with instrumentation. The new artifact lifecycle suite is green under
AddressSanitizer. This does not establish memory safety for generated
LLVM instructions.

### Local measurements, 2026-10-19

Apple M1 Max, 32 GiB RAM, arm64 macOS. Both hosts are optimized builds.
Five fresh PTY sessions per build, 25 warm expressions, and 150 key responses.
Runs were sequential after compilation and sanitizer testing finished. The
baseline is the preceding synchronous editor, already including retained
results and dependency-aware history.

| Operation | Baseline median / p95 | Current median / p95 |
| --- | --- | --- |
| First prompt | 419.6 / 626.9 ms | 437.0 / 441.9 ms |
| First native result | 385.5 / 389.4 ms | 414.6 / 446.6 ms |
| Subsequent expression | 100.9 / 371.2 ms | 133.3 / 397.3 ms |
| Add function | 152.1 / 152.8 ms | 185.5 / 186.4 ms |
| Replace function | 161.5 / 164.0 ms | 195.9 / 197.9 ms |
| Key response | 0.025 / 0.075 ms | 0.028 / 0.075 ms |

In this workload, the warm evaluation median rose from 101 to 133 ms.
Definition additions and replacements added about 34 ms. Key-response p95
stayed at 0.075 ms.

These are small local samples. With five startup/update samples, p95 is the
largest observation. Key response measures changed text received through a
PTY, excluding terminal-emulator paint latency. It does not measure time to
semantic feedback. The unbounded-macro PTY regression separately verifies
that typing responds within 250 ms while a preview is running.

Allow roughly 0.4–0.8 seconds for startup, 0.35–0.7 seconds for initial native
evaluation, and 0.1–0.5 seconds for small subsequent expressions on this
machine. Semantic previews have their separate 500 ms cooperative deadline.
Retained-result typing and native callback preparation remain significant
evaluation costs; this change does not optimize those paths.

Reproduce with `python3 carp-repl/test/benchmark.py <binary> <core-dir>`.


### Retained-publication inspection

The following compares the preceding REPL with retained artifact inspection,
on the same machine and with the same optimized workload. Runs were sequential
after test execution finished: five startup/update samples, 25 warm expressions,
and 150 key responses per build.

| Operation | Before median / p95 | Retained artifacts median / p95 |
| --- | --- | --- |
| First prompt | 421.5 / 429.7 ms | 434.7 / 451.1 ms |
| First native result | 404.6 / 432.4 ms | 421.0 / 485.5 ms |
| Subsequent expression | 129.5 / 398.5 ms | 134.1 / 507.0 ms |
| Add function | 180.5 / 182.2 ms | 182.0 / 191.5 ms |
| Replace function | 188.5 / 191.8 ms | 196.5 / 204.6 ms |
| Key response | 0.025 / 0.059 ms | 0.029 / 0.082 ms |

Warm evaluation median increased by about 4.6 ms; its p95 increased by about
108 ms in this small sample. Allow 0.1–0.7 seconds for the small subsequent
expressions in this workload. Artifact capture copies exact module/entity
text and records LLVM operand edges on the publication path. Code and its
artifact storage share the native generation's lifetime; storage grows with
the emitted modules retained by a session.

### Retained C support

This comparison uses the preceding LLVM-artifact build and the build with
the former process-wide C artifact registry. The machine and optimized PTY workload
are the same: five startup/update samples, 25 warm expressions, and 150 key
responses, taken after validation finished. The cold support workload starts
a fresh process, evaluates `[1 2]`, and exits. Its five samples per build were
alternated; that timing includes startup and clang.

| Operation | Before median / p95 | C artifacts median / p95 |
| --- | --- | --- |
| First prompt | 433.3 / 452.3 ms | 436.9 / 447.1 ms |
| First native result | 406.4 / 417.5 ms | 413.9 / 735.4 ms |
| Subsequent expression | 133.8 / 394.7 ms | 134.4 / 531.5 ms |
| Add function | 182.8 / 190.2 ms | 183.3 / 187.3 ms |
| Replace function | 194.7 / 202.4 ms | 196.1 / 201.0 ms |
| Key response | 0.027 / 0.061 ms | 0.029 / 0.077 ms |
| Cold support process | 872.1 / 908.5 ms | 895.8 / 948.2 ms |

The warm median changed by less than 1 ms; the cold support median increased
by about 24 ms. The first-native and warm-expression tails increased in this
small sample. Allow 0.1–0.8 seconds for these small evaluations and roughly
0.9–1.5 seconds for the cold support process on this machine, with additional
margin for larger specializations or compiler retries. These samples do not
establish a stable upper bound. C artifact storage grows with successfully
loaded support units and remains available until process exit, matching the
native libraries' lifetime at that stage. The unified ORC publication described
above replaces that registry and library lifetime.

### Unified native publication

C-derived support and LLVM code now share an ORC publication transaction and
generation lifetime. The stale-template regression failed against the preceding
executable, returning 11 after replacement with a body returning 22. It now
returns 11, then 22. Focused checks also cover reset, discarded staged sessions,
C-to-LLVM callbacks, C static state across cells and support additions, publication
rollback and retry, C compilation failure, and independent live JIT sessions.
The REPL run passed 76 existing process and PTY scenarios, followed by two added
callback and state regressions. The artifact lifecycle suite passed 35 assertions.

The optimized PTY measurements below use the same machine as the earlier runs,
with five startup/update samples, 25 warm expressions, and 150 key responses per
build. No compiler builds or test suites ran concurrently with the after samples.
The native-template measurement times the first `(benchmark-native)` call after
committing a nullary template that returns 42, in five fresh sessions per build;
it excludes startup and definition commitment.

| Operation | Before median / p95 | Unified publication median / p95 |
| --- | --- | --- |
| First prompt | 442.2 / 755.6 ms | 407.1 / 618.2 ms |
| First native result | 410.6 / 452.8 ms | 248.6 / 251.4 ms |
| Subsequent expression | 136.6 / 469.7 ms | 126.1 / 224.5 ms |
| Add function | 190.2 / 192.0 ms | 174.5 / 175.6 ms |
| Replace function | 200.8 / 202.9 ms | 185.2 / 192.3 ms |
| Key response | 0.029 / 0.084 ms | 0.026 / 0.045 ms |
| First native-template call | 381.2 / 438.5 ms | 244.9 / 248.4 ms |

These small local samples show a lower cold native-call cost after removing the
dynamic-library link and load. They do not establish stable tail bounds. Allow
roughly 0.4–0.9 seconds for startup, 0.25–0.6 seconds for a small first native call,
and 0.1–0.5 seconds for small subsequent expressions, with more time for larger
specializations and retries. C support, materialization caches, and retained
artifacts now grow within a generation and are retired together at reset.

### Continuation layout and row updates

The rebuilt REPL passed all 82 process and PTY scenarios. The dedicated checks
also passed 22 input, 10 syntax, 18 display, one wait, and four service assertions.
The display assertions and seven targeted terminal scenarios passed with an
AddressSanitizer host, covering continuation prompts, unchanged rows, scrolling,
resize, Unicode history, cancellation, and terminal restoration.

The approved compiler checks passed: generation 2 and generation 3 emitted
byte-identical compiler C and the bootstrap smoke ran successfully; all 37 phase
suites passed their 486 assertions. The LLVM backend passed 55 assertions, the
incremental JIT passed 27, and the artifact lifecycle suite passed 35 under
AddressSanitizer. The memory fixture passed under both C and LLVM drivers.
These sanitizer runs instrument the host; they do not instrument generated LLVM
instructions.

The optimized PTY benchmark ran sequentially after validation, with five fresh
sessions, 25 warm evaluations, and 150 key responses per build. Key-response
median stayed at 0.026 ms; p95 changed from 0.057 to 0.067 ms. Warm-expression
median / p95 changed from 130.3 / 234.5 ms to 132.1 / 237.2 ms. These small local
samples measure text received over a PTY, excluding terminal-emulator paint.
The ordinary editing path now overwrites changed rows in one batch and leaves
unchanged rows in place; it no longer clears the frame before repainting.

### Style continuity and newline indentation

The preceding row-update checks missed asynchronous style changes within a
row. A PTY trace of an unrelated whitespace edit showed the old executable
repainting semantic text as plain text, then reader styles, then semantic
styles again. The new regression models visible cells and attributes throughout
that update cycle. It fails against the preceding executable and passes with
the separate provisional paint cache. Local bindings also no longer force a
white foreground, which could hide them on a light background.

Cell updates retain unchanged styled prefixes, overwrite changed suffixes, and
erase only retired tails. Tests cover equal-width replacements, shortening,
combining marks, wide characters, and independent attributes. Reader-derived
newline edits replace the old fixed two-space insertion. Input assertions cover
calls, nested bodies and collections, quoted data, quasiquote depth, comments,
unfinished literals, and replacement in the middle of a buffer. PTY regressions
also check binding-vector alignment and the actual value of a multiline string.

The rebuilt executable passed all 88 process, PTY, and screen-model scenarios.
Dedicated suites passed 43 input, 10 syntax, 15 paint, 24 display, one wait, and
four service assertions. All 38 compiler phase suites passed their 522
assertions. Input, paint, and display assertions also passed under
AddressSanitizer, along with eleven targeted PTY scenarios covering the new
regressions, completion, scrolling, resize, Unicode, cancellation, EOF, and
terminal restoration. Sanitization instruments the host, not generated LLVM
instructions.

Sequential optimized PTY measurements, after the test runs completed, used
five fresh sessions, 25 warm expressions, and 150 key responses per build.
Key-response median / p95 changed from 0.063 / 0.079 ms to 0.041 / 0.059 ms.
Startup median stayed near 403 ms, first-native median near 243 ms, and warm
expression median near 124 ms. Both builds used the same screen-aware test
harness. These small samples measure PTY receipt, excluding terminal-emulator
paint and time to semantic feedback; they do not establish tail bounds.

### Declaration highlighting during incomplete edits

The language adapter now applies the resolver's explicit function-declaration
role before considering an inferred binding type. The function name retains
its style through `(defn x [] `, `(defn x [] (`, and `(defn x [] (let`, including
backspacing between these states. Same-named parameters keep their own role,
and quoted declaration names remain plain. The regression failed against the
preceding executable. All 91 process, PTY, and screen-model scenarios and the
97 supporting assertions passed after the change. The three new regressions
also passed with an AddressSanitizer host.

Sequential optimized PTY runs used five sessions, 25 warm expressions, and
150 key responses per build. Key-response median / p95 measured 0.056 / 0.231 ms
before and 0.039 / 0.085 ms after; warm-expression median / p95 measured
143.1 / 267.0 ms and 138.3 / 260.5 ms. These small local samples include system
load variation, exclude terminal-emulator paint, and do not establish upper
latency bounds or a causal performance improvement from the classification fix.

### Type tooling and native inspection, 2026-10-20

The release host passes all 104 process, PTY, and screen checks, plus the
input, syntax, paint, native display, wait, and service suites. The compiler
phase suites and generation-2/generation-3 fixed point pass. LLVM backend,
JIT, publication-artifact, and native-layout suites pass 55, 27, 35, and 10
assertions respectively; the C/LLVM memory fixture also passes. Ten focused
AddressSanitizer host scenarios cover sums, managed closure captures, paging,
padding and unit fields, custom dispatch, callback retirement, and partial
analysis. These checks instrument the host, not generated LLVM instructions.
The 165-case reference corpus, seven expansion-parity fixtures, and library
linkage checks pass.

The complete `self` assurance group remains red at its zero-leak gate:
compiling `map.carp` leaks 231,440 bytes. The compiler built before this change
reports exactly the same count with the same reader source. An isolated build
of `main` (`952b183`), compiled from its own checkout directory, reports
232,272 bytes on the same fixture.
The allocation traces point to reader string buffers. Expansion parity and
library linkage were run separately after the leak gate stopped the group.
This work does not fix that compiler leak.

Measurements below compare optimized hosts immediately before and after this
change on the same Apple M1 Max. Runs were sequential after builds and tests
finished. The general benchmark uses five fresh PTYs, 25 warm expressions,
and 150 key responses per build. The inspection benchmark uses five fresh
PTYs and ten repeated `:inspect 1 1 0` commands per session over one retained
nested array, excluding its evaluation.

| Operation | Before median / p95 | After median / p95 |
| --- | --- | --- |
| First prompt | 425.2 / 454.1 ms | 424.0 / 431.5 ms |
| First native result | 271.3 / 274.6 ms | 253.4 / 261.4 ms |
| Warm expression | 132.0 / 244.1 ms | 131.7 / 243.2 ms |
| Add function | 184.0 / 185.9 ms | 183.1 / 190.6 ms |
| Replace function | 192.4 / 198.2 ms | 194.6 / 197.5 ms |
| Key response | 0.040 / 0.074 ms | 0.041 / 0.068 ms |
| Nested inspection | 167.2 / 263.2 ms | 32.3 / 33.7 ms |

Nested inspection no longer compiles getters and a full string renderer for
each request. Its measured median is about five times lower. Small differences
in the other operations should be treated as local measurement variation.
The million-element regression checks both paging near the end and automatic
display of a borrowed result, limits combined output to under 1,000 characters,
and verifies that the original source executes only once.

Reproduce these measurements with `carp-repl/test/benchmark.py` and
`carp-repl/test/benchmark-inspection.py`, passing an optimized executable and
Core directory to each script.

### Shared declarative views, 2026-10-21

The terminal and gt4carp now use `carp-views` for `defview`, typed descriptors,
standard providers, and owned object registration. Notebook capture, source
overrides, HTTP, JSON, remote Phlow specifications, and client paging remain in
gt4carp. Its JSON dependency is 0.7.2. Both hosts embed the shared source when
built and must be rebuilt after changes to it.

The rebuilt terminal passes 108 process, PTY, and screen checks and its six
supporting native suites. The shared-view suite passes 16 assertions covering
bounded evaluation, UTF-8 clipping, applicability, source copies, and parent
leases. The backend suite passes 34 assertions, including a regression for
generic closures with identical function signatures and different captures.
The aggregate-copy fixture passes its memory-balance check under both drivers.
Closure copying and destruction use the actual callee's calling convention;
aggregate values do not by themselves imply a C ABI wrapper.
Notebook protocol checks pass for ranges, navigation, source metadata, and
leases. Three GT paging examples pass in a copied image. All three notebook
regression suites pass their anchors; they still report the two cases marked
as known defects for `meta-set!` documentation and DAP macro visibility.

After preserving executable permissions on the assurance runner's seed copy,
all 39 phase suites and the generation-2/generation-3 fixed point pass. LLVM
backend, JIT, artifact, and layout suites pass 55, 27, 35, and 10 assertions.
The shared-view suite also passes under AddressSanitizer, including reading a
borrowed child after its parent client releases its reference. Four focused
REPL sanitizer scenarios pass after rebuilding with the destructor fix.
These checks instrument the host and generated C,
not generated LLVM instructions.

The reference corpus passes all 165 cases. The complete `self` group still
fails its zero-leak gate at 231,440 bytes while compiling `map.carp`, matching
the preceding build. The checked `main` baseline (`952b183`) leaks 232,272
bytes on the same fixture. This change does not fix that leak.
All seven expansion-parity fixtures and the library-linkage checks pass when
run separately after the leak gate stops the group.

Sequential optimized PTY measurements compare the preceding terminal with the
shared-view build. Builds and tests had finished before measurement. Sample
counts match the preceding section.

| Operation | Before median / p95 | After median / p95 |
| --- | --- | --- |
| First prompt | 439.5 / 565.3 ms | 722.9 / 759.5 ms |
| First native result | 267.4 / 409.0 ms | 680.3 / 699.7 ms |
| Warm expression | 137.2 / 242.2 ms | 218.9 / 228.6 ms |
| Add function | 189.4 / 191.7 ms | 303.7 / 310.3 ms |
| Replace function | 202.4 / 204.3 ms | 330.2 / 338.4 ms |
| Key response | 0.040 / 0.091 ms | 0.042 / 0.087 ms |
| Nested inspection | 33.2 / 35.4 ms | 52.4 / 186.7 ms |

This is a latency regression for startup, compilation, and inspection. The
shared runtime enlarges the warm compiler base, and a concrete view query must
be compiled on first use. Queries are cached within their native generation;
provider selection still runs for each presentation. The inspection sample
includes the first query for the selected child type. These measurements do
not establish how much time each source of overhead contributes. Key-response
measurements exclude terminal-emulator painting and semantic analysis.

### Shared API naming

The shared builders now live in `View`, with `ViewSpec`, `ViewRequest`, and
`ViewColumn` data types. The interfaces are `views`, `view-summary`,
`view-type-name`, and `view-register`. Generated providers, compiler view
declarations, both hosts, and examples use these names. `defview` retains its
syntax. The `NB` module is confined to gt4carp's notebook adapter.

The renamed shared suite passes all 16 assertions, and the compiler's own view
declarations compile and render a type through `View`. The notebook protocol
test and all three regression suites pass their anchors. The complete REPL run
passes 107 of 108 checks. Its F2 editor check reports the 500 ms analysis
deadline; two isolated runs each of the preceding and renamed executables
report the same failure. Other work was running on the machine during these
checks. The analysis deadline remains 500 ms.

Timing samples were also collected during that concurrent activity. The prior
executable ran several times slower than in the preceding measurements.
Alternating samples measured startup medians of 2,444.7 / 2,733.4 ms and warm
expression medians of 723.0 / 792.7 ms before / after. Each build used three
fresh sessions and nine warm expressions. These samples do not provide a clean
comparison of the rename's performance cost.

### Combined command

The combined executable passes all eight command tests and all 108 process,
PTY, and screen checks through `metacarp repl`. This run includes the F2 check
that exceeded its deadline during the preceding loaded-machine run; the
500 ms deadline is unchanged. The C-only compiler rebuilds, generation 2 and
generation 3 emit byte-identical C, and the bootstrap smoke test passes.

Five-session samples of the preceding standalone host and the combined host
measured startup medians of 1,089.5 / 996.4 ms, first native evaluation of
1,067.3 / 833.6 ms, and warm evaluation of 308.0 / 270.5 ms. These sequential
samples were taken on the same busy machine and do not establish a speedup.
The command integration adds dispatch and reuses the existing drivers.


## Structured navigation measurements, 2026-10-24

`:browse` uses owned pages and generation-checked handles for text, tables,
trees, sampled RGBA images, and native Raw navigation. Closing a viewer
releases its leases. The terminal retains parent pages and selections, and
uses the existing frame diff. Compiler workers inherit blocked terminal signals.
The terminal loop processes pending signals synchronously during input and
paging, restoring terminal mode before termination or suspension. Libedit's
asynchronous handlers depend on its builtin reader and are disabled here.

Three optimized PTY runs on the same MacBookPro18,2, arm64 macOS 15.8.1,
with LLVM 23.1.4 gave these medians. Each run measured three warm integer
expressions. The baseline is the local pager checkpoint `4852837`.

| Measurement | Pager checkpoint | Structured viewer |
| --- | ---: | ---: |
| Process ready | 725 ms | 812 ms |
| First integer expression | 775 ms | 852 ms |
| Warm integer expression | 227 ms | 253 ms |

Opening the default Raw view of 100 integers took 450 ms; requesting its next
20-row page took 1.14 ms. These are local end-to-end observations on a busy
machine, with an 80-column, 24-row terminal, rather than throughput claims.
The additional warm runtime has a measurable startup and expression cost.

The engine view fixture passes 29 lifetime and navigation assertions and
reports zero leaks under macOS `leaks -atExit`. Compiler regressions cover
header ownership on cached template dependencies, references to specialized
globals, aggregate calling conventions and cached native adapters across incremental
publications, String
field derivation without imported deleter declarations, and null storage for
empty LLVM array literals.

## Native binding revision measurements, 2026-10-25

Ordinary revisions keep historical publications resident and version only the
affected bindings. Resolved body comparison preserves lexical binding identity
and names used by inspection. ABI comparison uses declaration deltas; inherited
builtins and dispatch declarations stay in the warm compiler context. LLVM
pointer-ABI bodies carry their original binding ownership for dependency
traversal. Native version namespaces cannot collide with generated source names.

Three alternating optimized PTY runs compared the mixed-submission checkpoint
`766b177` with binding revisions on the same busy Mac. These are medians of
local observations, with three warm integer evaluations per session.

| Measurement | Mixed submissions | Binding revisions |
| --- | ---: | ---: |
| Process ready | 785 ms | 749 ms |
| First integer expression | 814 ms | 768 ms |
| Warm integer expression | 240 ms | 229 ms |
| Add a function | 335 ms | 322 ms |
| Replace a function | 363 ms | 357 ms |
| Evaluate the replaced function | 759 ms | 482 ms |

Ordinary commits snapshot user definitions and their IR. Copying the full warm
session added about 60–70 ms to declaration commits in an earlier measurement.
Historical values, closure storage, native template state, view leases, and
current provider queries are covered by regression checks. Failed publication
restores the previous specialization and binding policy.
