# carp-infer

`carp-infer` performs Hindley–Milner-style inference for the resolved core
subset. It handles calls, conditionals, lexical lets, lambdas, and explicit
annotations. Top-level definitions are predeclared, inferred as one recursive
group, unified, then generalized. It records global call signatures together
with the final substitution for specialization.

Registered builtins and interface signatures seed the inference environment as
polymorphic schemes. Declaration variables use a separate identity space, so
they instantiate safely alongside inference variables.

Reference declarations retain implicit, named, or static `CoreLifetime`
syntax. Named lifetimes such as `(Ref String a)` share one quantified
`MonoLifetime` identity wherever `a` occurs; implicit references receive
distinct stable identities. Lifetime constraints pass through generalization,
instantiation, unification, and the final solver snapshot.
Local let-bound and top-level value lifetimes are not generalized, so repeated
uses retain one borrow identity. String and pattern literals carry `static`.

Two entries build on earlier inference. `Infer.module-against` infers a
transient module against the schemes of a warm base, which the session uses
for each cell. `Infer.module-resumable` and `Infer.module-from-base` instead
continue one run: the first infers a module and keeps what the second needs,
and the second infers a larger module that only adds definitions by inferring
the additions alone, on the base's substitution and with fresh variables past
the base's, so the result carries one substitution for both halves. When an
addition takes over the id of a builtin that existing code or an overload
refers to, it infers the whole module instead. The driver uses this for the
module `close-generics` extends.

Ownership constraints and full Carp type syntax remain later gates.

```bash
carp -x test/carp-infer.carp
```
