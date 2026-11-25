"""Operator catalogue: typed graph-analysis operators bound to igraph.

Each operator has a signature (param -> type), an output type, preconditions,
a cost class and optional approximate tiers. The catalogue is the only thing the
planner is allowed to compose. Types: Graph, NodeSet, NodeMap, Partition, Path,
Scalar, Table, Bool.
"""
from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import igraph as ig
import numpy as np

from .graphs import LoadedGraph


@dataclass
class OpSpec:
    name: str
    doc: str
    params: dict[str, str]                 # param -> type description
    returns: str
    cost: str                              # "O(n+m)", "O(nm)", "O(n^2)", "O(k(n+m))", "O(1)"
    tiers: list[str] = field(default_factory=lambda: ["exact"])
    preconditions: list[str] = field(default_factory=list)
    directed_only: bool = False
    fn: Optional[Callable] = None
    scope_sensitive: bool = False          # the value at a node depends on which nodes and edges are in the graph


CATALOGUE: dict[str, OpSpec] = {}


def op(name: str, doc: str, params: dict[str, str], returns: str, cost: str, tiers=None, preconditions=None, directed_only=False):
    def deco(fn):
        CATALOGUE[name] = OpSpec(name=name, doc=doc, params=params, returns=returns, cost=cost,
                                 tiers=tiers or ["exact"], preconditions=preconditions or [],
                                 directed_only=directed_only, fn=fn)
        return fn
    return deco


# --------------------------------------------------------------------------- helpers
class Ctx:
    """Execution context: the loaded graph plus a registry of intermediate values."""
    def __init__(self, lg: LoadedGraph, seed: int = 1):
        self.lg = lg
        self.seed = seed
        self.values: dict[str, Any] = {"G": lg.g}
        self.log: list[dict[str, Any]] = []

    def node(self, ref: Any) -> int:
        """Resolve a node reference (label, int id, or 'node:<idx>') to a vertex index."""
        if isinstance(ref, int) and not self.lg.semantics.labelled:
            r = self.lg.resolve(str(ref))
            if r["matched"] is None:
                raise ValueError(f"node {ref} not found")
            return r["matched"]
        r = self.lg.resolve(ref)
        if r["matched"] is None:
            raise ValueError(f"node '{ref}' not found; candidates: {r['candidates']}")
        return r["matched"]

    def label(self, idx: int) -> str:
        return self.lg.labels[idx]


def _pos(ctx: Ctx, g: ig.Graph) -> dict:
    """label -> vertex index in graph g, built once per graph per plan."""
    cache = ctx.__dict__.setdefault("_pos_cache", {})
    if id(g) not in cache:
        cache[id(g)] = (g, {name: i for i, name in enumerate(g.vs["name"])})   # keep g alive so id() stays unique
    return cache[id(g)][1]


def _vid(ctx: Ctx, g: ig.Graph, ref: Any) -> int:
    """Vertex index of a node reference *in graph g* (which may be a subgraph with its own indexing)."""
    if g is ctx.lg.g:
        return ctx.node(ref)
    idx = _pos(ctx, g).get(ctx.label(ctx.node(ref)))
    if idx is None:
        raise ValueError(f"node '{ref}' is not in this subgraph")
    return idx


def _lab(g: ig.Graph, idx: int) -> str:
    return g.vs[idx]["name"]


def _nodeset(ctx: Ctx, x: Any) -> list[str]:
    """Coerce a NodeSet reference, a Table with a node column, or a literal list to a list of labels."""
    v = ctx.values[x] if isinstance(x, str) and x in ctx.values else x
    if isinstance(v, dict) and "membership" in v:
        raise ValueError("a Partition is not a NodeSet; use largest_block or block_of")
    if isinstance(v, list):
        return [str(e["node"]) if isinstance(e, dict) and "node" in e else str(e) for e in v]
    if isinstance(v, dict):
        return [str(k) for k in v.keys()]
    raise ValueError(f"not a NodeSet: {x}")


def _graph(ctx: Ctx, g: Any) -> ig.Graph:
    if isinstance(g, ig.Graph):
        return g
    if isinstance(g, str) and g in ctx.values:
        return ctx.values[g]
    raise ValueError(f"not a graph: {g}")


def _nodemap(ctx: Ctx, values: list[float], g: ig.Graph) -> dict[str, float]:
    names = g.vs["name"]
    return {names[i]: float(v) for i, v in enumerate(values)}


# --------------------------------------------------------------------------- basic
@op("node_count", "Number of nodes.", {"graph": "Graph"}, "Scalar", "O(1)")
def node_count(ctx, graph="G"):
    return _graph(ctx, graph).vcount()


@op("edge_count", "Number of edges (undirected edges counted once; directed arcs counted once).", {"graph": "Graph"}, "Scalar", "O(1)")
def edge_count(ctx, graph="G"):
    return _graph(ctx, graph).ecount()


@op("distinct_edge_count", "Number of distinct node pairs connected (collapses parallel edges in a multigraph).", {"graph": "Graph"}, "Scalar", "O(m)")
def distinct_edge_count(ctx, graph="G"):
    g = _graph(ctx, graph)
    return len(set((e.source, e.target) if g.is_directed() else (min(e.source, e.target), max(e.source, e.target)) for e in g.es))


@op("edge_multiplicity", "Number of parallel edges (repeated interactions) between two nodes in a multigraph; 0 if none.", {"graph": "Graph", "source": "NodeRef", "target": "NodeRef"}, "Scalar", "O(deg)")
def edge_multiplicity(ctx, source, target, graph="G"):
    g = _graph(ctx, graph)
    return g.count_multiple(g.get_eids([(_vid(ctx, g, source), _vid(ctx, g, target))], error=False)) [0] if g.get_eid(_vid(ctx, g, source), _vid(ctx, g, target), error=False) >= 0 else 0


@op("undirected_graph", "A directed graph with direction dropped: the simple undirected graph with one edge per pair of nodes linked in either direction (a pair linked both ways is one edge), all nodes and node attributes kept. Use it as the graph argument whenever a question on a directed graph says to ignore direction: counts of links or neighbours, degrees, cycles, paths and diameter, components, cliques, clustering, neighbour sums. mode=all on the directed graph is not the same: it counts a pair linked both ways twice.",
    {"graph": "Graph"}, "Graph", "O(m)", directed_only=True)
def undirected_graph(ctx, graph="G"):
    h = _graph(ctx, graph).as_undirected(mode="collapse")
    h.simplify(multiple=True, loops=True)
    return h


@op("simplify", "Collapse parallel edges and self-loops into a simple graph (parallel edges summed into a 'weight' attribute).", {"graph": "Graph"}, "Graph", "O(m)")
def simplify(ctx, graph="G"):
    g = _graph(ctx, graph).copy()
    if "weight" not in g.es.attributes():
        g.es["weight"] = 1.0
    g.simplify(multiple=True, loops=True, combine_edges={"weight": "sum"})
    return g


