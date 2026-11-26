# Notes on the first draft (2026-11-25)

Files: `main.tex`, `refs.bib`, `main.pdf` (built with `tectonic main.tex`; 4 pages, US letter, page 4 full since the 2026-11-26 update, which added the results of plan 3.23). No experiment, Slurm job or model call was made for the draft itself. Nothing is committed.

"Plan" below is `docs/sigmod27-demo-plan.md`.

## 1. What the call says (read 2026-11-25)

Source: https://2027.sigmodconf.hosting.acm.org/calls_sigmod_demos.shtml. It agrees with plan section 1.

- 4 US-letter pages **including** title, abstract, body and bibliography; same limit for the camera-ready.
- `\documentclass[sigconf,9pt]{acmart}`, latest template, margins and spacing unchanged; violations are desk-rejected.
- Not double-blind: names and affiliations must be in the PDF. Every author needs a CMT account and an ORCID.
- Deadline Monday January 11, 2027, 11:59 PM AoE; conflicts declared within 24 hours; notification March 8; camera-ready April 1.
- Video optional, up to 5 minutes, hosted online, URL in the abstract; "highly encouraged".
- The proposal should say what the audience sees and can do, and which parts are implemented and which planned.
- Submission site: https://cmt3.research.microsoft.com/SIGMODdemo2027.
- The demo call has no rule on AI tools; the research call it points to was not read.

## 2. Every number in the paper

