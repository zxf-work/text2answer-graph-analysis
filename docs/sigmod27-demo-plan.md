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

**Name: GraphAudit** (decided 2026-11-22). Candidate title: *GraphAudit: Verifiable Conversational Graph Analytics with
Computation Reuse*. One collision found so far: "GraphAudit: Privacy Auditing for Massive Graph Mining", a 2014
NC State technical report (TR-2014-10) on taint tracking in vertex-centric graph processing. It is a different
problem and an unpublished report, and the collision was accepted. The fallback from the comments, GraphCompass,
is taken by a 2024 *Bioinformatics* paper with a PyPI package, so it is not an option.

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
| Session state, follow-up references ("them", "instead") | **built 2026-11-22** (`t2r/session.py`): the planner sees the profile card and a compact state record (accepted semantics, earlier plans with result sizes, current selection, chosen reading), never the chat history or raw values |
| Plan patches | **first version built**: the planner returns a complete plan that copies earlier steps and labels its intent and patch type; unchanged steps are reused through their lineage keys. The engine does not yet derive the patch type itself |
| Reuse decision, reuse checks | **first version built**: operators marked scope-sensitive; scope-ambiguity rule with the second contract produced by a mechanical plan rewrite (both directions); a chosen reading is carried to later turns; a claimed "explicit" reading must quote the question; changed semantics reported; outcome per turn is exact reuse, partial reuse, recompute or clarify. **Not built:** the truncated-list rule (unneeded so far, since rankings are always re-taken from the full score map) |
| Stateful and independent code-generation session agents | built Nov 22 (3.8); self-reviewing variant for single questions absent |
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

### 3.5 Live session on Pokec, model-planned (2026-11-22)

Seven turns on Pokec with the model planning every turn (`bench/big/session_live.py`, jobs 304309 Haiku and 304310
Opus; one run each, so this shows the mechanism, not a rate).

| turn | request | Haiku | Opus |
|---|---|---|---|
| 1 | top 10 by PageRank | recompute, 3.8 s | recompute, 3.8 s |
| 2 | region of each of them | partial reuse (PageRank and top-k reused) | same |
| 3 | top 20 instead | partial reuse (PageRank reused) | same |
| 4 | most influential within region X | rule raises two contracts; "user" picks B; subgraph PageRank executed, 0.3 s | same |
| 5 | and within region Y | reading B carried over, stated | same |
| 6 | regions by total PageRank | partial reuse | partial reuse |
| 7 | "show the top 20 again" | read as top 20 within region Y | read as turn 3, exact reuse |

- Cost for the session: $0.010 (Haiku), $0.36 (Opus); about 60k input tokens either way, most of it the operator
  catalogue repeated each turn.
- Planning takes 3 to 12 s per turn and dominates; execution after turn 1 is under 1.3 s.
- Two defects found by these runs and fixed, both kept as tests: the planner computed both readings in one plan
  (Haiku) or restricted two measures (Opus), and the first rewrite changed only one of them, so the answer shown did
  not match the contract chosen. A contract now covers every restricted measure the answer depends on.
- Turn 7 shows a second kind of ambiguity the rules do not cover: which earlier result "again" refers to.

### 3.6 E1: reuse fault injection (2026-11-22, job 304356, no model calls)

`bench/sessions/reuse_fault.py`; report in `prototype/results/sessions/e1_reuse_fault/`. Nine graphs: trust,
follows, citations, roads, facebook, epinions and three regional subgraphs of Pokec with real profile attributes
(122k to 176k users). 246 fault scenarios and 201 valid-reuse scenarios, each run under seven cache-key schemes.

| key scheme | wrong value served (of 246 faults) | final answer changed | valid steps reused (of 390) |
|---|---|---|---|
| full lineage key | 0 | 0 | 390 |
| without input lineage (arguments as written) | 117 | 105, plus 36 wrong answers on valid scenarios | 318 |
| without graph reading | 32 | 32 | 390 |
| without content hash (dataset name as root) | 48 | 44 | 390 |
| without node table in the root | 12 | 12 | 390 |
| without seed | 27 | 26 | 390 |
| the prototype's original cache | 71 | 70 | 237 |

- Every ingredient of the key is needed: removing any one admits a class of wrong reuse, and each removed
  ingredient admits exactly the classes it is there for.
- The full key gives up no valid reuse in these scenarios, including plans with renamed or reordered steps and
  defaults written out.
- Scope readings: over 60 group restrictions (4 measures, 5 districts, 3 graphs) the two readings gave a different
  top-10 set in all 60, sharing 3.7 of 10 nodes on average (PageRank 5.5, degree 5.6, core number 3.0, approximate
  closeness 0.5). The rule identified the reading of both plans in 60 of 60 and flagged none of 387 plans without a
  group restriction.
- Limits: the scenarios are generated from templates, so the counts show coverage of fault classes, not rates in
  real use. The "short list extended" fault is modelled as a stale derived result, the only form it can take here.

### 3.7 E2 pilot: session workload (2026-11-22)

`bench/sessions/workload.py`, `run_sessions.py`; summaries in `prototype/results/sessions/e2_pilot/`. 14 sessions,
82 turns, 9 of them ambiguous scope turns; a simulated user answers a two-contract question with the annotated
reading. Second repetition (after the selection fix), one run each:

| system | model | answers correct | follow-ups correct | ambiguous turns handled | silent other reading | cost |
|---|---|---|---|---|---|---|
| full | Opus | 100% | 100% | 9/9 | 0 | $3.67 |
| full | Haiku | 98.8% | 97.9% | 9/9 | 0 | $0.10 |
| without the scope rule | Haiku | 92.7% | 87.2% | 0/9 | 6 | $0.10 |
| without reuse | Haiku | 93.9% | 91.5% | 9/9 | 0 | $0.10 |
| without session context | Haiku | 80.5% | 66.0% | 3/9 | 0 | $0.10 |

- The scope rule removes the silent wrong readings (6 of 9 without it, in both repetitions).
- Session context is what makes follow-ups answerable.
- Reuse covered 26 to 28% of steps but saved under 3 s per run: these graphs are small and planning (about 4 s a
  turn) dominates. The time argument has to be made on the large graphs (E4), not here.
- The lower accuracy "without reuse" is not an effect of reuse: three of its five misses are a cost-model crash
  (fixed, below) and the rest model variance. One repetition cannot separate variants this close.
- Defects found and fixed, each with a test: "among them" after a count resolved to an older ranking (the session
  record now tracks the set a count was taken over); approximate closeness ran one search per node; the cost model
  failed when `k` was a reference to an earlier step.
- Missing: repetitions and a second annotator for the gold readings. The code-generation systems are in 3.8.

### 3.8 E2 pilot: code-generation agents on the same sessions (2026-11-22)

`bench/sessions/run_codegen_sessions.py`, `rescore.py`. Two agents, both given the conversation so far (questions,
their own code, printed output), the file facts and the head of the node table, with one repair attempt:
**stateful** runs each turn as a cell in one Python process per session, so earlier variables stay available;
**independent** runs each turn as a complete script in a new process. One run each.

| system | model | answers correct | follow-ups correct | ambiguous turns: asked / correct | execution time | cost |
|---|---|---|---|---|---|---|
| GraphAudit full | Opus | 100% | 100% | 6 of 6 asked / 9 of 9 | 2.9 s | $3.67 |
| code generation, stateful | Opus | 100% | 100% | 0 of 6 asked / 9 of 9 | 17.5 s | $1.64 |
| code generation, independent | Opus | 100% | 100% | 0 of 6 asked / 9 of 9 | 96.5 s | $2.20 |
| GraphAudit full | Haiku | 98.8% | 97.9% | 6 of 6 asked / 9 of 9 | 3.2 s | $0.10 |
| code generation, stateful | Haiku | 98.8% | 100% | 0 of 6 asked / 9 of 9 | 65.3 s | $0.06 |
| code generation, independent | Haiku | 95.1% | 91.5% | 1 of 6 asked / 7 of 9 | 125.6 s | $0.08 |

(Three of the nine ambiguous turns repeat a choice the user already made, so six are the ones where asking is
expected.)

- **This workload does not separate GraphAudit from a code-generation agent on accuracy.** With Opus all three are
  at 100%; with Haiku the stateful agent equals GraphAudit.