@op("is_bipartite", "Whether the graph is bipartite (two node types with edges only between types).", {"graph": "Graph"}, "Bool", "O(n+m)")
def is_bipartite(ctx, graph="G"):
    return bool(_graph(ctx, graph).is_bipartite())


@op("project_bipartite", "One-mode projection of a bipartite graph onto the side containing `side_node` (or side 'source'/'target' of the file). Two nodes of that side are linked when they share a neighbour; edge weight = number of shared neighbours.",
    {"graph": "Graph", "side": "str: 'source'|'target'|a node id on the wanted side"}, "Graph", "O(sum deg^2)")
def project_bipartite(ctx, side="source", graph="G"):
    g = _graph(ctx, graph)
    ok, types = g.is_bipartite(return_types=True)
    if not ok:
        raise ValueError("graph is not bipartite")
    if side in ("source", "target"):
        wanted = {u for u, _, _ in _rows_cache(ctx)} if side == "source" else {v for _, v, _ in _rows_cache(ctx)}
        # the type that covers the wanted ids
        t_true = sum(1 for i, t in enumerate(types) if t and g.vs[i]["name"] in wanted)
        t_false = sum(1 for i, t in enumerate(types) if not t and g.vs[i]["name"] in wanted)
        want_type = t_true >= t_false
    else:
        want_type = types[_vid(ctx, g, side)]
    p1, p2 = g.bipartite_projection(types=types, multiplicity=True)
    proj = p2 if want_type else p1
    return proj


def _rows_cache(ctx):
    if not hasattr(ctx, "_rows"):
        from .graphs import read_raw
        ctx._rows = read_raw(ctx.lg.facts.path)[1]
    return ctx._rows


@op("heaviest_edges", "The k edges with the largest weight (e.g. most shared neighbours in a projection, most interactions in a simplified multigraph). Returns ordered list of {source, target, weight}.",
    {"graph": "Graph", "k": "int"}, "Table", "O(m log m)")
def heaviest_edges(ctx, graph="G", k=10):
    g = _graph(ctx, graph)
    if "weight" not in g.es.attributes():
        raise ValueError("graph has no edge weights")
    es = sorted(g.es, key=lambda e: -e["weight"])[: int(k)]
    return [{"source": g.vs[e.source]["name"], "target": g.vs[e.target]["name"], "weight": e["weight"]} for e in es]


@op("strongest_ties", "A node's neighbours ordered by edge weight (or by number of parallel edges in a multigraph), strongest first. mode in {all,in,out}. Returns list of {node, weight}.",
    {"graph": "Graph", "node": "NodeRef", "k": "int", "mode": "str"}, "Table", "O(deg)")
def strongest_ties(ctx, node, graph="G", k=10, mode="all"):
    g = _graph(ctx, graph)
    v = _vid(ctx, g, node)
    acc: dict[int, float] = {}
    for e in g.es[g.incident(v, mode=mode)]:
        other = e.target if e.source == v else e.source
        acc[other] = acc.get(other, 0.0) + (e["weight"] if "weight" in g.es.attributes() else 1.0)
    return [{"node": g.vs[o]["name"], "weight": w} for o, w in sorted(acc.items(), key=lambda kv: -kv[1])[: int(k)]]


@op("density", "Edge density: m / possible edges.", {"graph": "Graph"}, "Scalar", "O(1)")
def density(ctx, graph="G"):
    return _graph(ctx, graph).density()


@op("degree_stats", "Degree summary: min, median, mean, max, and a 10-bin histogram. mode in {all,in,out}.",
    {"graph": "Graph", "mode": "str: all|in|out (default all)"}, "Table", "O(n+m)")
def degree_stats(ctx, graph="G", mode="all"):
    g = _graph(ctx, graph)
    d = np.array(g.degree(mode=mode))
    hist, edges = np.histogram(d, bins=10)
    return {"min": int(d.min()), "median": float(np.median(d)), "mean": float(d.mean()), "max": int(d.max()),
            "std": float(d.std()), "histogram": [{"range": [float(edges[i]), float(edges[i + 1])], "count": int(hist[i])} for i in range(len(hist))]}


@op("degree", "Degree of every node as a NodeMap. mode in {all,in,out}. On a directed graph mode=all is in-degree plus out-degree, so a node linked in both directions counts twice; for the number of distinct linked nodes take the degree in undirected_graph.", {"graph": "Graph", "mode": "str"}, "NodeMap", "O(n+m)")
def degree(ctx, graph="G", mode="all"):
    g = _graph(ctx, graph)
    return _nodemap(ctx, g.degree(mode=mode), g)


@op("strength", "Weighted degree (sum of edge weights, or number of parallel edges in a multigraph) per node as NodeMap.", {"graph": "Graph", "mode": "str"}, "NodeMap", "O(n+m)")
def strength(ctx, graph="G", mode="all"):
    g = _graph(ctx, graph)
    w = "weight" if "weight" in g.es.attributes() else None
    return _nodemap(ctx, g.strength(mode=mode, weights=w), g)


@op("node_degree", "Degree of one node. mode in {all,in,out}.", {"graph": "Graph", "node": "NodeRef", "mode": "str"}, "Scalar", "O(1)")
def node_degree(ctx, node, graph="G", mode="all"):
    g = _graph(ctx, graph)
    return g.degree(_vid(ctx, g, node), mode=mode)


@op("reciprocity", "Fraction of directed edges whose reverse also exists. Directed graphs only.",
    {"graph": "Graph"}, "Scalar", "O(m)", directed_only=True)
def reciprocity(ctx, graph="G"):
    return _graph(ctx, graph).reciprocity()


# --------------------------------------------------------------------------- components
@op("components", "Connected components. mode: weak (default) or strong (directed only). Returns count and sizes (descending).",
    {"graph": "Graph", "mode": "str: weak|strong"}, "Partition", "O(n+m)")
def components(ctx, graph="G", mode="weak"):
    g = _graph(ctx, graph)
    c = g.connected_components(mode=mode)
    sizes = sorted(c.sizes(), reverse=True)
    return {"count": len(c), "sizes": sizes[:20], "largest": sizes[0] if sizes else 0, "membership": c.membership, "_names": g.vs["name"], "_kind": "components", "_mode": mode}


@op("largest_component", "Induced subgraph of the largest (weakly) connected component.", {"graph": "Graph", "mode": "str: weak|strong"}, "Graph", "O(n+m)")
def largest_component(ctx, graph="G", mode="weak"):
    g = _graph(ctx, graph)
    c = g.connected_components(mode=mode)
    return c.giant() if g.vcount() else g


@op("is_connected", "Whether the graph is (weakly) connected.", {"graph": "Graph"}, "Bool", "O(n+m)")
def is_connected(ctx, graph="G"):
    return _graph(ctx, graph).is_connected(mode="weak")


# --------------------------------------------------------------------------- distances
@op("diameter", "Longest shortest path. Infinite if disconnected unless largest_component_only. tier exact: all-pairs BFS O(nm); tier approx: double-sweep lower bound from k sources.",
    {"graph": "Graph", "largest_component_only": "bool (default true)", "tier": "exact|approx", "k": "int sources for approx (default 20)"},
    "Scalar", "O(nm)", tiers=["exact", "approx"])
