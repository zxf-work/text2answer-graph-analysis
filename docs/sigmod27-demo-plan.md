# SIGMOD 2027 Demo Submission Plan (revision 2)

Date: 2026-11-21. Revision 2 folds in the positioning comments of the same date
(`GraphAudit_SIGMOD2027_Positioning_and_Codegen_Justification.md`, kept outside the repository): the system is
reframed around an auditable analytical contract, the code-generation comparison is made fair, and
**semantics-aware reuse across a conversation** becomes the new technical contribution.

Supersedes sections 1 to 5 and 8 of `demo-paper-plan.md`. Its related-work table and risk list still apply.

Everything marked *proposed* below does not exist yet. Nothing proposed may appear in the paper as a result until
it has been built and measured.

## 1. Fixed facts from the call

Source: https://2027.sigmodconf.hosting.acm.org/calls_sigmod_demos.shtml (read 2026-11-21).

| item | value |
|---|---|
| Submission deadline | **Monday, January 11, 2027**, 11:59 PM AoE (moved up from January 15) |
| COI declaration | within 24 hours of the deadline, per author, separate from the research track; missing it is a desk reject |
| Notification / camera-ready | March 8, 2027 / April 1, 2027 (same 4-page limit) |
| Conference | June 13 to 18, 2027, Huntington Beach, CA |
| Length and format | 4 US-letter pages **including** bibliography; `\documentclass[sigconf,9pt]{acmart}`; violations are desk-rejected |
| Review | not double-blind; every author needs a CMT account and an ORCID |
| Video | optional, up to 5 minutes, URL in the abstract; "highly encouraged" and used in selection |
| Also required | state clearly which parts are implemented and which are planned |

Seven weeks from today. Internal target: submit Saturday January 9.

## 2. Name, claim and what we do not claim

**Working name: GraphAudit.** Candidate title: *GraphAudit: Verifiable Conversational Graph Analytics with
Computation Reuse*. One collision found so far: "GraphAudit: Privacy Auditing for Massive Graph Mining", a 2014
NC State technical report (TR-2014-10) on taint tracking in vertex-centric graph processing. It is a different
problem and an unpublished report, but it is the same name in the graph-systems area; decide whether that is
acceptable before the title is fixed. Fallback from the comments: GraphCompass.

**Central claim.** GraphAudit turns natural-language graph questions into grounded, inspectable, budget-aware
computations, checks detectable semantic inconsistencies without ground-truth answers, and, across a session of
related questions, reuses earlier computation only when the analytical contract shows the reuse is valid.

**Not claimed, anywhere in the paper:**

- that a typed plan is more accurate than generated code (measured: a tie when both get the file facts);
- that the verifier proves an answer matches the user's intent (it detects inconsistencies it has rules for);
- that 87% is an accuracy (it is recall on 87 answer-changing injected mutations, 76 flagged);
- that code generation cannot reuse results (a stateful coding agent can; it is one of our baselines).

**Answer to "why not just generate code?"** Runnable code is not an analysis whose semantics, assumptions and cost
can be examined. GraphAudit adds an explicit contract between the question and the computation, and that contract
is what makes both checking and safe reuse possible. Typed plans are the default executor and code generation the
fallback, under the same profile, checks and budget.

## 3. Where the project stands

### 3.1 Built and committed

- Pipeline: loader, file facts, profile card, 54-operator catalogue, typed plan with validator and cost model,
  verifier, binary graph cache, resident-graph server.
- Six systems: full, no_verify, no_interp, flat, codegen, codegen_nofacts.
- Benchmarks: base 60, hard 27, scale 16 (synthetic graphs), scorer, fault-injection harness.
- Demo UI: profile card, plan diagram, verifier findings, answer with variants, executor switcher, graph panel,
  replay of seven recorded scenes.

### 3.2 What the code has toward reuse, and what it lacks

Read from `t2r/ir.py`, `t2r/ops.py`, `t2r/systems.py`, `demo/server.py` on 2026-11-21:

| piece | state |
|---|---|
| Resident graphs across questions | exists |
| Operator-result cache | **rebuilt 2026-11-21** with lineage keys (section 5.2, item 3): every step is cacheable and a key covers the operator, parameters, seed, all inputs and the graph as loaded |
| Cache key and semantics | **bug confirmed, then fixed**: the old key `(file hash, operator, arguments)` returned directed PageRank for the undirected reading of the trust network (T0 = 0.2047 served, 0.0549 correct). Kept as a regression test and as the paper's motivating example |
| Full score vectors kept | yes: `pagerank` returns a NodeMap and `top_k` is a separate operator, so "top 10, now top 20" is an exact reuse by construction |
| Scope operators | `induced_subgraph`, `restrict_map`, `filter_nodes`, `k_core`, `largest_component` exist |
| Node attributes | **built 2026-11-21**: a node table next to the edge file is attached on load and profiled; operators `attribute_of`, `filter_by_attribute`, `group_by_attribute`, `attribute_map`; the validator checks attribute names and category values |
| Session state, follow-up references ("them", "instead") | **absent**: every question is planned independently |
| Plan patches, reuse decision, reuse checks | **absent** |
| Self-reviewing or stateful code-generation baselines | **absent** |
| Code-generation fallback inside the scaffold | decided in experiment 2; implementation not confirmed |

### 3.3 Cluster setup and first run (done 2026-11-21)

- itiger: repo at `~/text2answer-sigmod27/`, Python 3.12 environment (`requirements.lock.txt`), API key in place,
  job scripts in `slurm/`.
- Real graphs in `~/text2answer-sigmod27/data/snap/`, row counts equal to SNAP's published edge counts:
  soc-pokec-relationships (30,622,564), soc-LiveJournal1 (68,993,773), com-orkut.ungraph (117,185,083).
- First full run, Slurm job 304285: hard set (27 questions, no descriptions), Haiku 5.5, three independent
  repetitions, commit `8a36539`. Answer accuracy:

| repetition | full | no_verify | no_interp | flat | codegen | codegen_nofacts |
|---|---|---|---|---|---|---|
| 1 | 0.98 | 0.98 | 0.96 | 0.98 | 0.96 | 0.87 |
| 2 | 0.98 | 0.98 | 0.98 | 0.98 | 0.94 | 0.87 |
| 3 | 0.98 | 0.98 | 0.98 | 0.94 | 0.96 | 0.83 |

  This reproduces the November 5 and 6 numbers (0.98 / 0.98 / 0.98 / 0.98 / 0.96 / 0.85) within two points. The
  only stable gap is code generation without file facts. The full system's one miss is the same question each
  time (H4, assumption not stated), so it is systematic, not noise. Flat-agent plan correctness ranged 0.85 to 0.91.
- The runner has no seed parameter; "seed" directories are repetitions.
- Raw outputs of experiments 1 to 3 (`results*/raw/`) are git-ignored and absent from the repository, so fault
  injection and re-scoring produce empty tables on a fresh clone. Recover them or regenerate from new runs.
- The NetworkX cross-check of the ground truth did not finish in a 10-minute job; rerun with a longer limit.

### 3.4 Session check on Pokec (hand-written plans, no model; itiger, 2026-11-21)

Pokec with its profile table: 1,632,803 nodes, 30,622,564 edges, every node matched; attributes region (187
values), gender, age (given for 1,138,314 users), public, completion percentage. Load 66 s from the file, 13 s
from the binary cache; profile card 4 s.

| turn | executed | reused | wall | time saved |
|---|---|---|---|---|
| 1 top 10 by PageRank | pagerank, top_k | | 4.10 s | |
| 2 their region | attribute_of | pagerank, top_k | 0.01 s | 3.05 s |
| 3 top 20 instead | top_k | pagerank | 0.11 s | 2.94 s |
| 4a within a region, whole-graph scores filtered | filter, restrict, top_k | pagerank | 0.20 s | 2.94 s |
| 4b within a region, PageRank on the induced subgraph | subgraph, pagerank, top_k | filter | 0.15 s | 0.13 s |
| 5 repeat of 4b | | all four steps | 0.00 s | 0.25 s |

The two readings of turn 4 share 4 of their top 10 users, in a different order: the choice changes the answer on
real data. One run, one region (the largest); not yet a measurement. The plans were written by hand: the planner
does not yet produce follow-up plans, and no reuse rule beyond the keys exists.

Unit tests: `prototype/tests/test_reuse.py`, 10 tests, passing on itiger.

## 4. Where things run

**No experiment runs on a laptop. Every experiment and every large-graph load goes to a remote server.**

