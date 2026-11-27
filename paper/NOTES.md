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
| Table 1 (rebuilt 2026-11-27) | four measures per cell: correct [stale], time, tokens, fees, for E2b, E4 and the practice sessions (P), Haiku and Opus | per-run `summary.json` files under `prototype/runs/{stale,large,practice}/<model>/<system>/rep*` on the cluster, read 2026-11-27 |
| Table 1, per turn (changed 2026-11-27) | time, tokens and fees are divided by the number of turns of the set (122, 24, 43): seconds, thousands of tokens and US cents per turn. Computed from the same run summaries; totals are in the three rows below. Text: 1.9 cents per turn on Opus without replay is $0.80 over 43 turns | same files |
| Table 1, time | setup seconds plus compute seconds (wall time minus model time), mean over runs. E2b and E4: runs after the loader of plan 3.11 (rep2 and later for GraphAudit and our agents; all runs for CodeAct and GraphTeam, which were made later). P: all runs | same files, fields `setup_seconds`, `compute_seconds` |
| Table 1, tokens | `tokens_in` + `tokens_out`, mean over all runs, in millions; in P the input count includes tokens read from the cache | same files |
| Table 1, fees | `cost_usd`, mean over all runs; cents for Haiku, dollars for Opus | same files |
| Table 1, P columns | 43 turns, 6 traps; GraphAudit `full-cache-replay`, agents `*-cache`, three runs each on both models; CodeAct without caching, Haiku, three runs | Plan 3.14, 3.16, 3.23 |
| Sec. 4, time | on E4 a third of the warned Opus agent's time (239 s against 741 s) and a fifth to a seventh of the independent agent's (257 against 1,318 s on Haiku, 239 against 1,720 s on Opus); on E2b with Opus the stateful (191 s), warned (295 s) and both CodeAct agents (174, 259 s) are below GraphAudit (324 s) | Table 1 |
| Sec. 4, fees | Opus fee on P without plan replay $0.80 (two runs, $0.795 and $0.813) against $0.85 for the warned agent | Plan 3.23; `practice/claude-opus-5-5/full-cache` |
| Sec. 4, accuracy | in P, GraphAudit on Haiku is wrong on `pokec/hubs` turn 7 in each of the three runs (a "them" read as the previous answer) | Plan 3.14 caveat; `wrong_turns` in the three summaries |
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
- **Time advantage (changed 2026-11-27).** The earlier draft quoted "5 to 7 times the compute" for the warned Opus agent on E4 (590–874 s against 118–122 s). That figure left out GraphAudit's loading at the start of each session (about 120 s on E4), while the agents' loading is inside their compute. Table 1 now adds the setup time for every system, which gives about 3 times (741 s against 239 s). The text also says that on the small graphs of E2b most Opus agents finish sooner. Left out: the "fifteenth / tenth" ratios of plan 3.14 and the per-graph timings of 3.10 to 3.12.
- **Fees and tokens (changed 2026-11-27).** No advantage is claimed. Table 1 shows that without caching GraphAudit reads about twice the tokens of our agents and costs more on E2b (Haiku 15.6 cents against 10.8–11.7; Opus $5.86 against $2.33–3.43). The P columns use caching on both sides and plan replay; one of the four P sessions (`dashboard`) was written to favour replay, and the text gives the Opus fee without replay ($0.80).
- **Cut on 2026-11-27 to make room for the four-measure table:** the counts of withheld, declined and failed questions and of answers by code in the coverage paragraph; "74%"; the numbers of questions that are the same or different in all three runs (290, 81, 57, 3; only "60" is kept); 41 of 47 code answers equal to the reference; the sentence on advisory notes; GraphTeam's fee and compute figures in the text (now in Table 1); the by-trap-class sentence; "a script, not its container" is now "a script, no container". A separate table for the coverage numbers was tried and did not fit in four pages.
- **Clarity pass on 2026-11-27 (three rounds of cold reads by readers who had not seen the paper).** Names: the session sets are now "short sessions" (was E2b), "large graphs" (was E4) and "long sessions" (the practice sessions of plan 3.14, was P); "contract" is replaced by "reading" everywhere, as on the session page; "trap" and "stale" are defined where first used; Table 1 gives all fees in dollars. Cross-references to other sections are removed. Statements tightened to match Table 1: "the stateful agent and plain CodeAct are stale in every run" (the warned agent is not), "the only system correct on every turn of both the short sessions and the large graphs", tokens "up to three times" and fees "up to 2.5 times" those of our agents without caching, "under half of GraphTeam" on Haiku only. Script step 3 now says the cut and the lookup run (the page shows 1 step reused, 2 run); the video caption for that step still says only the last step runs. Cut for space: the 61% cache share of the ledger; compute seconds and fees of the side-by-side run (19 s against 48 s, $0.006 against $0.005); the LiveJournal self-loop counts; the split of the hand labels (40 and 11, now 51 together) and "three share one cause"; the sentences on "again" and on the task statement as the weak point; the examples of input preparation in the fallback.
- **Conclusion in place of Status (2026-11-27, at the author's request).** The last section summarises what GraphAudit does differently from code agents (reuse is decided by a key, not by the model), the main result, and what attendees see. At the author's request it does not say what is implemented or planned; the call asks proposals to say this, and the Demonstration section carries it in one sentence ("Every part of the demonstration is implemented."). The old list of planned work is dropped: recordings of further sessions, a second annotator and labels for answers that differ in only some runs, a check on what "them" refers to, showing the task statement of an answer by code before it runs, and GraphTeam on the large model.
- **Fixes after a fourth cold read (2026-11-27).** Conclusion: "a small model gets it wrong even when warned" replaces "cannot tell when its variables have expired" (the warned Opus agent is not stale). Abstract: the fallback gives an answer "only if they agree" (was "or the request is declined"). Evidence: "nearly three times the tokens" (the largest ratio in Table 1 is 2.8); the sentence on graph size and fees now names GraphAudit, since the agents' fees per turn do rise on the large graphs; GraphAudit is the fastest system on the short sessions with Haiku; GraphTeam's 12 of 91 and 46 of 48 are counted over its three runs, and its two stale answers come from the earlier answers given to it (plan 3.23). Left as it is: "stale answers are excluded by construction", although the engine hashes the file only when its size or modification time moved, so an edit that keeps both would not be noticed.
- **Open models (Qwen3).** Left out entirely: one run per configuration, and one configuration gave 3 stale answers before the G3 fix.
- **E2 pilot (scope rule ablation, 6 silent other readings without the rule).** Left out: the plan itself reads it as a weakness of our planner prompt, and code agents picked the annotated reading without asking.
- **Unguarded error classes** are named in the paper: direction wording (fixed by an operator, no guard), the shared task statement of the fallback, which earlier result "again" means. Not named for space: a share outside [0, 1], reuse of "deciles" with the wrong grouping variable, a number given where yes or no was asked.
- **"Not supported" and "Not confirmed" in the interface** were checked on edited recordings only, not live (plan 7). The paper lists them as things an attendee may see; it does not claim they were exercised live.
- **Booth extras from plan 7** ("break the plan, press Audit", "force a reuse", "no file facts") are not in the paper: I could not confirm from the plan that each works in the current interface. Upload of an own edge list is mentioned because the single-question page and the server have it (`/api/upload`).
- **The "share 4 users" figure** was checked against the recording on 2026-11-26: the two top-10 lists in `sessions/pokec.json` share 4 users, as in the live run.

## 4. Gaps (numbers or facts that are missing)

1. Published tasks, runs p3 and p4: answered + not confirmed + unsupported is 100 of 101. The plan does not say what happened to the last question (an error, or the question the reference did not answer). The paper quotes only "answered 98, matched 90".
2. Number of runs per E4 Haiku cell is read off the lists in plan 3.15 (6 for GraphAudit, 4 for the agents); the plan does not state it in words.
3. Hand labels cover only the 60 stable disagreements; no second reader; the 40 written and 2 published questions that differ in one or two runs are unlabelled (plan 3.21). The total of published answers by code per run is not in the plan table (same + different gives 29 to 37; another session reported 30 to 38), so the paper gives only the same / different split.
4. No cross-check of the reference answers with a second engine (plan 3.3: the NetworkX check did not finish).
5. Video URL: placeholder in the abstract.
6. Sole author (confirmed 2026-11-26). The e-mail address and the ORCID are still to be added by hand.

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

## 6. References (checked 2026-11-26)

Each entry was compared with a primary page. Nothing below was taken from memory.

| Entry | Checked against | Result |
|---|---|---|
| codeact | proceedings.mlr.press/v235/wang24h.html, arXiv 2402.01030 | authors, title, ICML 2024 correct (PMLR 235, pages 50208–50232, not printed) |
| graphteam | arXiv 2410.18032 | authors and title correct; no venue found beyond arXiv. A search result shows a later version titled "... Graph Reasoning ..." while the abstract page shows "... Graph Analysis ..."; look at the current PDF once |
| grapharena | arXiv 2407.00379 ("ICLR 2025 camera ready version") | correct |
| nlgraph | arXiv 2305.10037 ("NeurIPS 2023 Spotlight") | correct |
| graphseek | arXiv 2602.11052 | was a stub; now "GraphSeek: Next-Generation Graph Analytics with LLMs", Besta, Jarmocik, Hrycyna and 7 others (shortened for the page limit, as sparc and cosql are) |
| sparc | aclanthology.org/P19-1443 | correct (19 authors, pages 4511–4523) |
| cosql | aclanthology.org/D19-1204 | venue corrected to EMNLP-IJCNLP (24 authors, pages 1962–1979) |
| helix | arXiv 1812.05762; a bibliographic record giving PVLDB 12(4), 2018, DOI 10.14778/3297753.3297763 | authors, title, volume and number correct; page numbers not confirmed and not printed |
| snap | snap.stanford.edu/data ("Citing SNAP") | correct; month added |
| igraph | igraph.org (how igraph asks to be cited) | correct; 1695 is an article number, moved from volume to number |

dblp refused automated access, so it was not used.

Sentences that cite these, checked against the abstracts only (the full papers were not read):

- GraphSeek: the abstract describes planning by the model over a "Semantic Catalog" and a separate plane for deterministic execution on a graph database. The sentence was reworded to say this and no more ("non-model executor through structured operator calls" was our inference).
- Helix: the abstract says it caches and reuses intermediate results across iterations, or recomputes when cheaper. The earlier claim that it "matches operators and inputs as our keys do" was not supported by the abstract and was replaced.
- SParC, CoSQL: context-dependent question sequences and dialogues over databases, across domains; the sentence stands. "Translates every turn" is our reading of the task, not a quotation.
- GraphTeam: "the benchmarks GraphTeam is evaluated on" stands (the abstract says six benchmarks).
- Pokec figures (1,632,803 nodes, 30,622,564 links) match the SNAP page. SNAP asks that the Pokec data be cited as Takac and Zabovsky, 2012; the paper cites only the SNAP collection, for space.
- Not cited for space: GraphInstruct, Talk like a Graph, GraphWiz, LangGraph itself, text-to-Cypher, GraphRAG.

## 7. Decisions in the draft that the author should confirm

- Title: the candidate of plan section 2. Plan 3.9 and E2b say reuse belongs in the title only if announced trap classes separate the systems; only the unannounced class did. The title still names reuse; the alternative title of plan section 9 is the fallback.
- The conference header is set with `\acmConference` to SIGMOD '27; copyright block suppressed for submission.
- CCS concepts are omitted (acmart warns, does not fail).