def diameter(ctx, graph="G", largest_component_only=True, tier="exact", k=20):
    g = _graph(ctx, graph)
    if largest_component_only and not g.is_connected(mode="weak"):
        g = g.connected_components(mode="weak").giant()
    if tier == "exact":
        return int(g.diameter(directed=g.is_directed(), unconn=True))
    rng = random.Random(ctx.seed)
    best = 0
    for _ in range(k):
        s = rng.randrange(g.vcount())
        for _sweep in range(2):
            d = g.distances(source=s, mode="out")[0]
            far = max(range(len(d)), key=lambda i: d[i] if d[i] != math.inf else -1)
            best = max(best, int(d[far]) if d[far] != math.inf else best)
            s = far
    return best


@op("shortest_path", "Shortest path between two nodes (hop count, or weighted if use_weights and weights are distances). Returns length and node list.",
    {"graph": "Graph", "source": "NodeRef", "target": "NodeRef", "use_weights": "bool (default false)"}, "Path", "O(n+m)")
def shortest_path(ctx, source, target, graph="G", use_weights=False):
    g = _graph(ctx, graph)
    s, t = _vid(ctx, g, source), _vid(ctx, g, target)
    w = "weight" if (use_weights and "weight" in g.es.attributes()) else None
    paths = g.get_shortest_paths(s, to=t, weights=w, mode="out", output="vpath")
    p = paths[0]
    if not p:
        return {"length": math.inf, "path": [], "reachable": False}
    if w:
        length = sum(g.es[g.get_eid(p[i], p[i + 1])]["weight"] for i in range(len(p) - 1))
    else:
        length = len(p) - 1
    return {"length": length, "path": [_lab(g, i) for i in p], "reachable": True, "hops": len(p) - 1}


@op("distance", "Shortest-path distance (hops) from source to target; inf if unreachable.",
    {"graph": "Graph", "source": "NodeRef", "target": "NodeRef"}, "Scalar", "O(n+m)")
def distance(ctx, source, target, graph="G"):
    g = _graph(ctx, graph)
    d = g.distances(source=_vid(ctx, g, source), target=_vid(ctx, g, target), mode="out")[0][0]
    return d if d != math.inf else math.inf


@op("is_reachable", "Whether target can be reached from source (following edge direction in directed graphs).",
    {"graph": "Graph", "source": "NodeRef", "target": "NodeRef"}, "Bool", "O(n+m)")
def is_reachable(ctx, source, target, graph="G"):
    g = _graph(ctx, graph)
    return g.distances(source=_vid(ctx, g, source), target=_vid(ctx, g, target), mode="out")[0][0] != math.inf


@op("reachable_set", "All nodes reachable from source (following edge direction in directed graphs, within max_hops if given).",
    {"graph": "Graph", "source": "NodeRef", "max_hops": "int or null"}, "NodeSet", "O(n+m)")
def reachable_set(ctx, source, graph="G", max_hops=None):
    g = _graph(ctx, graph)
    s = _vid(ctx, g, source)
    order = max_hops if max_hops is not None else g.vcount()
    nb = g.neighborhood(s, order=order, mode="out")
    return [_lab(g, i) for i in nb if i != s]


@op("k_hop_neighbourhood", "Nodes within k hops of a node (excluding the node). mode in {all,in,out}.",
    {"graph": "Graph", "node": "NodeRef", "k": "int", "mode": "str"}, "NodeSet", "O(k*m)")
def k_hop_neighbourhood(ctx, node, k, graph="G", mode="all"):
    g = _graph(ctx, graph)
    s = _vid(ctx, g, node)
    nb = g.neighborhood(s, order=int(k), mode=mode)
    return [_lab(g, i) for i in nb if i != s]


@op("neighbours", "Direct neighbours of a node, each once. mode in {all,in,out}.", {"graph": "Graph", "node": "NodeRef", "mode": "str"}, "NodeSet", "O(deg)")
def neighbours(ctx, node, graph="G", mode="all"):
    g = _graph(ctx, graph)
    return [_lab(g, i) for i in sorted(set(g.neighbors(_vid(ctx, g, node), mode=mode)))]      # a reciprocated neighbour once


# --------------------------------------------------------------------------- clustering
@op("triangle_count", "Total number of triangles in the graph (undirected interpretation).", {"graph": "Graph"}, "Scalar", "O(m^1.5)")
def triangle_count(ctx, graph="G"):
    g = _graph(ctx, graph)
    if g.is_directed():
        g = g.as_undirected(mode="collapse")
    if g.ecount() < 200_000:
        return int(len(g.cliques(min=3, max=3)))
    deg = np.array(g.degree(), dtype=float)
    lcc = np.nan_to_num(np.array(g.transitivity_local_undirected(mode="zero"), dtype=float))
    return int(round(float((lcc * deg * (deg - 1) / 2).sum() / 3)))


@op("average_clustering", "Average local clustering coefficient (nodes with degree<2 count as 0).", {"graph": "Graph"}, "Scalar", "O(m^1.5)")
def average_clustering(ctx, graph="G"):
    g = _graph(ctx, graph)
    if g.is_directed():
        g = g.as_undirected(mode="collapse")
    return g.transitivity_avglocal_undirected(mode="zero")


@op("transitivity", "Global clustering coefficient (3 x triangles / connected triples).", {"graph": "Graph"}, "Scalar", "O(m^1.5)")
def transitivity(ctx, graph="G"):
    g = _graph(ctx, graph)
    if g.is_directed():
        g = g.as_undirected(mode="collapse")
    return g.transitivity_undirected()


@op("local_clustering", "Local clustering coefficient per node as NodeMap.", {"graph": "Graph"}, "NodeMap", "O(m^1.5)")
def local_clustering(ctx, graph="G"):
    g = _graph(ctx, graph)
    u = g.as_undirected(mode="collapse") if g.is_directed() else g
    return _nodemap(ctx, u.transitivity_local_undirected(mode="zero"), g)


@op("assortativity", "Degree assortativity coefficient (Pearson correlation of degrees at edge ends).", {"graph": "Graph"}, "Scalar", "O(m)")
def assortativity(ctx, graph="G"):
    return _graph(ctx, graph).assortativity_degree(directed=_graph(ctx, graph).is_directed())


# --------------------------------------------------------------------------- cores
@op("core_number", "k-core number (coreness) of every node as NodeMap.", {"graph": "Graph"}, "NodeMap", "O(n+m)")
def core_number(ctx, graph="G"):
    g = _graph(ctx, graph)
    return _nodemap(ctx, g.coreness(mode="all"), g)


@op("max_core", "Maximum k such that a k-core exists (degeneracy) and the size of that core.", {"graph": "Graph"}, "Table", "O(n+m)")
def max_core(ctx, graph="G"):
    g = _graph(ctx, graph)
    c = g.coreness(mode="all")
    k = max(c)
    return {"k": int(k), "size": int(sum(1 for x in c if x == k))}