| Where in the paper | Number | Source |
|---|---|---|
| Abstract, Sec. 2 | 76 operators | Plan 3.19 (catalogue 76 after `undirected_graph`); also 76 `@op` entries in `prototype/t2r/ops.py` |
| Abstract | Pokec, 30.6 million links | Plan 3.3 (30,622,564 rows) |
| Sec. 1 | 60 of 60 group restrictions give a different top-10; 3.7 of 10 shared on average | Plan 3.6 (E1, scope readings) |
| Sec. 1 | "in a pilot on sessions that contain no trap the two did not separate on accuracy" | Plan 3.8 (one run per cell) |
| Sec. 2 | files of up to 117 million links | Plan 3.3, 3.10 (Orkut, 117,185,083) |
| Sec. 2 | LiveJournal: 518,382 of 68,993,773 rows are self-loops | Plan 3.18, 3.20 (convention note) |
| Sec. 3 | Pokec: 1,632,803 users, 30,622,564 links | Plan 3.4; `prototype/demo/sessions/pokec.json` (card, ledger `data_changes`) |
| Sec. 3, step 2 | 2 steps reused, 1 executed | Plan 7 table; recording turn 2 |
| Sec. 3, step 4 | 27,466 rows appended | Plan 7 table; recording event text |
| Sec. 3, step 6 | the two top-10 lists share 4 users | Plan 7, live path ("4 of 10 shared") |
| Sec. 3, step 7 | four checked steps, 20-user subgraph, group of 5 | Plan 7 table; recording turn 7 finding ("prepared by 4 checked steps") |
| Sec. 3, ledger | 6 reused, 20 executed, 1 replayed, 15 model calls, about one cent, 61% of tokens from the cache | Plan 7; recording ledger (6, 20, 1, 15, $0.0106, 53,111 of 87,719 input tokens = 60.5%) |
| Sec. 3, live path | about 35 s to start, turns 5 to 30 s, all seven steps as recorded | Plan 7, "Live path, checked 2026-11-25" |
| Sec. 3, side by side | ten questions; agent 5 of 10 correct, 3 stale, 2 more wrong; GraphAudit 10 of 10; 19 s against 48 s of which 29 s loading; $0.006 against $0.005 | Plan 7, "Side by side with the stateful agent" |
| Sec. 3, side by side | warned agent on Opus right on every turn of this session | Plan 3.14 (43 of 43, one run, cached and uncached) |
| Sec. 4, key ingredients | 246 faults, 201 valid scenarios, nine graphs; full key 0 wrong, 390 valid steps reused; 12 (no node table) to 117 (no input lineage) | Plan 3.6 table |
| Table 1 caption | E2b: 22 sessions, 122 turns, 47 traps; three regions of Pokec plus two small graphs | Plan 3.9 |
| Table 1 caption | E4: 8-turn session on each of three graphs, 24 turns, 6 traps | Plan 3.10, 3.15 |
| Table 1 caption | runs per cell: E2b 5 and 3; E4 4 to 6 and 3; CodeAct 3 (Haiku) and 1 (Opus); GraphTeam 3 | Plan 3.15, 3.16, 3.23 |
| Table 1, E2b rows | GraphAudit 122 [0] both; stateful 107–118 [2–6], 114–117 [5–6]; warned 114–120 [0–1], 121–122 [0]; independent 111–122 [0], 121–122 [0] | Plan 3.15 |
| Table 1, E4 rows | GraphAudit 24 [0] both; stateful 13 [5–6], 13 [6]; warned 12–15 [5–6], 24 [0]; independent 23–24 [0], 24 [0] | Plan 3.15 |
| Table 1, CodeAct rows | E2b 103–114 [1–4], warned 111–117 [0–2]; E4 13–14 [6], warned 15–20 [2–6]; Haiku only | Plan 3.16 |
| Table 1, CodeAct Opus cells | E2b 108 [5], warned 109 [0]; one run each | Plan 3.23 |
| Table 1, GraphTeam row | E2b, Haiku, 81–85 [0–2]; three runs | Plan 3.23 |
| Sec. 4, stale answers | GraphTeam: 2 stale answers in one of three runs; about 900 s of compute (880–991 s); twice GraphAudit's fees ($0.36–0.38 against $0.16); 37–41 wrong, all on the Pokec regions; NetworkX PageRank 12 of 91 ranking turns correct, igraph 46 of 48 | Plan 3.23 |
| Sec. 4, baselines | what was substituted in GraphTeam (model client, sandbox, embeddings) | Plan 3.23; `prototype/bench/sessions/run_graphteam.py` |
| Sec. 4, coverage | 39–42 of the different written answers equal a printed variant, leaving 33–43; published: 1 per run | Plan 3.23 |
| Sec. 3, side by side | warned Opus agent right on every turn in three runs | Plan 3.23 (practice sessions, 43 of 43 three times) |
| Sec. 4, stale answers | stale only on the unannounced class, in one run per model | Plan 3.9 (by-class line) |
| Sec. 4, stale answers | warned Opus at 5 to 7 times the compute; 590–874 s against 118–122 s | Plan 3.15 (table and third bullet) |
| Sec. 4, stale answers | warned Haiku stale on 5 or 6 of 6 large-graph traps | Plan 3.15 |
| Sec. 4, stale answers | fees about equal with caching on both sides | Plan 3.14, G1 |
| Sec. 4, coverage | 429 questions, writers Opus 5.5 and Qwen3-14B, three graphs | Plan 3.17, 3.18 |
| Sec. 4, coverage | three runs: answered 399–406, by code 13–15, not confirmed 11–12, declined 1–3, error 4–7; same 316–317 (74%), incomplete 8–11, different 72–82 | Plan 3.21, runs 11 to 13 (by code = same + different by code per run: 15, 13, 14) |
| Sec. 4, coverage | 101 restated questions; first run 63 answered, 38 declined, 52 same; all six NP-complete GraphArena tasks declined | Plan 3.19, run p1 |
| Sec. 4, coverage | three runs after the fix, with the fallback: answered 95–100, same 87–93, different 3–5; by code 28–35 same, 1–2 different | Plan 3.21, runs p11 to p13 |
| Sec. 4, coverage | 57 written and 3 published questions different in all three runs; 290 and 81 same in all three | Plan 3.21, per-question bullet |
| Sec. 4, coverage | hand labels of the 60 stable disagreements: 35 self-loop convention, 5 another listed reading, 5 open choice, 5 randomised or sampled, 1 same list cut differently, 8 GraphAudit wrong, 1 reference wrong; none of the 8 flagged; 3 share the "them" cause; 40 written and 2 published not labelled | Plan 3.21, hand-label table and bullets; `prototype/bench/sessions/hand_labels_stable.json` |
| Sec. 4, errors | advisory notes flagged 1 of 232 differing written answers over three runs | Plan 3.21, guards (232 = 82 + 72 + 78) |
| Sec. 4, errors | 47 confirmed code answers: 41 same, 2 wrong | Plan 3.20, hand check |

