# Compile-time Carp: our reading of its semantics

This describes what metacarp's compile-time evaluator does: the language of
`defndynamic`, `defmacro`, `defdynamic` and the code they run. It is a
reading of `carp-ct-eval/` and `carp-expand/`, not of reference Carp; where
the two differ, §10 says so. The type check in `docs/bas-calculus.md` is
argued against this document.

The language is `CtIR` (`carp-ct-eval/carp-ct-ir.carp`): every compile-time
form is lowered to it before it runs, so it is the only description of what
a form means. `carp-ct-compile.carp` turns `CtIR` into bytecode and
`CtEval.run-code` runs it; the bytecode is an implementation of the rules
below, not a second definition.

## 1. Values

    v ::= form s                 a reader syntax node
        | closure ⟨p, ρ, f⟩      prototype p, defining frame ρ, file f
        | macro ⟨p, ρ, f⟩        the same, called on forms
        | builtin b              a builtin, by name
        | list⟨v₁ … vₙ⟩ | array⟨v₁ … vₙ⟩
                                 a list or an array holding a value that
                                 is not a form

Forms are what the reader makes: symbols, numbers of five kinds, strings,
characters, bools, patterns, comments, lists, arrays, static arrays and
dictionaries. Syntax cannot hold a closure, a builtin or a macro, so a list
or an array that holds one is a value of its own, `list⟨…⟩` or `array⟨…⟩`
(`CtValue.Collection`, with its kind). The evaluator makes one exactly when
it would make a list or array form and an element is not a form, so it is
always one or the other: a sequence of forms is a form. Reference Carp has
no such split; there a list is a list whatever it holds, which is what the
kind keeps.

**Reading a value as a form**, `⌊v⌋` (`syntax-from-value`): `⌊form s⌋ = s`;
any other value is the error "compile-time expression must evaluate to
syntax". Most builtins read their arguments this way. The sequence
builtins (`car`, `cdr`, `cons`, `length`, `empty?`, …) read a `list⟨…⟩` or
`array⟨…⟩` like the form it would be; `list?`, `array?` and `dynamic-type`
answer by its kind.

**Reading a value as a bool**: `if` takes a value that is the bool form
itself (`strict-bool-at`); `when`, `while`, `cond`, `and` and `or` take any
value whose `⌊v⌋` is a bool form (`bool-argument`). Only a bool form reads
as a bool form, so the two accept the same values, with different messages.

**Equality** of forms (`syntax-equal?`, used by `=` and `case`): numbers
compare numerically across kinds, a string of one character equals that
character, symbols compare by their segments, lists and arrays element by
element, bools by value; anything else is unequal.

## 2. Environments

A session's store holds **frames** and **cells** (`carp-ct-env`). A frame has
an optional parent, a list of imported frames, and bindings from names to
cells; a cell holds one value and can be overwritten. Looking up `x` from
frame `ρ` (`CtEnv.lookup-status`):

1. the latest binding of `x` in `ρ`;
2. otherwise `x` in each frame `ρ` imports: found if exactly one cell
   answers, ambiguous if two different cells do;
3. otherwise the same from `ρ`'s parent; missing when there is none.

The inline caches in lowered code answer what this lookup would answer;
they are keyed by the frame a body was defined in and by a binding epoch
that changes whenever a binding or import could change an answer.

## 3. Lowering

`CtLower.lower` turns a form into `CtIR` in a scope of local names:

- a symbol becomes `Sym`: a local if an enclosing `fn` or `let` binds it,
  otherwise free; in argument position a free symbol becomes `ArgSym`, which
  stays as its own form when it names nothing;
- an array literal becomes `Coll`, a dictionary literal the call
  `(Map.from-array [(Pair.init k v) …])`, other atoms and `()` themselves;
- `quote`, `do`, `if` (exactly three parts), `when`, `and`, `or`, `cond`,
  `while`, `set!`, `fn`, `let`, `let-do` and `case` become their own nodes;
  `for` becomes a `let` with a `while` and a `set!` that steps it;
- `apply`, `eval`, `expand`, `members`, `type`, `meta`, `managed?`,
  `s-expr`, `use`, `concat`, `with-test-internal` and `Dynamic.compose`
  become `Special` nodes that say which arguments are evaluated and which
  stay forms;
- any other list is a call: `CallSym` when its head is a symbol (with the
  builtin it names, if any, and the arguments both lowered and as raw
  forms), `CallExpr` otherwise;
- a malformed special form becomes `Fail`, which raises its message when it
  runs, not when it is read.