@op("k_core", "Induced subgraph of the k-core.", {"graph": "Graph", "k": "int"}, "Graph", "O(n+m)")
def k_core(ctx, k, graph="G"):
    g = _graph(ctx, graph)
    return g.k_core(int(k))


# --------------------------------------------------------------------------- centrality
@op("pagerank", "PageRank as NodeMap (directed if graph directed).", {"graph": "Graph", "damping": "float (default 0.85)"}, "NodeMap", "O(k(n+m))")
def pagerank(ctx, graph="G", damping=0.85):
    g = _graph(ctx, graph)
    return _nodemap(ctx, g.pagerank(damping=damping, directed=g.is_directed()), g)


@op("betweenness", "Betweenness centrality as NodeMap. tier exact O(nm); tier approx samples k pivot sources (default 500). use_weights=true treats edge weights as distances (only for distance-like weights).",
    {"graph": "Graph", "tier": "exact|approx", "k": "int pivots for approx", "use_weights": "bool (default false)"}, "NodeMap", "O(nm)", tiers=["exact", "approx"])
def betweenness(ctx, graph="G", tier="exact", k=500, use_weights=False):
    g = _graph(ctx, graph)
    w = "weight" if (use_weights and "weight" in g.es.attributes()) else None
    if tier == "exact":
        return _nodemap(ctx, g.betweenness(directed=g.is_directed(), weights=w), g)
    rng = random.Random(ctx.seed)
    pivots = rng.sample(range(g.vcount()), min(int(k), g.vcount()))
    vals = g.betweenness(directed=g.is_directed(), sources=pivots, weights=w)
    scale = g.vcount() / len(pivots)
    return _nodemap(ctx, [v * scale for v in vals], g)


@op("closeness", "Closeness centrality as NodeMap (harmonic variant handles disconnection). tier approx samples k targets.",
    {"graph": "Graph", "tier": "exact|approx", "k": "int"}, "NodeMap", "O(nm)", tiers=["exact", "approx"])
def closeness(ctx, graph="G", tier="exact", k=500):
    g = _graph(ctx, graph)
    if tier == "exact":
        return _nodemap(ctx, g.harmonic_centrality(mode="out"), g)
    rng = random.Random(ctx.seed)
    targets = rng.sample(range(g.vcount()), min(int(k), g.vcount()))
    # distance from every node to each sampled target = distance from the target along reversed edges: k searches, not n
    d = np.array(g.distances(source=targets, target=None, mode="in"), dtype=float)
    with np.errstate(divide="ignore"):
        h = np.where(d > 0, 1.0 / d, 0.0)
    return _nodemap(ctx, (h.sum(axis=0) * (g.vcount() - 1) / len(targets)).tolist(), g)


@op("eigenvector_centrality", "Eigenvector centrality as NodeMap.", {"graph": "Graph"}, "NodeMap", "O(k(n+m))")
def eigenvector_centrality(ctx, graph="G"):
    g = _graph(ctx, graph)
    return _nodemap(ctx, g.eigenvector_centrality(scale=True), g)


# --------------------------------------------------------------------------- communities
@op("communities", "Community detection. method in {leiden, louvain, label_propagation}. Returns count, sizes, modularity, membership. Undirected interpretation.",
    {"graph": "Graph", "method": "str", "resolution": "float (default 1.0)"}, "Partition", "O(k(n+m))")
def communities(ctx, graph="G", method="leiden", resolution=1.0):
    g = _graph(ctx, graph)
    u = g.as_undirected(mode="collapse") if g.is_directed() else g
    w = "weight" if "weight" in u.es.attributes() else None
    random.seed(ctx.seed)
    ig.set_random_number_generator(random)
    if method == "leiden":
        cl = u.community_leiden(objective_function="modularity", weights=w, resolution=resolution, n_iterations=-1)
    elif method == "louvain":
        cl = u.community_multilevel(weights=w, resolution=resolution)
    elif method == "label_propagation":
        cl = u.community_label_propagation(weights=w)
    else:
        raise ValueError(f"unknown method {method}")
    sizes = sorted(cl.sizes(), reverse=True)
    return {"count": len(cl), "sizes": sizes[:20], "largest": sizes[0], "modularity": float(u.modularity(cl, weights=w)),
            "membership": cl.membership, "_names": g.vs["name"], "method": method, "_kind": "communities"}


@op("largest_block", "Node set of the largest block of a Partition (component or community).", {"partition": "Partition"}, "NodeSet", "O(n)")
def largest_block(ctx, partition):
    p = ctx.values[partition] if isinstance(partition, str) else partition
    mem = p["membership"]
    names = p.get("_names") or ctx.lg.labels
    counts: dict[int, int] = {}
    for c in mem:
        counts[c] = counts.get(c, 0) + 1
    big = max(counts, key=counts.get)
    return [names[i] for i, c in enumerate(mem) if c == big]


@op("block_of", "Node set of the block containing a given node.", {"partition": "Partition", "node": "NodeRef"}, "NodeSet", "O(n)")
def block_of(ctx, partition, node):
    p = ctx.values[partition] if isinstance(partition, str) else partition
    mem = p["membership"]
    names = p.get("_names") or ctx.lg.labels
    c = mem[names.index(ctx.label(ctx.node(node)))]
    return [names[i] for i, x in enumerate(mem) if x == c]


# --------------------------------------------------------------------------- node attributes
ATTR_PREFIX = "a:"


def _attr(g: ig.Graph, attribute: Any) -> list:
    name = ATTR_PREFIX + str(attribute)
    if name not in g.vs.attributes():
        raise ValueError(f"no node attribute '{attribute}'; available: {[a[len(ATTR_PREFIX):] for a in g.vs.attributes() if a.startswith(ATTR_PREFIX)]}")
    return g.vs[name]


def _index_of(ctx: Ctx, g: ig.Graph, label: str) -> Optional[int]:
    if g is ctx.lg.g:
        try:
            return ctx.lg.index[label]
        except KeyError:
            return None
    return _pos(ctx, g).get(label)


_CMP = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
        "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, "in": lambda a, b: a in b,
        "startswith": lambda a, b: str(a).startswith(str(b)), "contains": lambda a, b: str(b) in str(a)}


@op("attribute_of", "Join with the node table: the value of a node attribute for each node of a NodeSet, in the same order. Returns list of {node, value}.",
    {"nodes": "NodeSet", "attribute": "str", "graph": "Graph"}, "Table", "O(n)")
def attribute_of(ctx, nodes, attribute, graph="G"):
    g = _graph(ctx, graph)
    vals = _attr(g, attribute)
    out = []
    for lab in _nodeset(ctx, nodes):
        i = _index_of(ctx, g, lab)
        out.append({"node": lab, "value": vals[i] if i is not None else None})
    return out


