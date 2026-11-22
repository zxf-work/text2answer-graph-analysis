"""Build the node table for the Pokec graph from SNAP's soc-pokec-profiles.txt.

Usage: python prep_pokec.py <soc-pokec-profiles.txt> <soc-pokec-relationships.txt>
Writes <relationships stem>.nodes.tsv next to the edge file, where load_graph finds it.
Columns kept (SNAP readme order): 0 user_id, 1 public, 2 completion_percentage, 3 gender, 4 region, 7 AGE.
AGE 0 means "not given" in the source and is written as missing.
"""
import os
import sys

import pandas as pd

src, edges = sys.argv[1], sys.argv[2]
df = pd.read_csv(src, sep="\t", header=None, usecols=[0, 1, 2, 3, 4, 7], dtype=str, quoting=3, keep_default_na=False, on_bad_lines="skip")
df.columns = ["id", "public", "completion_percentage", "gender", "region", "age"]
df.loc[df["age"].isin(["0", "null", ""]), "age"] = ""
df["gender"] = df["gender"].map({"1": "male", "0": "female"}).fillna("")
df["region"] = df["region"].str.strip().str.replace("\t", " ")
out = os.path.splitext(edges)[0] + ".nodes.tsv"
df.to_csv(out, sep="\t", index=False)
print(f"wrote {out}: {len(df)} rows; regions {df['region'].nunique()}; age given {int((df['age'] != '').sum())}")
print(df.head(3).to_string())
