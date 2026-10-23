# Carp views

The declarative view model shared by the terminal REPL and gt4carp. The runtime
has no terminal, HTTP, JSON, or notebook dependency. `defview` declares typed
`ViewSpec` descriptors through the `View.*` builders:

```carp
(deftype Point [x Int y Int])

(defview coordinates [p Point]
  (=> (View.text)
      (View.title @"Coordinates")
      (View.content (fmt "point(%d, %d)" @(Point.x p) @(Point.y p)))))
```

Views carry selectors, titles, priorities, source, and applicability. `View.empty`
marks an inapplicable view. The compiler's ordinary interface selection chooses
the `views` provider for a concrete type, including generic types.
`ViewColumn` describes a table column and `ViewRequest` carries rendering bounds.
`view-summary` formats bounded summaries, `view-type-name` supplies a display
type name, and `view-register` transfers an owned value to the object registry.

For reusable providers, callbacks can receive the borrowed source when called:

```carp
(defview samples [xs (Array Float)]
  (=> (View.columned)
      (View.title @"Samples")
      (View.value-items (fn [value] (Array.length value)))
      (View.with-columns
        [(View.value-column @"Value"
           (fn [value i request]
             (str @(Array.unsafe-nth value i))))])))
```

`View.value-content` receives the source and a `ViewRequest`. `View.value-format`
and `View.value-column` also receive the item index. Requests carry `selector`,
`offset`, `count`, `depth`, and `bytes`. Existing closed callbacks passed to
`View.items`, `View.column`, `View.item-format`, `View.send`, and `View.children` continue
to work. User callbacks execute native code and must bound their own work;
transport clipping cannot interrupt arbitrary computation or allocation.

The standard collection providers read requested items from their sources.
Registration moves an owned source into stable storage once. Built-in selection
providers borrow children and retain their parent until the child is released.
Descriptors do not own copied collections, and registration does not eagerly
format values. Unknown foreign values have an opaque summary; a view or an
`view-summary` implementation can provide a useful representation.

The terminal adds its native Raw view using compiler-recorded layouts. It
constructs and renders custom views during a synchronous borrow, then releases
the callbacks before returning. Compiled queries are cached per concrete type
and provider and retired before their JIT generation. gt4carp owns the remote
object leases, Phlow specifications, HTTP transport, paging, and notebook
capture. Both hosts embed this source when built, so rebuild them after changing
the view runtime.

Run `test/views.carp` with the self-hosting compiler. The tests cover bounded
item evaluation, UTF-8 windows, applicability, ownership, and parent leases.
