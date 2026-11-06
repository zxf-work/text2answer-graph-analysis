"""One-off: visualisation data for the 50M-edge scenes (needs the big file; ~6 minutes)."""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
from t2r.graphs import load_graph
from viz import make_viz
lg = load_graph("ba_50m", sys.argv[1], "", override={"directed": False, "weighted": False})
for f in sorted(glob.glob(os.path.join(HERE, "scenes", "0[6-9]_scale_*.json"))):
    sc = json.load(open(f)); sc["result"]["viz"] = make_viz(lg, sc["result"].get("answer"))
    if sc.get("card"):
        sc["card"]["viz"] = make_viz(lg)
    json.dump(sc, open(f, "w"), indent=1, default=str); print("viz ->", f, sc["result"]["viz"]["n_shown"], sc["result"]["viz"]["highlighted"], flush=True)
