"""One-off: profile card for the 50M graph (used by the replayed scale scene)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from t2r.graphs import load_graph, profile_card
path = sys.argv[1]
lg = load_graph("ba_50m", path, "Synthetic undirected preferential-attachment network, 10M nodes, 50M edges, each edge listed once", override={"directed": False, "weighted": False})
json.dump(profile_card(lg), open(os.path.join(HERE, "scenes", "card_ba_50m.json"), "w"), indent=1, default=str)
print("card written")