@op("filter_by_attribute", "Nodes (of the graph, or of a NodeSet) whose node attribute satisfies op in {==,!=,>,>=,<,<=,in,startswith,contains} value. A list as value means any of them (op == or in). "
    "On a text attribute <,<=,>,>= compare as text, which orders ISO dates correctly: created_at >= '2019-01-01' selects 2019 and later, and startswith '2019' selects the year 2019; startswith and contains also serve prefixes of place names. Nodes with a missing value never match.",
    {"attribute": "str", "op": "str", "value": "value: a string, a number, or a list of them", "nodes": "NodeSet or null", "graph": "Graph"}, "NodeSet", "O(n)")
def filter_by_attribute(ctx, attribute, value, op="==", nodes=None, graph="G"):
    g = _graph(ctx, graph)
    vals = _attr(g, attribute)
    numeric = g["node_table"]["attributes"][str(attribute)]["type"] == "numeric"
    conv = (lambda x: float(x)) if numeric else (lambda x: str(x))
    target = [conv(x) for x in value] if isinstance(value, list) else conv(value)
    if isinstance(target, list) and op in ("==", "in"):
        op, target = "in", set(target)
    f = _CMP[op]
    names = g.vs["name"]
    if nodes is None:
        return [names[i] for i, v in enumerate(vals) if v is not None and f(v, target)]
    out = []
    for lab in _nodeset(ctx, nodes):
        i = _index_of(ctx, g, lab)
        if i is not None and vals[i] is not None and f(vals[i], target):
            out.append(lab)
    return out


@op("group_by_attribute", "Group nodes (of the graph, or of a NodeSet) by a node attribute. Returns list of {value, count} sorted by count; with values (a NodeMap), also {agg} = sum|mean|max|min|median|std of those values per group, sorted by it.",
    {"attribute": "str", "nodes": "NodeSet or null", "values": "NodeMap or null", "agg": "str: sum|mean|max|min|median|std", "graph": "Graph"}, "Table", "O(n)")
def group_by_attribute(ctx, attribute, nodes=None, values=None, agg="mean", graph="G"):
    g = _graph(ctx, graph)
    vals = _attr(g, attribute)
    m = (ctx.values[values] if isinstance(values, str) else values) if values is not None else None
    names = g.vs["name"]
    if nodes is None:
        members = enumerate(names)
    else:
        members = ((_index_of(ctx, g, lab), lab) for lab in _nodeset(ctx, nodes))
    groups: dict[Any, list] = {}
    for i, lab in members:
        if i is None or vals[i] is None:
            continue
        groups.setdefault(vals[i], []).append(m.get(lab) if m is not None else None)
    rows = []
    for v, xs in groups.items():
        row = {"value": v, "count": len(xs)}
        if m is not None:
            ys = [x for x in xs if x is not None]
            if ys:
                row[agg] = float({"sum": np.sum, "mean": np.mean, "max": np.max, "min": np.min, "median": np.median, "std": np.std}[agg](ys))
        rows.append(row)
    rows.sort(key=lambda r: (r.get(agg, float("-inf")) if m is not None else r["count"], r["count"]), reverse=True)
    return rows


@op("attribute_map", "A numeric node attribute as a NodeMap (nodes with a missing value are left out), usable with top_k, filter_nodes, map_stats.",
    {"attribute": "str", "graph": "Graph"}, "NodeMap", "O(n)")
def attribute_map(ctx, attribute, graph="G"):
    g = _graph(ctx, graph)
    vals = _attr(g, attribute)
    names = g.vs["name"]
    return {names[i]: float(v) for i, v in enumerate(vals) if v is not None}


# --------------------------------------------------------------------------- set / map algebra
@op("induced_subgraph", "Subgraph induced by a NodeSet.", {"graph": "Graph", "nodes": "NodeSet"}, "Graph", "O(n+m)")
def induced_subgraph(ctx, nodes, graph="G"):
    g = _graph(ctx, graph)
    ns = _nodeset(ctx, nodes)
    idx = [_vid(ctx, g, x) for x in ns]
    return g.induced_subgraph(idx)


@op("remove_nodes", "The graph without the nodes of a NodeSet (and without their edges). The input graph is not changed.", {"graph": "Graph", "nodes": "NodeSet"}, "Graph", "O(n+m)")
def remove_nodes(ctx, nodes, graph="G"):
    g = _graph(ctx, graph)
    drop = {_vid(ctx, g, x) for x in _nodeset(ctx, nodes)}
    return g.induced_subgraph([i for i in range(g.vcount()) if i not in drop])


@op("top_k", "Top-k entries of a NodeMap by value (descending). Returns ordered list of {node, value}.",
    {"map": "NodeMap", "k": "int", "ascending": "bool"}, "Table", "O(n log n)")
def top_k(ctx, map, k=10, ascending=False):
    m = ctx.values[map] if isinstance(map, str) else map
    pick = heapq.nsmallest if ascending else heapq.nlargest      # same result and tie order as a full sort, without sorting every node
    items = pick(int(k), m.items(), key=lambda kv: kv[1])
    return [{"node": n, "value": v} for n, v in items]


@op("map_value", "Value of a NodeMap at one node.", {"map": "NodeMap", "node": "NodeRef"}, "Scalar", "O(1)")
def map_value(ctx, map, node):
    m = ctx.values[map] if isinstance(map, str) else map
    return m[ctx.label(ctx.node(node))]


@op("set_intersection", "Nodes in both NodeSets.", {"a": "NodeSet", "b": "NodeSet"}, "NodeSet", "O(n)")
def set_intersection(ctx, a, b):
    sb = set(_nodeset(ctx, b))
    return [x for x in _nodeset(ctx, a) if x in sb]


@op("set_union", "Nodes in either NodeSet.", {"a": "NodeSet", "b": "NodeSet"}, "NodeSet", "O(n)")
def set_union(ctx, a, b):
    seen = set(); out = []
    for x in _nodeset(ctx, a) + _nodeset(ctx, b):
        if x not in seen:
            seen.add(x); out.append(x)
    return out


@op("set_difference", "Nodes in a but not in b.", {"a": "NodeSet", "b": "NodeSet"}, "NodeSet", "O(n)")
def set_difference(ctx, a, b):
    sb = set(_nodeset(ctx, b))
    return [x for x in _nodeset(ctx, a) if x not in sb]


@op("argmax", "Node with the largest NodeMap value (optionally within a NodeSet). Returns {node, value}.",
    {"map": "NodeMap", "nodes": "NodeSet or null"}, "Table", "O(n)")
def argmax(ctx, map, nodes=None):
    m = ctx.values[map] if isinstance(map, str) else map
    keys = _nodeset(ctx, nodes) if nodes is not None else list(m.keys())
    best = max(keys, key=lambda k: m[k])
    return {"node": best, "value": m[best]}


@op("filter_nodes", "Subset of a NodeSet (or all nodes) whose NodeMap value satisfies op in {>,>=,<,<=,==} threshold.",
    {"map": "NodeMap", "op": "str", "threshold": "number", "nodes": "NodeSet or null"}, "NodeSet", "O(n)")
def filter_nodes(ctx, map, op, threshold, nodes=None):
    m = ctx.values[map] if isinstance(map, str) else map
    ns = _nodeset(ctx, nodes) if nodes is not None else list(m.keys())
    f = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}[op]
    threshold = _scalar(ctx, threshold, "threshold")
    return [n for n in ns if f(m[n], threshold)]


