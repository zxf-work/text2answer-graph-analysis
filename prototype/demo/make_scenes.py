"""Record the guided-demo scenes: run each scene's question through the named executor and save the result,
the profile card and a note to demo/scenes/<nn>_<name>.json. The UI replays these without a model call.

Usage: python3 demo/make_scenes.py [--model claude-opus-5-5] [--only trust_most_trusted,...]
The 50M-edge scene is imported from an earlier experiment run (prototype/results_scale/raw) because recomputing it
takes 20 minutes; pass --scale-raw <dir> to point at those files.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ["T2R_GRAPH_CACHE"] = "1"
from server import _plan_graph, _profile  # noqa: E402
from t2r.llm import LLM  # noqa: E402
from t2r.systems import SYSTEMS  # noqa: E402

D = os.path.join(ROOT, "bench", "data_hard")
SCENES = [
    {"name": "trust_most_trusted", "system": "full", "dataset": "trust", "path": f"{D}/trust.csv",
     "question": "Who is the most trusted person?",
     "title": "1. See the plan, not just the answer",
     "subtitle": "No description given. The profile card says the file is directed with integer strengths; the plan uses in-degree; the verifier checks every step.",
     "note": "Scene 1 of 4: every decision that produced the number is on screen: profile card, interpretation, typed plan, checks."},
    {"name": "trust_trusts_most_full", "system": "full", "dataset": "trust", "path": f"{D}/trust.csv",
     "question": "Who trusts the most people?",
     "title": "2a. Direction matters: typed plan",
     "subtitle": "The same graph, the opposite direction. Compare with the tool agent on the same question (switch executor tabs).",
     "note": "Scene 2 of 4: 'trusts' means outgoing edges. The plan states mode=out and the verifier confirms the question and the plan agree."},
    {"name": "trust_trusts_most_flat", "system": "flat", "dataset": "trust", "path": f"{D}/trust.csv",
     "question": "Who trusts the most people?",
     "title": "2b. Direction matters: tool agent",
     "subtitle": "The conventional agent answers the same question. There is no plan to inspect and no check between the question and what was computed.",
     "note": "Scene 2 of 4 (contrast): a transcript instead of a plan, and nothing that verifies the direction."},
    {"name": "emails_pairs", "system": "full", "dataset": "emails", "path": f"{D}/emails.csv",
     "question": "How many pairs of people have exchanged email?",
     "title": "2c. Repeated rows: pairs or messages?",
     "subtitle": "An email log with one row per message. 'Pairs' means distinct sender-recipient pairs, not rows; the multigraph check watches for the confusion.",
     "note": "Scene 2 of 4: the profile card marks the file as a multigraph and the plan counts distinct pairs."},
    {"name": "roads_shortest", "system": "full", "dataset": "roads", "path": f"{D}/roads.csv",
     "question": "What is the shortest route from J0 to J299?",
     "title": "3. Ambiguity gets a clarification or both readings",
     "subtitle": "Weights are kilometres. 'Shortest' can mean fewest hops or least distance; the system either asks or computes both and says which is which.",
     "note": "Scene 3 of 4: ambiguous questions are not guessed. Look for a clarification or variants under the answer."},
]
SCALE = [
    {"name": "scale_betweenness_full", "system": "full", "qid": "X15", "title": "4a. 50M edges: the cost model takes over",
     "subtitle": "The planner asked for 500 betweenness pivots; the cost model cut it to 125 to fit the budget; the run finished in 20 minutes.",
     "note": "Scene 4 of 4: recorded on a 10M-node, 50M-edge graph. See the cost model decision under Cost."},
    {"name": "scale_betweenness_flat", "system": "flat", "qid": "X15", "title": "4b. 50M edges: the tool agent fabricates",
     "subtitle": "One model call, no tool call, and an explanation that describes tool rejections which never happened.",
     "note": "Scene 4 of 4 (contrast): the transcript is empty because no tool was called; the explanation was invented."},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("T2R_MODEL", "claude-opus-5-5"))
    ap.add_argument("--only", default="")
    ap.add_argument("--scale-raw", default=os.path.join(ROOT, "results_scale", "raw"))
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    out_dir = os.path.join(HERE, "scenes"); os.makedirs(out_dir, exist_ok=True)
    for i, sc in enumerate(SCENES, 1):
        if only and sc["name"] not in only:
            continue
        print("scene", sc["name"], flush=True)
        card = _profile(sc["path"], sc["dataset"], "")
        llm = LLM(model=a.model)
        res = SYSTEMS[sc["system"]](sc["name"], sc["path"], sc["dataset"], None, sc["question"], llm=llm)
        d = json.loads(json.dumps(asdict(res), default=str))
        d["plan_graph"] = _plan_graph(d.get("plan")) if isinstance(d.get("plan"), dict) else None
        d["question"] = sc["question"]; d["dataset"] = sc["dataset"]; d["model"] = llm.model
        json.dump({"title": sc["title"], "subtitle": sc["subtitle"], "note": sc["note"], "card": card, "result": d},
                  open(os.path.join(out_dir, f"{i:02d}_{sc['name']}.json"), "w"), indent=1, default=str)
        print("  ->", str(d.get("answer"))[:80], "| error", d.get("error"), flush=True)
    card_big = os.path.join(out_dir, "card_ba_50m.json")
    for j, sc in enumerate(SCALE, len(SCENES) + 1):
        if only and sc["name"] not in only:
            continue
        src = os.path.join(a.scale_raw, sc["system"], f"{sc['qid']}.json")
        if not os.path.exists(src):
            print("skip", sc["name"], "(no raw result at", src + ")"); continue
        d = json.load(open(src))
        d["plan_graph"] = _plan_graph(d.get("plan")) if isinstance(d.get("plan"), dict) else None
        d["question"] = "Which 10 nodes have the highest betweenness centrality? An approximation is fine."
        d["dataset"] = "ba_50m"; d["model"] = "claude-opus-5-5"
        card = json.load(open(card_big)) if os.path.exists(card_big) else None
        json.dump({"title": sc["title"], "subtitle": sc["subtitle"], "note": sc["note"], "card": card, "result": d,
                   "description": "Synthetic undirected preferential-attachment network, 10M nodes, 50M edges, each edge listed once"},
                  open(os.path.join(out_dir, f"{j:02d}_{sc['name']}.json"), "w"), indent=1, default=str)
        print("imported", sc["name"])


if __name__ == "__main__":
    main()