- **The agents never ask, and still pick the annotated reading.** The wording of our ambiguous turns ("within
  district X", "among them") leads the model to the reading we annotated as the user's. So "silent other reading" is
  0 for them, and the 6 silent wrong readings of our own "without the scope rule" variant are a weakness of our
  planner prompt, not evidence against code generation. What GraphAudit adds on these turns is that the reading is
  shown and chosen, not that the answer is more often right.
- **A notebook agent reuses too.** The stateful agent's follow-up turns cost 2.0 s of execution in total with Opus
  (35.8 s with Haiku) against 59 s for the independent one. Reuse by keeping variables works when the model
  chooses the right variable; E1 is where wrong reuse is tested, and it has no code-generation counterpart yet.
- GraphAudit executes faster (about 3 s against 17 to 126 s), but all of these are small next to model time.
- **Scoring was widened after the first look, for every system** (earlier runs rescored; the summaries before
  rescoring are kept as `summary.before_rescore.json`). The first scoring gave the agents 80 to 85% because the gold
  plans fixed conventions the questions do not settle. Now also accepted: PageRank using the weights on the trust
  graph; counts and means over the node table (which lists about 10k users per region who have no links) instead of
  over graph nodes; degeneracy on the undirected simple graph (36 on Trnava) instead of on in- plus out-degree (58);
  means rounded to four decimals; free-form answer shapes. GraphAudit's numbers moved only for "without reuse"
  (93.9% to 95.1%).
- **Three of those conventions are GraphAudit's own unstated choices** and should be surfaced or changed: it drops
  users with no links from attribute counts without saying so; its degeneracy on a directed graph is not the textbook
  one; it has no weighted PageRank.
- **Consequence for the paper:** the claim cannot be "more accurate than code generation on follow-ups". The
  supportable claims are (a) wrong reuse is excluded by construction (E1), (b) the reading and what is reused are
  shown and auditable, (c) execution cost on large graphs (E4, not yet run). A fair test of (a) against a notebook
  agent needs sessions where reusing a variable is wrong: the graph reading changes, the file or node table changes
  between turns, a seed or approximation changes. That is the next experiment to design.

### 3.9 E2b: sessions where reusing an earlier result is wrong (2026-11-22)

Design in section 5 (E2b). `bench/sessions/workload_stale.py`, `run_stale.py`; summaries in
`prototype/results/sessions/e2b_stale/`. 22 sessions, 122 turns: 47 trap turns (3 more were void because the stale
and the correct answer coincide) and 22 valid-reuse turns. Each session runs on its own copy of the files; events
rewrite the copy between turns. One run each.

| system | model | trap turns correct | stale answers | otherwise wrong | valid-reuse correct | execution | cost |
|---|---|---|---|---|---|---|---|
| GraphAudit | Opus | 47 / 47 | 0 | 0 | 22 / 22 | 7.9 s | $5.86 |
| GraphAudit | Haiku | 47 / 47 | 0 | 0 | 22 / 22 | 7.9 s | $0.16 |
| stateful agent | Opus | 42 / 47 | **5** | 0 | 22 / 22 | 49.9 s | $2.38 |
| stateful agent | Haiku | 45 / 47 | **2** | 0 | 22 / 22 | 104.6 s | $0.10 |
| stateful agent, warned | Opus | 47 / 47 | 0 | 0 | 22 / 22 | 103.9 s | $3.06 |
| stateful agent, warned | Haiku | 46 / 47 | 0 | 1 | 22 / 22 | 157.5 s | $0.11 |
| independent agent | Opus | 46 / 47 | 0 | 1 | 22 / 22 | 191.3 s | $3.49 |
| independent agent | Haiku | 47 / 47 | 0 | 0 | 21 / 22 | 212.2 s | $0.12 |

Stale answers by class (stateful agent, not warned): R1 reading changed 0/10; R2 data changed, announced 0/6;
**R3 data changed, not announced: Opus 5/9, Haiku 2/9**; R4 name reused 0/6; R5 upstream parameter 0/6; R6 graph cut
0/10.

- **Only the unannounced data change separates the systems.** On the five classes where the user says what changed,
  no agent gave a stale answer. The decision rule of the design applies: reuse is a supporting row, not the title.
- **The stronger model is the one that goes stale.** Opus keeps the graph in memory and reuses it; Haiku re-reads
  the file in most cells and so is rarely caught.
- **One sentence of warning removes the stale answers**, at about twice the execution time (Opus 50 s to 104 s),
  because the warned agent reloads. The independent agent pays about four times.
- **GraphAudit**: no stale answer, 90% of steps reused on the valid-reuse turns, 8 s of execution in total, and each
  change is reported in the turn (`data_changed`, `semantics_changed`). It costs about twice the stateful agent in
  model calls (the profile card and catalogue are sent every turn).
- Limits: one run; templated sessions over three regions of one dataset plus two small graphs; execution times are
  all small at this graph size; the R3 events are large (6000 new links to two users), chosen so the correct
  answer visibly changes.
- Scoring: answers that count users without links (from the node table) as nodes and as single-node components are
  accepted for every system; all eight runs were rescored (`summary.before_rescore.json` kept).
- Not built: the randomness class (R7) and the two sessions on full Pokec that would show the price of reloading.
- Infrastructure: the first two attempts died on the home-directory quota (the per-copy graph caches); caches of
  throwaway copies now go to node scratch and the project lives under `/project/xzhang12` (200 GB limit).

### 3.10 E4 (first part): sessions on the full large graphs (2026-11-22)

Pokec (30.6M links), LiveJournal (69M), Orkut (117M); one 8-turn session per graph (`bench/sessions/workload_large.py`):
most-linked top 10, PageRank top 10, "top 20 instead" (valid reuse), component count, then the edge file is changed
without a word (two users gain 27k to 67k links) and both rankings are asked again (R3), then two follow-ups that
may reuse what was computed after the change. Four systems, Haiku and Opus, **one run each**. Files are copied to
node scratch per session. "Compute" is wall time minus time waiting for the model.

| System | Model | Turns correct (24) | After change correct (6) | Stale (6) | Setup s | Compute s | Model cost |
|---|---|---|---|---|---|---|---|
| GraphAudit | Opus | 24 | 6 | 0 | 449 | 539 | $1.11 |
| GraphAudit | Haiku | 24 | 6 | 0 | 457 | 541 | $0.03 |
| Stateful agent | Opus | 13 | 0 | 6 | 320 | 131 | $0.53 |
| Stateful agent | Haiku | 13 | 0 | 6 | 451 | 327 | $0.02 |
| Stateful agent, warned | Opus | 24 | 6 | 0 | 326 | 790 | $0.92 |
| Stateful agent, warned | Haiku | 12 | 0 | 6 | 309 | 349 | $0.03 |
| Independent agent | Opus | 24 | 6 | 0 | 319 | 1357 | $0.99 |
| Independent agent | Haiku | 23 | 6 | 0 | 322 | 1065 | $0.03 |

Compute seconds per turn (Opus runs; t5 is the first turn after the change):

| Graph | System | t1 | t2 | t3 | t4 | t5 | t6 | t7 | t8 | Sum |
|---|---|---|---|---|---|---|---|---|---|---|
| Pokec | GraphAudit | 1.4 | 4.0 | 0.1 | 0.1 | 75.9 | 1.4 | 0.1 | 0.4 | 83 |
| Pokec | Warned agent | 5.0 | 14.9 | 0.7 | 2.1 | 15.3 | 5.5 | 0.8 | 5.3 | 50 |
| Pokec | Independent | 4.0 | 15.2 | 15.3 | 14.0 | 15.6 | 2.7 | 19.3 | 11.0 | 97 |
| LiveJournal | GraphAudit | 4.8 | 11.0 | 0.3 | 2.8 | 136.0 | 4.6 | 0.4 | 1.1 | 161 |
| LiveJournal | Warned agent | 7.6 | 70.3 | 8.8 | 2.8 | 66.8 | 0.9 | 2.4 | 0.5 | 160 |
| LiveJournal | Independent | 7.8 | 51.5 | 51.0 | 31.4 | 50.7 | 9.3 | 103.1 | 56.6 | 361 |
| Orkut | GraphAudit | 3.0 | 15.7 | 0.2 | 0.3 | 271.9 | 2.9 | 0.2 | 0.6 | 295 |
| Orkut | Warned agent | 11.3 | 148.4 | 10.5 | 47.7 | 147.1 | 102.7 | 10.6 | 101.9 | 580 |
| Orkut | Independent | 11.3 | 214.0 | 200.0 | 15.1 | 218.7 | 11.5 | 216.5 | 11.3 | 898 |

- **The stateful agent never notices the change at this size**: 6 of 6 stale with both models (on the small graphs
  of 3.9 it was 5 of 9 and 2 of 9), and the follow-ups built on the stale state are wrong too (5 of 9 valid turns
  wrong). Its sessions are the cheapest because it never re-reads the file.
- **The one-sentence warning works for Opus and not for Haiku** (6 of 6 stale); on the small graphs it worked for both.
- **GraphAudit**: all correct, change reported on every graph. Its cost is concentrated in one place: the first turn
  after the change re-reads, hashes and re-profiles the file (75 / 136 / 272 s), of which the computation is 4 to 16 s.
  Reused follow-ups take under 0.5 s. Its setup is also the slowest (73 / 124 / 253 s against 43 / 89 / 187 s).
- **Not a win everywhere**: on Pokec the warned Opus agent is correct and cheaper in compute (50 s against 83 s);
  on LiveJournal they tie; GraphAudit is ahead only on Orkut and against the independent agent. With a session this
  short the detection cost is not amortised. Making detection cheaper (hash only what changed, or check size and
  mtime before hashing, reuse the profile for an append) is the obvious engineering step before claiming a time advantage.
- **Self-loops**: GraphAudit's loader drops self-loops and says nothing in the answer; the agents keep them and
  state it. On LiveJournal this swaps PageRank ranks 9 and 10 and gives 776 instead of 775 users above 1000 incoming
  links. The scorer now accepts both (`run_stale.py`, `_with_loops`); all eight runs were rescored. GraphAudit should
  report the convention as a finding.
- Agent errors that are not conventions: Haiku independent, 187 components on Orkut (1); Haiku warned, 914
  components on LiveJournal (1876).
- Limits: one run per cell; one session shape; the change is large and append-only; node-to-node timing variation is
  visible (the Haiku stateful run's setup is 451 s against 309 to 326 s for the other agents); the first attempt of
  one job hung on a node that was draining (itiger08, now excluded).
- Not done: the budget sweep of the E4 design; repetitions.
- Results: `prototype/results/sessions/e4_large/`.

### 3.11 Load time: where it went and what replaced it (2026-11-23)

Stage timing of a cold load (`bench/load_profile.py`, `slurm/load_profile.sbatch`, 16 cores, file on node scratch):

| Stage | Orkut before | Orkut after | LiveJournal before | LiveJournal after |
|---|---|---|---|---|
| Parse and file statistics (`read_raw_fast`) | 233.6 s | 3.8 s | 105.6 s | 2.5 s |
| Build (`_build_big`), of which igraph `add_edges` | 79.4 s (38.3) | 40.8 s (37.7) | 25.9 s (24.3) | 24.5 s (23.0) |
| Profile card | 2.4 s | 2.3 s | 8.6 s | 8.4 s |

- Cause: two `np.unique` calls counting distinct links (224 s on Orkut, 101 s on LiveJournal); polars `n_unique` does
  the same in 1.1 s and 0.7 s. The pandas parse was 8.8 s; pyarrow reads the file in 0.7 s.
- Changes in `t2r/graphs.py`: pyarrow reader for plain numeric edge lists (pandas stays as the fallback), polars for
  distinct counts and deduplication (numpy fallback), lookup-table relabelling of non-contiguous ids, binary cache
  key on mtime in nanoseconds, cache format 2.
- **The file hash now covers the whole file** (about 1 s per 1.8 GB). Before, it covered the first megabyte and the
  size, so an edit further down that kept the size reloaded the graph but could still match stored results.
- Check: 30 tests pass; the reference answers of all 24 large-session turns are identical to the old loader's.
- Floor: igraph builds its graph at about 0.35 s per million links, and the same from the binary cache (39 s on
  Orkut). File order, the constructor, pre-sorted edges and 64-bit ids all take 22 to 24 s on LiveJournal
  (`bench/igraph_build.py`). Going lower needs appending in place (60k links onto the loaded graph: 15 s on Orkut,
  10 s on LiveJournal, 5 s on Pokec) or another graph engine. Neither is started.

GraphAudit large sessions again with the new loader (Haiku, one run, `rep2`; 24 of 24 correct, 0 stale):

| Graph | Setup before | Setup after | Turn after change before | after | Session compute before | after |
|---|---|---|---|---|---|---|
| Pokec | 73 s | 27 s | 75 s | 30 s | 83 s | 36 s |
| LiveJournal | 124 s | 35 s | 139 s | 45 s | 161 s | 68 s |
| Orkut | 253 s | 47 s | 272 s | 62 s | 295 s | 81 s |

Against the Opus agents of 3.10 (compute seconds, not rerun): warned agent 50 / 160 / 580, independent agent
97 / 361 / 898. GraphAudit is now below both correct agents on all three graphs. The agents' setup in 3.10 (about
320 s in total) was measured with the old file-facts reader, which they share, and would shrink as well.

### 3.12 Appending in place when the edge file only grew (2026-11-23)

`t2r/graphs.py: append_in_place`, called from `Session._refresh`. If the first `n_bytes` of the file are unchanged
(hash) and the new rows are integer pairs, the rows are added to the loaded graph; the file statistics are updated
exactly from the graph and the semantics inferred again. It declines, and the file is loaded in full, when the result
could differ from a full load: header, text ids or weight column; node table changed too; a new id that sorts between
old ones or leaves a gap; a self-loop appended to a file that had self-loops; an appended pair already present under
an undirected reading; reciprocity within reach of a decision threshold; inferred semantics would change; more new
rows than half the old ones. The reason is kept in `graphs.APPEND_DECLINED`; `T2R_APPEND=0` switches it off.
Edge order can differ from a full load's (no effect beyond floating-point rounding). Tests: `tests/test_append.py`
(equality with a full load for directed and undirected readings, eight decline cases, session answers equal to a
fresh session); 41 tests pass.

GraphAudit large sessions (Haiku, one run each; all 24 of 24 correct, 0 stale):

| Graph | Turn after change: old loader | new loader, full reload (`rep2`) | new loader, append (`rep3`) | of which computing the answer | Session compute: old | reload | append |
|---|---|---|---|---|---|---|---|
| Pokec | 75 s | 30 s | 13 s | 3 s | 83 s | 36 s | 19 s |
| LiveJournal | 139 s | 45 s | 29 s | 10 s | 161 s | 68 s | 52 s |
| Orkut | 272 s | 62 s | 30 s | 13 s | 295 s | 81 s | 50 s |

What is left of the turn after a change is igraph rebuilding its index after `add_edges` (5 / 10 / 15 s), the
profile card, and recomputing the answer. Setup is unchanged from 3.11 (27 / 35 / 47 s).

### 3.13 Open models: Qwen3 served on our own GPU (2026-11-23)

Question: does GraphAudit work with a free open model, so that the model bill is zero? `t2r/llm.py` now talks to any OpenAI-compatible server (`T2R_BASE_URL`); `slurm/run_open_model.sbatch` starts the server on the job's own GPU (Ollama with 4-bit weights, or vLLM 0.10.2 with the published weights; `slurm/setup_vllm.sbatch` builds the vLLM environment, pinned to `vllm==0.10.2 transformers<5` because the cluster driver supports CUDA 12 only). One run each; temperature 0.

GraphAudit on the 22 E2b sessions (122 turns, 47 trap turns):

| Model | Server | Correct | Stale | Model seconds | Model cost |
|---|---|---|---|---|---|
| Claude Opus 5.5 | API | 122 | 0 | - | $5.86 |
| Claude Haiku 5.5 | API | 122 | 0 | - | $0.16 |
| Qwen3-32B | vLLM, H100 | 121 | 0 | 2,932 | 0 |
| Qwen3-32B | Ollama, 4-bit, H100 | 114 | 0 | 3,298 | 0 |
| Qwen3-14B | vLLM, RTX 6000 Ada | 116 | 0 | 4,567 | 0 |
| Qwen3-14B | vLLM, forced JSON | 98 | 0 | 2,516 | 0 |
| Qwen3-14B | Ollama, 4-bit | 106 | 3 | 3,572 | 0 |

On the three full large graphs (E4 sessions, 24 turns) Qwen3-14B answers 24 of 24 on both servers, no stale answer.

- Every Qwen failure but a handful is a plan the validator rejected (unknown step reference, wrong value type, text that is not JSON): GraphAudit reports an error, it does not answer wrongly. The same questions fail across regions: the count over "those 10", and the scores computed on the whole network then restricted to a district.
- The three stale answers (14B, 4-bit) have one cause: the turn that set a standing setting ("treat every friendship as mutual") came back unparseable, the setting was never recorded, and the next three turns used the old reading. To fix: a failed turn that carried a setting must be retried or flagged on later turns.
- Forcing JSON output (`T2R_JSON_MODE=1`) halves model time and lowers accuracy (more plans with wrong step types); cause not confirmed, probably no reasoning before the answer. Left off.
- Latency is the price: about 24 s of model time per turn for 32B on an H100 and 37 s for 14B on an RTX 6000 Ada, thinking included. The servers were not compared on the same GPU.

Stateful code agent with Qwen3-14B on the same sessions: 2 of 122 correct on Ollama and 0 of 122 on vLLM, mostly because the cell ends in a bare JSON object instead of printing it. With `T2R_AGENT_NOTEBOOK=1` (the harness shows the value of the last expression as a notebook does; off by default, Claude baselines unchanged) it gets 32 of 122 with 4 stale; the rest are wrong answers and igraph calls that do not exist. The same model behind GraphAudit gets 116: a typed plan over a fixed catalogue is within reach of a 14B model, free-form graph code is not.

Summaries: `prototype/results/sessions/open_models/`. Not done: repetitions, 32B on the large graphs, a no-thinking run, a larger open model.

### 3.14 What a session costs: reuse, prompt caching, plan replay (2026-11-24)

Question: how much is reused in a realistic session, and what does that do to the bill? Haiku 5.5 is now the default model (`T2R_MODEL` overrides).

Workload: four sessions on full Pokec (1.6M users, 30.6M friendships, node table), 43 turns, in `bench/sessions/workload_practice.py`, run with `slurm/run_practice.sbatch`.

- `campaign` (10 turns): one PageRank, then cuts of it by gender, region and list length.
- `refresh` (10): a morning dashboard, 27,466 friendships are appended, the dashboard again in other words.
- `hubs` (8): the network with and without its five largest hubs.
- `dashboard` (15): a saved report of five questions run word for word three times, with the same append after the first run. Written to exercise plan replay, so it is a best case for it.

Three switches, all off by default:

- **Reuse** (the `full_noreuse` variant turns it off): stored step results, as before.
- **Prompt caching** (`T2R_PROMPT_CACHE=1`): GraphAudit sends the catalogue, the session rules and the profile card as a cached prefix (the turn number moves into the message). The code agents send their instructions, the file facts and the conversation so far as a cached prefix that grows by one turn; the text they see is unchanged.
- **Plan replay** (`T2R_PLAN_REPLAY=1`): a question repeated word for word runs its earlier plan with no model call, only if that plan declared intent "new", no reference to an earlier turn, no setting, no open reading, and the settings and reading in force are the same. The plan is validated and executed on the data as it then is, so a data change in between is still caught by the lineage keys.

All four sessions, model fees and query compute (graph loading excluded: about 28 s per session for GraphAudit, inside the compute figure for the agents). Opus: one run. Haiku: three runs, shown as the range of correct answers and the mean of the rest.

| System | Opus correct | Opus stale | Opus fees | Opus compute | Haiku correct | Haiku stale | Haiku fees | Haiku compute |
|---|---|---|---|---|---|---|---|---|
| GraphAudit, cache + replay | 43 | 0 | $0.71 | 62 s | 42 | 0 | $0.020 | 74 s |
| GraphAudit, cache | 43 | 0 | $0.94 | 66 s | 42–43 | 0 | $0.027 | 69 s |
| GraphAudit | 43 | 0 | $2.14 | 64 s | 43 | 0 | $0.056 | 66 s |
| GraphAudit, no reuse | 43 | 0 | $2.13 | 154 s | 41–43 | 0 | $0.057 | 203 s |
| Stateful agent, cache | 41 | 2 | $0.62 | 158 s | 29–30 | 5–6 | $0.026 | 141 s |
| Stateful agent | 33 | 5 | $1.20 | 129 s | 29–30 | 5–6 | $0.048 | 218 s |
| Warned agent, cache | 43 | 0 | $0.89 | 473 s | 33–40 | 2–5 | $0.032 | 356 s |
| Warned agent | 43 | 0 | $1.78 | 545 s | 37–40 | 2–5 | $0.056 | 306 s |
| Independent agent, cache | 43 | 0 | $0.99 | 950 s | 43 | 0 | $0.033 | 654 s |
| Independent agent | 43 | 0 | $1.71 | 908 s | 42–43 | 0 | $0.058 | 676 s |

What it shows:

- **Reuse saves compute, not fees.** 42 steps are reused over the 43 turns; query compute goes from 150–200 s to about 65 s; fees do not move, because the model writes a plan every turn.
- **Without caching GraphAudit is the dearest in fees** (about 9,200 input tokens per turn against 5,000–7,200 for the agents): its prompt carries the whole catalogue.
- **With caching on both sides fees are about equal.** Opus: GraphAudit $0.94, warned agent $0.89, independent agent $0.99. Do not claim a fee advantage from caching alone.
- **Plan replay is a fee saving on verbatim repeats only.** On `dashboard` GraphAudit makes 6–7 model calls for 15 turns and costs $0.11 on Opus against $0.27–0.32 for the cached agents, all 15 answers right including those after the append. On the other three sessions it skips at most one call.
- **Compute is the robust gap**: about a fifteenth of the independent agent's on Opus, a tenth on Haiku; a seventh and a fifth of the warned agent's.
- **Stale answers depend on the model.** Haiku stateful agents are stale in every run (always on the turns after the append). The warned agent on Opus was right on all 43 turns in its one run, cached and uncached, so on these sessions the correctness case against it rests on Haiku and on E2b.

Caveats:

- GraphAudit on Haiku misses `hubs` turn 7 ("And without them, the PageRank top 20?") in 4 of 9 runs with reuse on: it reads "them" as the ten users of the previous answer, as rule S3 says. The wording is ambiguous and is mine; Opus reads it as intended. Not caused by caching or replay (no replay happens in that session).
- The practice sessions were written by us, on one graph. One Opus run.
- At $1 per hour for a 16-core, 128 GB machine (an assumption), 600 s of compute is $0.17: more than the whole Haiku fee, small next to the Opus fee.

Summaries and per-session totals: `prototype/results/sessions/practice/` (`by_session.json`). Not done: an outside baseline; a second graph; replay for repeats that are not word for word; the agents' equivalent of replay (re-running stored code for a repeated question) was not built.

### 3.15 Repetitions of the session benchmarks (2026-11-24)

Correct answers per run (stale answers in brackets). Claude calls send no temperature, so repetitions differ naturally.

E2b, 22 sessions, 122 turns, 47 trap turns:

| System | Haiku 5.5, 5 runs | Opus 5.5, 3 runs |
|---|---|---|
| GraphAudit | 122, 122, 122, 122, 122 [0] | 122, 122, 122 [0] |
| Stateful agent | 118, 107, 109, 112, 112 [2, 6, 3, 2, 4] | 117, 114, 114 [5, 6, 5] |
| Warned agent | 120, 120, 114, 118, 119 [0, 0, 0, 1, 0] | 121, 122, 122 [0] |
| Independent agent | 120, 111, 122, 122, 118 [0] | 121, 122, 122 [0] |

E4, three full large graphs, 24 turns, 6 trap turns:

| System | Haiku 5.5 | Opus 5.5, 3 runs |
|---|---|---|
| GraphAudit | 24 in each of 6 runs [0]; compute 119–185 s | 24, 24, 24 [0]; 118–122 s |
| Stateful agent | 13, 13, 13, 13 [6, 5, 5, 6]; 303–342 s | 13, 13, 13 [6, 6, 6]; 131–418 s |
| Warned agent | 12, 13, 15, 13 [6, 6, 5, 6]; 349–495 s | 24, 24, 24 [0]; 590–874 s |
| Independent agent | 23, 23, 24, 23 [0]; 1,065–1,667 s | 24, 24, 24 [0]; 1,357–2,017 s |

(The first run of GraphAudit on each model, 540 s, used the loader that 3.11 replaced.)

Qwen3-14B on vLLM, GraphAudit, E2b: 116 at temperature 0; 110 and 114 at temperature 0.6 (seeds 2, 3); no stale answer. The Qwen3-32B repetitions are still waiting for an H100.

What the repetitions support:

- GraphAudit is the only system that is fully correct in every run on both models (8 runs of E2b, 9 of E4).
- The unwarned stateful agent gives stale answers in every run, on both models.
- Telling the agent to check works with Opus and not with Haiku: the warned Opus agent matches GraphAudit's answers, at 5 to 7 times the compute on the large graphs; the warned Haiku agent is still stale on 5 or 6 of the 6 large-graph traps.
- So the claim is not "agents cannot get this right". It is: GraphAudit gets it right by construction, with a small model, at the lowest compute, and shows why; an agent gets it right only with the strongest model, a warning, and recomputation.

### 3.16 An outside baseline: LangGraph CodeAct (2026-11-24)

`langgraph-codeact` 0.1.3, the framework's own loop, prompt and conversation memory; we supply the sandbox (the same persistent Python process our stateful agent uses) and the task text (same file facts, same answer format). Variants: plain, and warned (the same warning paragraph our warned agent gets). Haiku 5.5, 3 runs each, no prompt caching (framework default). Ranges over runs.

| workload (turns) | system | correct | stale | fees | compute |
|---|---|---|---|---|---|
| E2b (122) | GraphAudit | 122 | 0 | $0.16 | |
| | our stateful agent | 107–118 | 2–6 | | |
| | CodeAct | 103–114 | 1–4 | $0.13–0.18 | 232–310 s |
| | our warned agent | 114–120 | 0–1 | | |
| | CodeAct warned | 111–117 | 0–2 | $0.17–0.22 | 276–340 s |
| E4 large (24) | GraphAudit | 24 | 0 | | 118–185 s |
| | our stateful agent | 13 | 5–6 | | |
| | CodeAct | 13–14 | 6 | $0.03–0.04 | 302–414 s |
| | our warned agent | 12–15 | 5–6 | | |
| | CodeAct warned | 15–20 | 2–6 | $0.03–0.05 | 318–603 s |
| practice (43) | GraphAudit (cache, replay) | 42 | 0 | $0.020 | |
| | our stateful agent (cache) | 29–30 | 5–6 | $0.026 | |
| | CodeAct | 30–33 | 5–6 | $0.045–0.047 | 140–359 s |
| | our warned agent (cache) | 33–40 | 2–5 | $0.032 | |
| | CodeAct warned | 41–42 | 1 | $0.069–0.080 | 721–759 s |

Reading:

- The framework agent behaves like ours: same level of correct answers, the same stale answers on the same kind of turn. Our stateful baseline was not a weak one.
- The warning helps CodeAct more than it helps our agent on the practice sessions (41–42 against 33–40) and it pays in compute (about 740 s against 140–359 s): it recomputes. On E4 the warning is not enough with Haiku: 2, 5 and 6 stale answers in the three runs.
- CodeAct makes about two model calls per turn (code, then the answer), so its fees are above our agents'.
- Blank cells: not measured in the same configuration; fill from 3.9, 3.10 and 3.14 runs before the paper.

### 3.17 Sessions we did not write: first pass on Twitch (2026-11-24)

Writers: Claude Opus 5.5 (10 sessions, 80 questions) and Qwen3-14B (10 sessions, 52 questions), each given only a brief and the dataset description (`bench/sessions/write_sessions.py`). Runner: `bench/sessions/run_written.py` (answers stored, not scored; a question that announces a refresh gets a real append first). GraphAudit runs on Haiku 5.5 with the new `unsupported` outcome (rule S9); when it asks which scope reading is meant, a simulated user (Haiku, sees the persona, the questions so far and the two contracts) answers: 7 times A, 2 times B. Reference: the independent script agent on Opus 5.5 (answered all 132, $2.89). Comparison: `compare_written.py` (loose match), then an Opus judge on the rest (`judge_written.py`, $0.22). One run.

| GraphAudit (Haiku) on 132 questions | Opus-written (80) | Qwen-written (52) | all |
|---|---|---|---|
| same values as the reference | 45 | 34 | 79 (60%) |
| incomplete: ingredients or part of the answer, nothing conflicting | 5 | 3 | 8 |
| different from the reference | 12 | 2 | 14 (11%) |
| unsupported, with the missing capability named | 13 | 10 | 23 (17%) |
| asks a question back | 3 | 0 | 3 |
| error (invalid plan, engine error) | 2 | 3 | 5 |

Compute: GraphAudit 50 s for all 132 turns (plus 98 s loading), the Opus script agent 497 s.

What this says:

- On our own sessions GraphAudit is right on every turn; on questions written without knowledge of the catalogue it matches the reference on 60%. The claim "right by construction" holds for what the catalogue expresses, not for what analysts ask.
- 14 answers differ from the reference and were given without a warning. Not all are GraphAudit's fault (the reference is a model too: 4,354 against 4,335 reached users, 3,632 against 3,589 for a percentile are open), but several are: after two unsupported turns the planner answered a different quantity (s10), and a year filter returned other years. Each needs a hand check before a number goes into the paper.
- The 8 incomplete answers have one cause: no arithmetic on results. The plan returns the two counts and not their difference or complement.
- Missing capabilities named in the 23 unsupported turns and behind most incomplete ones: arithmetic on scalars; edges between two node groups (mixing matrix, attribute assortativity); quantiles and binning of a node map; correlation between two node maps; range filters on dates; aggregating an attribute over each node's neighbours; neighbourhoods of a node set; a node map from a partition.
- Engine bugs found: `float() argument ... not 'list'` on two share questions; a list passed as a filter value.
- The first runner always chose reading B when GraphAudit asked; that produced wrong group averages (mean degree of affiliates 34 instead of 72) and was replaced by the simulated user. Those runs (rep1) are not used.

Pokec and LiveJournal results are in 3.18.

### 3.18 Catalogue extended from 59 to 73 operators; Pokec and LiveJournal as the held-out test (2026-11-24)

The 14 operators were chosen from the Twitch failures only (3.17): `arithmetic`, `edges_between`, `edges_touching`, `mixing_matrix`, `attribute_assortativity`, `neighbour_aggregate`, `neighbours_in_set`, `neighbourhood_of_set`, `membership_map`, `map_arithmetic`, `map_quantile`, `map_bins`, `group_by_map`, `map_correlation`. Also: text filters (`startswith`, `contains`, date ranges, a list of values), rule S10 (state the value asked for, not its ingredients). Pokec and LiveJournal sessions were not looked at before the additions, so they measure whether the additions generalise.

Same protocol as 3.17: GraphAudit on Haiku 5.5 with the simulated user, one run per column; reference = independent script agent on Opus 5.5 (answered 427 of 429, $12.06); Opus judge on answers the loose match does not accept ($0.6 to $0.7 per pass). "same" = loose match or judged same. Table: `bench/sessions/table_written.py`.

| writer, graph (questions) | catalogue | answered | unsupported | asks back | error | same as reference | incomplete | different |
|---|---|---|---|---|---|---|---|---|
| Opus, Twitch (80) — design graph | 59 | 62 | 13 | 3 | 2 | 45 | 6 | 11 |
| | 73 | 76 | 2 | 0 | 2 | 66 | 2 | 8 |
| Qwen, Twitch (52) — design graph | 59 | 39 | 10 | 0 | 3 | 33 | 3 | 3 |
| | 73 | 50 | 0 | 1 | 1 | 47 | 1 | 2 |
| Opus, Pokec (76) — held out | 59 | 44 | 29 | 3 | 0 | 33 | 3 | 8 |
| | 73 | 57 | 19 | 0 | 0 | 50 | 1 | 6 |
| Qwen, Pokec (70) — held out | 59 | 61 | 4 | 1 | 4 | 46 | 6 | 9 |
| | 73 | 63 | 3 | 1 | 3 | 50 | 5 | 8 |
| Opus, LiveJournal (81) — held out | 59 | 40 | 40 | 1 | 0 | 26 | 2 | 12 |
| | 73 | 47 | 33 | 1 | 0 | 32 | 0 | 15 |
| Qwen, LiveJournal (70) — held out | 59 | 57 | 11 | 0 | 2 | 33 | 1 | 23 |
| | 73 | 57 | 7 | 1 | 5 | 35 | 1 | 21 |
| **all (429)** | 59 | 303 | 107 | 8 | 11 | 216 (50%) | 21 | 66 |
| | 73 | 350 | 64 | 4 | 11 | 280 (65%) | 10 | 60 |

Regression: E2b stays 122 of 122, 47 of 47 traps, 0 stale in four runs with the larger catalogue (rep11ops to rep13ops, rep14fix).

What this says:

- On the design graph the additions close the gap: Twitch unsupported 23 to 2, same-as-reference 78 to 113 of 132. This number is optimistic by construction and must be labelled so.
- On the held-out graphs the gain is real but smaller: unsupported 84 to 62 of 297, same-as-reference 138 to 167 (46% to 56%). The operators generalise where the questions overlap (Opus-written Pokec: same 33 to 50); they do not cover what only directed graphs raise.
- What is still unsupported on the held-out graphs, by family: per-user reciprocity and the graph of mutual friendships (about 35 of the 62; one family, two operators would cover it: reciprocated-neighbour count per node, mutual-edge subgraph); per-edge attribute differences (age gap across an edge, 4); arithmetic on node ids (shard = id mod 64, 4); ratio of two grouped tables and row sums of a mixing matrix (4); sampled average path length (2); which rows are new after an append (3); a significance test (1). Adding these now would use up the held-out set: any further addition needs a new unseen set (the published task lists of G6) to be reported honestly.
- No unsupported turn gave a wrong value; each names the missing capability.

The "different" column, read by hand from plans and reference scripts (not recomputed):

- LiveJournal, Qwen-written, 21 different: about 18 have one cause. The file has 68,993,773 rows of which 518,382 link a user to themselves (counted on the cluster); GraphAudit leaves self-loops out (68,475,391 edges) and did not say so; the reference counts raw rows. Both are defensible, the silence is not. Fixed: the graph reading now carries a `self_loops` line that the planner sees and is told to state. Three more are population against sample standard deviation.
- Twitch, Opus-written, 8 different: 4 are another reading that the other side lists as its variant (edge share against edge-end share; neighbours counted with or without the 20 seed users, 4,354 = 4,335 + 19); 1 is Louvain's randomness; 2 are GraphAudit errors that passed every check (a "share" of 11.26 from ranking over all users instead of ES users; degree deciles where the previous turn defined views deciles); 1 open (betweenness ranking order).
- So "different" is not an error rate. A defensible split needs a hand label per row: same value under another stated convention / nondeterministic / GraphAudit wrong / reference wrong. Not done for Pokec and Opus-written LiveJournal (29 rows).
- Two checks follow from the GraphAudit errors: a value called a share or fraction must lie in [0, 1]; a turn that reuses "deciles" or "top group" must use the grouping variable of the turn it refers to.

Crashes found on the held-out graphs and fixed afterwards (so the 73-operator rows above still contain them): statistics of an empty set, division by zero in a share, components of an empty subgraph, `median` per attribute group, a non-numeric threshold. `std` added to `map_stats` and the grouping operators. A rerun after the fixes (rep4): answered 360, unsupported 60, error 4, same 277, incomplete 7, different 76. Errors drop from 11 to 4 (3 of the 4 came from the division-by-zero fix itself, which evaluated the division for every `arithmetic` step whose second operand was 0; corrected after rep4, tests pass, not rerun); "same" does not move, and "different" moves by 16 between two runs of the same system on Qwen-written sessions, where questions are vague ("fastest-growing languages", "top influencers") and each run picks a definition. One run per cell is not enough for these; repeat three times before quoting.

Compute for all 429 turns: GraphAudit about 1,900 s (rep4; one LiveJournal session in rep3 took 11,000 s on a slow exact computation, to look at), the Opus script agent 5,400 s.

### 3.19 Reciprocity operators (75), then the published task lists as the unseen test (2026-11-24)

**Two operators for the largest unsupported family of 3.18**: `mutual_degree` (per node, the number of nodes linked in both directions) and `mutual_graph` (the undirected graph of reciprocated links). Catalogue 73 to 75. Pokec and LiveJournal are no longer held out from here on: these operators were chosen after reading their questions.

Same 429 model-written questions, GraphAudit on Haiku, same Opus reference:

| operators | answer | unsupported | clarify | error | same as reference | incomplete | different |
|---|---|---|---|---|---|---|---|
| 59 (rep2) | 303 | 107 | 8 | 11 | 216 (50%) | 21 | 66 |
| 73 (rep3) | 350 | 64 | 4 | 11 | 280 (65%) | 10 | 60 |
| 75 (rep6) | 394 | 27 | 3 | 2 | 305 (71%) | 7 | 82 |
| 75, mutual graph without isolated nodes (rep7) | 390 | 27 | 5 | 5 | 310 (72%) | 7 | 72 |

- Opus-written LiveJournal: unsupported 33 to 14, same 32 to 47 of 81. Opus-written Pokec: unsupported 19 to 8, same 50 to 59 of 76.
- Two mistakes of mine on the way, both found by reading results and both fixed: (1) the new operators carried a cost label the estimator did not know, so every plan using them was rejected as too expensive (rep5, 38 errors; `t2r/ir.py` now knows the label); (2) `mutual_graph` first kept users with no mutual tie, which gave 426,975 "communities" on Pokec against the reference's 6,530 and an average local clustering of 0.077 against 0.104. It now leaves them out unless `keep_isolated` and says so in its description (rep7: 6,509 against 6,530, the rest is Louvain's randomness).
- "Different" is still 72 to 82 and moves by about 10 between runs. Read by hand in this round: LiveJournal counts that differ by the users whose only link is a self-loop (3,919,375 against 3,950,121; GraphAudit now says "self-loops excluded" in the answer); unseeded Louvain; one session where turn 1 returns an empty group and the two systems then follow different groups. No hand label per row yet.
- Still unsupported (27): per-edge attribute differences (age gap), arithmetic on node ids (id mod 64), sums over rows or the diagonal of a mixing matrix, sampled average path length, comparison with the graph before an append, per-edge triangle tests, a significance test, a seeded Louvain.
- Regression: E2b 122 of 122, 47 of 47 traps, 0 stale (rep15recip).

