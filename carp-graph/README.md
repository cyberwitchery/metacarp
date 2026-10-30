# carp-graph

`carp-graph` is a small integer-graph library: `IntGraph` stores adjacency
lists by node index and provides depth-first visit order and Tarjan
strongly-connected components. The compiler uses it for order-independent
definition handling — mutually recursive groups come back as one component, in
a deterministic order.

`positions.carp` provides `PositionBuckets`, stable groups of input positions
by integer key. Sparse and negative keys are supported. Specialization and
backend cleanup share this index without copying the indexed records.

```bash
carp -x test/carp-graph.carp
carp -x test/positions.carp
```
