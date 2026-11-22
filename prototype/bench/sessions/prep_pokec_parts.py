"""Attributed subgraphs of Pokec for the session experiments: one per kraj (the part of `region` before the comma).

Usage: python bench/sessions/prep_pokec_parts.py <soc-pokec-relationships.txt> <out dir> [n parts, default 3]
Each part is the subgraph induced by the users of one kraj: <out>/pokec_<kraj>.txt (directed edge list) and
<out>/pokec_<kraj>.nodes.tsv with real profile attributes (district, gender, age, public, completion_percentage).
"""
import os
import sys

import pandas as pd

edges, out = sys.argv[1], sys.argv[2]
n_parts = int(sys.argv[3]) if len(sys.argv) > 3 else 3
os.makedirs(out, exist_ok=True)
nodes = pd.read_csv(os.path.splitext(edges)[0] + ".nodes.tsv", sep="\t", dtype=str, keep_default_na=False)
nodes["kraj"] = nodes["region"].str.split(",").str[0].str.strip()
nodes["district"] = nodes["region"].str.split(",", n=1).str[1].fillna("").str.strip()
counts = nodes[nodes["kraj"].str.endswith(" kraj")]["kraj"].value_counts()
print(counts.to_string())
picked = list(counts.index[-n_parts:])           # the smallest ones: quick to run many scenarios on
e = pd.read_csv(edges, sep="\t", header=None, names=["u", "v"], dtype=str)
for kraj in picked:
    part = nodes[nodes["kraj"] == kraj]
    ids = set(part["id"])
    sub = e[e["u"].isin(ids) & e["v"].isin(ids)]
    stem = os.path.join(out, "pokec_" + kraj.replace(" kraj", "").replace(" ", "_"))
    sub.to_csv(stem + ".txt", sep="\t", header=False, index=False)
    part[["id", "district", "gender", "age", "public", "completion_percentage"]].to_csv(stem + ".nodes.tsv", sep="\t", index=False)
    print(f"{stem}.txt: {len(part)} users, {len(sub)} edges, {part['district'].nunique()} districts")