@op("restrict_map", "Restrict a NodeMap to a NodeSet.", {"map": "NodeMap", "nodes": "NodeSet"}, "NodeMap", "O(n)")
def restrict_map(ctx, map, nodes):
    m = ctx.values[map] if isinstance(map, str) else map
    ns = _nodeset(ctx, nodes)
    return {n: m[n] for n in ns if n in m}


@op("map_stats", "min, max, mean, median, std (population standard deviation), sum and n of a NodeMap. An empty map gives n = 0 and no other value.", {"map": "NodeMap"}, "Table", "O(n)")
def map_stats(ctx, map):
    m = ctx.values[map] if isinstance(map, str) else map
    v = np.array(list(m.values()), dtype=float)
    if not len(v):
        return {"min": None, "max": None, "mean": None, "median": None, "std": None, "n": 0, "sum": 0.0}
    return {"min": float(v.min()), "max": float(v.max()), "mean": float(v.mean()), "median": float(np.median(v)), "std": float(v.std()), "n": int(len(v)), "sum": float(v.sum())}


@op("set_size", "Number of elements in a NodeSet.", {"nodes": "NodeSet"}, "Scalar", "O(1)")
def set_size(ctx, nodes):
    return len(_nodeset(ctx, nodes))


@op("pairwise_distances", "Distances between all pairs in a NodeSet; returns the pair with the largest distance and the full matrix.",
    {"graph": "Graph", "nodes": "NodeSet"}, "Table", "O(|S|(n+m))")
def pairwise_distances(ctx, nodes, graph="G"):
    g = _graph(ctx, graph)
    ns = _nodeset(ctx, nodes)
    idx = [_vid(ctx, g, x) for x in ns]
    d = g.distances(source=idx, target=idx, mode="out")
    best = (-1, None, None)
    for i, a in enumerate(ns):
        for j, b in enumerate(ns):
            if i < j and d[i][j] != math.inf and d[i][j] > best[0]:
                best = (d[i][j], a, b)
    return {"max_distance": best[0], "pair": [best[1], best[2]], "matrix": [[(x if x != math.inf else None) for x in row] for row in d]}


def _scalar(ctx: Ctx, v: Any, what: str = "value") -> float:
    v = ctx.values[v] if isinstance(v, str) and v in ctx.values else v
    if isinstance(v, (list, dict)):
        raise ValueError(f"{what} must be one number, got a {'list' if isinstance(v, list) else 'table'} of {len(v)} entries; refer to one entry, e.g. 'step.field[0]'")
    if v is None:
        raise ValueError(f"{what} has no value (an earlier step was undefined, e.g. a statistic of an empty set or a division by zero)")
    return float(v)


@op("arithmetic", "One arithmetic operation on two scalars (step ids of Scalar steps, 'step.field' or 'step.field[i]' refs, or literal numbers): a op b with op in {+,-,*,/}. Chain steps for longer formulas (a difference, a share, a complement 1 - x, a count times two).",
    {"a": "Scalar", "op": "str: + | - | * | /", "b": "Scalar"}, "Scalar", "O(1)")
def arithmetic(ctx, a, op, b):
    x, y = _scalar(ctx, a, "a"), _scalar(ctx, b, "b")
    if op == "/" and y == 0:
        return None                                        # undefined (a share of an empty group): reported as no value, the other entries of the answer stand
    return {"+": lambda: x + y, "-": lambda: x - y, "*": lambda: x * y, "/": lambda: x / y}[op]()


@op("compare", "Compare two scalars (step refs, 'step.field' refs, or literals), optionally labelled: returns {a, b, a_greater, greater: label, ratio}.",
    {"a": "Scalar", "b": "Scalar", "label_a": "str or null", "label_b": "str or null"}, "Table", "O(1)")
def compare(ctx, a, b, label_a=None, label_b=None):
    av, bv = _scalar(ctx, a, "a"), _scalar(ctx, b, "b")
    la = label_a if label_a is not None else (a if isinstance(a, str) else "a")
    lb = label_b if label_b is not None else (b if isinstance(b, str) else "b")
    return {"a": av, "b": bv, "label_a": la, "label_b": lb, "a_greater": av > bv, "greater": la if av > bv else lb, "ratio": (av / bv) if bv else None}


@op("is_finite", "True if a scalar is a finite number (e.g. a distance that is not inf).", {"value": "Scalar"}, "Bool", "O(1)")
def is_finite(ctx, value):
    v = ctx.values[value] if isinstance(value, str) and value in ctx.values else value
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------- edges between groups, neighbours' values, maps
_EDGES: dict = {}


def _edges(g: ig.Graph):
    """(sources, targets) of a graph as arrays, kept for the last two graphs asked about."""
    if id(g) in _EDGES and len(_EDGES[id(g)][1]) != g.ecount():        # the graph grew in place (appended rows)
        del _EDGES[id(g)]
    if id(g) not in _EDGES:
        while len(_EDGES) >= 2:
            _EDGES.pop(next(iter(_EDGES)))
        e = np.array(g.get_edgelist(), dtype=np.int64).reshape(-1, 2)
        _EDGES[id(g)] = (g, e[:, 0].copy(), e[:, 1].copy())
    return _EDGES[id(g)][1], _EDGES[id(g)][2]


def _mask(ctx: Ctx, g: ig.Graph, nodes: Any) -> np.ndarray:
    m = np.zeros(g.vcount(), dtype=bool)
    idx = [i for i in (_index_of(ctx, g, lab) for lab in _nodeset(ctx, nodes)) if i is not None]
    m[idx] = True
    return m


def _map(ctx: Ctx, x: Any) -> dict:
    m = ctx.values[x] if isinstance(x, str) and x in ctx.values else x
    if not isinstance(m, dict) or "membership" in m:
        raise ValueError("not a NodeMap")
    return m


def _over_neighbours(g: ig.Graph, x: np.ndarray, mode: str):
    """For every node: the sum of x over its neighbours and the number of neighbours with a value (x is nan where missing)."""
    src, dst = _edges(g)
    n = g.vcount()
    has = ~np.isnan(x)
    x0 = np.where(has, x, 0.0)
    tot, cnt = np.zeros(n), np.zeros(n)
    both = (not g.is_directed()) or mode == "all"
    if both or mode == "out":                # a node sees the far end of the edges it starts
        tot += np.bincount(src, weights=x0[dst], minlength=n); cnt += np.bincount(src, weights=has[dst].astype(float), minlength=n)
    if both or mode == "in":
        tot += np.bincount(dst, weights=x0[src], minlength=n); cnt += np.bincount(dst, weights=has[src].astype(float), minlength=n)
    return tot, cnt


@op("edges_between", "Number of edges with one end in NodeSet a and the other in NodeSet b (directed graphs: from a to b). With a == b: the edges inside the set. Edges between two groups, e.g. between two languages, without any subtraction.",
    {"a": "NodeSet", "b": "NodeSet", "graph": "Graph"}, "Scalar", "O(n+m)")
