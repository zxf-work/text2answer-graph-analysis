"""Build a single-file static preview of the demo UI with the recorded scenes inlined (demo/dist/index.html).

The static page replays scenes only: no live questions, no uploads. Useful for sharing a look at the UI without the server.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
from server import _datasets, _scenes  # noqa: E402

html = open(os.path.join(HERE, "static", "index.html")).read()
css = open(os.path.join(HERE, "static", "style.css")).read()
js = open(os.path.join(HERE, "static", "app.js")).read()
scenes = _scenes()
cards = {s["result"]["dataset"]: s.get("card") for s in scenes if s.get("card")}
datasets = []
for d in _datasets():
    if d["name"] in cards:
        datasets.append({**d, "path": d["path"], "card": cards[d["name"]]})
for name, card in cards.items():
    if not any(d["name"] == name for d in datasets):
        datasets.append({"name": name, "path": name, "file": card.get("file", name), "tier": "scale", "bytes": 0, "description": "", "head": [], "examples": [], "card": card})
data = f"<script>window.T2A_STATIC=true;window.T2A_SCENES={json.dumps(scenes, default=str)};window.T2A_DATASETS={json.dumps(datasets, default=str)};</script>"
html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")
html = html.replace('<script src="app.js"></script>', data + f"<script>\n{js}\n</script>")
os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
out = os.path.join(HERE, "dist", "index.html")
open(out, "w").write(html)
print("wrote", out, len(html) // 1024, "kB,", len(scenes), "scenes,", len(datasets), "datasets")
# Artifact variant: body content only (the publishing host wraps it in its own document skeleton), title and viewport meta first.
import re
head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
head = re.sub(r"<meta[^>]*>", "", head)
head = re.sub(r"<title>.*?</title>", "", head, flags=re.S)
art = '<title>text2answer graph analysis</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n' + head.strip() + "\n" + body
open(os.path.join(HERE, "dist", "artifact.html"), "w").write(art)
print("wrote", os.path.join(HERE, "dist", "artifact.html"), len(art) // 1024, "kB")