## 4. Evaluation

`ρ ⊢ e ⇓ v` means `e` evaluated in frame `ρ` answers `v`; `ρ ⊢ e ⇓ err`
that it raises an error. The store is threaded through implicitly: cells
written by one step are seen by the next. Every rule propagates an error
from a premise, and evaluates premises left to right unless it says
otherwise.

- **Lit, Quote**: the form itself.
- **Sym x**: the value of the cell `x` resolves to; if `x` resolves to
  nothing but names a builtin, `builtin x`; an ambiguous or missing name is
  an error.
- **ArgSym x**: as Sym, except that a name that resolves to nothing and is
  not a builtin answers the symbol form `x`.
- **Coll e₁ … eₙ**: the array form `[v₁ … vₙ]` when every `vᵢ` is a form,
  as in reference Carp; `array⟨v₁ … vₙ⟩` otherwise.
- **If c t e**: `c` must be a bool form; the chosen branch.
- **When c t**: `t` if `c` is true, otherwise the empty list form.
- **And e₁ … eₙ**: each `eᵢ` but the last is read as a bool; the first that
  is false is the answer, otherwise the value of `eₙ`; `(and)` is `true`.
  **Or** is dual; `(or)` is `false`.
- **Seq e₁ … eₙ**: the value of `eₙ`; `(do)` is the form `(do)` itself.
- **Let**: a fresh child frame of `ρ`; each binding is evaluated in it and
  bound in it in order, so later ones see earlier ones; then the body.
  **LetDo**: the same with a sequence as body; an empty body is the empty
  list form.
- **Cond c₁ b₁ … [d]**: the branch of the first true `cᵢ`; else `d`; with no
  `d`, the `cond` form itself.
- **Case e p₁ b₁ … [d]**: `e` once, then each pattern in turn until one is
  equal to it (§1); its branch, else `d`, else the error "compile-time case
  has no matching branch".
- **While c b**: `b` while `c` is true; the answer is the empty list form.
- **SetName x e**: the cell `x` resolves to is overwritten with the value of
  `e`, which is the answer; if `x` resolves to nothing it is an error.
  `set!` never creates a binding.
- **Fn p**: `closure ⟨p, ρ, f⟩` with `f` the file being loaded. The frame is
  captured, not copied: a later `set!` of a captured local is seen by the
  closure and by everyone else holding that frame.
- **Fail m**: the error `m`.

## 5. Calls

**A call by name** `(x a₁ … aₙ)` (`CallSym`), in this order:

1. if `x` resolves to a cell holding a macro, the macro is expanded from the
   raw argument forms (§6) and the expansion is evaluated in `ρ`; the
   arguments are not evaluated;
2. otherwise the arguments are evaluated, and if `x` names a builtin, the
   builtin is applied, even if `x` is also bound;
3. otherwise the value `x` resolves to is applied (below); a name that
   resolves to nothing is the error "unknown compile-time function".

**A computed call** `(e a₁ … aₙ)` (`CallExpr`) evaluates the arguments, then
`e`, and applies its value.

**Applying a value** to argument values (`apply-function-value`):

- a closure `⟨p, ρ', f⟩`: the number of arguments must be the number of
  fixed parameters, or at least that with a rest parameter; a fresh child of
  `ρ'` binds the parameters to the arguments and the rest parameter to the
  remaining ones (a list form when they are all forms, `list⟨…⟩`
  otherwise); the body runs there;
- a builtin: its implementation, which may raise errors of its own;
- a macro: the arguments are read as forms, the macro is expanded from them,
  and the expansion is the answer, as data;
- a form: it is evaluated once, and its value applied; if that value is
  again a form, it is the error "compile-time application expects a
  function";
- a `list⟨…⟩` or `array⟨…⟩`: the error "compile-time application expects a
  function".

## 6. Macros

Expanding the macro `⟨p, ρ', f⟩` from argument forms `s₁ … sₙ`
(`expand-ct-macro-args`): the arity is checked as for a closure; a fresh
child of `ρ'` binds each fixed parameter to its form and the rest parameter
to the list form of the remaining ones; the body runs there; its value `v`
is read as a form, and `⌊v⌋` is the expansion.

A macro defined with `defmacro` is both an entry in the expander's macro
table and a `macro` value bound in the frame it was defined in, so dynamic
code can call it, pass it, and `apply` it.

## 7. Special forms