**Published task lists (G6 source 2), the test nobody here designed for.** `bench/sessions/workload_published.py`: the 10 task types of GraphArena, the 8 of NLGraph, and the further types of the benchmarks GraphTeam is evaluated on (GraphInstruct, Talk like a Graph, GraphWiz; LLM4DyG and GNN-AutoGL have no counterpart on these graphs), restated on Twitch, Pokec and LiveJournal: 101 questions, each standing alone. We chose the wording, the node ids (by degree only) and the subgraph sizes for the tasks the benchmarks pose on small graphs (the 50 highest-degree users for clique, independent set, vertex cover; two small ego networks for common subgraph and edit distance). Reference: the independent Opus script agent, 100 of 101 answered, $3.05.

First run, 75 operators, before anything was changed (p1):

| graph | questions | answer | unsupported | same as reference | incomplete | different |
|---|---|---|---|---|---|---|
| Twitch (undirected) | 33 | 21 | 12 | 20 | 1 | 0 |
| Pokec (directed) | 34 | 22 | 12 | 16 | 1 | 5 |
| LiveJournal (directed) | 34 | 20 | 14 | 16 | 0 | 4 |
| **all** | 101 | 63 | 38 | 52 (51%) | 2 | 9 |

- **38 unsupported, no error, no wrong value among them.** They are the same task types on every graph: maximum clique, maximum independent set, minimum vertex cover, maximum common subgraph, graph edit distance, travelling salesman, maximum flow, maximum matching, Hamilton path, depth-first visit order, the heaviest triangle, induced 4-cycles (and exact triangle counting on LiveJournal, declined for cost). All six NP-complete tasks of GraphArena are outside the catalogue. The script agent answered all of them on the 50-node subgraphs. This is the honest coverage number for combinatorial tasks: the catalogue is an analytics catalogue, and the paper must say so and point to the fallback (G7).
- **What it answers, it answers like the reference on the undirected graph (20 of 21), not on the directed ones.** Of the 9 different, 6 have one cause, and it is ours: the question says "ignoring direction" and the plan uses `mode=all` on the directed graph, which counts a pair linked both ways twice. Results: user 0 listed twice as a common neighbour, 10 common neighbours where there are 5, a "cycle" found in a tree, neighbour sums 4 times too large, a diameter of 15 against 11. No check flagged any of them. The other 3: two are the self-loop convention on LiveJournal (stated in our answer), one is a number given where a yes or no was asked.
- This is the most useful result of the round: a silent error class that our own sessions never produced, because we never wrote "ignoring direction" on a directed graph.

