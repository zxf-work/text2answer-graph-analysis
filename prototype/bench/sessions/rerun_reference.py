"""Model-written sessions: run the reference's own scripts again for the stable differences, to get the variants each
script prints next to its main answer (the runs stored the main answer only). No model is called.

  python bench/sessions/rerun_reference.py runs/written-runs/stable_11.jsonl --snap $T2A_DATA/snap --out runs/written-runs/stable_11.variants.jsonl [--jobs 4]

For each row: the main answer as recomputed, every variant with its label, and which of them our answers match under
the loose test of compare_written.py. A match with a variant says the two systems computed the same thing under a
convention the reference itself listed as an alternative; it does not say which convention the user meant.
Sessions in which the data file was changed before the turn are skipped (the script would run on the wrong file).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import tempfile

from compare_written import agree


def run(row, snap, timeout):
    live = tempfile.mkdtemp(prefix="t2a-rerun-")
    for f in os.listdir(snap):
        os.symlink(os.path.join(snap, f), os.path.join(live, f))
    script = re.sub(r"/tmp/t2a-wr-\w+/work/s\d+/live/", live + "/", row["ref_script"])
    path = os.path.join(live, "_script.py")
    open(path, "w").write(script)
    out = {"key": row["key"], "q": row["q"], "ref_answer_stored": row["ref_answer"]}
    try:
        p = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=timeout, cwd=live)
        doc = None
        for line in reversed(p.stdout.strip().splitlines()):
            try:
                doc = json.loads(line); break
            except ValueError:
                continue
        if doc is None:
            out["error"] = (p.stderr or p.stdout)[-400:]
            return out
    except subprocess.TimeoutExpired:
        out["error"] = "timeout"
        return out
    cands = [("main", doc.get("answer"))] + [(str(v.get("label")), v.get("answer")) for v in doc.get("variants") or [] if isinstance(v, dict)]
    out["main_reproduced"] = agree(doc.get("answer"), row["ref_answer"])
    out["measure"] = (doc.get("assumptions") or {}).get("measure")
    out["candidates"] = [{"label": l, "answer": json.loads(json.dumps(a, default=str)[:3000]) if len(json.dumps(a, default=str)) <= 3000 else json.dumps(a, default=str)[:3000]} for l, a in cands]
    out["ours_match"] = {rep: [l for l, a in cands if a is not None and agree(o["answer"], a)] for rep, o in row["ours"].items()}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stable"); ap.add_argument("--snap", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=4); ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.stable)]
    todo = [r for r in rows if r.get("ref_script") and not r.get("event_before")]
    print(len(rows), "rows,", len(todo), "to run", flush=True)
    with open(a.out, "w") as f, cf.ThreadPoolExecutor(a.jobs) as ex:
        for res in ex.map(lambda r: run(r, a.snap, a.timeout), todo):
            f.write(json.dumps(res, default=str) + "\n"); f.flush()
            print("/".join(map(str, res["key"])), res.get("error") or res.get("ours_match"), flush=True)


if __name__ == "__main__":
    main()