| host | cores | RAM | free disk | role |
|---|---|---|---|---|
| `itiger.memphis.edu` (Slurm `bigTiger`, 11 nodes; limit 120 CPUs, 3 nodes) | 64 per node | 515 GB per node | 7.1 TB | **all experiments** |
| `xzgpu2.uom.memphis.edu` | 32 | 62 GB | 204 GB | **demo server** (needs uv and tmux installed in the home directory) |
| `xzgpu.uom.memphis.edu` | 40 | 93 GB | 279 GB | backup; shared and busy when checked |
| `xzws.uom.memphis.edu` | | | | key login refused from the laptop; unused |

All reachable hosts and itiger compute nodes reach `api.anthropic.com` and `snap.stanford.edu`. Compute nodes have
no `git`; the job script reads the commit hash from `.git` directly. The API key is in
`~/.config/t2a/anthropic_key`, mode 600, never committed. To confirm: whether `xzgpu2` is reachable from off campus
without a VPN.

Rules for every run: pinned model id, commit hash, repetition index and raw transcripts stored with the results.

## 5. New contribution: semantics-aware reuse across a session (*proposed*)

Analysts ask sequences of related questions. Treating each as independent wastes planning effort and graph
computation; reusing carelessly is worse, because a reused result computed under a different scope or
interpretation is a silent semantic failure. The contribution is the decision between the two, made by rules over
the plan and shown to the user.

### 5.1 Running example on a real graph

Pokec (1.6M users, 30.6M directed friendship edges) ships with a profile table: region, age, gender and more. It
is real, it has node attributes with real meaning, and PageRank on it takes seconds, so the whole session runs
live. Region plays the role "department" plays in the comments' example.

| turn | question | decision | what happens |
|---|---|---|---|
| 1 | Who are the 10 most influential users? | new analysis | measure made explicit (PageRank, with variants offered); full score vector kept |
| 2 | Which regions are they from? | drill-down, exact reuse | attribute join on the turn-1 node set; no PageRank |
| 3 | Show the top 20 instead. | plan patch, exact reuse | `top_k` 10 to 20 over the kept vector; valid only because the vector, not the list, was kept |
| 4 | Who is most influential within region X? | **ambiguous scope** | two contracts shown: global ranking filtered to X (reuse), or PageRank on the subgraph induced by X (recompute). The user picks; choosing the second invalidates reuse and the recomputation is shown |
| 5 | Show their immediate neighbours. | drill-down, partial reuse | "their" resolved against the current selection and stated |

### 5.2 Mechanism

1. **Node attributes.** Loader for a node table keyed by node id; profile card reports each attribute's type,
   coverage and cardinality; operators `node_attribute`, `filter_by_attribute`, `group_by_attribute`.
2. **Session state.** One record per session: graph id and content hash, accepted semantics, current scope,
   active entities, the session plan DAG, result handles (type, size, lineage summary), clarification log. The
   planner sees this compact record, never raw arrays and never the full chat history.
3. **Lineage keys.** Replace the current cache key with a content-addressed one:
   `key(step) = hash(operator, canonical parameters, semantics in force, seed and approximation tier, keys of all inputs)`,
   with the graph's content hash as the root. Consequences: derived steps become cacheable; PageRank on an induced
   subgraph can never collide with PageRank on the whole graph; a changed interpretation changes every key
   downstream. Exact reuse is then sound by construction rather than by judgment.
4. **Intent classes.** Each follow-up is classified as new analysis, plan patch, drill-down or ambiguous. Patch
   types for the first version: change a parameter, add or change a scope restriction, swap the measure, extend
   from an existing handle. A patched plan is re-validated and re-verified in full; a cache hit never skips
   verification.
5. **Reuse checks, rule-based.** Operators are marked scope-sensitive (PageRank, betweenness, closeness,
   communities, components, degree) or not (attribute lookups, set operations, top-k). Rules:
   - a turn that introduces a scope restriction, with a plan that restricts or filters a scope-sensitive result
     computed on a wider scope, raises a *scope ambiguity* finding: show both contracts or ask;
   - a result handle that holds a truncated list cannot serve a request for more rows;
   - a handle computed under different semantics, graph version, seed or approximation tier is not reusable;
   - if no rule establishes validity, recompute.
6. **Three outcomes, always shown:** exact reuse, partial reuse (safe ancestors kept, changed descendants rerun),
   recompute or clarify. The audit record lists each step as reused or executed, with measured time.

Out of scope before January: optimisation over a whole workload, reuse across different graphs, mutable graphs.

## 6. Experiments

All on itiger. Ordered by what the paper needs.

### E1. Reuse-decision fault injection (no model calls)