Fix, after the first run and therefore reported separately: operator `undirected_graph` (one edge per pair linked in either direction; catalogue 76), `neighbours` returns each neighbour once, and the description of `degree` says what `mode=all` counts. Rerun (p2): same 58 (57%), incomplete 2, different 3 (two self-loop conventions, one yes where the reference says no on the ordering task, which the first run got right), unsupported 38. E2b 122 of 122 (rep16und). The 51% is the number to quote as unseen; 57% is after a fix made with the answers in view.

Also fixed in the comparison: a bare yes against a bare no used to count as agreement (no numbers on either side). It no longer does; one turn of the 3.18 table moves from "same" to unjudged.

Open after this round: a check that would have caught the direction error without the reference (when the question says "ignoring direction" or "linked in either direction" and the graph is directed, the plan must go through `undirected_graph` or `mutual_graph`); the fallback for the 38 (G7); hand labels; three repetitions.

### 3.20 Checked code fallback for requests outside the catalogue (2026-11-25)

Decision (2026-11-25): the 38 declined tasks of 3.19 are covered by a fallback to generated code, not by more operators. Built in `t2r/fallback.py`, switched on with `T2R_CODE_FALLBACK=1` or `Session(code_fallback=True)`; off by default, so every earlier number is unchanged.

How it works when the planner returns `unsupported`:

