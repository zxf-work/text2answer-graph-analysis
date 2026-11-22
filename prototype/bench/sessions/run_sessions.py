"""E2: run the session workload with a model and score every turn. Calls a model: run on a server.

Usage: python bench/sessions/run_sessions.py <out dir> --model M --variant V <attributed graph>...
Variants of the system:
  full        session state, lineage reuse, scope rule (asks on an unsettled group restriction)
  no_rule     as full, but the planner's own scope reading is taken without asking
  no_reuse    as full, but nothing is taken from the result store
  no_context  every turn is planned and run as a fresh single question (no state, no store)
A simulated user answers a two-contract question with the reading annotated in the workload.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ["T2R_GRAPH_CACHE"] = "1"
from reuse_fault import run as run_plan  # noqa: E402
from workload import alternative_golds, gold_value, matches, sessions  # noqa: E402
from t2r.graphs import load_graph, profile_card  # noqa: E402
from t2r.ir import validate  # noqa: E402
from t2r.llm import LLM  # noqa: E402
from t2r.session import Session  # noqa: E402

DESC = {"trust": "Who trusts whom: each row is truster, trustee and a trust strength from 1 to 10.",
        "follows": "A follower network: each row is an account and an account it follows.",
        "citations": "A citation network: each row is a citing paper and the paper it cites.",
        "roads": "A road network: each row is a road between two junctions with its length in km; roads are two-way.",
        "emails": "An email log: each row is one email with sender, recipient and timestamp.",
        "pokec": "Part of the Pokec social network (one region of Slovakia): each row is a directed friendship from the first user to the second."}


def specs(attributed):
    hard = json.load(open(os.path.join(ROOT, "bench", "datasets_hard.json")))
    out = []
    for name in ("trust", "follows", "citations", "roads", "emails"):
        d = hard[name]
        out.append({"name": name, "path": os.path.join(ROOT, d["path"]), "directed": d["directed"], "weighted": d.get("weighted", False), "description": DESC[name]})
    for p in attributed:
        lg = load_graph(os.path.splitext(os.path.basename(p))[0], p, DESC["pokec"])
        a = profile_card(lg)["node_attributes"]["attributes"]["district"]
        out.append({"name": lg.name, "path": p, "directed": True, "weighted": False, "attr": "district", "values": [t["value"] for t in a["top_values"][:3]], "description": DESC["pokec"]})
    return out


def summarise(rows, llm, variant, model, out):
    n = len(rows) or 1
    amb = [r for r in rows if r["ambiguous"]]; fol = [r for r in rows if r["kind"] != "new"]
    steps = sum(r["steps_reused"] + r["steps_executed"] for r in rows) or 1
    S = {"variant": variant, "model": model, "turns": len(rows), "sessions": len({r["session"] for r in rows}),
         "answer_accuracy": round(sum(r["correct"] for r in rows) / n, 4),
         "follow_up_accuracy": round(sum(r["correct"] for r in fol) / (len(fol) or 1), 4), "follow_up_turns": len(fol),
         "ambiguous_turns": len(amb), "ambiguous_handled": sum(r["decision_ok"] for r in amb), "ambiguous_correct": sum(r["correct"] for r in amb),
         "silent_other_reading": sum(r["other_reading"] and not r["asked"] for r in amb),
         "needless_questions": sum(r["asked"] for r in rows if not r["ambiguous"]),
         "errors": sum(bool(r["error"]) for r in rows),
         "share_steps_reused": round(sum(r["steps_reused"] for r in rows) / steps, 4),
         "execute_seconds": round(sum(r["execute_seconds"] for r in rows), 2), "seconds_saved": round(sum(r["seconds_saved"] for r in rows), 2),
         "wall_seconds": round(sum(r["wall_seconds"] for r in rows), 1), "llm_calls": llm.usage.calls, "tokens_in": llm.usage.input_tokens,
         "tokens_out": llm.usage.output_tokens, "cost_usd": round(llm.usage.cost_usd, 4),
         "wrong_turns": [f"{r['session']} t{r['turn']} ({r['kind']})" for r in rows if not r["correct"]]}
    json.dump(S, open(os.path.join(out, "summary.json"), "w"), indent=1)
    print(json.dumps(S, indent=1))
    return S


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("graphs", nargs="*")
    ap.add_argument("--model", default="claude-haiku-5-5"); ap.add_argument("--variant", default="full"); ap.add_argument("--only", default="")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    llm = LLM(model=a.model)
    rows = []
    log = open(os.path.join(a.out, "turns.jsonl"), "w")
    for spec in specs(a.graphs):
        gold_lg = load_graph(spec["name"], spec["path"], spec["description"], override={"directed": spec["directed"], "weighted": spec["weighted"]})
        for sess in sessions(spec):
            if a.only and a.only not in sess["id"]:
                continue
            new = lambda: Session(spec["path"], name=spec["name"], description=spec["description"],  # noqa: E731
                                  on_ambiguity="planner" if a.variant == "no_rule" else "ask", reuse=a.variant != "no_reuse")
            s = new()
            for i, t in enumerate(sess["turns"], 1):
                if a.variant == "no_context":
                    s = new()
                golds = {}
                for reading, plan in t["gold"].items():
                    assert not validate(plan, gold_lg, 1e13), (sess["id"], i, validate(plan, gold_lg, 1e13))
                    vals, _ = run_plan(plan, gold_lg, 1, None, {})
                    golds[reading] = gold_value(t["expect"], vals[plan.steps[-1].id], t)
                ambiguous = "user" in t
                want = golds[t["user"]] if ambiguous else golds["-"]
                t0 = time.time()
                r = s.ask(t["q"], llm)
                asked = r["outcome"] == "clarify"
                asked_contracts = asked and bool(r.get("contracts"))
                if asked_contracts:
                    idx = next((k for k, c in enumerate(r["contracts"]) if c["reading"] == t.get("user", "B")), 0)
                    r = s.choose(idx)
                wall = time.time() - t0
                ok = any(matches(t["expect"], w, r.get("answer")) for w in [want] + alternative_golds(t, gold_lg, spec["path"]))
                other = [k for k in golds if ambiguous and k != t["user"]]
                row = {"session": sess["id"], "graph": spec["name"], "turn": i, "q": t["q"], "kind": t["kind"], "expect": t["expect"], "variant": a.variant, "model": a.model,
                       "ambiguous": ambiguous, "carried": bool(t.get("carried")), "asked": asked, "asked_contracts": asked_contracts,
                       # an ambiguous turn is handled correctly if the system asks, or if the user already chose earlier in the session
                       "decision_ok": (asked_contracts or bool(t.get("carried")) and r.get("reading") == t["user"]) if ambiguous else not asked,
                       "correct": ok, "other_reading": bool(other) and matches(t["expect"], golds[other[0]], r.get("answer")) and not ok,
                       "outcome": r.get("outcome"), "reading": r.get("reading"), "intent": r.get("intent"), "error": r.get("error"),
                       "steps_reused": r.get("steps_reused") or 0, "steps_executed": r.get("steps_executed") or 0, "execute_seconds": r.get("execute_seconds") or 0,
                       "seconds_saved": r.get("seconds_saved") or 0, "wall_seconds": round(wall, 3), "llm_calls": r.get("llm_calls"), "tokens_in": r.get("tokens_in"),
                       "tokens_out": r.get("tokens_out"), "cost_usd": r.get("cost_usd"),
                       "verifier_flags": [f["check"] for f in r.get("findings") or [] if not f["ok"]], "rule_flags": [f["check"] for f in r.get("reuse_findings") or [] if not f["ok"]]}
                rows.append(row)
                log.write(json.dumps({**row, "answer": r.get("answer"), "gold": want, "plan": r.get("plan"), "clarification": r.get("clarification")}, default=str) + "\n"); log.flush()
                print(f"{sess['id']:<28} t{i} {t['kind']:<8} {'OK ' if ok else 'BAD'} {r.get('outcome'):<14} reused {row['steps_reused']}/{row['steps_reused'] + row['steps_executed']}"
                      f"{' asked' if asked else ''}{' OTHER-READING' if row['other_reading'] else ''} {r.get('error') or ''}"[:230], flush=True)
    summarise(rows, llm, a.variant, a.model, a.out)


if __name__ == "__main__":
    main()