- **(apply f xs)**: `xs` is evaluated and read as a sequence of values; `f`
  stays a form (`special-apply`):
  - a symbol that is qualified, or names a builtin: the call form
    `(f ⌊x₁⌋ … ⌊xₙ⌋)`, unevaluated;
  - a symbol bound to a form `s`: the call form `(s ⌊x₁⌋ … ⌊xₙ⌋)`;
  - a symbol bound to anything else: that value applied to `x₁ … xₙ`
    (§5), so a macro gives its expansion as data;
  - a symbol bound to nothing: the call form, as for a builtin;
  - any other form: evaluated, and its value applied.
- **(eval e)**: the value `v` of `e`; when `v` is a symbol form that names
  nothing and is not a builtin, `v` itself; when `v` is another form, `v`
  evaluated in `ρ`; any other value, `v` itself. Core's `eval-form` is
  `eval` followed by a check that the result is a form (a `macro-error`
  otherwise), for macros that expand to what they evaluate.
- **(expand e)**: `⌊v⌋` of `e`'s value, with `(ignore* a …)` rewritten to
  `((ignore a) …)`.
- **(use M)** imports module `M`'s frame into `ρ`; **members**, **managed?**,
  **type**, **meta** and **s-expr** read what the expander recorded about
  types and bindings; **concat** joins two sequences into an array.

## 8. Loading a file

`MacroExpand.expand-body` walks a file's top-level forms in order, in the
frame of the module being defined (`carp-expand.carp`):

- **defmacro** lowers the body once and registers the macro (§6).
- **defndynamic** makes a closure whose captured frame is the **root**
  frame, not the module's: unqualified names in its body resolve globally,
  as in reference Carp, so a dynamic function cannot see its module's
  siblings without qualifying them. It is bound in the module frame and, as
  `M.name`, in the root frame.
- **defdynamic** evaluates its value now, in the module frame, and binds it
  the same way. The cell is mutable through `set!`.
- **defmodule**, **deftype**, **use** and the load markers maintain module
  frames, recorded types and the load stack.
- a top-level **eval**, **set!**, **Project.config** or **macro-log** is
  evaluated for its effect; so is a call of a pure string command with literal arguments, and
  a call of a name bound to a closure. A call of a name bound to anything
  else is an error.
- **build** and **run**, the REPL's commands, record that the driver should
  build, and run, what it compiles once compilation is done; **quit** does
  nothing, since a batch compile ends anyway. A macro that defines `main`
  and then builds and runs expands to `(do (defn main …) (build) (run))`,
  which works the same on both compilers.
- a top-level **if** whose condition evaluates to a bool picks its branch
  now; otherwise it stays as code.
- everything else is static code: macro calls in it are expanded until none
  is left, a call qualified with `Dynamic.` is evaluated and its value read
  as a form and spliced in, and the result goes on to resolution.

## 9. Errors

An evaluation either answers a value, raises an error, or does not
terminate. `docs/bas-calculus.md` §1 splits errors into **type errors** (a
builtin given a value it does not accept, `car` or `cdr` of something that
is not a cons, a call of something that is not a function or with the wrong
number of arguments, a condition that is not a bool, a value that is not a
form where a form is read, an unbound name) and **intended errors**
(`macro-error`, errors raised by code `eval` runs, a macro that fails to
expand).

## 10. Where metacarp differs from reference Carp

Found while writing this, by running both on the same input:

| input | reference | metacarp |
|---|---|---|
| `(apply f '(1 2))`, `f` a `defndynamic` | the call form `(f 1 2)` | `f` called: `3` |
| `(apply + '(1 2))` | `(Dynamic.+ 1 2)` | `(+ 1 2)` |
| `(dynamic-type car)` | `list` | `fn` |
| `(s-expr f)`, `f` a `defndynamic` | a list form, `(dynamic f [a] …)` | not a form: `str` of it fails |
| `(dynamic-type (car (s-expr f)))` | `dynamic` | fails, as above |

Each row was run through both compilers on the same file (the reference at
the master revision this repository follows).

Fixed in this work: an array literal evaluated to a collection even when
every element was a form (reference: an array); a list holding a non-form
answered `array` to `dynamic-type` and `false` to `list?` (reference: `list`,
`true`); `dynamic-type` answered
`array` for static arrays and dictionaries (reference: `static-array`,
`map`) and aborted the process on a macro (reference: `macro`); `macro-log`
printed nothing, and a top-level one was not evaluated; `write-file`,
`build`, `run` and `quit` did not exist; `cdr` past the end of a sequence
and `all-but-last` of an empty one answered `()` (reference: an error, and
for `all-but-last` an abort of the compiler).
