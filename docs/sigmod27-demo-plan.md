# SIGMOD 2027 Demo Submission Plan

Date: 2026-11-21. Supersedes sections 2, 4 and 8 of `demo-paper-plan.md` (venue, build list, next actions); the
claim, scenario, outline, related-work table and risks there still stand unless changed below.

## 1. Fixed facts from the call

Source: https://2027.sigmodconf.hosting.acm.org/calls_sigmod_demos.shtml (read 2026-11-21).

| item | value |
|---|---|
| Submission deadline | **Monday, January 11, 2027**, 11:59 PM AoE (moved up from January 15) |
| COI declaration | within 24 hours of the deadline, per author, separate from the research track; missing it is a desk reject |
| Notification | March 8, 2027 |
| Camera-ready | April 1, 2027 (same 4-page limit) |
| Conference | June 13 to 18, 2027, Huntington Beach, CA |
| Length | 4 US-letter pages **including** title, abstract and bibliography |
| Format | `\documentclass[sigconf,9pt]{acmart}`, latest ACM template, margins untouched; violations are desk-rejected |
| Review | not double-blind; names and affiliations on the paper |
| Authors | every author needs a CMT account and an ORCID before submission |
| Video | optional, up to 5 minutes, hosted online, URL in the abstract; "highly encouraged" and used in selection |
| Judged on | what the audience sees, whether they can interact, the scenario; plus target users, architecture, key techniques, novelty |
| Also required | state clearly which parts are implemented and which are planned |

Seven weeks from today. Internal target: submit Saturday January 9, leaving two days of slack.

## 2. Where the project stands

Done and committed:

- Pipeline: loader, file facts, profile card, operator catalogue, typed plan IR with validator and cost model,
  verifier, planner and interpreter prompts, binary graph cache, resident-graph server.
- Six compared systems: full, no_verify, no_interp, flat, codegen, codegen_nofacts.
- Three benchmark sets (base 60, hard 27, scale 16) with a scorer, plus a fault-injection harness.
- Demo UI: standard-library server, single-page front end with file picker and upload, profile card, plan diagram,
  verifier findings, answer with variants, executor switcher, graph panel, guided replay of seven recorded scenes.

Not yet good enough for a submission:

| gap | why it matters |
|---|---|
| Accuracy tables are 0.94 to 1.00 everywhere | they cannot be the evidence; a reviewer reads them as an easy benchmark |
| One run per cell, no seeds, no variance | three-point gaps on 16 questions are not distinguishable from noise |
| Scale tier is synthetic preferential-attachment graphs | hub-dominated, easy for sampling; real graphs spread the approximation error |
| Verifier false-alarm rate on correct plans was never reported | 87% recall means little without the flag rate on unmutated plans |
| Verifier is weak on method swaps (12%) and in/out flips (57%) | either improve it or show the clarification path covering those cases |
| No interactive-latency numbers | a live demo is judged on response time; the reports only give batch wall time including load |
| Four related papers unread in full, GraphSeek among them | the closest system must be described from its text, not its abstract |
| UI has only been exercised by its author | scenes need a dry run by someone who did not build it |

## 3. Where things run

**No experiment runs on a laptop. Every experiment and every large-graph load goes to a remote server.** The
laptop is for editing, the paper, and a browser pointed at the server.

Servers, as surveyed over SSH on 2026-11-21:

| host | cores | RAM | free disk | tools | state when checked | role |
|---|---|---|---|---|---|---|
| `itiger.memphis.edu` (Slurm, partition `bigTiger`, 11 nodes) | 64 per node | 515 GB per node (773 GB on itiger01) | 7.1 TB on `/home` | uv, tmux, Python 3.9 | 2 nodes idle, 7 mixed; account limit 120 CPUs and 3 nodes; 28-day time limit | **all experiments** |
| `xzgpu2.uom.memphis.edu` | 32 | 62 GB (58 free) | 204 GB | Python 3.10; no uv, conda or tmux | idle apart from an ollama process | **demo server** |
| `xzgpu.uom.memphis.edu` | 40 | 93 GB (70 free) | 279 GB | uv, conda, tmux, Python 3.8 | busy: an 8-core job of ours and two of another user's | backup for either role |
| `xzws.uom.memphis.edu` | not checked | | | | key login refused from the laptop | unused until a key is installed |

All three reachable hosts, and an itiger compute node (tested with a one-minute job on itiger11), can reach both
`api.anthropic.com` and `snap.stanford.edu`, so LLM calls and dataset downloads work from inside Slurm jobs.

| question | answer |
|---|---|
| Environment | uv-managed Python 3.12 virtual environment in the project directory on each host, same lock file |
| Graphs and caches | on itiger `/home` (about 15 GB for the three real graphs plus binary caches); copied to the demo server once built |
| LLM access | `ANTHROPIC_API_KEY` in a mode-600 file on each host, exported by the job script (the `claude -p` backend is a development convenience, not for experiments) |
| Job control | Slurm array jobs on itiger, one array task per (set, model, seed); scale-tier tasks request 64 GB, the rest 8 GB |
| Concurrency | bounded by the API rate limit, not by the cluster; start with 3 workers per task as in the earlier runs |

