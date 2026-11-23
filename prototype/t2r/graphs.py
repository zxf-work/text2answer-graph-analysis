"""Graph loading, semantics inference, profile card, and node-name resolution.

The profile card is the only description of the graph that an LLM ever sees.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from difflib import get_close_matches
from typing import Any, Optional

import igraph as ig
import numpy as np


# --------------------------------------------------------------------------- raw file facts
@dataclass
class RawFacts:
    """What can be read from the file without interpreting it."""
    path: str
    n_lines: int
    header: Optional[list[str]]
    n_columns: int
    sample_rows: list[list[str]]
    ids_numeric: bool
    n_distinct_ids: int
    n_rows: int
    n_rows_dedup_directed: int       # distinct (u,v)
    n_rows_dedup_undirected: int     # distinct {u,v}
    n_self_loops: int
    reciprocity: float               # fraction of (u,v) rows whose (v,u) also appears
    weight_column_numeric: bool
    weight_values_distinct: int
    weight_min: Optional[float]
    weight_max: Optional[float]
    sha1: str
    weight_column_name: Optional[str] = None
    columns_used: tuple[int, int, Optional[int]] = (0, 1, None)   # (source col, target col, weight col)
    row_index_column: bool = False          # first column is a running row number, not a node id
    weight_has_fractions: bool = False
    id_ranges_disjoint: bool = False        # source ids and target ids never overlap (bipartite file)
    n_bytes: int = 0                        # file size the facts describe (large-file reader only; needed to append in place)


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


SRC_NAMES = {"source", "src", "from", "u", "node1", "a", "head", "user", "person", "from_id", "src_id", "i", "sender", "citing", "follower", "buyer", "parent", "from_junction", "customer"}
TGT_NAMES = {"target", "tgt", "to", "v", "node2", "b", "tail", "item", "to_id", "dst", "dst_id", "j", "recipient", "cited", "followed", "seller", "child", "to_junction", "product"}
NOT_WEIGHT = ("time", "date", "stamp", "id", "year", "label", "type", "name")
WEIGHT_NAMES = {"weight", "w", "count", "n", "distance", "dist", "km", "length", "cost", "time", "minutes", "strength", "value", "freq", "frequency", "times", "distance_km", "travel_time_min"}
INDEX_NAMES = {"id", "row", "idx", "index", "edge_id", "eid", "#"}


def _pick_columns(header: Optional[list[str]], raw: list[list[str]]) -> tuple[int, int, Optional[int], bool]:
    """Decide which columns are source, target, weight. Returns (s, t, w, row_index_detected)."""
    ncol = max(len(r) for r in raw) if raw else (len(header) if header else 2)
    if header:
        low = [c.strip().lower() for c in header]
        si = next((i for i, c in enumerate(low) if c in SRC_NAMES), None)
        ti = next((i for i, c in enumerate(low) if c in TGT_NAMES and i != si), None)
        wi = next((i for i, c in enumerate(low) if c in WEIGHT_NAMES and i not in (si, ti)), None)
        idx = next((i for i, c in enumerate(low) if c in INDEX_NAMES), None)
        if si is None or ti is None:
            cands = [i for i in range(len(low)) if i != idx]
            si = cands[0] if si is None else si
            ti = next(i for i in cands if i != si) if ti is None else ti
        if wi is None and ncol > 2:
            wi = next((i for i in range(ncol) if i not in (si, ti, idx) and i < len(low) and not any(k in low[i] for k in NOT_WEIGHT)), None)
        return si, ti, wi, idx is not None
    # no header: detect a running row index in column 0 when there are 3+ columns
    if ncol >= 3 and len(raw) >= 20:
        c0 = [r[0] for r in raw[:200] if len(r) >= 3]
        if all(_is_number(x) for x in c0):
            vals = [int(float(x)) for x in c0]
            if all(vals[i + 1] - vals[i] == 1 for i in range(len(vals) - 1)):
                wi = 3 if ncol >= 4 else None
                return 1, 2, wi, True
    return 0, 1, (2 if ncol > 2 else None), False


BIG_FILE_BYTES = 60_000_000


def _read_arrow(path: str):
    """Multi-threaded parse of a plain numeric edge list (pyarrow). Returns (u, v, weight column or None, sample rows, column
    names), or None when pyarrow is missing or the file is not that simple (the pandas reader then takes over).
    Measured on Orkut (117M rows, 1.8 GB): 0.7 s against 8.8 s for the chunked pandas parse."""
    try:
        import pyarrow as pa
        import pyarrow.csv as pc
        skip = 0
        with open(path, "rb") as f:
            for line in f:
                if not line.startswith(b"#"):
                    break
                skip += 1
        sep = "\t" if b"\t" in line else ("," if b"," in line else " ")
        tb = pc.read_csv(path, read_options=pc.ReadOptions(skip_rows=skip, autogenerate_column_names=True, block_size=64 << 20),
                         parse_options=pc.ParseOptions(delimiter=sep))
        names = tb.column_names
        if len(names) < 2 or not all(pa.types.is_integer(tb[c].type) for c in names[:2]) or tb.num_rows == 0:
            return None
        if any(tb[c].null_count for c in names[:3]):
            return None
        head = tb.slice(0, 200).to_pandas()
        sample = head.astype(str).values.tolist()
        u = tb[names[0]].to_numpy(); v = tb[names[1]].to_numpy()
        wcol = tb[names[2]].to_pandas() if len(names) > 2 else None
        return u, v, wcol, sample, list(range(len(names)))
    except Exception:  # noqa: BLE001  (anything unusual: comments inside the file, ragged rows, text ids)
        return None


def _n_distinct(key) -> int:
    """Number of distinct values. polars (parallel hashing) when installed: 1 s where numpy's sort-based unique took 110 s
    per array on 117M rows."""
    try:
        import polars as pl
        return int(pl.Series("k", key).n_unique())
    except ImportError:
        return len(np.unique(key))


def _sorted_distinct(key):
    try:
        import polars as pl
        return pl.Series("k", key).unique().sort().to_numpy()
    except ImportError:
        return np.unique(key)


def _first_of_each(key):
    """Row index of the first occurrence of every distinct key, ordered by key (what np.unique(return_index=True) gives)."""
    try:
        import polars as pl
        d = pl.DataFrame({"k": key}).with_row_index("i").group_by("k").agg(pl.col("i").min()).sort("k")
        return d["i"].to_numpy().astype(np.int64)
    except ImportError:
        return np.unique(key, return_index=True)[1]


def read_raw_fast(path: str) -> tuple[RawFacts, Any]:
    """Large-file path: pandas load, numpy statistics, sampled reciprocity. Returns (facts, (u, v, w) arrays)."""
    import pandas as pd
    # The hash covers the whole file: it is part of every reuse key, so an edit anywhere must change it (about 1 s per GB).
    with open(path, "rb") as f:
        h = hashlib.file_digest(f, "sha1")
    h.update(str(os.path.getsize(path)).encode())
    with open(path, "r") as f:
        first = f.readline()
    delim = "," if "," in first else r"\s+"
    toks = [x.strip() for x in (first.strip().split(",") if delim == "," else first.split())]
    header = toks if (len(toks) >= 2 and not all(_is_number(x) for x in toks[:2]) and not first.startswith("#")) else None
    fast = None if header else _read_arrow(path)
    if fast is not None:
        u, v, wcol, raw_sample, cols = fast
        si, ti, wi, row_index = _pick_columns(header, raw_sample)
        if (si, ti) != (0, 1) or (wi is not None and wi != 2):
            fast = None
    if fast is None:
        # Read in chunks: a single frame for a 50M-row file peaks at several GB; chunks bound the peak to one chunk plus the column arrays.
        us, vs, ws = [], [], []
        raw_sample = None; cols = None; si = ti = wi = row_index = None
        for df in pd.read_csv(path, sep=delim, header=0 if header else None, comment="#", engine="c", dtype=str if header else None, chunksize=5_000_000):
            if raw_sample is None:
                raw_sample = df.head(200).astype(str).values.tolist()
                si, ti, wi, row_index = _pick_columns(header, raw_sample)
                cols = list(df.columns)
            us.append(df[cols[si]].to_numpy()); vs.append(df[cols[ti]].to_numpy())
            if wi is not None and wi < len(cols):
                ws.append(df[cols[wi]])
            del df
        u = np.concatenate(us); v = np.concatenate(vs); del us, vs
        wcol = pd.concat(ws, ignore_index=True) if ws else None; del ws
    try:
        u = u.astype(np.int64, copy=False); v = v.astype(np.int64, copy=False); numeric = True
    except (ValueError, TypeError):
        numeric = False
    w = None
    if wi is not None and wi < len(cols):
        try:
            w = pd.to_numeric(wcol, errors="coerce").to_numpy(dtype=float)
            if np.isnan(w).any():
                w = None
        except Exception:
            w = None
    n_rows = len(u)
    if numeric:
        N = int(max(u.max(), v.max())) + 1
        # presence arrays instead of np.unique over the concatenation: O(N) bytes rather than a sorted 2m-element copy
        if N <= 50 * n_rows + 1000:
            seen_u = np.zeros(N, dtype=bool); seen_u[u] = True
            seen_v = np.zeros(N, dtype=bool); seen_v[v] = True
            n_ids = int((seen_u | seen_v).sum())
            srcs_tgts_disjoint = not bool((seen_u & seen_v).any())
            del seen_u, seen_v
        else:
            n_ids = len(np.unique(np.concatenate([u, v])))
            srcs_tgts_disjoint = len(np.intersect1d(np.unique(u), np.unique(v))) == 0
        self_loops = int((u == v).sum())
        lo = np.minimum(u, v); hi = np.maximum(u, v)
        n_dedup_u = _n_distinct(lo * N + hi)
        del lo, hi
        uniq_d = _sorted_distinct(u * N + v)
        n_dedup_d = len(uniq_d)
        rng = np.random.default_rng(0)
        idx = rng.choice(n_rows, size=min(200_000, n_rows), replace=False)
        su, sv = u[idx], v[idx]
        nonloop = su != sv
        rev = sv[nonloop] * N + su[nonloop]
        pos = np.searchsorted(uniq_d, rev)
        pos[pos >= len(uniq_d)] = 0
        recip = float(np.mean(uniq_d[pos] == rev)) if nonloop.any() else 0.0
        del uniq_d, rev, pos
    else:
        n_ids = len(set(u) | set(v)); self_loops = int((u == v).sum()); recip = 0.0
        n_dedup_d = n_rows; n_dedup_u = n_rows; srcs_tgts_disjoint = False
    facts = RawFacts(
        path=path, n_lines=n_rows + (1 if header else 0), header=header, n_columns=len(cols), sample_rows=raw_sample[:5],
        ids_numeric=numeric, n_distinct_ids=n_ids, n_rows=n_rows, n_rows_dedup_directed=n_dedup_d, n_rows_dedup_undirected=n_dedup_u,
        n_self_loops=self_loops, reciprocity=recip, weight_column_numeric=w is not None,
        weight_values_distinct=int(len(np.unique(w))) if w is not None else 0,
        weight_min=float(w.min()) if w is not None else None, weight_max=float(w.max()) if w is not None else None,
        sha1=h.hexdigest()[:12], weight_column_name=(header[wi] if (header and wi is not None and wi < len(header)) else None),
        columns_used=(si, ti, wi), row_index_column=row_index,
        weight_has_fractions=bool(w is not None and (w != np.floor(w)).any()), id_ranges_disjoint=srcs_tgts_disjoint,
        n_bytes=os.path.getsize(path),
    )
    return facts, (u, v, w)


def read_facts(path: str) -> RawFacts:
    """File facts only (no graph). Uses the chunked numpy path for big files so the row list is never materialised."""
    if os.path.getsize(path) > BIG_FILE_BYTES:
        facts, _ = read_raw_fast(path)
        return facts
    facts, _ = read_raw(path)
    return facts


def read_raw(path: str) -> tuple[RawFacts, list[tuple[str, str, Optional[float]]]]:
    rows: list[tuple[str, str, Optional[float]]] = []
    header = None
    sample: list[list[str]] = []
    h = hashlib.sha1()
    n_lines = 0
    raw: list[list[str]] = []
    with open(path, "r", newline="") as f:
        first = f.readline()
        n_lines += 1
        h.update(first.encode())
        delim = "," if "," in first else ("\t" if "\t" in first and not " " in first.strip() else None)
        toks = [x.strip() for x in first.strip().split(delim)]
        if toks and len(toks) >= 2 and not all(_is_number(x) for x in toks[:2]) and not first.startswith("#"):
            header = toks
        elif len(toks) >= 2 and not first.startswith("#"):
            raw.append(toks)
        for line in f:
            n_lines += 1
            h.update(line.encode())
            if not line.strip() or line.startswith("#"):
                continue
            t = [x.strip() for x in line.strip().split(delim)]
            if len(t) < 2:
                continue
            raw.append(t)
    si, ti, wi, row_index = _pick_columns(header, raw)
    for t in raw:
        if len(t) <= max(si, ti):
            continue
        w = float(t[wi]) if (wi is not None and len(t) > wi and _is_number(t[wi])) else None
        rows.append((t[si], t[ti], w))
        if len(sample) < 5:
            sample.append(t)
    srcs = set(u for u, _, _ in rows); tgts = set(v for _, v, _ in rows)
    ids = srcs | tgts
    ids_numeric = all(_is_number(x) for x in list(ids)[:1000])
    directed_set = set((u, v) for u, v, _ in rows)
    undirected_set = set(frozenset((u, v)) if u != v else frozenset((u,)) for u, v, _ in rows)
    self_loops = sum(1 for u, v, _ in rows if u == v)
    recip = sum(1 for (u, v) in directed_set if u != v and (v, u) in directed_set)
    non_loop = sum(1 for (u, v) in directed_set if u != v)
    reciprocity = recip / non_loop if non_loop else 0.0
    weights = [w for _, _, w in rows if w is not None]
    n_cols = len(sample[0]) if sample else (len(header) if header else 2)
    facts = RawFacts(
        path=path, n_lines=n_lines, header=header, n_columns=n_cols, sample_rows=sample,
        ids_numeric=ids_numeric, n_distinct_ids=len(ids), n_rows=len(rows),
        n_rows_dedup_directed=len(directed_set), n_rows_dedup_undirected=len(undirected_set),
        n_self_loops=self_loops, reciprocity=reciprocity,
        weight_column_numeric=bool(weights) and len(weights) == len(rows),
        weight_values_distinct=len(set(weights)) if weights else 0,
        weight_min=min(weights) if weights else None, weight_max=max(weights) if weights else None,
        sha1=h.hexdigest()[:12],
        weight_column_name=(header[wi].strip() if (header and wi is not None and wi < len(header)) else None),
        columns_used=(si, ti, wi), row_index_column=row_index,
        weight_has_fractions=any(not float(w).is_integer() for w in weights[:10000]) if weights else False,
        id_ranges_disjoint=bool(rows) and not (srcs & tgts),
    )
    return facts, rows


# --------------------------------------------------------------------------- semantics
@dataclass
class Semantics:
    directed: bool
    weighted: bool
    weight_semantics: Optional[str]   # "strength" | "distance" | None
    multigraph: bool                  # duplicate rows kept as parallel edges
    labelled: bool
    confidence: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    needs_clarification: list[str] = field(default_factory=list)


def infer_semantics(facts: RawFacts, description: str = "") -> Semantics:
    """Infer directedness, weights, multigraph-ness from the file alone.

    Returns a Semantics with confidences and the questions the system should ask
    when the evidence is weak. The description (if provided by the user) is used
    only as a weak textual hint.
    """
    ev: dict[str, str] = {}
    conf: dict[str, float] = {}
    ask: list[str] = []
    desc = description.lower()

    # directedness
    if facts.reciprocity > 0.98:
        directed, c = False, 0.95
        ev["directed"] = f"{facts.reciprocity:.1%} of rows have their reverse present: undirected graph stored in both directions"
    elif facts.reciprocity < 0.02:
        # either an undirected graph stored once, or a directed graph with no reciprocity.
        # Real directed networks almost always have some reciprocity, so lean undirected-stored-once,
        # but flag it.
        directed, c = False, 0.6
        ev["directed"] = f"only {facts.reciprocity:.1%} of rows are reciprocated: either undirected stored once (likely) or a directed graph with no mutual edges"
        ask.append("directed")
    else:
        directed, c = True, 0.85
        ev["directed"] = f"{facts.reciprocity:.1%} of rows are reciprocated: partial reciprocity is the signature of a directed graph"
    hdr_l = [c.lower() for c in facts.header] if facts.header else []
    DIRECTED_HDR = {"sender", "recipient", "citing", "cited", "follower", "followed", "buyer", "seller", "parent", "child", "trust", "rating", "payer", "payee", "caller", "callee"}
    hits = [c for c in hdr_l if c in DIRECTED_HDR]
    if hits and facts.reciprocity < 0.98:
        directed, c = True, max(c, 0.85)
        ev["directed"] = ev["directed"] + f"; column names {hits} denote an asymmetric relation"
        ask = [a for a in ask if a != "directed"]
    if "undirected" in desc or "symmetric" in desc:
        directed, c, ev["directed"] = False, max(c, 0.9), ev["directed"] + "; description says undirected"
        ask = [a for a in ask if a != "directed"]
    elif "directed" in desc or "trust" in desc or "follow" in desc or "cites" in desc:
        directed, c, ev["directed"] = True, max(c, 0.9), ev["directed"] + "; description says directed"
        ask = [a for a in ask if a != "directed"]
    conf["directed"] = c

    # weights
    weighted = facts.weight_column_numeric and facts.weight_values_distinct > 1
    wsem = None
    if weighted:
        conf["weighted"] = 0.9
        wname = (facts.weight_column_name or "").lower()
        ev["weighted"] = f"numeric column '{facts.weight_column_name or 'col ' + str(facts.columns_used[2])}' with {facts.weight_values_distinct} distinct values in [{facts.weight_min}, {facts.weight_max}]"
        if any(k in wname for k in ("dist", "km", "length", "cost", "time", "min", "sec", "hour", "metre", "meter", "mile")):
            wsem, conf["weight_semantics"] = "distance", 0.9
            ev["weight_semantics"] = f"column name '{facts.weight_column_name}' denotes a distance or cost"
        elif any(k in wname for k in ("count", "freq", "times", "strength", "n_", "num", "share", "co")):
            wsem, conf["weight_semantics"] = "strength", 0.9
            ev["weight_semantics"] = f"column name '{facts.weight_column_name}' denotes a count or strength"
        elif any(k in desc for k in ("distance", "cost", "length", "km", "time")):
            wsem, conf["weight_semantics"] = "distance", 0.85
        elif any(k in desc for k in ("count", "strength", "co-", "frequency", "number of", "times")):
            wsem, conf["weight_semantics"] = "strength", 0.85
        elif facts.weight_has_fractions:
            wsem, conf["weight_semantics"] = None, 0.4
            ev["weight_semantics"] = "fractional weights under an uninformative name: could be distances or similarities"
            ask.append("weight_semantics")
        elif facts.weight_min is not None and facts.weight_min >= 1 and float(facts.weight_min).is_integer() and float(facts.weight_max).is_integer():
            wsem, conf["weight_semantics"] = "strength", 0.6
            ev["weight_semantics"] = "integer counts starting at 1 look like interaction counts (strength), not distances"
            ask.append("weight_semantics")
        else:
            wsem, conf["weight_semantics"] = None, 0.3
            ask.append("weight_semantics")
    else:
        conf["weighted"] = 0.95
        ev["weighted"] = "no numeric weight column" if facts.n_columns < 3 else "third column is constant"

    # multigraph
    dup = facts.n_rows - (facts.n_rows_dedup_directed if directed else facts.n_rows_dedup_undirected)
    multigraph = False
    hdr = " ".join(facts.header).lower() if facts.header else ""
    if dup > 0:
        if not directed and facts.reciprocity > 0.98 and abs(dup - facts.n_rows / 2) < 0.01 * facts.n_rows:
            ev["multigraph"] = "duplicates are exactly the reverse copies of an undirected graph stored both ways; collapsed"
            conf["multigraph"] = 0.95
        elif dup / facts.n_rows > 0.05 or any(k in hdr for k in ("time", "date", "event", "msg", "message", "email", "call", "transaction")):
            multigraph = True
            conf["multigraph"] = 0.8
            ev["multigraph"] = f"{dup} repeated rows ({dup / facts.n_rows:.1%}): rows look like events (repeated interactions), kept as parallel edges; use distinct_edge_count for unique pairs"
            if not any(k in hdr for k in ("time", "date", "event", "msg", "message", "email", "call", "transaction")):
                ask.append("multigraph")
        else:
            ev["multigraph"] = f"{dup} duplicate rows ({dup / facts.n_rows:.1%}); treated as noise and collapsed"
            conf["multigraph"] = 0.7
    else:
        conf["multigraph"] = 0.95
        ev["multigraph"] = "no duplicate rows"

    labelled = not facts.ids_numeric
    if facts.row_index_column:
        ev["columns"] = f"first column is a running row number; edges read from columns {facts.columns_used[0]} and {facts.columns_used[1]}"
        conf["columns"] = 0.9
    if facts.id_ranges_disjoint:
        ev["bipartite"] = "source ids and target ids never overlap: the file looks bipartite (two node types); one-mode questions need a projection"
        conf["bipartite"] = 0.85
    return Semantics(directed=directed, weighted=weighted, weight_semantics=wsem,
                     multigraph=multigraph, labelled=labelled, confidence=conf, evidence=ev,
                     needs_clarification=ask)


# --------------------------------------------------------------------------- loaded graph
@dataclass
class LoadedGraph:
    name: str
    g: ig.Graph
    facts: RawFacts
    semantics: Semantics
    labels: list[str]                       # index -> label
    index: dict[str, int]                   # label -> index
    lower_index: dict[str, int]
    strict: bool = False                    # exact-match-only node resolution (ablation)
    load_info: dict = field(default_factory=dict)  # {"source": "file"|"disk-cache"|"memory", "seconds": float}
    _cache_key: Optional[str] = None            # set while a parse is in progress so the builders can write the disk cache

    def __post_init__(self):
        if self._cache_key is None and _PENDING_KEY:
            self._cache_key = _PENDING_KEY[-1]

    def resolve(self, name: Any, k: int = 3) -> dict[str, Any]:
        """Resolve a user-supplied node reference to a vertex index.

        Returns {"matched": idx or None, "method": ..., "candidates": [...]}.
        """
        s = str(name).strip()
        if s in self.index:
            return {"matched": self.index[s], "method": "exact", "candidates": [s]}
        if s.lower() in self.lower_index:
            return {"matched": self.lower_index[s.lower()], "method": "case-insensitive", "candidates": [self.labels[self.lower_index[s.lower()]]]}
        if self.strict or not self.semantics.labelled:
            # numeric ids: never fuzzy-match; strict mode (ablation): exact only
            return {"matched": None, "method": "none", "candidates": []}
        # token containment (e.g. "Jean Valjean" -> "Valjean")
        toks = [t for t in re.split(r"[\s,_-]+", s.lower()) if t]
        contained = [lab for lab in self.labels if any(t == lab.lower() or t in lab.lower().split() for t in toks)]
        if len(contained) == 1:
            return {"matched": self.index[contained[0]], "method": "token", "candidates": contained}
        close = get_close_matches(s, self.labels, n=k, cutoff=0.75)
        if len(close) == 1 or (close and len(contained) == 0):
            return {"matched": self.index[close[0]], "method": "fuzzy", "candidates": close}
        return {"matched": None, "method": "none", "candidates": (contained or close)[:k]}


def _load_graph_uncached(name: str, path: str, description: str = "", override: Optional[dict] = None) -> LoadedGraph:
    """Load an edge list and build an igraph.Graph according to inferred (or overridden) semantics."""
    big = os.path.getsize(path) > BIG_FILE_BYTES
    if big:
        facts, arrays = read_raw_fast(path)
        rows = None
    else:
        facts, rows = read_raw(path)
    sem = infer_semantics(facts, description)
    if override:
        for k, v in override.items():
            setattr(sem, k, v)
            sem.confidence[k] = 1.0
            sem.evidence[k] = "declared by user"
        sem.needs_clarification = [a for a in sem.needs_clarification if a not in override]
    if big:
        return _build_big(name, facts, sem, arrays)
    # vertex index
    if facts.ids_numeric:
        ids = sorted({int(float(u)) for u, v, _ in rows} | {int(float(v)) for u, v, _ in rows})
        labels = [str(i) for i in ids]
    else:
        labels = sorted({u for u, v, _ in rows} | {v for u, v, _ in rows})
    index = {lab: i for i, lab in enumerate(labels)}
    def key(x: str) -> str:
        return str(int(float(x))) if facts.ids_numeric else x
    elist: list[tuple[int, int]] = []
    wlist: list[float] = []
    seen: set[tuple[int, int]] = set()
    for u, v, w in rows:
        a, b = index[key(u)], index[key(v)]
        if a == b:
            continue
        if not sem.directed and a > b:
            a, b = b, a
        if (a, b) in seen and not sem.multigraph:
            continue
        seen.add((a, b))
        elist.append((a, b))
        wlist.append(w if (w is not None and sem.weighted) else 1.0)
    g = ig.Graph(n=len(labels), edges=elist, directed=sem.directed)
    g.vs["name"] = labels
    if sem.weighted:
        g.es["weight"] = wlist
    lg = LoadedGraph(name=name, g=g, facts=facts, semantics=sem, labels=labels, index=index,
                     lower_index={l.lower(): i for l, i in index.items()})
    _disk_cache_put(lg, np.array(elist, dtype=np.int64).reshape(-1, 2), np.array(wlist, dtype=float) if sem.weighted else None, np.array(labels, dtype=str), contiguous=False)
    return lg


class _RangeIndex:
    """label -> index mapping for contiguous integer ids 0..N-1 without a 10M-entry dict."""

    def __init__(self, n: int):
        self.n = n

    def _key(self, k: Any) -> Optional[int]:
        try:
            i = int(k)
        except (TypeError, ValueError):
            return None
        return i if 0 <= i < self.n and str(i) == str(k).strip() else None

    def __contains__(self, k: Any) -> bool:
        return self._key(k) is not None

    def __getitem__(self, k: Any) -> int:
        i = self._key(k)
        if i is None:
            raise KeyError(k)
        return i

    def __len__(self) -> int:
        return self.n



# --------------------------------------------------------------------------- node attribute table
NODE_TABLE_SUFFIXES = (".nodes.csv", ".nodes.tsv", ".nodes.txt")
ATTR_PREFIX = "a:"          # vertex attributes holding node-table columns; subgraphs inherit them from igraph


def sidecar_node_table(edge_path: str) -> Optional[str]:
    """A node table lives next to the edge file as <stem>.nodes.csv|tsv|txt (stem = edge file name without extension)."""
    stem = os.path.splitext(edge_path)[0]
    for suf in NODE_TABLE_SUFFIXES:
        if os.path.exists(stem + suf):
            return stem + suf
    return None


def attach_node_table(lg: "LoadedGraph", path: str) -> dict:
    """Read a node table (first column = node id, header row required) and attach its columns as vertex attributes.

    Each column is typed numeric (at least 95% of its non-empty values parse as numbers) or categorical. Rows whose id
    is not a node of the graph are counted and skipped; nodes without a row have a missing value (None).
    Returns the table summary, also stored on the graph as g["node_table"]."""
    import pandas as pd
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    sha = h.hexdigest()[:12]
    g = lg.g
    if "node_table" in g.attributes() and g["node_table"]["sha1"] == sha:
        return g["node_table"]
    with open(path, "r", errors="replace") as f:
        first = f.readline()
    sep = "\t" if "\t" in first else ("," if "," in first else r"\s+")
    df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, engine="python" if sep == r"\s+" else "c")
    idcol = df.columns[0]
    n = g.vcount()
    pos = np.full(len(df), -1, dtype=np.int64)
    for r, lab in enumerate(df[idcol].tolist()):
        try:
            pos[r] = lg.index[lab.strip()]
        except KeyError:
            pass
    ok = pos >= 0
    summary: dict[str, Any] = {}
    values: dict[str, Any] = {}
    for col in df.columns[1:]:
        raw = df[col].to_numpy()[ok]
        present = np.array([x.strip() not in ("", "null", "NULL", "None", "NA", "nan") for x in raw], dtype=bool)
        num = pd.to_numeric(pd.Series(raw[present]), errors="coerce")
        numeric = bool(present.any()) and float(num.notna().mean()) >= 0.95
        column: list = [None] * n
        if numeric:
            full = pd.to_numeric(pd.Series(raw), errors="coerce").to_numpy()
            for p_, v in zip(pos[ok].tolist(), full.tolist()):
                if v == v:
                    column[p_] = float(v)
            vals = np.array([v for v in column if v is not None], dtype=float)
            summary[col] = {"type": "numeric", "coverage": round(len(vals) / max(n, 1), 4), "n_distinct": int(len(np.unique(vals))) if len(vals) else 0,
                            "min": float(vals.min()) if len(vals) else None, "median": float(np.median(vals)) if len(vals) else None,
                            "max": float(vals.max()) if len(vals) else None}
            values[col] = None
        else:
            for p_, v, pr in zip(pos[ok].tolist(), raw.tolist(), present.tolist()):
                if pr:
                    column[p_] = v.strip()
            counts = Counter(v for v in column if v is not None)
            summary[col] = {"type": "categorical", "coverage": round(sum(counts.values()) / max(n, 1), 4), "n_distinct": len(counts),
                            "top_values": [{"value": v, "count": c} for v, c in counts.most_common(8)]}
            values[col] = set(counts) if len(counts) <= 20000 else None
        g.vs[ATTR_PREFIX + col] = column
    g["node_table"] = {"file": os.path.basename(path), "sha1": sha, "id_column": idcol, "rows": int(len(df)), "rows_matched": int(ok.sum()),
                       "nodes_without_row": int(n - len(set(pos[ok].tolist()))), "attributes": summary, "values": values}
    return g["node_table"]


_GRAPH_CACHE: dict = {}


def _load_or_restore(name: str, path: str, description: str, override: Optional[dict]) -> LoadedGraph:
    """Disk cache first, then a full parse that writes the disk cache. Records where the graph came from and how long it took."""
    t0 = time.time()
    lg = _disk_cache_get(name, path, override)
    if lg is not None:
        lg.load_info = {"source": "disk-cache", "seconds": round(time.time() - t0, 1)}
        return lg
    key = _cache_key(path, override) if _disk_cache_enabled() else None
    _PENDING_KEY.append(key)
    try:
        lg = _load_graph_uncached(name, path, description, override)
    finally:
        _PENDING_KEY.pop()
    lg.load_info = {"source": "file", "seconds": round(time.time() - t0, 1)}
    return lg


_PENDING_KEY: list = []


def load_graph(name: str, path: str, description: str = "", override: Optional[dict] = None) -> LoadedGraph:
    """Load a graph: process memory (T2R_GRAPH_CACHE=1, the demo server), else the binary disk cache, else parse the file.

    A node table next to the edge file (see sidecar_node_table) is attached to every load."""
    lg = _load_graph_any(name, path, description, override)
    table = sidecar_node_table(path)
    if table is not None:
        attach_node_table(lg, table)
    return lg


def _load_graph_any(name: str, path: str, description: str = "", override: Optional[dict] = None) -> LoadedGraph:
    if os.environ.get("T2R_GRAPH_CACHE") != "1":
        return _load_or_restore(name, path, description, override)
    key = (os.path.abspath(path), os.path.getmtime(path), json.dumps(override, sort_keys=True) if override else "")
    lg = _GRAPH_CACHE.get(key)
    if lg is None:
        lg = _load_or_restore(name, path, description, override)
        _GRAPH_CACHE[key] = lg
        return dataclasses.replace(lg, strict=False)
    return dataclasses.replace(lg, strict=False, load_info={"source": "memory", "seconds": 0.0})


def _build_big(name: str, facts: RawFacts, sem: Semantics, arrays) -> LoadedGraph:
    u, v, w = arrays
    del arrays
    if not facts.ids_numeric:
        raise ValueError("large files must have integer node ids")
    nmax = int(max(u.max(), v.max())); nmin = int(min(u.min(), v.min()))
    contiguous = nmin == 0 and nmax + 1 == facts.n_distinct_ids
    if contiguous:
        N = nmax + 1
        a, b = u, v
        del u, v
    else:
        if nmin >= 0 and nmax < 50 * len(u) + 1000:
            # lookup table instead of a sort over 2m values: O(max id) memory, linear time
            present = np.zeros(nmax + 1, dtype=bool); present[u] = True; present[v] = True
            ids = np.flatnonzero(present)
            remap = np.cumsum(present, dtype=np.int64) - 1
            del present
            a = remap[u]; b = remap[v]
            del remap, u, v
        else:
            ids, inv = np.unique(np.concatenate([u, v]), return_inverse=True)
            a = inv[: len(u)].astype(np.int64); b = inv[len(u):].astype(np.int64)
            del inv, u, v
        N = len(ids)
    if not sem.directed:
        lo = np.minimum(a, b); hi = np.maximum(a, b); a, b = lo, hi
        del lo, hi
    mask = a != b
    if not mask.all():
        a, b = a[mask], b[mask]
        ww = w[mask] if w is not None else None
    else:
        ww = w
    del mask, w
    n_dedup = facts.n_rows_dedup_directed if sem.directed else facts.n_rows_dedup_undirected
    if not sem.multigraph and n_dedup < facts.n_rows:
        key = a.astype(np.int64) * N + b
        first = _first_of_each(key)
        del key
        a, b = a[first], b[first]
        ww = ww[first] if ww is not None else None
        del first
    # igraph accepts a numpy (m, 2) array directly; a Python list of 50M tuples would need ~6 GB on its own
    dt = np.int32 if N < 2**31 else np.int64
    edges = np.stack([a.astype(dt, copy=False), b.astype(dt, copy=False)], axis=1)
    del a, b
    g = _graph_from_edges(N, edges, sem.directed)
    if contiguous:
        labels = np.arange(N).astype(str).tolist()
        index: Any = _RangeIndex(N)
    else:
        labels = ids.astype(str).tolist()
        index = {lab: i for i, lab in enumerate(labels)}
    g.vs["name"] = labels
    if sem.weighted and ww is not None:
        g.es["weight"] = ww.tolist()
    g["file_state"] = facts.sha1
    lg = LoadedGraph(name=name, g=g, facts=facts, semantics=sem, labels=labels, index=index, lower_index=index)
    _disk_cache_put(lg, edges, ww if sem.weighted else None, None if contiguous else ids, contiguous=contiguous)
    del edges
    return lg


def _graph_from_edges(n: int, edges, directed: bool) -> "ig.Graph":
    """Build the igraph graph from an (m, 2) integer array with one add_edges call. Measured on 50M edges: 31 s at a
    3.3 GB peak; inserting in 10M slices took 60 s because igraph rebuilds its index after every call, and the Graph
    constructor given the array peaked at three times the final size."""
    g = ig.Graph(n=n, directed=directed)
    g.add_edges(edges)
    return g


# --------------------------------------------------------------------------- appending in place
APPEND_DECLINED = ""      # why the last append_in_place call returned None (for logs and tests)


def _declined(why: str) -> None:
    global APPEND_DECLINED
    APPEND_DECLINED = why
    return None


def append_in_place(lg: LoadedGraph, path: str, description: str = "", override: Optional[dict] = None) -> Optional[LoadedGraph]:
    """The file grew at its end: add the new rows to the loaded graph instead of loading everything again.

    Returns the updated LoadedGraph, or None whenever the result could differ from a full load, in which case the
    caller loads the file again. It is used only when all of these hold:
    - the graph came from the large-file reader (integer ids, no header, no weight column) and is in the state its
      facts describe;
    - the first n_bytes bytes of the file are unchanged (their hash is the old file hash) and end with a newline;
    - the new rows parse as integer pairs and are at most half the old row count;
    - no new node id would change the vertex order a full load gives (new ids come after all old ones, and keep the
      ids contiguous if they were);
    - the file statistics can be updated exactly from the graph (see the two early returns on self-loops and on an
      undirected reading), and the semantics inferred from the updated statistics are the ones already in force.
    Vertex order equals a full load's; edge order can differ, which changes no result beyond floating-point rounding.
    The graph object is modified, so any other holder of it must reload (the "file_state" mark tells them)."""
    if os.environ.get("T2R_APPEND", "1") == "0":
        return _declined("switched off")
    f, g = lg.facts, lg.g
    if (not f.n_bytes or f.header or not f.ids_numeric or f.columns_used != (0, 1, None) or f.row_index_column or f.id_ranges_disjoint
            or "file_state" not in g.attributes() or g["file_state"] != f.sha1):
        return _declined("graph not from the large-file reader, or not in the state of its facts")
    t0 = time.time()
    try:
        size = os.path.getsize(path)
        if size <= f.n_bytes:
            return _declined("file did not grow")
        h = hashlib.sha1()
        with open(path, "rb") as fh:
            left = f.n_bytes
            last = b""
            while left:
                chunk = fh.read(min(left, 16 << 20))
                if not chunk:
                    return _declined("file shorter than before")
                h.update(chunk); left -= len(chunk); last = chunk[-1:]
            old = h.copy(); old.update(str(f.n_bytes).encode())
            if old.hexdigest()[:12] != f.sha1 or last != b"\n":
                return _declined("the old part of the file changed, or did not end with a newline")
            tail = fh.read()
        h.update(tail); h.update(str(size).encode())
        import io
        import pandas as pd
        df = pd.read_csv(io.BytesIO(tail), sep="," if b"," in tail[:4096] else r"\s+", header=None, comment="#", engine="c")
        if df.shape[1] != f.n_columns or len(df) == 0 or len(df) > f.n_rows // 2 or df[0].dtype.kind != "i" or df[1].dtype.kind != "i":
            return _declined("new rows are not integer pairs, or too many")
        tu = df[0].to_numpy(dtype=np.int64); tv = df[1].to_numpy(dtype=np.int64)
        k = len(tu)
        # the directedness evidence is a sampled reciprocity: stay away from its two decision thresholds
        # (k new rows can at most be reciprocated themselves and reciprocate k old rows; 0.01 covers the sampling error)
        r_lo = f.reciprocity * f.n_rows / (f.n_rows + k) - 0.01
        r_hi = (f.reciprocity * f.n_rows + 2 * k) / (f.n_rows + k) + 0.01
        if any(r_lo <= t <= r_hi for t in (0.02, 0.98)):
            return _declined("reciprocity too close to a decision threshold")
        n = g.vcount()
        contiguous = isinstance(lg.index, _RangeIndex)
        both = np.concatenate([tu, tv])
        if both.min() < 0:
            return _declined("negative id")
        if contiguous:
            new_ids = np.unique(both[both >= n])
            if len(new_ids) and not np.array_equal(new_ids, np.arange(n, n + len(new_ids))):
                return _declined("new ids would leave a gap in contiguous ids")
            a, b = tu, tv
        else:
            ids = np.asarray(lg.labels, dtype=np.int64)
            pos = np.searchsorted(ids, both); pos[pos >= n] = n - 1
            found = ids[pos] == both
            new_ids = np.unique(both[~found])
            if len(new_ids) and new_ids[0] <= ids[-1]:
                return _declined("a new id sorts before an existing one")
            mapped = np.where(found, pos, n + np.searchsorted(new_ids, both))
            a, b = mapped[:k], mapped[k:]
        loops = a == b
        if loops.any() and f.n_self_loops:
            return _declined("self-loop appended to a file that already had self-loops")                    # the graph holds no self-loops, so a repeated one cannot be recognised
        m = n + len(new_ids)
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        key_d, first_d = np.unique(a * m + b, return_index=True)
        key_u, first_u = np.unique(lo * m + hi, return_index=True)

        def in_graph(x, y):
            """For each pair, whether the edge x->y (or {x, y}) is in the graph as loaded."""
            out = np.zeros(len(x), dtype=bool)
            q = (x < n) & (y < n) & (x != y)
            if q.any():
                out[q] = np.asarray(g.get_eids(np.stack([x[q], y[q]], axis=1).tolist(), error=False)) >= 0
            return out
        if g.is_directed():
            had_d = in_graph(a[first_d], b[first_d])
            had_u = in_graph(a[first_u], b[first_u]) | in_graph(b[first_u], a[first_u])
        else:
            had_u = in_graph(lo[first_u], hi[first_u])
            if had_u.any():
                return _declined("appended pair already present under the undirected reading")                # the undirected graph does not say in which direction the old row was written
            had_d = np.zeros(len(first_d), dtype=bool)
        facts = dataclasses.replace(
            f, n_lines=f.n_lines + k, n_rows=f.n_rows + k, n_distinct_ids=f.n_distinct_ids + len(new_ids),
            n_rows_dedup_directed=f.n_rows_dedup_directed + int((~had_d).sum()),
            n_rows_dedup_undirected=f.n_rows_dedup_undirected + int((~had_u).sum()),
            n_self_loops=f.n_self_loops + int(loops.sum()), sha1=h.hexdigest()[:12], n_bytes=size)
        sem = infer_semantics(facts, description)
        for kk, vv in (override or {}).items():
            setattr(sem, kk, vv); sem.confidence[kk] = 1.0; sem.evidence[kk] = "declared by user"
        sem.needs_clarification = [x for x in sem.needs_clarification if x not in (override or {})]
        was = lg.semantics
        if (sem.directed, sem.weighted, sem.multigraph, sem.weight_semantics, sem.labelled) != (was.directed, was.weighted, was.multigraph, was.weight_semantics, was.labelled):
            return _declined("inferred semantics would change")
        if sem.directed != g.is_directed():
            return _declined("directedness would change")
        # rows to add, in file order: no self-loops; without parallel edges, only the first copy of a pair not yet there
        if sem.multigraph:
            keep = np.flatnonzero(~loops)
        else:
            keep = np.sort((first_d[~had_d] if g.is_directed() else first_u[~had_u]))
            keep = keep[~loops[keep]]
        x, y = (a, b) if g.is_directed() else (lo, hi)
        dt = np.int32 if m < 2**31 else np.int64
        edges = np.stack([x[keep].astype(dt), y[keep].astype(dt)], axis=1)
    except Exception:  # noqa: BLE001  (anything unexpected: load the file again)
        return _declined("unexpected: " + repr(sys.exc_info()[1]))
    # ---- from here the graph is modified
    labels, index = lg.labels, lg.index
    if len(new_ids):
        g.add_vertices(len(new_ids))
        new_labels = [str(int(i)) for i in new_ids]
        g.vs[n:]["name"] = new_labels
        labels = lg.labels + new_labels
        index = _RangeIndex(m) if contiguous else {**lg.index, **{lab: n + j for j, lab in enumerate(new_labels)}}
    if len(edges):
        g.add_edges(edges)
    g["file_state"] = facts.sha1
    new = dataclasses.replace(lg, facts=facts, semantics=sem, labels=labels, index=index, lower_index=index,
                              load_info={"source": "append", "seconds": round(time.time() - t0, 1), "rows": int(k), "edges_added": int(len(edges))})
    if len(new_ids) and "node_table" in g.attributes():
        del g["node_table"]
        table = sidecar_node_table(path)
        if table is not None:
            attach_node_table(new, table)
    for kk, vv in list(_GRAPH_CACHE.items()):
        if vv.g is g:
            del _GRAPH_CACHE[kk]
    if os.environ.get("T2R_GRAPH_CACHE") == "1":
        _GRAPH_CACHE[(os.path.abspath(path), os.path.getmtime(path), json.dumps(override, sort_keys=True) if override else "")] = new
    return new


# --------------------------------------------------------------------------- binary cache on disk
# The text parse, id statistics and deduplication are the slow part of a load (5.5 minutes for 50M edges). The
# first load writes the built edge array, weights, labels, facts and semantics to T2R_CACHE_DIR; later loads in
# any process rebuild the igraph graph from that in seconds (10M edges) to under a minute (50M edges).
CACHE_FORMAT = 2   # 2: the file hash in the stored facts covers the whole file


def _cache_dir() -> str:
    d = os.environ.get("T2R_CACHE_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "graphs")
    os.makedirs(d, exist_ok=True)
    return d


def _disk_cache_enabled() -> bool:
    return os.environ.get("T2R_DISK_CACHE", "1") != "0"


def _cache_key(path: str, override: Optional[dict]) -> str:
    st = os.stat(path)
    h = hashlib.sha1(f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}|{json.dumps(override or {}, sort_keys=True)}|{CACHE_FORMAT}".encode()).hexdigest()
    return h[:20]


def _disk_cache_put(lg: "LoadedGraph", edges, weights, ids, contiguous: bool) -> None:
    if not _disk_cache_enabled() or getattr(lg, "_cache_key", None) is None:
        return
    try:
        base = os.path.join(_cache_dir(), lg._cache_key)
        arrays = {"edges": np.ascontiguousarray(edges)}
        if weights is not None:
            arrays["weights"] = np.asarray(weights, dtype=float)
        if ids is not None:
            arrays["ids"] = np.asarray(ids)
        np.savez(base + ".npz.tmp.npz", **arrays)
        os.replace(base + ".npz.tmp.npz", base + ".npz")
        meta = {"format": CACHE_FORMAT, "name": lg.name, "n": lg.g.vcount(), "directed": lg.g.is_directed(), "contiguous": contiguous,
                "facts": asdict(lg.facts), "semantics": asdict(lg.semantics), "path": os.path.abspath(lg.facts.path)}
        with open(base + ".json.tmp", "w") as f:
            json.dump(meta, f)
        os.replace(base + ".json.tmp", base + ".json")
    except Exception:  # noqa: BLE001  (a cache write failure must never fail a load)
        pass


def _disk_cache_get(name: str, path: str, override: Optional[dict]) -> Optional["LoadedGraph"]:
    if not _disk_cache_enabled():
        return None
    base = os.path.join(_cache_dir(), _cache_key(path, override))
    if not (os.path.exists(base + ".npz") and os.path.exists(base + ".json")):
        return None
    try:
        meta = json.load(open(base + ".json"))
        if meta.get("format") != CACHE_FORMAT:
            return None
        z = np.load(base + ".npz")
        edges = z["edges"]
        n = int(meta["n"])
        g = _graph_from_edges(n, edges, bool(meta["directed"]))
        facts = RawFacts(**meta["facts"])
        sem = Semantics(**meta["semantics"])
        if meta.get("contiguous"):
            labels = np.arange(n).astype(str).tolist()
            index: Any = _RangeIndex(n)
            lower = index
        else:
            labels = z["ids"].astype(str).tolist()
            index = {lab: i for i, lab in enumerate(labels)}
            lower = index if facts.ids_numeric else {l.lower(): i for l, i in index.items()}
        g.vs["name"] = labels
        if "weights" in z.files and sem.weighted:
            g.es["weight"] = z["weights"].tolist()
        g["file_state"] = facts.sha1
        return LoadedGraph(name=name, g=g, facts=facts, semantics=sem, labels=labels, index=index, lower_index=lower)
    except Exception:  # noqa: BLE001  (a damaged cache entry is ignored, the file is parsed again)
        return None


def cache_status(path: str, override: Optional[dict] = None) -> dict:
    """Whether a binary cache entry exists for this file (for the UI)."""
    base = os.path.join(_cache_dir(), _cache_key(path, override))
    ok = os.path.exists(base + ".npz") and os.path.exists(base + ".json")
    return {"cached": ok, "bytes": os.path.getsize(base + ".npz") if ok else 0}


# --------------------------------------------------------------------------- profile card
def profile_card(lg: LoadedGraph, with_inference: bool = True) -> dict[str, Any]:
    """Compact, LLM-facing description of the graph. Cheap statistics only."""
    g = lg.g
    deg = np.array(g.degree())
    card: dict[str, Any] = {
        "name": lg.name,
        "file": os.path.basename(lg.facts.path),
        "n_nodes": g.vcount(),
        "n_edges": g.ecount(),
        "density": round(2 * g.ecount() / (g.vcount() * (g.vcount() - 1)) if not g.is_directed() else g.ecount() / (g.vcount() * (g.vcount() - 1)), 6),
        "degree": {"min": int(deg.min()), "median": float(np.median(deg)), "mean": round(float(deg.mean()), 2), "max": int(deg.max())},
        "node_id_type": "integer" if lg.facts.ids_numeric else "string label",
        "sample_node_ids": lg.labels[:5] + (lg.labels[-3:] if len(lg.labels) > 8 else []),
    }
    comps = g.connected_components(mode="weak")
    card["n_components_weak"] = len(comps)
    card["largest_component_fraction"] = round(max(comps.sizes()) / g.vcount(), 4)
    if g.is_directed():
        scc = g.connected_components(mode="strong")
        card["n_components_strong"] = len(scc)
        card["largest_scc_fraction"] = round(max(scc.sizes()) / g.vcount(), 4)
        card["reciprocity"] = round(g.reciprocity(), 4)
    if g.ecount() and g.ecount() < 5_000_000:
        card["is_bipartite"] = bool(g.is_bipartite())
    card["size_class"] = "small" if g.ecount() < 1_000_000 else ("large" if g.ecount() < 20_000_000 else "very large")
    if lg.semantics.multigraph:
        card["n_edges_distinct_pairs"] = len(set((min(e.source, e.target), max(e.source, e.target)) if not g.is_directed() else (e.source, e.target) for e in g.es))
    if lg.facts.header:
        card["columns"] = {"header": lg.facts.header, "source_col": lg.facts.columns_used[0], "target_col": lg.facts.columns_used[1], "weight_col": lg.facts.columns_used[2]}
    elif lg.facts.row_index_column:
        card["columns"] = {"note": "first column is a row index; edges read from columns 1 and 2"}
    if "node_table" in g.attributes():
        t = g["node_table"]
        card["node_attributes"] = {"file": t["file"], "rows_matched": t["rows_matched"], "nodes_without_row": t["nodes_without_row"], "attributes": t["attributes"]}
    if with_inference:
        s = lg.semantics
        card["semantics"] = {
            "directed": s.directed, "weighted": s.weighted, "weight_semantics": s.weight_semantics,
            "multigraph": s.multigraph, "labelled": s.labelled,
            "confidence": s.confidence, "evidence": s.evidence,
            "needs_clarification": s.needs_clarification,
        }
    return card


def raw_card(facts: RawFacts) -> dict[str, Any]:
    """What a system without an interpretation stage sees: file facts only."""
    return {
        "file": os.path.basename(facts.path), "n_lines": facts.n_lines, "header": facts.header,
        "n_columns": facts.n_columns, "sample_rows": facts.sample_rows,
        "n_distinct_ids": facts.n_distinct_ids, "ids_numeric": facts.ids_numeric,
        "n_rows": facts.n_rows, "n_distinct_directed_pairs": facts.n_rows_dedup_directed, "n_distinct_undirected_pairs": facts.n_rows_dedup_undirected,
        "reciprocity_of_rows": round(facts.reciprocity, 4), "weight_column_numeric": facts.weight_column_numeric,
    }
