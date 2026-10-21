# What the checker rejects in Core

The compile-time checker (`carp-ct-typecheck`) run over every definition in
Core, macros included, at upstream master c6309d90: 248 of 276 check. This
classifies the 28 that do not.

12 of the 28 fail only because they use one that fails. The 16 direct
failures were each read at their site. A failure counted as a real bug only
if a program showing it was run on the reference compiler.

| Class | Definitions | Count |
|---|---|---|
| real bugs | `Dynamic.Map.shrink`, `thread-first-internal`, `thread-last-internal` | 3 |
| narrowing through a user-defined predicate | `Dynamic.sort`, `Dynamic.List.find-index`, `Introspect.arguments` | 3 |
| `eval`'s result used as data | `unreachable`, `Dynamic.unreduce-internal`, `Derive.make-update-deriver`, `derive` | 4 |
| an invariant on an argument's shape | `Dynamic.cxr`, `cond->`, `cond-->` | 3 |
| a result that depends on an argument's value | `Project.append-flag` | 1 |
| `expand` does not keep the macro's result type | `ignore-do` | 1 |
| an invariant on the compiler's state | `current-file` | 1 |

## Real bugs

**`Dynamic.Map.shrink`** (`Map.carp:711`) compares against `dflt-len`,
unqualified. A `defndynamic` resolves names from the root, not its module,
so it must be `Map.dflt-len`, as its siblings write `Map.min-load`. It is
reachable: on a map of 4 entries in 16 buckets (25% load), reference fails
`Dynamic.Map.remove` with "Can't find symbol 'dflt-len'". `Dynamic.Map.remove`
fails as a cascade.

Two more bugs sit behind it, which the checker does not report: `remove`
shrinks when the load is *above* `min-load`, and when `shrink` hands a
16-bucket map back unchanged, `remove` calls itself on it again; with the
name qualified, that `remove` does not terminate (killed after 60 s). And
`put` grows when the load passes `min-load` (20%), where `max-load` (80%)
looks intended.

**`thread-first-internal`, `thread-last-internal`**: `(-> 1)` and `(->)`
fail on reference with "Applying 'last' to non-list or empty list". The
helpers recurse on `all-but-last` down to an empty list and take its `last`;
`->`, `-->`, `=>` and `==>` pass their arguments on unchecked. `(-> x)`
should answer `x`. The checker reports `last` of a possibly empty list,
which is the failure reference shows; the four macros fail as cascades.

## Limits of the checker

**User-defined predicates.** `nil?` is `(= value nil)`, a Core function,
and `Introspect.external?` and its siblings test an s-expression's head. A
test through them narrows nothing: BAS gives a function one arrow, and a
type test needs one arrow per outcome. `Dynamic.sort`, `List.find-index`
(via `nil?`) and `Introspect.arguments` (via `external?`) fail on that.

**`eval`.** `unreachable` splices `(eval (list 'file msg))` into its
expansion; `eval-form` makes it checkable. `unreduce-internal` conses
`(eval (f x))` into its accumulator. `make-update-deriver` uses
`(eval (list 'members t))` to call `members` on a computed name and reduces
over the answer; `eval-form` would not help, since a symbol is a form but
not a sequence. `derive` calls the closures `make-deriver` stores, and the
derivers registered at load use the same `eval`/`members` pattern, so
their closures are opaque (read, not run through the checker in
isolation).

**Shape.** `Dynamic.cxr` reads its first argument as count/letter pairs and
takes `cddr` after reading one pair; that the list has even length is a
precondition no local type states. `cond->` and `cond-->` take
`(last (all-but-last binds))` of a non-empty `binds`, which is safe because
`cond-thread-binds` answers two items per clause. With that expression
replaced by `(car binds)` in a copy of Core, `cond->` checks, including its
`(collect-into full-binds 'array)`, which calls the symbol `array`
(`bas-calculus.md` §4).

**Value-dependent results.** `Project.append-flag` conses onto
`(Project.get-config flag-set)`, where `flag-set` is a parameter, so the
answer is the union over every key (a string, a bool, a list or an array).
Its callers pass flag keys, which hold lists.

**`expand`.** `ignore-do` conses onto `(expand (apply ignore* forms))`.
`expand` answers any form; that it is the expansion of `ignore*`, a list,
is not tracked.

**Compiler state.** `current-file` takes `car` of the load stack, which is
empty only when nothing is being loaded.

## Messages

Every failure has a location in its own definition, and names both ends:
`Dynamic.cxr` reads "found the empty list where a non-empty list or array
is needed (the value comes from 22:15)", at the `(cddr x)` the recursive
call's `(cons (- (car x) 1) (cdr x))` reaches.
