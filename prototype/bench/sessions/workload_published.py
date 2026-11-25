"""Task types of published graph-reasoning benchmarks, restated on our graphs (plan G6, source 2).

  python bench/sessions/workload_published.py runs/written/published-tasks

Writes <out>/<graph>.json in the format of write_sessions.py, so run_written.py, compare_written.py and
judge_written.py run them unchanged. One session per source, every question stands alone (the benchmarks are
single-shot). The task types were fixed by other people, not by us and not for this catalogue:

  GraphArena (Tang et al., ICLR 2025): 4 polynomial and 6 NP-complete tasks.
  NLGraph (Wang et al., NeurIPS 2023): 8 tasks.
  The benchmarks GraphTeam (Li et al., arXiv 2410.18032) is evaluated on: GraphInstruct's 21 tasks, Talk like a Graph
  and GraphWiz, less the types already listed above. LLM4DyG (links with time stamps) and GNN-AutoGL (writing a
  training pipeline) have no counterpart on these graphs and are left out.

What we chose: the wording, the node ids, and the size of the subgraph for the tasks the benchmarks pose on small
graphs (the NP-hard ones cannot be posed on millions of edges). Ids were picked by degree only (see IDS), before any
system saw a question.
"""
from __future__ import annotations

import json
import os
import sys

# a, b: two users of moderate degree; c, d: two users with few links (their ego networks are small); e: a third user
IDS = {"twitch": dict(a=17, b=24, c=13, d=12, e=50),            # degrees 92, 52, 6, 7, 192
       "pokec": dict(a=10, b=21, c=3, d=8, e=47),                 # out/in 66/68, 34/38, 3/3, 4/4, 89/92
       "livejournal": dict(a=10, b=20, c=60, d=35, e=50)}         # out/in 95/82, 75/72, 4/2, 9/5, 105/94

W = {"twitch": dict(link="mutual follow", links="mutual follows", deg="number of mutual follows", und="", nb="users who follow each other with",
                    top="the {k} users with the most mutual follows (ties broken by the lower user id)", directed=False,
                    sides="a mature user and a non-mature user", order="from the account created earlier to the account created later (ties: from the lower id to the higher id)",
                    tri="the largest total views"),
     "pokec": dict(link="friendship", links="friendships", deg="in-degree (the number of users who list them as a friend)", und=", ignoring the direction of friendships", nb="users linked in either direction to",
                   top="the {k} users with the highest in-degree (listed as a friend by the most users; ties broken by the lower user id)", directed=True,
                   sides="a male user and a female user", order="in the direction it is declared", tri="the largest total age"),
     "livejournal": dict(link="friend declaration", links="friend declarations", deg="in-degree (the number of users who declared them a friend)", und=", ignoring the direction of declarations", nb="users linked in either direction to",
                         top="the {k} users with the highest in-degree (declared a friend by the most users; ties broken by the lower user id)", directed=True,
                         sides="one of the 25 highest-ranked of those users and one of the other 25", order="in the direction it is declared", tri="the largest total in-degree")}


