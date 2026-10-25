# Metacarp REPL

A Carp terminal REPL over the existing compiler session and LLVM JIT. The
[umbrella RFC](../docs/metacarp-repl.md) records the six milestones, contracts,
and remaining hardening work.

Requires macOS, clang, the existing LLVM bindings, a linkable libLLVM, and Carp
Core. Build the compiler from current source before building the REPL:

```sh
./out/carp-compiler -c "$CARP_DIR/core" --optimize -b \
  -o out/carp-compiler-next main.carp
./out/carp-compiler-next -c "$CARP_DIR/core" --optimize -b \
  -o out/metacarp main-metacarp.carp
./out/metacarp
```

With no arguments, `metacarp` opens the REPL using `$CARP_DIR/core`. Use
`metacarp repl --core <dir> --no-history` for explicit options. File arguments
still compile, for example `metacarp -x program.carp`. The C-only bootstrap
entry point remains `main.carp`; `main-repl.carp` builds a standalone
`metacarp-repl` from the same driver.

The pinned `carp-reader@0.5.0` dependency includes `Reader.read-syntax`.
For reader development, `--package-override <reference>=<source.carp>` overrides
one exact reference; `CARP_PACKAGE_OVERRIDES` supplies newline-separated
defaults. Missing sources fail instead of falling back to a cached release.

`--core <dir>` overrides `$CARP_DIR/core`. `--help` lists all commands.
Piped input has no prompts or editor escape sequences.

```clojure
(defn twice [x] (Int.* 2 x))
(twice 21)
; 42, retained as _1

(Int.+ _1 1)
; 43

(String.append "hello" "!")
; "hello!", retained as _3

(String.length _3)
; 6
```

## Editing

The editor is Carp calling system libedit and terminal primitives through
`register`. There is no hand-written C editor or C shim.

| Key | Action |
| --- | --- |
| Enter | Submit complete input; continue incomplete input |
| Ctrl-J | Insert an indented newline |
| Alt-Enter | Force submission, including malformed input |
| Up / Down | Recall history and restore the current draft |
| Left / Right, Home / End, Ctrl-A / E | Move the cursor |
| Alt-B / F, Ctrl-W / K / Y | Word movement, kill, and yank |
| Ctrl-R | Search history |
| Ctrl-_ | Undo buffer changes |
| Tab | Complete the whole symbol around the cursor |
| F1 | Show documentation for that symbol |
| F2 | Check the buffer without committing or executing |
| Ctrl-C | Cancel input or an edit |
| Ctrl-D | Exit at an empty prompt; delete at the cursor otherwise |

Multiline input is one buffer and one history item. Bracketed paste inserts
editable text; embedded newlines never submit it. Lexical colors and matching
delimiters come from the shared reader, including incomplete input. Binding
styles, local completion, and F1 types come from actual compiler resolution
and inference. Function declaration names retain their role when an unfinished
body has no inferred type. Macro bodies use their compile-time environment.
Quoted data does not offer value completions. Type-namespace queries currently report
unavailable. Feedback uses at most three lines and
expires when the buffer or cursor changes. `NO_COLOR` disables colors;
`TERM=dumb` uses libedit's native presentation.

Logical continuation lines show `·> ` with the same prompt margin as the first
line, including the wider history-editing prompt. Prompts are display decoration;
source, cursor queries, recalled history, and export retain the original text.
The renderer updates changed rows in one output batch. Unchanged rows stay in
place, including unchanged styled prefixes within an edited row. Shorter rows
erase only their old tail. Terminal resize invalidates the cached layout.

Enter and Ctrl-J derive indentation from the shared reader's recovered tree.
Calls align with their first argument, body forms nest two columns from their
opener, and collections align with their first element. Closing delimiters align
with their opener. Unfinished strings and patterns receive a literal newline
without inserted spaces. Bracketed paste preserves the supplied indentation.

While a new analysis is pending, untouched source spans retain provisional
formatting. Reader replies recheck token boundaries, and current semantic
results replace that formatting even when analysis is partial or unavailable.
This presentation cache supplies no completion, documentation, or diagnostic
facts. Local bindings use italics with the terminal's default foreground.

History keeps up to 1,000 unique entries, including compiler failures. Its
location is `--history <file>`, `$METACARP_HISTORY`, or
`$XDG_STATE_HOME/metacarp/history`, falling back to
`$HOME/.local/state/metacarp/history`. `--no-history` or an empty
`METACARP_HISTORY` disables persistence. Loading history never evaluates it.