1. A second planner call (same prompt prefix, so it is read from the prompt cache) returns catalogue steps that prepare the inputs (select the nodes, induce the subgraph, drop direction), the names under which they are handed over, and a task statement for a programmer. These steps are validated, costed, reused and stored like any plan.
2. Two functions `solve(inputs)` are written by two separate model calls that do not see each other, one told to prefer igraph, the other to avoid igraph's routine for the core computation. Each runs in its own process on the prepared inputs. Neither reads the graph file.
3. Same value from both: outcome `answer by code`, with the findings `outside_catalogue` (warning, always) and `code_cross_check`. Different values, a failure or a refusal (the writers are told to raise an error when an exact result is not feasible): outcome `unconfirmed`, no answer, the candidates are shown. Code results are not stored for reuse.

What the check covers and what it does not: loading and reading of the graph are the engine's; an implementation slip in one function is caught by the other. Both writers read the same task statement, so a wrong reading of the question passes. The witness (members, path) is not compared.

Published task lists, GraphAudit on Haiku against the Opus reference (101 questions):

| run | answered | of which by code | unconfirmed | unsupported | same as reference | code answers same / different | incomplete | different |
|---|---|---|---|---|---|---|---|---|
| p2, no fallback (3.19) | 63 | 0 | 0 | 38 | 58 (57%) | | 2 | 3 |
| p3, fallback, first run | 99 | 34 | 1 | 0 | 88 (87%) | 31 / 2 | 6 | 5 |
| p4, after one instruction fix | 98 | 34 | 1 | 1 | 90 (89%) | 33 / 1 | 3 | 5 |

