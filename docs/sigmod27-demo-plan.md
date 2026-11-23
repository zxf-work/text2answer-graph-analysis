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