Setup done on itiger on 2026-11-21:

- Project root `~/text2answer-sigmod27/`; repo cloned at commit `8906019`; Python 3.12 environment in `.venv`
  (versions in `requirements.lock.txt`).
- Real graphs in `~/text2answer-sigmod27/data/snap/`, row counts equal to SNAP's published edge counts:
  soc-pokec-relationships (30,622,564), soc-LiveJournal1 (68,993,773), com-orkut.ungraph (117,185,083).
- Job scripts in `slurm/`: `env.sh`, `fetch_snap.sbatch`, `run_set.sbatch` (one set, one model, one seed per array
  task; results under `prototype/runs/<set>/<model>/seed<k>/` with the commit hash recorded).
- Checked without model calls: `bench/make_questions.py` regenerates the 60 base questions byte-identically to the
  committed file (42 s); the demo server module imports with 54 operators and six systems.
- Not yet done: the API key file `~/.config/t2a/anthropic_key` (mode 600) does not exist, so no model run has
  been made on the cluster.

Found during setup: the raw per-run results of experiments 1 to 3 (`results*/raw/`) are git-ignored and are not in
the repository. Fault injection and re-scoring read them, so on a fresh clone both produce empty tables. Either
recover the raw directories from the machine that ran them, or treat the E4 reruns as the new source of plans.

To confirm: whether `xzgpu2` is reachable from outside the campus network without a VPN, which decides how the
booth laptop connects in June.

The demo server is separate from the experiment cluster because it must stay up: `demo/server.py --preload` keeps
the large graphs resident, and the presenting laptop reaches it over an SSH tunnel. That is also how the video is recorded, and how the booth demo runs, with the
recorded scenes as the offline fallback.

Reproducibility rules for every run: pinned model ids recorded in each result file, the git commit hash in the
summary header, a fixed seed list, one results directory per (set, model, seed), raw transcripts kept.

## 4. Experiments

Ordered by value to a 4-page paper. E1 to E4 feed the single results table and two sentences each; E5 and E6 are
there because the demo itself needs them.

### E1. Verifier precision and recall (headline number)

- Extend fault injection from the 60 base plans to the hard set and the new set (E3), so the mutation counts for
  `mode_flip`, `method_swap` and `use_weights` are no longer in single digits.
- Add the missing half: run the verifier on every **unmutated correct** plan and report the flag rate. Report
  precision, recall and the breakdown by check type.
- Try to close the two weak rows: for method swaps, a second independent computation and an agreement check; for
  in/out flips where the question names both directions, a forced clarification. Report before and after.
- No LLM calls except the optional agreement check. Hours, not days.

### E2. Real large graphs (replaces the synthetic scale tier)

- Graphs from SNAP: soc-Pokec (directed, 31M edges), soc-LiveJournal1 (directed, 69M), com-Orkut (undirected,
  117M). SNAP is reachable; download directly on the server.
- Same 16 question templates, regenerated ground truth. Where exact ground truth is infeasible (betweenness), use a
  high-pivot reference computed once and report the reference's own stability across seeds.
- Systems: full, flat, codegen. Three seeds each.
- New measurement: **budget sweep**. Vary the cost budget over two orders of magnitude and plot answer quality and
  wall time against it. This turns "the cost model cut 500 pivots to 125" from an anecdote into a curve.
- Report cold load, binary-cache restore and resident (zero load) separately from reasoning and execution time.

### E3. A benchmark that separates systems

About 50 new questions, descriptions withheld, aimed at what failed before:

- compositional depth 4 to 6 with intermediate constraints (where the flat agent ran out of turns);
- contestable approximations with a graded reference (sampled betweenness, approximate diameter, community counts);
- method-ambiguous questions where the right response is a clarification or labelled variants;
- questions outside the operator catalogue, to measure how often the typed path must fall back to code generation.

Before building, check whether the code-generation escape hatch inside the scaffold (the decision recorded in
experiment 2) is implemented or only decided. If it is not, either implement it or do not claim it.

### E4. Seeds and models on all sets

- Six systems on base, hard and the E3 set; three on scale. Three seeds. Models: Opus 5.5, Sonnet 5.5, Haiku 5.5.
- Report mean and range per cell, and cost per question (calls, tokens, USD, seconds).
- Size: (60 + 27 + 50) x 6 + 16 x 3 = 870 runs per (model, seed), about 7,800 in total. At the measured Opus cost of
  3 to 7 cents per question the Opus third is on the order of $150; Sonnet and Haiku are cheaper. Scale-tier runs
  dominate wall time, not money.

### E5. Interactive latency (needed for the demo)

With graphs resident on the server: time from question to answer, broken into planning call, validation,
execution, verification. Per size class. This is the number that says the demo is live rather than replayed.

### E6. Pilot with outside users (optional, only if E1 to E5 are done by December 13)