## Output

Long command and result output opens a pager in an interactive terminal.
Space, Page Down, or Ctrl-F advance a page; `b`, Page Up, or Ctrl-B go back.
Arrows or `j`/`k` move one row. Home/End or `g`/`G` select the first/last page.
`/` starts a literal Unicode search; Enter accepts it, and `n`/`N` repeat it
forward/backward. Resizing reflows the same source position. `q`, Escape,
Ctrl-C, or Ctrl-D close the pager and return to the REPL.

Pipes and simple terminals receive the original output without paging.

## Session and results

Definitions persist. Compiler errors leave accepted source available. Mixed
declarations and expressions are prepared before native execution: successful
submissions commit declarations and execute runtime roots once. Native
preparation failure preserves the previous semantic and runtime state.

Function and value revisions preserve unrelated native globals and result
handles. The compiler compares resolved bodies and ABI declarations, then follows
the emitted LLVM and C dependency graphs to invalidate affected specializations.
Changed bindings receive fresh symbols. Historical values and view handles keep
their original code; future inspection queries use current provider versions.
Published versions stay resident until reset.

Editing an input preserves its unchanged value initializers. Submitting a new
value declaration explicitly initializes that binding again. Type, interface,
foreign, and compile-time definition changes retain a conservative reset boundary.
Reset releases retained values before retiring their code. The REPL reports
native resets. Declarations can still fail when first specialized; acceptance
does not compile every possible polymorphic instance.

The final non-Unit value is retained in one of 32 live slots, with a monotonic
`_N` alias; `_` names the newest. Scalars are copied into expression scope.
Owned values are borrowed; use `@_N` to copy when ownership is required.
String literals are copied into owned results. Other borrowed results use
a temporary bounded view without retention; their original expression is
ownership-checked before capture. At capacity, new owned results use a temporary slot, are displayed once, and
are immediately released. Existing handles stay live.

`:results` lists handles. `:inspect N` displays a type and bounded value.
Selectors follow checked array indices, record fields, active sum payloads,
and closure captures: `:inspect N 1 field 0`. A sum payload can be selected by
its logical field index; a closure capture by its original name. Inspection
borrows stored values and never reevaluates their source. Closures remain
callable, for example `(@_1 42)`. `:drop N` releases N and newer handles.

Automatic display and inspection both apply limits before traversing values:
32 children, six compound levels, and 4,096 output bytes by default. Use
`:inspect N --offset 100 --count 20 --depth 3 --bytes 2048` to page a view.
Offsets select children for collections and UTF-8 bytes for strings; a string
offset advances to a character boundary. String views scan only through the
offset and bounded slice. Maximum options are offset 1,048,576, count 1,024,
depth 32, and bytes 65,536. A truncation marker can extend the byte limit.

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

## Queries and editable source

`:type`, `:doc`, `:complete`, `:expand`, `:expand-1`, and `:ownership`
query the warm compiler session. Ownership reports include action kinds and
source byte ranges.

`:llvm` inspects retained native publications:

| Command | View |
| --- | --- |
| `:llvm` | The last evaluated cell's emitted roots |
| `:llvm name` | Published instances of a committed runtime definition |
| `:llvm --deps [name]` | Referenced LLVM values and associated initializers |
| `:llvm --full [name]` | Complete modules containing the selected artifacts |

Each view identifies its publication, JIT generation, and source revision.
Globals show their storage and initializer; functions show the concrete
instances actually published. An unmaterialized definition reports “not
compiled yet.” Auxiliary inspection helpers and failed inputs do not replace
the last evaluated cell. Retiring native code also retires its artifacts.

IR is copied from emission before ORC optimization. Default views are focused
excerpts; complete modules include types, metadata, Core, and other support.
Native templates appear as LLVM declarations because their implementation is
compiled by the existing C backend. Inspection reads stored artifacts and
preserves native values; initializer code describes source initialization.

`:c` inspects retained C support artifacts using the same published binding
identities and last evaluated cell:

| Command | View |
| --- | --- |
| `:c` | Generated C support reachable from the last evaluated cell |
| `:c name` | Generated C support reachable from a published binding |
| `:c --full [name]` | Exact translation units containing that support |
| `:c-render <source>` | Explicit alternate compilation through the C backend |