def sessions(graph):
    w, i = W[graph], IDS[graph]
    d = w["directed"]
    top50, top1000, top12, top8 = (w["top"].format(k=k) for k in (50, 1000, 12, 8))
    sub50 = f"Take {top50} and the {w['links']} among them"
    ego = lambda x: f"user {x} together with the {w['nb']} {x}, and the {w['links']} among all of them"   # noqa: E731
    arena = [
        f"Which users are linked to both user {i['a']} and user {i['b']}{w['und']}? Give how many there are and list them.",
        f"What is the length of the shortest path from user {i['a']} to user {i['b']}" + (", following the direction of each link?" if d else "?"),
        "How many " + ("weakly " if d else "") + "connected components does the network have, and how many users are in the largest one?",
        f"Take {top1000} and the {w['links']} among them{w['und']}. What is the diameter of the largest connected component of that subgraph?",
        f"{sub50}{w['und']}. What is the size of the largest clique in that subgraph, and which users form it?",
        f"{sub50}{w['und']}. What is the size of the largest set of those users in which no two are linked?",
        f"{sub50}{w['und']}. What is the smallest number of those users needed so that every link among the 50 has at least one end in the chosen set?",
        f"Take two small subgraphs{w['und']}: {ego(i['c'])}; and {ego(i['d'])}. How many nodes does the largest common induced subgraph of the two have?",
        f"Take two small subgraphs{w['und']}: {ego(i['c'])}; and {ego(i['d'])}. What is the graph edit distance between them (nodes carry no labels; adding or deleting a node or a link costs 1)?",
        f"Take {top8}. The cost of going from one of them to another is the length of the shortest path between the two in the whole network{w['und']}. What is the cost of the cheapest round trip that visits all 8 and returns to its start?",
    ]
    nlgraph = [
        f"Is there a path from user {i['a']} to user {i['e']}" + (" that follows the direction of each link?" if d else "?"),
        f"Take {ego(i['c'])}{w['und']}. Does this subgraph contain a cycle?",
        f"{sub50}, each {w['link']} pointing {w['order']}. Can the 50 users be put in an order in which every link points from an earlier user to a later one? If yes, give such an order; if not, say what prevents it.",
        f"Give one shortest path from user {i['a']} to user {i['b']}" + (", following the direction of each link" if d else "") + ", as the sequence of users on it.",
        f"Take {top1000} and the {w['links']} among them, each link with capacity 1" + (" in its own direction" if d else " in both directions") + ". What is the maximum flow from the highest-ranked of those users to the lowest-ranked one?",
        f"{sub50}{w['und']}. Keep only the links that join {w['sides']}. What is the largest number of those links that can be chosen so that no user is in two chosen links?",
        f"Take {top12} and the {w['links']} among them{w['und']}. Is there a path that visits each of the 12 users exactly once? If yes, give one.",
        f"Give every user a starting value equal to their number of links{w['und'].replace(', ignoring', ' (ignoring') + (')' if d else '')}. In each round every user's value is replaced by the sum of the values of the users they are linked to. After 2 rounds, what is the value of user {i['a']}?",
    ]
    team = [
        (f"What are the in-degree and the out-degree of user {i['a']}?" if d else f"What is the degree of user {i['a']}?"),
        (f"Which users does user {i['c']} list as friends?" if d else f"Which users are linked to user {i['c']}?"),
        (f"Does user {i['a']} list user {i['b']} as a friend, and does {i['b']} list {i['a']}?" if d else f"Is there a link between user {i['a']} and user {i['b']}?"),
        f"How many users and how many {w['links']} does the network have?",
        "Which user has the highest PageRank (damping factor 0.85), and what is that user's PageRank value?",
        f"What is the clustering coefficient of user {i['a']}{w['und']}?",
        f"What is the Jaccard coefficient of the neighbour sets of user {i['a']} and user {i['b']}{w['und']}?",
        f"Starting a breadth-first search at user {i['a']}" + (" along the direction of links" if d else "") + ", how many users are reached at depth 1, at depth 2 and at depth 3?",
        f"{sub50}{w['und']}. Run a depth-first search from the highest-ranked of them, always moving to the unvisited linked user with the lowest id. What are the first 10 users visited, in order?",
        f"Take {ego(i['c'])}{w['und']}. Is this subgraph bipartite?",
        f"How many links does a spanning forest of the whole network have{w['und']}?",
        f"{sub50}{w['und']}. Does that subgraph have an Euler circuit, an Euler path only, or neither?",
        f"{sub50}{w['und']}. Among the triangles of that subgraph, which three users form the triangle with {w['tri']}, and what is that total?",
        f"{sub50}{w['und']}. How many sets of 4 of those users form a square with no diagonal (a cycle of 4 links and no other link among the 4)?",
        f"How many triangles does the whole network contain{w['und']}?",
    ]
    if d:
        team.insert(3, f"Which users list user {i['c']} as a friend?")
    return [{"persona": "someone checking the tool against the task list of the GraphArena benchmark", "source": "GraphArena", "questions": arena},
            {"persona": "someone checking the tool against the task list of the NLGraph benchmark", "source": "NLGraph", "questions": nlgraph},
            {"persona": "someone checking the tool against the task lists of the benchmarks GraphTeam is evaluated on", "source": "GraphTeam benchmarks (GraphInstruct, Talk like a Graph, GraphWiz)", "questions": team}]


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for g in W:
        doc = {"writer": "published-tasks", "graph": g, "sessions": sessions(g)}
        json.dump(doc, open(os.path.join(out, f"{g}.json"), "w"), indent=1)
        print(g, [len(s["questions"]) for s in doc["sessions"]])


if __name__ == "__main__":
    main()
