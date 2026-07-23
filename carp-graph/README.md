# carp-graph

`carp-graph` is a small integer-graph library: `IntGraph` stores adjacency
lists by node index and provides depth-first visit order and Tarjan
strongly-connected components. The compiler uses it for order-independent
definition handling — mutually recursive groups come back as one component, in
a deterministic order.

```bash
carp -x test/carp-graph.carp
```