The reuse analogue of the existing harness, and the cheapest strong number for the new claim. Take correct
session plans and force a wrong reuse: a global result used for a subgraph scope, a truncated list extended, a
result from the other interpretation, a stale graph version, a different approximation tier. Report how often the
answer changes, how often the checks flag it, and the flag rate on valid reuses.

### E2. Session workload

- About 16 sessions of 5 to 8 turns over four graphs (Pokec with attributes, the trust network, the email log,
  the road network): follow-up references, parameter changes, scope restrictions, measure swaps, repeats, and
  ambiguous scope changes, each turn annotated with the acceptable interpretations and the correct reuse decision.
  This replaces the separate "harder benchmark" of revision 1: the sessions supply the compositional depth.
- Systems:

| system | conversation-aware | reuses computation | purpose |
|---|---|---|---|
| independent code generation | no | no | floor, not the competitor |
| **stateful code-generation agent** | yes | yes: persistent Python process, kept variables | the realistic competitor; never forced to reload or recompute |
| GraphAudit without session mechanisms | no | existing narrow cache | isolates what is new |
| GraphAudit with verified reuse | yes | yes, plan level | the proposal |

- Ablations: no context; context only; execution cache only; both; both with reuse checks.
- Metrics: answer correctness; interpretation correctness; **invalid reuse rate**; reuse-check recall and
  precision; share of work reused; execution, planning and wall time; input, output and billed tokens with prompt
  caching on for every system; clarification turns.

### E3. Silent failures on single questions, against a fair code-generation ladder

- Ladder: bare code generation (exists as `codegen_nofacts`); grounded (exists as `codegen`); grounded with
  self-review (*new*); grounded with timeout, memory cap and retry (mostly exists, to be made explicit); typed
  plan (exists); hybrid with fallback (*to confirm or build*). Same model, same file facts; report both a
  call-matched and a best-effort comparison.
- Primary metric: **silent failure rate**, a wrong answer returned with no warning, variant or clarification.
  The scorer needs one new column; the repetitions already run can be re-scored for it.
- Verifier recall and precision on plan mutations, extended beyond the 60 base plans, including the flag rate on
  unmutated correct plans (never measured). Try to lift the two weak rows (method swaps 1 of 8, in/out flips 4 of 7).

### E4. Real large graphs and the budget curve

Pokec, LiveJournal, Orkut with regenerated ground truth; full, flat and code generation; three repetitions. Sweep
the cost budget over two orders of magnitude and report answer quality, wall time and budget compliance. Report
cold load, cache restore and resident time separately.

### E5. Repetitions and models on the existing sets

Base, hard and scale sets, three repetitions, Opus, Sonnet and Haiku 5.5. Hard set with Haiku is done (section 3.3).
About 600 runs per (model, repetition); the Opus third is on the order of $100 at measured costs.

### E6. Interactive latency

Per turn, with graphs resident: planning call, validation, execution, verification, and the reused share.

### Deferred

A user study comparing a code-and-output view with the audit view is the right experiment and does not fit in
seven weeks with recruitment and approval. Keep it for the camera-ready or a follow-up; at most an informal pilot
with three or four students in week 4.

## 7. Demo

### Three-minute signature session (Pokec, live)

1. **0:00 to 0:40, start a session.** Top influential users; plan and assumptions on screen.
2. **0:40 to 1:30, fast drill-down.** Their regions; then top 20 instead. Reused steps highlighted, with measured
   time and tokens against the first turn. A real cache hit.
3. **1:30 to 2:25, the safety moment.** "Most influential within region X": two contracts side by side; pick the
   subgraph reading; the global scores are marked invalid for this scope and PageRank reruns on the subgraph. The
   two rankings differ on screen.
4. **2:25 to 3:00, audit and cost.** The session's audit record: reused versus executed, checks, time, tokens.
   Then the budget decision on a large resident graph (requested versus allowed betweenness pivots).

### Booth extras, visitor-driven

- **Break the plan, press Audit.** "Who trusts the most people?" with the plan flipped to in-degree; the verifier
  reports the mismatch without knowing the answer. Visitors flip other things, including ones the verifier misses.
- **Force a reuse.** Override the reuse decision in scene 3 and watch the check object.
- **No file facts.** Code generation reads the row-number column as a node.
- Bring your own edge list, with an optional node table.

Video, 5 minutes: the signature session in three, then break-the-plan and no-facts in one minute each. Recorded
against the server.

## 8. Build list

