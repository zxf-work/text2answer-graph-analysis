"""Sessions written by a model that is told nothing about GraphAudit (gap G6: workload independence).

The writer sees only BRIEF and a description of one dataset: no operator catalogue, no session rules, none of our
sessions, no mention of reuse, traps or stale answers. Its questions are kept word for word. Gold answers are added
afterwards (see docs/sigmod27-demo-plan.md, G6/G7).

  python bench/sessions/write_sessions.py <out_dir> --model claude-opus-5-5 [--sessions 10]
  T2R_BASE_URL=... python bench/sessions/write_sessions.py <out_dir> --model qwen3:14b
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from t2r.llm import LLM, parse_json  # noqa: E402

BRIEF = """You are helping to collect realistic examples of how analysts question a network dataset in conversation.

Below is a description of one dataset. Imagine {n} different people who work with it, each with a different job and a
different goal (for example marketing, trust and safety, product, research, infrastructure, journalism). For each
person, write the conversation they would have with an assistant that can compute anything about the network: {lo} to {hi}
questions, in the order they would ask them.

Write the way people really ask:
- later questions build on earlier ones ("of those", "and without them?", "the same for women", "show 20 instead");
- people change their mind, narrow down, compare groups, and come back to something asked before;
- sometimes the data is updated during the day (new rows arrive in the file); if it fits the person's job, say so in a
  question ("the file was just refreshed - ...") in at most two of the conversations;
- every question must have one definite answer that can be computed from the files described: a number, a list of
  nodes, a ranking, a table of groups. No opinions, no "why", no plots, no predictions.

Dataset:
{dataset}

Reply with only JSON:
{{"sessions": [{{"persona": "<job and goal in one line>", "questions": ["...", "..."]}}, ...]}}"""

DATASETS = {
    "pokec": """Pokec, a social network (Slovakia). Edge file: one row per friendship, "user_a<TAB>user_b", directed: user_a lists
user_b as a friend (not always returned). 1,632,803 users, 30,622,564 friendships.
Node table, one row per user: id, public (1 if the profile is public), completion_percentage (0-100), gender ("male",
"female" or empty), region (text such as "bratislavsky kraj, bratislava - petrzalka", 187 values), age (years; 0 = not given).""",
    "livejournal": """LiveJournal, a blogging community. Edge file: one row per friendship declaration, "user_a<TAB>user_b", directed:
user_a declared user_b a friend. 4,847,571 users, 68,993,773 declarations. There is no table of user attributes.""",
    "twitch": """Twitch gamers, a streaming platform. Edge file: one row per pair of users who follow each other, "user_a<TAB>user_b";
each pair appears once and the relationship is mutual (undirected). 168,114 users, 6,797,557 mutual-follow pairs.
Node table, one row per user: id, views (total channel views), mature (1 if the channel is marked for mature audiences),
life_time (days between account creation and last update), created_at and updated_at (dates, YYYY-MM-DD), dead_account
(1 if inactive), language (code such as EN, DE, FR, ES, RU; 21 values), affiliate (1 if the user is in the affiliate programme).""",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--model", required=True)
    ap.add_argument("--sessions", type=int, default=10); ap.add_argument("--graphs", default="pokec,livejournal,twitch")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    llm = LLM(a.model)
    for g in a.graphs.split(","):
        if os.path.exists(os.path.join(a.out, f"{g}.json")):
            continue
        prompt = BRIEF.format(n=a.sessions, lo=6, hi=10, dataset=DATASETS[g])
        r = llm.chat("", prompt, max_tokens=16000)
        with open(os.path.join(a.out, f"{g}.raw.txt"), "w") as f:
            f.write(r.text)
        d = parse_json(r.text)
        d.update(graph=g, writer=a.model, brief=prompt)
        with open(os.path.join(a.out, f"{g}.json"), "w") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        print(g, len(d["sessions"]), "sessions,", sum(len(s["questions"]) for s in d["sessions"]), "questions; cost", round(llm.usage.cost_usd, 4))


if __name__ == "__main__":
    main()