- All six NP-complete GraphArena tasks, maximum flow, matching, Hamilton path, depth-first order, heaviest triangle, induced 4-cycles and the exact triangle count on LiveJournal (285,730,264, 148 s) are now answered with the reference's value. The one withheld turn is a vertex cover on LiveJournal where one function refused its own result.
- An error that passed the cross-check in p3: on LiveJournal both functions ordered node ids as text ("103117" before "39243") in the depth-first search. The writers' instruction now says to compare numeric ids as numbers (p4). This is the kind of error two writers share.
- The code answer still different in p4: maximum flow on the LiveJournal top-1000 subgraph, 20 against the reference's 21. Not yet decided who is right.
- The other "different" rows are from the plan path, not the code: the self-loop convention on LiveJournal (2), and the ordering task answered "yes" on Pokec and LiveJournal although the subgraph has directed cycles (an error of ours, present before the fallback on LiveJournal).
- Fees on Haiku: about $0.07 per graph for 34 questions, against $0.03 without the fallback.

Model-written sessions (429 questions), where the questions are conversational:

| run | answered | by code | unconfirmed | unsupported | error | same as reference | incomplete | different |
|---|---|---|---|---|---|---|---|---|
| rep7, no fallback | 390 | 0 | 0 | 27 | 5 | 310 | 7 | 72 |
| rep8, fallback | 402 | 13 | 13 | 0 | 3 | 309 | 12 | 81 |

- Of the 27 formerly unsupported turns, 13 got a confirmed code answer and 13 were withheld. The withheld ones are mostly right to be withheld: exact computations on 68 million edges that a function refused or that ran past the 300 s limit, a count of raw file rows that the loaded graph cannot give, a seeded Louvain. In 5 of the 13 a candidate equalled the reference.
- **Of the 13 confirmed code answers, 8 are the same as the reference and 5 differ.** On precise single-shot questions the cross-check holds (33 of 34); on conversational follow-ups it does not, because the error is in the task statement, which both writers share. Not hand-labelled yet: at least one of the five is a difference of layout (a list of counts against its minimum, maximum and deviation).
- So the fallback raises coverage, not agreement, on these sessions (309 against 310 same). A confirmed code answer must be shown as a lower grade of answer than an operator answer; the interface and the paper must say so.

Regression: E2b 122 of 122, 47 of 47 traps, 0 stale with the fallback code in place and switched off (rep17fb). Tests: 57 pass (`tests/test_fallback.py`: agreement gives an answer, disagreement gives none, prepared inputs are reused, the switch off leaves the turn unsupported).

**Hand check of the 6 code answers that differ from the reference (2026-11-25).** Read from the task statements, both sides' scripts and, for LiveJournal, a direct recomputation on the cluster under both conventions.

| turn | ours | reference | verdict |
|---|---|---|---|
| published, LiveJournal: maximum flow in the top-1000 subgraph | 20 | 21 | self-loop convention. Ranking by in-degree with self-loops counted gives another 1000th user (4 users of the top 1000 change): 21 with them, 20 without. Both reproduced. |
| Opus-written LiveJournal s05 t3: edges per shard, min / max / deviation | 1,053,003 / 1,096,044 / 8,096.4 | 1,061,052 / 1,104,331 / 8,114.4 | self-loop convention. Both reproduced; our counts sum to 68,475,391. |
| Opus-written LiveJournal s05 t8: edges with both ends in one shard | 976,990 | 1,495,372 | self-loop convention: the difference is exactly the 518,382 self-loops. For a question about stored rows the reference's count is the one the user wants. |
| Qwen-written Pokec s04 t3: regions with the highest share of women | includes regions with 1 user | only regions with at least 1,000 users | two readings. The question names no minimum; the reference added one and lists ours as its variant. |
| Opus-written Pokec s06 t5: regions with the highest share of links to another kraj | 10 krajs | 10 regions | **ours wrong.** The task statement changed the unit from region to kraj; both functions implemented it faithfully. |
| Opus-written Pokec s02 t8: accounts in the refreshed group but not in the earlier one | the refreshed group (2 accounts) | none | **ours wrong.** The earlier group was no longer available; the task statement said so and asked for the refreshed members instead. The right outcome was to decline. |

- So of the 47 confirmed code answers (34 published, 13 written): 2 wrong, 1 another defensible reading, 3 right under our self-loop convention, 41 the same as the reference. Both errors are in the task statement, none in the code.
- The self-loop convention is now the largest single source of "different" on LiveJournal, in plans and in code alike. A code answer carries it only in the task statement, not in the answer shown. Decide before the paper: keep self-loops out and print the note with every count, or keep the rows and exclude them per operator.
- Guard added after the check: the instruction for the input-preparing call now says to answer in the unit the user named, and to return `unsupported` again when a needed input cannot be prepared; the engine then leaves the turn unsupported (`code.declined`). One rerun of the two Pokec sessions: s02 t8 is declined with the reason, s06 t5 is answered per region with the reference's regions. One run each, not a rate. Tests: 58 pass.

**Self-loops: decided 2026-11-25, keep them out of the graph and print the note with every answer.** Every answered turn, by plan or by code, now carries `conventions`, e.g. "518,382 of the 68,993,773 rows link a node to itself; they are left out of the graph, so counts of rows, links and degrees do not include them" (`conventions()` in `t2r/session.py`; empty when the file has no such rows). Checked on one LiveJournal session of the published tasks: all 16 turns carry it. E2b 122 of 122, 0 stale (rep18note); 59 tests pass. Not done: the interface does not show the field yet; the comparison with the reference still counts these turns as "different" (the judge does not see the note); a question about the raw rows themselves (how many self-loops, how many rows) still has no operator and is declined.

Open: the task statement as the weak point (candidates: show it to the user as the contract of the turn; have the second writer restate the question from the conversation instead of sharing the statement); the two new outcomes in the UI; the fallback has not been run on Opus or on the practice sessions.

### 3.21 Three repetitions of the written and published sets, and guards on the answer (2026-11-25)

Same setting as 3.20 (Haiku 5.5, prompt cache, checked code fallback), three new runs of each set (written: reps 11 to 13; published: p11 to p13), compared with the same Opus reference and judged by Opus ($2.48 for the six passes). The earlier single runs (rep 8, p4) are shown for comparison.

| set | run | answered | same | incomplete | different | by code: same / different | unconfirmed | unsupported | error |
|---|---|---|---|---|---|---|---|---|---|
| written (429) | 8 | 402 | 309 | 12 | 81 | 8 / 5 | 13 | 0 | 3 |
| | 11 | 406 | 316 | 8 | 82 | 8 / 7 | 11 | 2 | 4 |
| | 12 | 399 | 316 | 11 | 72 | 8 / 5 | 12 | 3 | 7 |
| | 13 | 404 | 317 | 9 | 78 | 9 / 5 | 12 | 1 | 7 |
| published (101) | p4 | 98 | 90 | 3 | 5 | 33 / 1 | 1 | 1 | 0 |
| | p11 | 100 | 93 | 2 | 5 | 35 / 2 | 0 | 0 | 0 |
| | p12 | 98 | 88 | 6 | 4 | 31 / 1 | 2 | 1 | 0 |
| | p13 | 95 | 87 | 5 | 3 | 28 / 1 | 1 | 0 | 4 |

- Ranges to report: written, same 316 to 317 of 429 (74%), different 72 to 82; published, same 87 to 93 of 101, different 3 to 5.
- Per question over the three runs: written, 290 same in all three, 84 in none, 55 in one or two; 57 are "different" in all three (a stable disagreement with the reference, the first candidates for the hand labels) and 40 in one or two. Published: 81 same in all three, 3 different in all three.
- The 4 errors of p13 are one fault: the planner wrote an operator named `code_task` (a field of the fallback, not an operator) in LiveJournal s01 t7; the plan was rejected, and the next three turns failed with `KeyError` because the session state looked up the unknown operator of the failed turn. Fixed (`Session.state`), test added. The run is reported as it ran.
- E2b with the guards in place (rep19guards): 122 of 122, 47 of 47 traps, 0 stale.

**Guards (`guards()` in `t2r/verify.py`).** Four checks made from errors found by hand in 3.18 to 3.20: direction ignored in the question but not collapsed in the plan; a value asked for as a share outside [0, 1]; a follow-up that bins by another variable than the turn it builds on; a yes/no taken from a labelled comparison. They add a failed finding and do not change the answer. First version of the share check fired on questions that only mention a share or "top 1%" (26 flags in the new runs, none a real error); it now requires the question to ask for a share, or an answer key named as one. `table_written.py` evaluates the guards again on the stored plans, so all runs are held to the current rules.

Result: the guards do not find the disagreements. Written: 2 answers flagged per run, of which 1 "different" over the three runs (of 232). Published: 3 to 5 flagged per run, all the comparison check, 1 "different" over the three runs; the other 11 flags are on answers that match the reference. The errors they were made from do not recur often enough to matter; what remains "different" has to be read by hand before anything is claimed about it.

**Hand labels of the 60 stable disagreements (2026-11-25).** The questions judged "different" in all three runs (57 written, 3 published; `bench/sessions/stable_differences.py`). Evidence: each reference script prints variants next to its main answer, which the runs had not stored; `bench/sessions/rerun_reference.py` ran the 60 scripts again on the cluster (no model calls; 59 of 60 main answers reproduced) and tested our answers against every variant. The rest was read from the plans and scripts. Labels and notes per question: `bench/sessions/hand_labels_stable.json`.

| label | n | what it means |
|---|---|---|
| self-loop convention | 35 | our value equals, in all three runs, the value the reference script itself prints for "self-loops excluded" (LiveJournal has 518,382 such rows; GraphAudit leaves them out and says so with the answer) |
| another reading the reference lists | 5 | our value equals another of its variants: seeds counted in their own 2-hop reach, the overall top 2 instead of the last list's, "age = 0" taken literally (no such user; 2 questions), no minimum region size |
| open choice in the question | 5 | cut-off of "top 1%" (2), age groups, "highly connected", which "top 5 languages"; in 2 of these our choice also changes between runs |
| randomised or sampled algorithm | 5 | Louvain (3; the operator takes no seed although the question names one), sampled betweenness (2; one with 125 sources where 1,000 were asked, one approximate by the budget rule with 14 of the top 15 the same users) |
| same list, cut differently | 1 | both give the start of a 416,294-user list |
| GraphAudit wrong | 8 | "them" / "that group" resolved to the previous answer's set instead of the group named (3, one inherited); counts where a reciprocated fraction was asked; same-region pairs where different regions were asked; region where kraj was asked; highest where lowest was asked; one unstable value matching no variant |
| reference wrong | 1 | the group is empty in both systems (its own turns 1 and 2), yet it answers "true" about the group's members |