| item | size | needed by |
|---|---|---|
| Test whether the current cache can return a result from another interpretation | hours | Nov 24 |
| Node attribute table: loader, profile card section, three operators; Pokec profiles on the cluster | 3 days | Nov 29 |
| Lineage keys and caching of derived steps | 2 days | Nov 29 |
| Session state and compact planner context | 3 days | Dec 3 |
| Intent classes and four plan-patch types | 4 days | Dec 8 |
| Reuse checks and the three-outcome decision | 3 days | Dec 8 |
| Self-reviewing code-generation baseline; silent-failure column in the scorer | 2 days | Dec 3 |
| Stateful code-generation agent baseline | 3 days | Dec 8 |
| Reuse fault-injection harness (E1) | 2 days | Dec 10 |
| Session workload, annotated (E2) | 4 days | Dec 10 |
| UI: session timeline, reused-versus-executed colouring on the plan, measured savings, two-contract chooser, Audit button, plan mutation controls | 8 days | Dec 20 |
| Hybrid fallback: confirm or build | 2 days | Dec 13 |
| Audit record export | 1 day | if time allows |

## 9. Schedule and the decision point

| week | dates | build | experiments (itiger) | paper |
|---|---|---|---|---|
| 1 | Nov 23 to 29 | attributes, lineage keys, cache test | E5 remaining runs; E3 re-scoring | read GraphSeek and the three other unread papers; reuse-side related work |
| 2 | Nov 30 to Dec 6 | session state, intent classes, self-review baseline | E3 ladder | architecture figure with both executors and the session layer |
| 3 | Dec 7 to 13 | reuse checks, stateful baseline, harness, workload | E1; E2 pilot on four sessions | system section |
| | **Dec 13** | **decision point** | | |
| 4 | Dec 14 to 20 | UI session view; **UI freeze Dec 20** | E2 full; E4; E6 | evaluation section |
| 5 | Dec 21 to 27 | fixes only; re-record scenes; screenshots | reruns | full draft |
| 6 | Dec 28 to Jan 3 | | | video; cut to 4 pages |
| 7 | Jan 4 to 9 | | | final read; CMT, ORCIDs; **submit Jan 9** |

**Decision point, December 13.** Reuse goes into the title and claim only if, on that date, the Pokec session
runs end to end with a real cache hit and a real invalidation, and E1 has numbers. Otherwise the paper is the
single-question GraphAudit (grounding, audit, cost control) with at most one two-turn reuse scene described as
such, under the title *GraphAudit: Demonstrating Transparent and Verifiable Natural-Language Graph Analytics*.
Everything built before the decision point is useful to both versions.

This revision is roughly twice the scope of revision 1 in the same seven weeks. If it slips, cut in this order:
audit export, Orkut, the Sonnet runs, the hybrid fallback claim, the plan-mutation controls beyond direction and
measure.

## 10. Paper

| space | content |
|---|---|
| 0.7 page | problem; the runnable-but-wrong example (in-degree for "trusts the most"); contributions |
| 1.0 page | profile, contract and plan, executors, verifier, cost model; session layer with lineage keys and reuse checks |
| 1.2 pages | the signature session and the booth interactions, one annotated screenshot |
| 0.7 page | evidence: silent failures against the ladder; reuse decisions (E1, E2); budget curve |
| 0.4 page | related work, limits, implemented-versus-planned statement |

Figure 1: architecture with typed-plan and code-generation executors under one profile and audit layer, and the
session plan DAG above them. Figure 2: the safety moment, two contracts and the invalidated reuse. One table with
verifier and reuse-check blind spots stated.

Related work to add for the reuse angle, all to be read before citing: conversational text-to-SQL (SParC, CoSQL),
reuse of intermediates in iterative analytics and ML workflows, multi-query optimisation and materialised-view
matching, semantic caching for LLM applications.

Prepared answers: "isn't this just caching?" (caching matches inputs; here the question is whether a follow-up's
changed scope makes a matching-looking result the wrong one, decided by rules over the plan and tested by E1);
"isn't chat history enough?" (text history carries no dependency graph and no validity condition).

## 11. Open decisions

1. Adopt GraphAudit despite the 2014 technical report of the same name, or use another name.
2. Confirm Pokec with its profile table as the session graph.
3. Author list, with a CMT account and ORCID for each.
4. Whether reviewers get a public demo URL or only the video; where the video is hosted.
5. Whether to rename the repository and the `t2r` package now or after submission.
