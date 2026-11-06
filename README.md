# text2answer graph analysis

A text-to-result graph analysis toolkit: the user types a question about a graph in plain language and the
system computes the answer. No Cypher, no graph query language, no graph database. The LLM never sees the graph;
it sees a profile card of the file, writes a typed analysis plan, and a validated executor computes the result,
which a verifier then checks without ground truth.

This repository collects the planning documents, the prototype and the experiments that decided the direction.
It started as a branch of the older GraphProfile repository and was moved here to continue as its own project.

## Where things are

| path | what |
|---|---|
| `docs/text-to-result-toolkit-assessment.md` | assessment of the two old repositories (GraphProfile, GRabbit) and a survey of the field |
| `docs/benchmark-analysis.md` | what existing benchmarks measure, why they saturate, and the benchmark design adopted here |
| `docs/solution-architecture.md` | the grounding gap, research questions, the typed plan IR and the six-stage architecture |
| `docs/headline-experiment-results.md` | experiment 1: five systems on 60 questions over real graphs (Opus and Haiku) |
| `docs/experiment-2-results.md` | experiment 2: hard interpretation set, fault injection, 10M to 50M-edge scale tier, conclusions and decision |
| `docs/experiment-3-codegen-without-facts.md` | experiment 3: code generation without file facts, the ablation that shows what the interpretation stage is worth |
| `docs/demo-paper-plan.md` | plan for a SIGMOD/VLDB demo paper: claim, venues, demo scenario, build list, paper outline, related work, risks |
| `prototype/demo/` | the demo web UI: standard-library server, single-page front end, recorded guided-demo scenes |
| `prototype/` | the working prototype: loaders, operator catalogue, plan IR, verifier, the five compared systems, benchmark generators, scorer, experiment runner |

## State of the work (November 2026)

- Accuracy: the typed-plan system ties code generation on the base and hard sets and leads by three points on the
  scale tier (1.00 vs 0.97), with the flat tool-calling agent behind on both.
- Verification without ground truth catches 87% of answer-changing plan mutations.
- Cost tiering is automatic: on a 50M-edge graph the cost model cut the planner's betweenness pivots to fit the
  budget and every question finished; the flat agent fabricated an answer on the same question.
- Decision: build a shared scaffold (profile card with file facts, cost model, verifier, clarification protocol)
  around both executors, typed IR by default and code generation as the escape hatch. The research claim is
  "verification and cost control without ground truth" rather than "IR beats codegen".
- Without the file facts, code generation loses 4 points (Opus) and 11 points (Haiku) on the hard set at twice
  the cost, making the same semantic errors the interpretation stage prevents: the profile card is the cheapest
  part of the system with the largest measured effect.
- Next: a harder benchmark (contestable approximations,
  multi-step analyses, weaker models); real large graphs once SNAP is reachable.

## Running the prototype

See `prototype/README.md`. Dependencies: python-igraph, networkx, numpy, pandas, pydantic; LLM calls go through
the `claude -p` headless CLI or the Anthropic SDK. The benchmark data for the base and hard sets is in the
repository; the large synthetic graphs are regenerated with `prototype/bench/big/gen_big.py` (not committed).