- So of the 60 stable disagreements, 8 are errors of GraphAudit and 1 of the reference; 40 are the same computation under a convention or reading the reference itself lists, and 11 are choices or algorithms where no match is expected.
- The self-loop convention alone is 35 of 60: the judge compares against the reference's main answer and does not see the convention note. Comparing against the reference's "self-loops excluded" variant where it exists would be the fairer test; not done for the whole set (it needs the variants of all 429 + 101 scripts, about an hour of cluster time, no fees).
- None of the 8 errors was flagged by a guard or any other check. Three share one cause (the referent of "them" / "that group"), which a check could target: when the question refers back to a group, compare the set the plan starts from with the set that the turn defining the group selected.
- Not labelled: the 40 written and 2 published questions that are "different" in only one or two of the runs.

**Referent check (2026-11-25, `referent()` in `t2r/verify.py`, finding `guard_referent`).** Fires when all of these hold: the question refers back ("them", "those", "that group", ...); the turn it builds on selected a group and reached its answer set from that group through links (neighbours, reach), so the two are different populations; and this turn's new steps continue from the answer set only. It does not say which set is meant; it says which one was taken and names the other, with sizes. A narrowed group ("of those, how many ...") is not flagged. A fault inside any guard can no longer cost a turn its answer (`guards_not_run`).

- On the stored plans of runs 11 to 13: 7 flags in 1,209 answered turns. 5 are the two independent referent errors of the hand labels (LiveJournal s01 t5 in all three runs, Pokec s02 t6 in two; in the third run the plan has another shape), 2 are one Twitch question ("Of those reached users, ..."; same as the reference in one run, different in the other, not labelled). The inherited error (s01 t6) is not flagged: it builds on the flagged turn.
- A first, wider version (either set, any derivation) fired 81 times, 59 of them on answers that match the reference; that version is not kept.
- E2b with the check in place (rep20referent): 122 of 122, 47 of 47 traps, 0 stale; no referent flag and no guard fault on its 122 turns. 65 tests pass.
- Caution: the rule was narrowed on the same runs it is measured on. What it does on questions it has not seen is not known; the next set of fresh sessions is the test.

Open: a seed argument for `communities`; judging against the matching variant; whether the comparison check should stay a warning, since most of its flags are on correct answers.

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

### E2b. Sessions where reusing an earlier result is wrong (designed 2026-11-22; built and run the same day, results in 3.9)

Why: the E2 pilot (3.8) does not separate GraphAudit from a notebook-style code-generation agent, because nothing
in those sessions punishes keeping a variable. These sessions do. Each has turns where an earlier result looks
reusable but is not (**trap turns**) and turns where it is (**valid-reuse turns**), so both stale answers and
needless recomputation are measured.

**Six trap classes.** Each is something that happens in ordinary analysis sessions, and each matches an ingredient
of the lineage key tested in E1.

| class | what happens in the session | what goes stale | key ingredient |
|---|---|---|---|
| R1 reading changed | "Treat friendships as mutual from now on" / "ignore the trust strengths" / "count repeated emails once", then a follow-up or "again" | every measure computed under the old reading | graph reading |
| R2 data changed, announced | "I appended this week's friendships to the file" (the harness rewrites the file), then "who is top now?" | the graph in memory and everything derived | content hash |
| R3 data changed, unannounced | the harness rewrites the edge file or node table between turns; the user only asks the next question | same | content hash, node table |
| R4 name shadowing | a ranking for one group, then the same request for another group, then "the first group's top 10 again" or "the overall top 10 again" | a variable or step name that now holds the other group's result | input lineage |
| R5 upstream change | "use damping 0.9 from now on" or "that estimate used 100 samples, use 1000", then a question about a result derived from the old one (which districts, how many are male) | the derived result | input lineage |
| R6 base altered | "remove the 5 best-connected users: how many components now?", then "on the full network, ..." | the base graph, if it was edited in place | input lineage |

One more, scored as consistency and not as a trap: **R7 randomness**. "How many communities?" then "how large is
the biggest?" must describe the same partition. An agent that recomputes with another seed gives two answers that
cannot both hold.

**Session shape.** 6 to 8 turns: two or three ordinary turns to build state, one event, one or two trap turns, one
valid-reuse turn (for R1: "back to directed: the top 10 again", where the first result is valid again), one
unrelated turn. About 14 sessions and 100 turns over the three Pokec regions, trust, emails and roads; about 30 trap
turns and 20 valid-reuse turns. Two sessions run on full Pokec (1.6M nodes, 30M edges) so that reloading has a
visible price.

**Scoring.** Gold is the gold plan run on the graph as it is at that turn (file version and reading). For each
trap turn the stale answer is also computed, as for the two scope readings, so every answer is one of: correct,
**stale** (equals what the outdated state gives), or otherwise wrong. Reported per class: stale rate, correct rate;
on valid-reuse turns: correct rate, execution time, and whether work was redone. Trap turns where the stale and the
correct answer happen to coincide are dropped before any system is run.

**Systems.**

| system | note |
|---|---|
| GraphAudit full | as in E2 |
| code generation, stateful | prompt reworded to be neutral: the sentence "do not reload the file if the graph is already in memory" is removed |
| code generation, stateful, warned | adds one sentence: the file may change between turns and earlier variables may be out of date; check before reusing |
| code generation, independent | recomputes everything: cannot be stale except through the conversation text; the cost ceiling |

The warned agent is the strong competitor. If it stays correct by reloading and recomputing every turn, the result
is a price (execution time, largest on full Pokec), not an error rate, and that is what gets reported.

**Fairness rules, fixed before any run.**
- Sessions, wording and gold are written and frozen first; no rewording after seeing a system's answers. A pilot
  on one session per class checks only that the harness works.
- R3 is reported separately from the rest and described for what it is: no agent is told anything changed.
- Stale-answer counts are reported for GraphAudit too, with every failure listed.
- Three repetitions; Opus and Haiku.