Three to five graduate students each ask ten questions of their own on a graph they did not prepare. Record how
many answers they accept, how many verifier flags they found useful, and what they asked that the catalogue could
not express. Two sentences in the paper, and the best source of audience questions for the booth.

## 5. Demo scenario for the booth and the video

Keep the four scenes of `demo-paper-plan.md` section 3 and change three things:

1. **Scene 4 uses a real graph** (LiveJournal or Orkut, resident on the server) with the cost decision shown live.
2. **Promote the no-facts scene from optional to scene 5.** It is the result with the largest measured effect and
   the easiest to understand on a screen: the row-number column read as a node.
3. **Add an audience scene: "break the plan".** The visitor takes a correct plan, flips one thing (direction,
   measure, in/out, a node) with a click, and watches the verifier flag it, or miss it. This is fault injection as
   an interaction, it answers the call's question "will they be able to interact with the system", and showing an
   honest miss is more convincing than claiming none.

Standing offers at the booth: bring your own edge list (upload already exists), or pick a question card for one of
the shipped graphs.

Video (5 minutes): scenes 1, 2, 5 and 4 in that order, about one minute each, then thirty seconds of "break the
plan". Recorded against the server, not from replay.

## 6. UI work

First step is an audit, not new code: run the server remotely, walk all seven scenes and three live questions per
shipped graph, and list what breaks. Known or likely items:

| item | note |
|---|---|
| "Break the plan" panel | new: plan step editor limited to the mutations the harness already implements, re-run without an LLM call |
| Side-by-side contrast | scenes 2, 4 and 5 compare two systems on one question; check whether the switcher shows them together or one at a time |
| Cost panel | must show requested tier, budget, chosen tier and estimated cost before the answer arrives |
| Clarification round trip | check that the user can answer a clarification in the UI and the plan is re-issued |
| Facts on/off toggle for code generation | needed for scene 5 |
| Large-graph view | a 117M-edge graph cannot be drawn; show the answer nodes with a sampled neighbourhood |
| Remote operation | server bind address, SSH tunnel, upload size limit, one job queue so two visitors do not starve each other |
| Offline fallback | every scripted scene replays from a recording if the network or the API is down |
| Screenshots for the paper | final ones taken after the UI freeze, light theme, at print resolution |

UI freeze: December 20. After that only fixes.

## 7. Paper

Four pages including references is tight. Budget:

| section | space |
|---|---|
| Abstract (with video URL) and introduction: the grounding gap, why query generation does not close it | 0.6 page |
| System: one architecture figure; profile card, typed plan, cost model, verifier, clarification | 1.1 pages |
| Demonstration: the scenes, with two screenshots, written as what the visitor does and sees | 1.1 pages |
| Evaluation: one table, plus one sentence each on E1, E2 and the no-facts ablation | 0.6 page |
| Related work, implemented-versus-planned statement, conclusion | 0.3 page |
| References, about 12 | 0.3 page |

Lead the evaluation with the three results that separate systems (verifier precision and recall, the budget curve
on real graphs, code generation without file facts). The accuracy table goes last and small.

Related work: read GraphSeek, Analytics-Augmented Generation, When the Tool Decides and the LLM+Graph workshop
summary in full, and search for anything since June 2026, before writing a word of positioning.

## 8. Schedule

| week | dates | experiments (remote) | UI and demo | paper |
|---|---|---|---|---|
| 1 | Nov 23 to 29 | server environment, pinned models, download real graphs, smoke-test one set end to end | audit on the server, issue list | read the four papers; set up the ACM template |
| 2 | Nov 30 to Dec 6 | E1 complete; E3 questions written and ground truth generated | "break the plan", cost panel, clarification round trip | architecture figure; system section draft |
| 3 | Dec 7 to 13 | E2 and E4 running; E5 measured | side-by-side contrast, facts toggle, large-graph view | introduction and related work draft |
| 4 | Dec 14 to 20 | reruns, analysis, results table frozen | dry run with an outside user; **UI freeze Dec 20** | evaluation section |
| 5 | Dec 21 to 27 | E6 if time allows | re-record all scenes on the frozen UI; screenshots | full draft |
| 6 | Dec 28 to Jan 3 | none | record and edit the video; host it | revision; cut to 4 pages |
| 7 | Jan 4 to 9 | none | none | final read, CMT entry, ORCIDs checked, **submit Jan 9** |
| | Jan 11 to 12 | | | deadline Jan 11; COI declarations by Jan 12 |

Weeks 5 and 6 cross the holidays; anything that needs two people at once should be done by December 20.

## 9. Open decisions

1. Confirm the server roles proposed in section 3 (itiger for experiments, xzgpu2 for the demo).
2. Author list, and a CMT account and ORCID for each author.
3. The system's name for the paper title ("text2answer" or another).
4. Model set for E4: Opus, Sonnet and Haiku 5.5 as proposed, or add a non-Anthropic model to show the scaffold is
   not model-specific.
5. Whether the hosted demo should be reachable by reviewers through a public URL, or only shown in the video.
6. Where the video is hosted.