## 3. Left out or softened because the evidence is thin

- **Written and published question sets** (updated 2026-11-25 from plan 3.21): now three-run ranges against a model reference. The paper says "different" is disagreement with the reference and that no answer is hand-labelled. The only percentage is 74% same on the written set. The unseen first run on the published tasks (63 / 38 / 52) is still one run and is labelled so.
- **Answer guards** (plan 3.21): described only as advisory notes that do not detect the disagreements; nothing is claimed for them.
- **Hand labels** (updated 2026-11-25 from plan 3.21): done for the 60 questions different in all three runs only, by one reader; the paper states both limits and that the 40 + 2 questions differing in some runs are unlabelled. The paper does not turn the labels into an error rate for the whole set. The hand check of 47 code answers (41 same, 2 wrong) is from the earlier single runs rep8 and p4 (plan 3.20) and is still quoted as such.
- **Warned agent.** The paper never says agents cannot avoid stale answers. It says the warned Opus agent matches GraphAudit's answers and what that costs, and the side-by-side paragraph repeats this.
- **Side-by-side numbers** are one run on Haiku and are presented as such.
- **GraphTeam and CodeAct on Opus** (updated 2026-11-26 from plan 3.23): both are in Table 1 for E2b. CodeAct on Opus is one run per variant and the caption says so. GraphTeam ran on Haiku only, with three parts of it replaced by ours, which the text states; its low accuracy is attributed in the text to a library default, not to sessions. Not run and marked so: either system on E4 with Opus, GraphTeam on Opus and on E4.
- **Left out on 2026-11-26 for space:** the Opus practice-session ranges of plan 3.23 (only "three runs" in the side-by-side paragraph uses them); CodeAct's turns without a JSON answer on Opus (2 and 5), which explain why its correct counts are below our agents'; the check of the variant recount against the hand labels (0 of 20 false matches).
- **Cut on 2026-11-26 to make room:** the sentence on semantic caches in Related Work (it had no citation), the verifier's second example, the breakdown of 11 hand labels into three classes, and wording in the attendee, status and caption text.
- **Accuracy against code generation.** Not claimed. The older single-question accuracy table (plan 3.3) and the verifier's recall on plan mutations (76 of 87) are left out: the raw outputs are not in the repository and the paper has no room to qualify them.
- **Compute advantage.** Only the E4 Opus comparison with the warned agent is quoted. Left out: the "fifteenth / tenth" ratios of plan 3.14 (one Opus run, sessions we wrote), per-graph timings of 3.10 to 3.12 (one run per cell), and the append-in-place timings. Note that the GraphAudit E4 compute ranges exclude each model's first run (540 s, old loader), and the agents' runs were not repeated with the new file reader; plan 3.11 says their setup, not their compute, would shrink.
- **Fees.** No fee advantage is claimed. Plan replay's saving on the `dashboard` session ($0.11 against $0.27–0.32) is left out: that session was written to favour replay.
- **Open models (Qwen3).** Left out entirely: one run per configuration, and one configuration gave 3 stale answers before the G3 fix.
- **E2 pilot (scope rule ablation, 6 silent other readings without the rule).** Left out: the plan itself reads it as a weakness of our planner prompt, and code agents picked the annotated reading without asking.
- **Unguarded error classes** are named in the paper: direction wording (fixed by an operator, no guard), the shared task statement of the fallback, which earlier result "again" means. Not named for space: a share outside [0, 1], reuse of "deciles" with the wrong grouping variable, a number given where yes or no was asked.
- **"Not supported" and "Not confirmed" in the interface** were checked on edited recordings only, not live (plan 7). The paper lists them as things an attendee may see; it does not claim they were exercised live.
- **Booth extras from plan 7** ("break the plan, press Audit", "force a reuse", "no file facts") are not in the paper: I could not confirm from the plan that each works in the current interface. Upload of an own edge list is mentioned because the single-question page and the server have it (`/api/upload`).
- **The "share 4 users" figure** for the two readings comes from the live run; the recording contains both lists and should be checked to give the same count before the camera-ready.

