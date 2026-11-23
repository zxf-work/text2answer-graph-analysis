"""How fast can the igraph graph be built from an edge array? Usage: python bench/igraph_build.py <edge file>"""
import sys, time, resource
import numpy as np, igraph as ig, pyarrow.csv as pc
p = sys.argv[1]
skip = sum(1 for l in open(p, "rb") if l.startswith(b"#")) if False else 0
with open(p, "rb") as f:
    for line in f:
        if not line.startswith(b"#"): break
        skip += 1
tb = pc.read_csv(p, read_options=pc.ReadOptions(skip_rows=skip, autogenerate_column_names=True), parse_options=pc.ParseOptions(delimiter="\t"))
u, v = tb["f0"].to_numpy(), tb["f1"].to_numpy()
N = int(max(u.max(), v.max())) + 1
e = np.stack([u.astype(np.int32), v.astype(np.int32)], axis=1); del u, v, tb
def t(name, f):
    t0 = time.time(); g = f(); print(f"{name:<52} {time.time()-t0:7.2f} s  peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6:.1f} GB  m={g.ecount()}", flush=True); return g
def add(ed, d=True):
    g = ig.Graph(n=N, directed=d); g.add_edges(ed); return g
t("add_edges, file order, int32", lambda: add(e))
t("Graph(n, edges=array)", lambda: ig.Graph(n=N, edges=e, directed=True))
o = np.lexsort((e[:, 1], e[:, 0])); es = np.ascontiguousarray(e[o]); del o
t("add_edges, sorted by source then target", lambda: add(es))
t("add_edges, int64 array", lambda: add(es.astype(np.int64)))
g = t("add_edges, undirected", lambda: add(es, False))
t0 = time.time(); g.degree(); print("degree", round(time.time()-t0, 2))
