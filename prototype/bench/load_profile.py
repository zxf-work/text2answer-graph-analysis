"""Where the time of a cold load goes, and what off-the-shelf pieces would change it.

Usage: python bench/load_profile.py <edge file> [--threads N]
Prints one line per stage: seconds and peak resident memory so far. No model calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import t2r.graphs as G  # noqa: E402

OUT: dict = {}


def rss():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 1)


class T:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.t = time.time()
        return self

    def __exit__(self, *a):
        s = round(time.time() - self.t, 2)
        OUT[self.name] = s
        print(f"{self.name:<46} {s:>8.2f} s   peak {rss()} GB", flush=True)


def comment_lines(path):
    n = 0
    with open(path, "rb") as f:
        for line in f:
            if not line.startswith(b"#"):
                break
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--skip-current", action="store_true")
    a = ap.parse_args()
    p = a.path
    print("file", p, round(os.path.getsize(p) / 1e9, 2), "GB; cpus", len(os.sched_getaffinity(0)), flush=True)
    os.environ["T2R_DISK_CACHE"] = "1"

    # ---------------------------------------------------------------- A. the current path, stage by stage
    if not a.skip_current:
        import pandas as pd
        with T("A1 pandas parse only (current reader)"):
            us, vs = [], []
            for df in pd.read_csv(p, sep=r"\s+", header=None, comment="#", engine="c", chunksize=5_000_000):
                us.append(df[0].to_numpy()); vs.append(df[1].to_numpy())
            u0 = np.concatenate(us); v0 = np.concatenate(vs); del us, vs
        del u0, v0
        with T("A2 read_raw_fast (parse + file statistics)"):
            facts, arrays = G.read_raw_fast(p)
        sem = G.infer_semantics(facts, "")
        key = G._cache_key(p, None)
        G._PENDING_KEY.append(key)
        real_put, real_from = G._disk_cache_put, G._graph_from_edges

        def put(*x, **k):
            with T("A4 write binary cache"):
                real_put(*x, **k)

        def from_edges(*x, **k):
            with T("A3b igraph add_edges"):
                return real_from(*x, **k)
        G._disk_cache_put, G._graph_from_edges = put, from_edges
        with T("A3 _build_big (dedup, igraph, labels, cache)"):
            lg = G._build_big("g", facts, sem, arrays)
        del arrays
        G._disk_cache_put, G._graph_from_edges = real_put, real_from
        G._PENDING_KEY.pop()
        with T("A5 profile_card"):
            G.profile_card(lg)
        g = lg.g
        with T("A5a   degree"):
            np.array(g.degree())
        with T("A5b   weak components"):
            g.connected_components(mode="weak")
        if g.is_directed():
            with T("A5c   strong components"):
                g.connected_components(mode="strong")
            with T("A5d   reciprocity"):
                g.reciprocity()
        # appending to the graph in memory instead of loading again
        rng = np.random.default_rng(0)
        extra = rng.integers(0, g.vcount(), size=(60_000, 2))
        extra = extra[extra[:, 0] != extra[:, 1]]
        with T("A6 add 60k edges to the loaded graph"):
            g.add_edges(extra)
        del lg, g
        with T("A7 restore from binary cache (second load)"):
            lg = G._disk_cache_get("g", p, None)
        del lg

    # ---------------------------------------------------------------- B. other readers
    skip = comment_lines(p)
    with open(p, "rb") as f:
        for _ in range(skip):
            f.readline()
        first = f.readline()
    sep = "\t" if b"\t" in first else ("," if b"," in first else " ")
    u = v = None
    try:
        import pyarrow as pa
        import pyarrow.csv as pc
        with T("B1 pyarrow.csv read (all threads)"):
            tb = pc.read_csv(p, read_options=pc.ReadOptions(skip_rows=skip, autogenerate_column_names=True, block_size=64 << 20),
                             parse_options=pc.ParseOptions(delimiter=sep),
                             convert_options=pc.ConvertOptions(column_types={"f0": pa.int64(), "f1": pa.int64()}, include_columns=["f0", "f1"]))
            u = tb["f0"].to_numpy(); v = tb["f1"].to_numpy()
        del tb
    except Exception as e:  # noqa: BLE001
        print("B1 pyarrow failed:", type(e).__name__, e)
    try:
        import polars as pl
        with T("B2 polars read_csv (all threads)"):
            df = pl.read_csv(p, separator=sep, has_header=False, comment_prefix="#", new_columns=["u", "v"], columns=[0, 1],
                             schema_overrides={"column_1": pl.Int64, "column_2": pl.Int64})
            u2 = df["u"].to_numpy(); v2 = df["v"].to_numpy()
        if u is None:
            u, v = u2, v2
        else:
            assert len(u) == len(u2) and int(u.sum()) == int(u2.sum()) and int(v.sum()) == int(v2.sum())
        del u2, v2
    except Exception as e:  # noqa: BLE001
        print("B2 polars failed:", type(e).__name__, e)
        df = None

    # ---------------------------------------------------------------- C. hashing the whole file
    for name, mk in (("sha1", hashlib.sha1), ("blake2b", hashlib.blake2b)):
        with T(f"C  full-file {name}"):
            h = mk()
            with open(p, "rb") as f:
                while True:
                    b = f.read(16 << 20)
                    if not b:
                        break
                    h.update(b)
    try:
        import xxhash
        with T("C  full-file xxh3_128"):
            h = xxhash.xxh3_128()
            with open(p, "rb") as f:
                while True:
                    b = f.read(16 << 20)
                    if not b:
                        break
                    h.update(b)
    except Exception as e:  # noqa: BLE001
        print("C xxhash failed:", type(e).__name__, e)

    if u is None:
        return
    # ---------------------------------------------------------------- D. file statistics (distinct pairs)
    N = int(max(u.max(), v.max())) + 1
    with T("D1 numpy: distinct directed + undirected pairs"):
        nd = len(np.unique(u * N + v))
        lo = np.minimum(u, v); hi = np.maximum(u, v)
        nu = len(np.unique(lo * N + hi)); del lo, hi
    try:
        import polars as pl
        with T("D2 polars: distinct directed + undirected pairs"):
            k = pl.DataFrame({"u": u, "v": v})
            nd2 = k.select((pl.col("u") * N + pl.col("v")).n_unique()).item()
            nu2 = k.select((pl.min_horizontal("u", "v") * N + pl.max_horizontal("u", "v")).n_unique()).item()
        assert (nd, nu) == (nd2, nu2), (nd, nu, nd2, nu2)
        with T("D3 polars: sort-based dedup of directed pairs"):
            kk = k.select((pl.col("u") * N + pl.col("v")).alias("k")).unique()
        del k, kk
    except Exception as e:  # noqa: BLE001
        print("D2 polars failed:", type(e).__name__, e)

    # ---------------------------------------------------------------- E. building the igraph graph
    import igraph as ig
    dt = np.int32 if N < 2**31 else np.int64
    mask = u != v
    edges = np.stack([u[mask].astype(dt), v[mask].astype(dt)], axis=1)
    del u, v, mask
    with T("E1 igraph add_edges, directed"):
        g = ig.Graph(n=N, directed=True); g.add_edges(edges)
    with T("E2 labels: arange().astype(str).tolist() + vs['name']"):
        labels = np.arange(N).astype(str).tolist(); g.vs["name"] = labels
    del g, labels
    with T("E3 np.save edges (uncompressed) to scratch"):
        np.save(os.path.join(os.environ.get("TMPDIR", "/tmp"), "lp_edges.npy"), edges)
    with T("E4 np.load edges"):
        e2 = np.load(os.path.join(os.environ.get("TMPDIR", "/tmp"), "lp_edges.npy"))
    with T("E5 np.load edges, memory-mapped"):
        e3 = np.load(os.path.join(os.environ.get("TMPDIR", "/tmp"), "lp_edges.npy"), mmap_mode="r"); int(e3[-1, 0])
    os.remove(os.path.join(os.environ.get("TMPDIR", "/tmp"), "lp_edges.npy"))
    print("JSON", json.dumps(OUT))


if __name__ == "__main__":
    main()