## 4. Gaps (numbers or facts that are missing)

1. Published tasks, runs p3 and p4: answered + not confirmed + unsupported is 100 of 101. The plan does not say what happened to the last question (an error, or the question the reference did not answer). The paper quotes only "answered 98, matched 90".
2. Number of runs per E4 Haiku cell is read off the lists in plan 3.15 (6 for GraphAudit, 4 for the agents); the plan does not state it in words.
3. Hand labels cover only the 60 stable disagreements; no second reader; the 40 written and 2 published questions that differ in one or two runs are unlabelled (plan 3.21). The total of published answers by code per run is not in the plan table (same + different gives 29 to 37; another session reported 30 to 38), so the paper gives only the same / different split.
4. No cross-check of the reference answers with a second engine (plan 3.3: the NetworkX check did not finish).
5. Video URL: placeholder in the abstract.
6. Author list, e-mail addresses and ORCIDs (plan 11, item 3). The draft has one author and no e-mail address, on purpose.

## 5. Figures (made 2026-11-26, in `figs/`)

| Figure | File | What it is | Size in the paper |
|---|---|---|---|
| 1 (one column) | `figs/fig1-architecture.pdf` | Architecture, drawn in TikZ (`figs/src/fig1-architecture.tex`) | 4.0 cm tall |
| 2 (full width) | `figs/fig2-session.pdf` | Three crops of the session page (recorded Pokec session, the turn with two readings) with callouts (a) to (d); composed in `figs/src/fig2-session.tex` | 7.3 cm tall |
| 3 (one column) | `figs/fig3-compare.png` | Side-by-side page, file-change card and turn 5 with details open (the agent's quoted code line) | 5.3 cm tall at 0.68 of the column |

- The screenshots come from the pages as they are (`prototype/demo/static/session.html`, `compare.html`, recordings `sessions/pokec.json` and `compare/refresh.json`), taken with headless Chrome by `figs/src/shot.mjs` and the step files `s2.js` and `c1.js` against a local file server. For capture only, the question box is hidden and the ledger is given a narrow width.
- Figure 3 is now set at 0.68 of the column (about 5.3 cm tall) to make room for the 2026-11-26 results; the paper builds to 4 pages with page 4 full. `figs/fig3-compare-short.png` is Figure 3 without the details (4.6 cm at the same width; it does not show the code line the caption mentions).
- Text in Figure 2 is about 4 pt in print.
- The ledger in Figure 2 shows the totals at that turn (3 steps reused, 11 executed), not the end-of-session totals the text quotes (6 and 20).

## 6. References: all to be verified

`refs.bib` was written from memory without the papers at hand. Check every entry. In particular:

- **GraphSeek** (arXiv 2602.11052) has no author list or full title in the file, and the sentence about it rests on the summary in `docs/demo-paper-plan.md`, which says the full paper is still to be read.
- **SParC, CoSQL, Helix**: the plan (section 10) says these are to be read before citing; the sentences about them are one-line characterisations and need checking against the papers.
- The uncited sentence on semantic caching was cut on 2026-11-26.
- Not cited for space: GraphInstruct, Talk like a Graph, GraphWiz, the Pokec dataset paper, LangGraph itself, text-to-Cypher, GraphRAG.

## 7. Decisions in the draft that the author should confirm

- Title: the candidate of plan section 2. Plan 3.9 and E2b say reuse belongs in the title only if announced trap classes separate the systems; only the unannounced class did. The title still names reuse; the alternative title of plan section 9 is the fallback.
- The conference header is set with `\acmConference` to SIGMOD '27; copyright block suppressed for submission.
- CCS concepts are omitted (acmart warns, does not fail).