Cells run through LLVM. Generated C support consists of native templates,
ABI adapters, allocation helpers, and indirect-call helpers. A selection with
no generated C support reports that state; it does not manufacture C for the
cell. Header-provided implementations have no retained generated body.
Dependency selection follows emitted LLVM operands and declared template and
adapter edges. It is a static dependency view, not an execution trace. Raw C
template bodies and included headers are not parsed to infer further edges.
Focused fragments are excerpts; use `--full` for their includes and declarations.

C fragments and complete units are captured during rendering. Clang from the
linked LLVM installation compiles support to IR; that module and the cell's
LLVM module are published under one ORC resource tracker. The JIT commits
artifacts and materialization caches only after publication and lookup succeed.
A failed publication removes both modules. Inspection neither recompiles nor
reads scratch files.

C support belongs to its JIT session and native generation. ABI boundary changes
and reset retire C code, LLVM code, caches, and artifacts together. A discarded
staged session cannot leave native definitions in another session. The next
successful call compiles the active template definition. Included runtime
implementations use explicit compiler annotations to import existing host or
session definitions, preserving shared runtime state.


`:c-render` labels its output as an alternate C-backend rendering that the
REPL did not execute. It restores transient compiler settings on success and
failure, preserves published artifacts and live values, and does not commit
the supplied source.

`:history` is the current process's source journal, distinct from persisted
editor recall. It includes failed inputs and dependency status. `:edit N`
seeds an editable buffer and replaces the owning input only after successful
submission. Inputs containing several declarations are edited together.
`:replay N` explicitly reevaluates source. No edit or removal automatically
replays expression effects.

Resolved references determine transitive dependencies. Native generation
changes conservatively mark earlier entries stale. `:remove N` previews the
affected inputs; `:remove! N` applies that preview only at the same journal
revision. Failed edits cannot become active removal targets.

`:export <file>` writes active declarations in session replay order.
`:export-transcript <file>` writes submitted source revisions, including failed
attempts, with status comments. Exported active source excludes past runtime
effects and displayed results.

## Boundaries and validation

The terminal knows buffer text, cursor positions, and structured query replies.
It has no compiler or JIT state. `protocol.carp` defines the narrow interface;
`service.carp` runs one serialized compiler worker; `language.carp` adapts
the shared reader and compiler observations. `display.carp` renders supplied
ranges and pairs. It does not recognize language syntax. `engine.carp` adapts
Session and SessionJit; `values.carp` owns typed result channels;
`journal.carp` tracks source history.

Reader facts arrive before semantic analysis. Cursor queries reuse the current
analysis. Every reply carries document, source, and session revisions; editing
replies also carry a request ID and cursor. Superseded replies are discarded.
The host pauses and drains the worker before accessing its engine.
The worker inherits blocked terminal signals when it is created. While editing
or paging, the terminal loop consumes those signals synchronously. It updates
the layout on resize and restores terminal mode before delegating termination
or suspension to the original signal disposition. Libedit's asynchronous signal
handlers are disabled because their rearming depends on its builtin reader.
The caller's signal mask is restored when input finishes.

Semantic previews have a two-million-unit work budget and a 500 ms deadline.
They restore compile-time state and never commit source or publish native code.
The VM checks the budget at every instruction. Automatic previews refuse
compile-time file reads; F2 explicitly permits them within the same bounds.
Buffers over 256 KiB report analysis unavailable. Incomplete and failed
analysis retain reader facts and available scope facts; unknown types stay
unknown. Quiet diagnostics appear after 450 ms.

Compiler recovery cannot undo runtime I/O, native crashes, or nontermination.
Ctrl-C cancels editing; interrupting arbitrary native execution is a separate
problem. Type completion and docs use a separate compiler-owned type namespace,
including pending declarations, parameters, and declaration generations. Automatic analysis has cooperative compiler
limits; these do not isolate native execution or make blocking filesystem
operations interruptible.

Run the input, reader-to-editor, display, service, process, and real PTY tests:

```sh
scripts/check-repl.sh
```

Input and reader-to-editor tests also run in the compiler phase suite.
Native display, browser, and service checks run with the macOS REPL check.
The shared view runtime and engine handle checks also run in LLVM assurance.
Session, JIT, C backend, and LLVM backend tests cover the underlying contracts.