def edges_between(ctx, a, b, graph="G"):
    g = _graph(ctx, graph)
    src, dst = _edges(g)
    ma, mb = _mask(ctx, g, a), _mask(ctx, g, b)
    hit = ma[src] & mb[dst]
    if not g.is_directed():
        hit |= mb[src] & ma[dst]
    return int(hit.sum())


@op("edges_touching", "Number of edges with at least one end in a NodeSet.", {"nodes": "NodeSet", "graph": "Graph"}, "Scalar", "O(n+m)")
def edges_touching(ctx, nodes, graph="G"):
    g = _graph(ctx, graph)
    src, dst = _edges(g)
    m = _mask(ctx, g, nodes)
    return int((m[src] | m[dst]).sum())


@op("mixing_matrix", "Edge counts by the attribute values of the two ends (of the graph, or only among a NodeSet): list of {a, b, count}, largest first. Undirected graphs: each unordered pair of values once; directed: a is the source's value. Ends with a missing value are left out.",
    {"attribute": "str", "nodes": "NodeSet or null", "graph": "Graph"}, "Table", "O(n+m)")
def mixing_matrix(ctx, attribute, nodes=None, graph="G"):
    g = _graph(ctx, graph)
    vals = _attr(g, attribute)
    src, dst = _edges(g)
    cats = sorted({v for v in vals if v is not None}, key=str)
    code = {v: i for i, v in enumerate(cats)}
    c = np.array([code[v] if v is not None else -1 for v in vals], dtype=np.int64)
    ok = (c[src] >= 0) & (c[dst] >= 0)
    if nodes is not None:
        m = _mask(ctx, g, nodes)
        ok &= m[src] & m[dst]
    a, b = c[src][ok], c[dst][ok]
    if not g.is_directed():
        a, b = np.minimum(a, b), np.maximum(a, b)
    k = len(cats)
    counts = np.bincount(a * k + b, minlength=k * k)
    rows = [{"a": cats[i // k], "b": cats[i % k], "count": int(n)} for i, n in enumerate(counts) if n]
    rows.sort(key=lambda r: -r["count"])
    return rows


@op("attribute_assortativity", "Assortativity coefficient of a node attribute over the edges (Newman): nominal for a categorical attribute, Pearson for a numeric one. Computed on the nodes that have a value.",
    {"attribute": "str", "graph": "Graph"}, "Scalar", "O(n+m)")
def attribute_assortativity(ctx, attribute, graph="G"):
    g = _graph(ctx, graph)
    vals = _attr(g, attribute)
    keep = [i for i, v in enumerate(vals) if v is not None]
    if len(keep) < g.vcount():
        g = g.induced_subgraph(keep); vals = [vals[i] for i in keep]
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return float(g.assortativity([float(v) for v in vals], directed=g.is_directed()))
    code: dict = {}
    return float(g.assortativity_nominal([code.setdefault(v, len(code)) for v in vals], directed=g.is_directed()))


@op("neighbour_aggregate", "For every node, an aggregate of a NodeMap over its neighbours: agg in {sum, mean, count} (count = number of neighbours that have a value in the map). mode in {all,in,out}: out = the nodes it points to. Nodes without such a neighbour are left out for mean. "
    "Examples: mean views of each user's neighbours; with restrict_map first, how much of a quantity sits among neighbours of one group.",
    {"values": "NodeMap", "agg": "str: sum|mean|count", "mode": "str", "graph": "Graph"}, "NodeMap", "O(n+m)")
def neighbour_aggregate(ctx, values, agg="mean", mode="all", graph="G"):
    g = _graph(ctx, graph)
    m = _map(ctx, values)
    names = g.vs["name"]
    x = np.array([m.get(nm, math.nan) for nm in names], dtype=float)
    tot, cnt = _over_neighbours(g, x, mode)
    if agg == "sum":
        return {names[i]: float(v) for i, v in enumerate(tot)}
    if agg == "count":
        return {names[i]: float(v) for i, v in enumerate(cnt)}
    if agg != "mean":
        raise ValueError(f"unknown agg {agg}")
    return {names[i]: float(tot[i] / cnt[i]) for i in np.nonzero(cnt)[0]}


def _reciprocated(g: ig.Graph):
    """(sources, targets) of the distinct directed edges whose reverse edge exists, self-loops left out."""
    s, t = _edges(g)
    n = g.vcount()
    key = np.unique(s[s != t] * n + t[s != t])
    u, v = key // n, key % n
    keep = np.isin(v * n + u, key)
    return u[keep], v[keep]


@op("mutual_degree", "For every node of a directed graph, the number of nodes it is linked to in both directions (it points to them and they point back): its reciprocated links, as a NodeMap. Divide by out-degree with map_arithmetic for a per-node reciprocity share; sum it over a NodeSet (restrict_map, map_stats) and divide by the set's summed out-degree for a group's reciprocation rate.",
    {"graph": "Graph"}, "NodeMap", "O(m log m)", directed_only=True)
def mutual_degree(ctx, graph="G"):
    g = _graph(ctx, graph)
    u, _ = _reciprocated(g)
    cnt = np.bincount(u, minlength=g.vcount())
    names = g.vs["name"]
    return {names[i]: float(c) for i, c in enumerate(cnt)}


@op("mutual_graph", "The undirected graph of reciprocated links of a directed graph: one edge per pair of nodes linked in both directions, one-way links dropped, node attributes kept. Nodes with no reciprocated link are left out (so averages, component and community counts are over nodes that have at least one mutual tie; say so in the answer) unless keep_isolated. Use it as the graph argument of any operator to analyse mutual ties only (triangles, clustering, k-core, communities, components, edges_between two groups).",
    {"graph": "Graph", "keep_isolated": "bool"}, "Graph", "O(m log m)", directed_only=True)
def mutual_graph(ctx, graph="G", keep_isolated=False):
    g = _graph(ctx, graph)
    u, v = _reciprocated(g)
    once = u < v
    h = ig.Graph(n=g.vcount(), edges=np.column_stack([u[once], v[once]]).tolist(), directed=False)
    for a_ in g.vs.attributes():
        h.vs[a_] = g.vs[a_]
    for a_ in g.attributes():
        h[a_] = g[a_]
    if not keep_isolated:
        h = h.induced_subgraph(np.flatnonzero(np.asarray(h.degree()) > 0).tolist())
    return h


@op("neighbours_in_set", "For every node of the graph, the number of its neighbours that are in a NodeSet (mode in {all,in,out}; out = nodes it points to), as a NodeMap. Divide by degree with map_arithmetic for a share, e.g. the share of a user's links that go to users of the same group.",
    {"nodes": "NodeSet", "mode": "str", "graph": "Graph"}, "NodeMap", "O(n+m)")
def neighbours_in_set(ctx, nodes, mode="all", graph="G"):
    g = _graph(ctx, graph)
    x = np.where(_mask(ctx, g, nodes), 1.0, math.nan)
    _, cnt = _over_neighbours(g, x, mode)
    names = g.vs["name"]
    return {names[i]: float(v) for i, v in enumerate(cnt)}


@op("neighbourhood_of_set", "All nodes within k hops of at least one node of a NodeSet (mode in {all,in,out}; in = the nodes that point to them). The nodes of the set themselves are left out unless include_sources.",
    {"nodes": "NodeSet", "k": "int", "mode": "str", "include_sources": "bool", "graph": "Graph"}, "NodeSet", "O(n+m)")
def neighbourhood_of_set(ctx, nodes, k=1, mode="all", include_sources=False, graph="G"):
    g = _graph(ctx, graph)
    idx = [i for i in (_index_of(ctx, g, lab) for lab in _nodeset(ctx, nodes)) if i is not None]
    seen = np.zeros(g.vcount(), dtype=bool)
    seen[idx] = True
    frontier = idx
    for _ in range(int(k)):
        nxt = set()
        for row in g.neighborhood(frontier, order=1, mode=mode, mindist=1):
            nxt.update(row)
        frontier = [i for i in nxt if not seen[i]]
        seen[frontier] = True
        if not frontier:
            break
    if not include_sources:
        seen[idx] = False
    names = g.vs["name"]
    return [names[i] for i in np.nonzero(seen)[0]]


@op("membership_map", "The block of every node of a Partition (communities or components) as a NodeMap: blocks are numbered by size, 1 = largest. Use with filter_nodes (== b) for the nodes of block b, and with group_by_map for block sizes or per-block aggregates.",
    {"partition": "Partition"}, "NodeMap", "O(n)")
def membership_map(ctx, partition):
    p = ctx.values[partition] if isinstance(partition, str) else partition
    mem = p["membership"]
    names = p.get("_names") or ctx.lg.labels
    counts: dict[int, int] = {}
    for c in mem:
        counts[c] = counts.get(c, 0) + 1
    rank = {c: r for r, c in enumerate(sorted(counts, key=lambda c: (-counts[c], c)), 1)}
    return {names[i]: float(rank[c]) for i, c in enumerate(mem)}


@op("map_arithmetic", "Node-by-node arithmetic on a NodeMap: a op b with op in {+,-,*,/}, where b is another NodeMap (a step id; nodes present in both are kept) or a number. Division by zero drops the node.",
    {"a": "NodeMap", "op": "str: + | - | * | /", "b": "value: a NodeMap step id or a number"}, "NodeMap", "O(n)")
def map_arithmetic(ctx, a, op, b):
    ma = _map(ctx, a)
    f = {"+": lambda x, y: x + y, "-": lambda x, y: x - y, "*": lambda x, y: x * y, "/": lambda x, y: x / y}[op]
    if isinstance(b, str) and b in ctx.values:
        mb = _map(ctx, b)
        return {n: float(f(v, mb[n])) for n, v in ma.items() if n in mb and not (op == "/" and mb[n] == 0)}
    y = float(b)
    if op == "/" and y == 0:
        raise ValueError("division by zero")
    return {n: float(f(v, y)) for n, v in ma.items()}


@op("map_quantile", "The q-quantile of the values of a NodeMap, q between 0 and 1 (0.99 = 99th percentile), by linear interpolation.", {"map": "NodeMap", "q": "float"}, "Scalar", "O(n log n)")
def map_quantile(ctx, map, q):
    q = float(q)
    q = q / 100.0 if q > 1 else q
    return float(np.quantile(np.array(list(_map(ctx, map).values()), dtype=float), q))


@op("map_bins", "Split the nodes of a NodeMap into `bins` groups of equal size by value (10 = deciles, 4 = quartiles): returns a NodeMap node -> bin number, 1 = lowest values. Ties are split by position. Use with filter_nodes (== b) or group_by_map.",
    {"map": "NodeMap", "bins": "int"}, "NodeMap", "O(n log n)")
def map_bins(ctx, map, bins=10):
    m = _map(ctx, map)
    names = list(m)
    order = np.argsort(np.array([m[n] for n in names], dtype=float), kind="stable")
    out = {}
    for r, i in enumerate(order):
        out[names[i]] = float(r * int(bins) // len(names) + 1)
    return out


@op("group_by_map", "Group nodes by the value of a NodeMap (a bin number from map_bins, a block from membership_map, a core number, a 0/1 flag): list of {value, count}, ascending by value; with values (another NodeMap) also {agg} = sum|mean|max|min|median|std of it per group.",
    {"groups": "NodeMap", "values": "NodeMap or null", "agg": "str: sum|mean|max|min|median|std"}, "Table", "O(n)")
def group_by_map(ctx, groups, values=None, agg="mean"):
    gm = _map(ctx, groups)
    vm = _map(ctx, values) if values is not None else None
    buckets: dict[float, list] = {}
    for n, k in gm.items():
        buckets.setdefault(k, []).append(vm.get(n) if vm is not None else None)
    rows = []
    for k in sorted(buckets):
        row = {"value": int(k) if float(k).is_integer() else k, "count": len(buckets[k])}
        if vm is not None:
            ys = [y for y in buckets[k] if y is not None]
            if ys:
                row[agg] = float({"sum": np.sum, "mean": np.mean, "max": np.max, "min": np.min, "median": np.median, "std": np.std}[agg](ys))
        rows.append(row)
    return rows


@op("map_correlation", "Correlation between two NodeMaps over the nodes present in both: method pearson or spearman (rank correlation, ties get average ranks). E.g. degree against a numeric attribute (attribute_map).",
    {"a": "NodeMap", "b": "NodeMap", "method": "str: pearson|spearman"}, "Scalar", "O(n log n)")
def map_correlation(ctx, a, b, method="pearson"):
    import pandas as pd
    ma, mb = _map(ctx, a), _map(ctx, b)
    keys = [n for n in ma if n in mb]
    x, y = pd.Series([ma[n] for n in keys], dtype=float), pd.Series([mb[n] for n in keys], dtype=float)
    if method == "spearman":
        x, y = x.rank(), y.rank()
    elif method != "pearson":
        raise ValueError(f"unknown method {method}")
    return float(np.corrcoef(x.to_numpy(), y.to_numpy())[0, 1])



# Scope-sensitive operators: computed on a subgraph they give different values than computed on the whole graph and
# then restricted to the subgraph's nodes. Session reuse must never substitute one for the other without saying so.
SCOPE_SENSITIVE = ("pagerank", "betweenness", "closeness", "eigenvector_centrality", "degree", "strength", "core_number",
                   "local_clustering", "communities", "components")
for _name in SCOPE_SENSITIVE:
    CATALOGUE[_name].scope_sensitive = True


def catalogue_text(include_tiers: bool = True) -> str:
    lines = []
    for s in CATALOGUE.values():
        p = ", ".join(f"{k}: {v}" for k, v in s.params.items())
        t = f" tiers={s.tiers}" if include_tiers and len(s.tiers) > 1 else ""
        d = " [directed graphs only]" if s.directed_only else ""
        lines.append(f"- {s.name}({p}) -> {s.returns}  cost {s.cost}{t}{d}\n    {s.doc}")
    return "\n".join(lines)
