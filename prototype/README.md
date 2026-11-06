# Text-to-result graph analysis: prototype and headline experiment

This prototype tests the claim in `../docs/solution-architecture.md`: a typed, interpretation-aware,
self-verifying plan beats both free code generation and flat tool calling on analyst-style questions over
real graphs, and the gain comes from the interpretation and verification stages rather than the executor.

## Layout

```
t2r/graphs.py    loaders, raw file facts, semantics inference, profile card, node-name resolution
t2r/ops.py       operator catalogue (40 typed operators on igraph, with cost classes and approximate tiers)
t2r/ir.py        plan IR (pydantic), validator, cost model / auto-tiering, executor, answer extraction
t2r/verify.py    verification without ground truth: invariants, cross-method agreement, approximation notes
t2r/llm.py       LLM client (Anthropic SDK, or `claude -p` headless inside a Claude Code session)
t2r/systems.py   the five systems compared: full, no_verify, no_interp, flat, codegen
bench/datasets.json     dataset manifest with declared semantics (ground truth for interpretation)
bench/make_questions.py 60 questions in 11 families with igraph ground truth
bench/check_gold.py     NetworkX cross-check of the ground truth
bench/score.py          deterministic checkers per family, plan score, cost
run_experiment.py       runs every (system, question) pair in an isolated subprocess, writes results/summary.md
```

## Systems

| system | interpretation stage | typed IR + validator + cost tiering | verifier | notes |
|---|---|---|---|---|
| full | yes | yes | yes | the proposal |
| no_verify | yes | yes | no | ablation |
| no_interp | no (raw file facts, strict node matching) | yes | yes | ablation |
| flat | no (may call a `file_facts` tool) | no (tool-calling loop over the same operators) | no | conventional agent |
| codegen | no | no (LLM writes a NetworkX/igraph script, run in a subprocess, one retry) | no | strongest conventional baseline |

All systems receive the same user message (file name, optional one-line dataset description, question) and the same model.

## Benchmark

Datasets: SNAP ego-Facebook (4k nodes, undirected, stored once), email-Enron (37k nodes, undirected, stored both ways),
soc-Epinions1 (76k nodes, directed), Les Miserables (77 labelled nodes, weighted by co-appearance count), Zachary karate club.

Families: profile, single metric, top-k, community, path, neighbourhood, comparative, compositional,
interpretation (directed/undirected, stored-both-ways, weights as strengths), clarification (under-specified
"most important"), node resolution (case, misspelling, partial names).

Scoring: answer score per family checker (tolerances, overlap@k, Jaccard, path validity, clarification credit);
plan score (expected operators present and expected assumptions stated; n/a for opaque code); cost
(LLM calls, tokens, USD, wall time).

## Running

```bash
pip install python-igraph networkx numpy pydantic
python bench/make_questions.py          # ground truth (about 1 minute)
python run_experiment.py --workers 3    # all systems, all questions
python run_experiment.py --score-only   # re-score existing raw results
```

Set `ANTHROPIC_API_KEY` to use the SDK backend; inside a Claude Code session the `claude -p` backend is used automatically.
`T2R_MODEL` overrides the model (default `claude-opus-5-5`).

## Limitations of this prototype

- One graph per question (no cross-graph comparison yet).
- Ground truth is igraph, cross-checked against NetworkX on a subset; community questions use tolerances because partitions are seed-dependent.
- The verifier covers a dozen invariants, not a general theory.
- No caching across questions, no MCP surface, no visualisation.


## Demo web UI

```bash
python3 demo/server.py --port 8765          # then open http://127.0.0.1:8765
python3 demo/make_scenes.py                 # re-record the guided-demo scenes (live model calls)
python3 demo/build_static.py                # single-file preview with the scenes inlined: demo/dist/index.html
```

The page walks through four steps: pick a graph file (shipped sets, or drop your own edge list), read the profile
card the system computed from it, ask in plain words, and inspect the plan, the verifier's checks, the answer and
its cost. The executor switcher runs the same question through the typed-plan system, the tool-calling agent or
code generation. "Guided demo" replays recorded scenes without a model call. Loaded graphs stay in memory between
questions (`T2R_GRAPH_CACHE=1`, set by the server).

### Loading and caches

- `T2R_GRAPH_CACHE=1` keeps loaded graphs in process memory (the demo server sets it).
- The first parse of a file writes a binary cache (edge array, weights, ids, facts, semantics) to
  `prototype/.cache/graphs/` (`T2R_CACHE_DIR` to move it, `T2R_DISK_CACHE=0` to disable). Later loads in any
  process restore from it: 10M edges in 10 s instead of 34 s, 50M edges in 34 s instead of 331 s.
- `python3 demo/server.py --preload trust,roads` (or `--preload all`) loads graphs at start; the UI shows each
  graph's state (cold, cached on disk, loading, resident) and loads in the background when one is picked.