**What GraphAudit needed first** (all built on 2026-11-22 with tests; the reading change already worked through the plan's interpretation):
- The session keeps the loaded graph and does not look at the file again, so R2 and R3 would be served stale
  today. It needs a cheap per-turn check (size and modification time, then the hash) that drops the loaded graph.
- A reading change stated in words has to reach the load override; today the override is set only by the
  accept-semantics call. The planner needs a way to return it.
- R6 needs "all nodes except these" as a set (set_difference against the node set) feeding `induced_subgraph`;
  to confirm the planner finds it.
- R5 needs damping and sample count as planner-visible arguments (they are) and "from now on" kept in the session
  state as a standing setting (it is not).

**What the outcome decides** (by Dec 13, with the title decision):
- Stateful agents give stale answers on announced classes (R1, R2, R4 to R6) and GraphAudit does not: reuse goes in
  the title, with this table.
- Only R3 separates them, or only the unwarned agent fails: the claim is the guarantee and the audit record (E1 plus
  the demo), and this table is one supporting row.
- Nothing separates them: drop the comparison, keep E1, and make the paper about the auditable contract.

Estimated effort: 2 days for the GraphAudit prerequisites, 2 days for workload and harness, about $40 of model
calls for three repetitions.

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

*First part (sessions with an unannounced change) run 2026-11-22, results in 3.10. The budget sweep below is not started.*

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

### Three-minute signature session (Pokec)

Fixed 2026-11-25 to what the numbers support. The script is data (`prototype/demo/signature.json`: questions, the file change, and the presenter's line for each step); `demo/make_session.py --script` plays it on a copy of the files and records `demo/sessions/pokec.json`, which the session page replays without a server or a model. Recorded on Haiku 5.5, 7 turns, 15 model calls, about one cent.

| step | what is asked or happens | what the screen shows | recorded result |
|---|---|---|---|
| 1 | Who are the 10 most influential users? | plan, reading of the file, measure chosen | PageRank, 4 steps executed |
| 2 | Which region is each of them from? | drill-down, reused steps marked | 2 reused, 1 executed |
| 3 | Show the top 20 instead. | parameter patch | scores reused |
| 4 | the edge file grows by 27,466 rows; nobody tells the system | a "data changed" card | |
| 5 | the same words as step 1 | plan replayed with no planner call; `data_changed`; nothing reused | two new users lead the ranking |
| 6 | ... within region X? | two contracts, nothing runs until one is chosen; B chosen, then A shown | the two top-10 lists differ |
| 7 | largest group of mutual friends among the top 20 | declined by the catalogue, inputs prepared by 4 checked steps, two functions agree, marked "answer by code" | 5 users |
| close | | ledger: 6 steps reused, 20 executed, 1 turn replayed, 61% of tokens read from the prompt cache, 1 answer by code; audit record | |

The budget decision on a large resident graph (requested against allowed betweenness pivots) is no longer in the three minutes; it stays as a single-question scene.

UI state 2026-11-25 (`demo/static/session.js`, `session.css`), checked in the browser against the recording and against edited copies of it for the two outcomes the recording does not contain:
- outcomes `Not supported` (reason shown, no answer), `Answered by code` (amber grade box saying what was and was not checked; "Generated code" opens the task statement, the inputs and both functions with their values), `Not confirmed` (both candidates, no answer);
- the convention note under the answer and in the ledger; a card for a data change; ledger lines for replayed turns, share of tokens from the prompt cache, data changes, answers by code, declined requests;
- recorded mode shows the presenter's line for each step and a closing line.
**Live path, checked 2026-11-25.** The server offers the script's graph for live sessions: `server.py --live <edge file> --script demo/signature.json` (`slurm/demo_server.sbatch`; job 308828 on itiger07, Haiku). A session on it runs on a working copy in node `/tmp`, with replay and the code fallback on. The page lists the script's questions as chips and has a "Change the data file" button (`POST /api/session/event`), which appends the rows on disk and tells the session nothing. All seven turns were driven through the page over an SSH tunnel and gave the recorded outcomes: computed, partial reuse twice, the data-change card, the repeat replayed with no planner call and the change noticed, two contracts then B then A (4 of 10 shared), and the answer by code (5 users, same members as the recording). 15 model calls, $0.011, start of the session about 35 s (copy and load of Pokec), turns 5 to 30 s. The generated-code view and the audit record open live. Reach: the server listens on the node's loopback only; `ssh -N -L 8772:localhost:8765 -J <login> <node>`.

Seen in the live run: "Show reading A instead" makes A the reading in force for later turns (the ledger says so); the recording puts B back. Decide which the demo wants. "Not supported" and "Not confirmed" did not occur live (the script does not produce them); they are checked on edited recordings only.

**Side by side with the stateful agent, built 2026-11-25.** Page `demo/static/compare.html` (third tab of the header), data `demo/compare/refresh.json`, built by `demo/make_compare.py` from two stored runs of the practice session `pokec/refresh` and calling no model: stateful agent `runs/practice/claude-haiku-5-5/codegen_stateful-cache/rep1` (job 307147) and GraphAudit `full-cache-replay/rep1` (job 307150), both Haiku, commit 20e1e0a. One row per turn, the two answers next to each other, each with the harness's verdict (correct / stale / wrong), compute time and model calls; the file change is a card between turns 4 and 5; ids that differ from the correct list are marked and the correct answer is printed under the row when either side is wrong. For the agent the row quotes the line of its own code that decides the reuse (turn 5: "# Reuse the PageRank vector from turn 2 if it is still in the session; otherwise recompute it.") and opens the whole script; for GraphAudit it says what was reused and that the change was noticed. Totals of this run: agent 5 of 10 correct, 3 stale, 2 more wrong after the change, 19 s compute, $0.006; GraphAudit 10 of 10, 0 stale, 48 s compute with loading (29 s of it), $0.005. The page says it is one run on Haiku and that the agent's result depends on the model and on the warning (3.14: the warned agent on Opus was right on every turn). Checked in the browser, light and dark, and at phone width. The server serves the record at `/api/compare`; that route was checked by calling the handler, not through a running server.

Not done: recordings of the dashboard session and of GraphAudit's refresh session in the session page (the side-by-side covers refresh); the single-question page is unchanged and has no link to the other two pages; the GraphAudit run in the side-by-side predates the code fallback and the convention note (neither applies to these ten questions).

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
| Session state and compact planner context | done Nov 22 | Dec 3 |
| Intent classes and four plan-patch types | first version Nov 22; engine-side derivation of the patch type open | Dec 8 |
| Reuse checks and the three-outcome decision | first version Nov 22; reference ambiguity ("again") open | Dec 8 |
| Self-reviewing code-generation baseline; silent-failure column in the scorer | 2 days | Dec 3 |
| Stateful code-generation agent baseline | built Nov 22, pilot in 3.8 | Dec 8 |
| Reuse fault-injection harness (E1) | done Nov 22, first run in 3.6 | Dec 10 |
| Session workload, annotated (E2) | first version Nov 22 (14 sessions, 82 turns), pilot in 3.7; code-generation agents in 3.8; needs sessions where reuse is wrong | Dec 10 |
| UI: session view (timeline, reused-versus-executed plan, savings, two-contract chooser, audit record, plan editing) | built Nov 22; replay checked in the browser, live endpoints checked by script | Dec 20 |
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

1. ~~Name~~ Decided 2026-11-22: GraphAudit. GraphCompass was checked and is taken (Bioinformatics 2024, PyPI package). Related system to cite and position against: GraphSeek (arXiv 2602.11052).
2. Confirm Pokec with its profile table as the session graph.
3. Author list, with a CMT account and ORCID for each.
4. Whether reviewers get a public demo URL or only the video; where the video is hosted.
5. Whether to rename the repository and the `t2r` package now or after submission.

## 12. Closing the gaps before submission (written 2026-11-24)

Eight gaps were listed after the cost runs. Status and plan for each, in the order to do them. Submission is Jan 9, UI freeze Dec 20.

### G1. Caching fairness for the baselines — closed

The code agents now use prompt caching (3.14). With caching on both sides the fees are about equal. Nothing further; the paper must not claim a fee advantage from caching.

### G2. Model fees on repeats — closed for word-for-word repeats, one extension

Plan replay is in (3.14). Extension, 1 day, by Dec 1: replay when the question differs only in case, punctuation and filler ("again", "once more", "now", "please", "show"/"show me"), under the same safety conditions. Measure on `refresh` (its repeats are worded this way) and on E2b, where a wrong replay would show as a wrong or stale answer. Keep it only if E2b stays at 122 of 122 in three runs. Also build the same thing for the independent agent (re-run the stored script for a repeated question), so the comparison stays fair.

### G3. Lost standing setting — closed (2026-11-24)

Cause (3.13): a turn that set a standing setting came back unreadable, the setting was never recorded, later turns used the old reading. Fix, in `t2r/session.py`: (a) a reply that cannot be read as a plan is asked for once more, with a larger output limit; (b) a turn that still fails is shown to the planner next to the new question as an earlier request that got no answer, with rule S8 telling it to apply a lasting request from such a turn; (c) later answers carry the finding `earlier_turn_unanswered`.

Verification on E2b (122 turns, 47 traps):

| model | run | correct | stale | turns with no answer |
|---|---|---|---|---|
| Qwen3-14B (Ollama), before the fix | 3.13 | 106 | 3 | |
| Qwen3-14B, first version of the fix (a + JSON state only) | 2 runs | 111, 111 | 1, 1 | 9, 9 |
| Qwen3-14B, final fix | 1 run | 110 | 0 | 10 |
| Haiku 5.5, final fix | 1 run | 122 | 0 | 0 |
| Haiku 5.5, first version (with and without cache+replay) | 2 runs | 122, 122 | 0, 0 | 0, 0 |

The stale answers are gone. What is left on Qwen3-14B are turns with no answer at all (the model's reply is still unreadable after the second request) and the turns that depend on them; these are visible failures, not silent ones. One Qwen run only for the final fix: repeat twice before quoting it.

### G4. Variance — mostly closed

3.14 and 3.15 give 3 to 6 runs for Haiku and 3 for Opus on E2b and E4; 3.21 gives 3 runs of the written and published sets. Left: the Qwen3-32B repetitions (queued), two more Opus runs of the practice sessions (about $12), and reporting every table in the paper as a range, not a single run.

### G5. Outside baselines — 5 days, by Dec 6

*Status 2026-11-24: LangGraph CodeAct done on Haiku, results in 3.16. Opus (1 run, about $25 for both variants on E2b) not run: needs a yes. GraphTeam not started.*

Two systems we did not write, both run with the same models and the same file facts:

1. **LangGraph CodeAct** (`langgraph-codeact`): a standard agent framework whose agent keeps Python variables between turns. It is the framework version of our stateful agent, so it tests whether our baseline was a weak one. Adapter: `bench/sessions/run_langgraph.py` implementing the same `ask(question)` interface as `Codegen`; variants plain and warned. Run on E2b, E4 and the practice sessions, Haiku 3 runs, Opus 1 run.
2. **GraphTeam** (BUPT-GAMMA, arXiv 2410.18032): a published multi-agent system for graph analysis with public code. It was built for benchmark problems with the graph in the prompt, so it may not take a 30M-edge file or a multi-turn session. Try it on E2b (graphs of about 100K edges) turn by turn with the conversation in the question; report plainly what it can and cannot run.

If GraphTeam cannot be made to run in 2 days, replace it with a plain LangGraph tool-calling agent with a Python REPL tool and say so. GraphSeek (arXiv 2602.11052) has no public code that we found: related work only.

Done when: one table with our three agents and the outside systems on the same turns, same scoring.

### G6. Workload independence — by Dec 10 (decided 2026-11-24: no human writers, models and published tasks)

Sessions we did not write, from two sources:

1. **Models that are told nothing about the system.** `bench/sessions/write_sessions.py` gives a writer model only a brief (what a conversation with an analyst's assistant looks like; no catalogue, no rules, none of our sessions, no word about reuse or stale answers) and a dataset description. Two writers from different families, Claude Opus 5.5 and Qwen3-14B, 10 sessions of 6 to 10 questions per graph. Questions are kept word for word.
2. **Published task lists.** The task types of GraphArena, NLGraph and GraphTeam's benchmarks, restated on our graphs. *Done 2026-11-24, 101 questions, results in 3.19.*

Graphs: full Pokec (node table) and LiveJournal (no table). A second graph with a node table needs a download (SNAP twitch-gamers is the candidate): ask first.

Gold answers: for each question a gold plan where the catalogue can express it, proposed by Opus with the catalogue in view and checked by hand; the answer is accepted as gold only when the independent Opus code agent, which sees neither the plan nor the catalogue, computes the same value. Disagreements are resolved by hand and counted. Questions no plan can express go to G7 and are scored against the code agent's answer after a hand check.

Limits to state in the paper: the writers are language models, one of them from the family that also plans; no human wrote a session. Report results per writer, never pooled with our own sessions.

### G7. Catalogue coverage — 3 days, by Dec 12, uses the G6 questions

Status 2026-11-25: fallback to checked code built and measured, results in 3.20 (published tasks 57% to 89% same as the reference, 34 answers by code of which 33 match; on model-written sessions 13 code answers of which 8 match). Status 2026-11-24: `unsupported` outcome built; first coverage numbers in 3.17 and 3.18 (model-written sessions: 65% same as the Opus reference, 15% unsupported with the reason, no wrong value on an unsupported turn). Open: hand labels for the differing answers, the reciprocity family, the fallback to checked code generation, the published task lists as a fresh unseen set.

For every question from G6: (a) can a gold plan be written with the operators (59 at the time of writing, 73 since 3.18, 76 since 3.19) (yes / yes after adding an operator, which one / no); (b) what GraphAudit does when the answer is no: an honest "not supported" with the reason, a clarification, or a wrong answer. The second number is the one that matters: an out-of-catalogue question must never produce a confident wrong answer. Build: an explicit `unsupported` outcome with the missing capability named, shown in the UI; then the fallback to checked code generation that section 8 lists as "hybrid fallback: confirm or build". Expect the NP-hard GraphArena tasks (TSP, maximum clique) to be out of scope; say so.

### G8. Demo deliverables — Dec 8 to Jan 9

| item | by |
|---|---|
| Fix the script of the signature session to what the numbers support: reuse, the two-contract moment, a data change caught, the cost ledger (fees, cache, replay, compute) | Dec 8 |
| UI: cost ledger with cached and replayed turns; `plan_replayed`, `data_changed`, `unsupported` and `earlier_turn_unanswered` shown in the timeline; side-by-side with the stateful agent on the refresh session | Dec 20 (freeze) |
| Recorded sessions for the booth with no network: Pokec signature, refresh, dashboard | Dec 22 |
| Paper: full draft from 3.9–3.15 with every number as a range | Dec 27 |
| Video, 5 minutes | Jan 3 |
| Cut to 4 pages, final read, submit | Jan 9 |

### Order and budget

Nov 24–Dec 1: G3 verification, G2 extension, G5 adapter. Dec 1–6: G5 runs, G6 model-written sessions. Dec 6–12: G6 gold plans and runs, G7. Dec 8 on: G8. Model fees: about $60 (Opus on the new baselines and sessions is most of it). If time runs out, cut in this order: GraphTeam, published task lists, the replay extension.

