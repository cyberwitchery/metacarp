# carp-ct-sub

> **Experimental.** Nothing loads this yet. It is the algebra a later
> `carp-ct-infer` would stand on, built and validated on its own first.

`carp-ct-sub` is a set-theoretic type algebra for the compile-time language:
tags and products, closed under union, intersection and negation, with
subtyping decided as emptiness of `t ⊓ ¬s`.

[`carp-ct-types`](../carp-ct-types/README.md) is the tag-only fragment of the
same idea — the shape homomorphism `H` alone. Tags answer what a value *is*.
They cannot answer what is inside it, so every constraint on the contents of a
value is inexpressible there: an argument whose elements must be symbols
(`Symbol.concat`), a position two levels into a list (`caadr`), or the syntax a
macro emits. A container is structure, and structure is products: a sequence is
either empty or a pair of a first element and a rest of the same kind.

## The model

Values fall in three kinds, and the algebra keeps them apart because a value is
one of them and never two:

| kind | values |
| --- | --- |
| atomic | `Int` `Byte` `Long` `Float` `Double` `Bool` `Char` `String` `Pattern` `Symbol` `Comment`, and the three callables |
| empty | the empty container, one leaf per container kind |
| product | a non-empty container: a first element and a rest of the same kind |

The five container kinds (list, array, static array, dictionary, collection)
stay siblings, as they are in the tag lattice: a conversion between two of them
is not a subtyping relation.

A type is a union of clauses in disjunctive normal form. One clause carries the
tag leaves it allows as a bitmask — tag literals only ever shrink it, so a
single mask holds every positive and negative tag literal at once — plus the
product atoms it requires and the ones it forbids. Types are interned in an
arena and named by index, so a type is an `Int` here exactly as a shape is an
`Int` in the tag lattice, and the walker that consumes them needs no new
plumbing.

Emptiness of a product clause is the subset rule of semantic subtyping: a
conjunction of required products minus a union of forbidden ones is inhabited
exactly when the forbidden atoms can be split so that one side leaves a first
element and the other a rest. It is exponential in the number of forbidden
atoms in a single clause, which is where the cost of the decision procedure
lives. `negative-limit` caps the enumeration and answers *inhabited* past the
cap, so a pass built on it keeps reporting only what it can prove.

## Checking the rule against a model

```bash
carp -x test/carp-ct-sub.carp
```

The subset rule is easy to write down slightly wrong, and a checker built on a
slightly wrong rule is worse than no checker, so the algebra is not trusted
here. A finite universe of values is enumerated, every generated type is
interpreted by direct membership against it, and the algebra has to agree:
`uninhabited?` against "no value is a member", `subtype?` against inclusion.

The comparison is made *inside* a world rather than against it. A finite
universe cannot witness every inhabited type — `⊤ ⊓ ¬Int` is inhabited by a
String and no String is enumerated — so each type is met with a `world` type
that mirrors the enumeration exactly, and both sides then range over the same
values. Writing that down was not a formality: the first run reported two
disagreements, and both were the truncated universe rather than the rule.

15 assertions: the lattice laws with products in, the element constraints the
tag fragment cannot state, the sequence decomposition, and the two model
agreements.

## Running the existing pass on it

`carp-ct-shape.carp` is a stand-in for the `CtShape` of
[`carp-ct-types`](../carp-ct-types/README.md): same names, same meanings, a type
still an `Int`. `carp-ct-infer` loads it, and swapping that one line moves the
whole pass back onto the bitmask:

```clojure
;; carp-ct-infer.carp
(load "../carp-ct-sub/carp-ct-shape.carp")     ;; set-theoretic (default)
(load "../carp-ct-types/carp-ct-types.carp")   ;; bitmask
```

Identity is the one thing the facade cannot provide: two structurally equal types
are different arena ids until they are interned, so sameness is `CtShape.equal?`
and not `Int.=`. Both backends have that function, and both have the four
questions a tag lattice cannot answer — what a function takes and returns, and
what a container holds. The lattice answers "nothing known" to all of them, which
is what keeps one pass source running on either and makes the difference between
them measurable rather than arguable.

Measured on the pinned reference Core, 289 compile-time definitions, analysis
only (built once, binary timed, no compilation in the number):

| | bitmask | set-theoretic |
| --- | --- | --- |
| constrained positions | 1002 | 1002 |
| of those, shape known | 434 | **466** |
| definitions where a contradiction was possible | 161 | **170** |
| definitions rejected | 0 | 0 |
| fixpoint rounds | 2 | 3 |
| analysis time | 0.82s | **2.97s** |

The cost went 6.5× → 2.8× → 3.6× along the way, and the middle of those numbers is
the interesting one: interning alone made it *worse* (5.37s → 7.49s), because the
work was never in deciding emptiness, it was in building canonical keys for
throwaway intermediate types. What paid was the algebra of ⊥ and ⊤ — a pass meets
something with ⊤ constantly, and the general path was canonicalising a key and
walking a clause product to hand back the operand it was given. The last rise is
the price of the structure the pass now carries.

## Status

Done: tags, products, arrows, singleton types, recursive types, chains with a
tail, the Boolean operations, emptiness, subtyping, interning, memoised
emptiness, widening, a readable renderer, and a facade that carries the existing
pass. All three gaps the case corpus of `carp-ct-infer` opened with are closed.

Not done, in the order it matters:

- **No polymorphism.** No type variables and no tallying, so a dynamic function
  is summarised monomorphically and a generic helper is summarised at the join of
  its uses. This is the largest remaining piece of the paper.
- **Sequences are prefixes and stars, not regular expressions.** A fixed prefix
  followed by any number of elements covers what a quasiquote with a splice
  produces, which is what the pass needed. Alternation inside a sequence, or a
  star in the middle of one, is not sayable.
- **Projections are partial.** Reading a component back out works for the types
  the pass writes down and declines otherwise, which is the `J` family of the
  paper stated as a `Maybe` rather than implemented.
- **Widening is a depth cut.** Sound, and blunt: a summary that legitimately
  describes a four-deep structure is cut to three.
- **Singletons are symbols only.** Nothing stops the same atom describing one
  string or one integer; no caller needs it yet.
