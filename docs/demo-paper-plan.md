# Demo Paper Plan: text2answer graph analysis

Date: 2026-11-06. Working plan for a demonstration paper at a database venue (SIGMOD or VLDB demo track), with the
workshop route as fallback. Builds on `solution-architecture.md` and the three experiment reports.

## 1. The one-sentence claim

A text-to-result graph analysis system over plain edge-list files, no graph database and no query language, in which
the language model never sees the graph: it reads a profile card, writes a typed analysis plan, and every answer is
returned with a stated interpretation, a verification report produced without ground truth, and a visible cost
decision.

Three things in that sentence are ours and are backed by measurements: interpretation from file facts
(experiment 3: 4 to 11 points and 2x cost when removed), verification without ground truth (experiment 2: 87% of
answer-changing plan mutations flagged), and automatic cost tiering (experiment 2: 50M-edge graph, every question
answered, planner's pivot count overridden by the cost model). The demo must make all three visible on screen.

## 2. Venue options

| route | format | what it needs from us | fit |
|---|---|---|---|
| SIGMOD demo track | 4-page paper + live demo at the conference | working UI, demo scenario, short evaluation | best fit: SIGMOD 2026 accepted PRISM, an LLM-driven interactive community-search system, so the track takes this kind of system |
| VLDB demo track | 4-page paper + live demo | same | equally good; usually a later deadline than SIGMOD's |
| VLDB workshops: LLM+Graph, Agents+Graph | 6 to 8 pages, no UI required | the experiments as they stand | fallback if the UI is not ready; lower visibility |
| Short research paper | 6 pages | harder benchmark, real large graphs, more seeds | later, on the verification and cost-tiering results |

Check the current calls for exact dates and page limits before planning backwards; demo deadlines are typically two
to four months before the conference, with SIGMOD's in late autumn and VLDB's in spring.

## 3. What the demo shows (the scenario)

Four scenes, each one a thing the audience can see change on screen. Every scene uses files that ship with the repo.

1. **Ask, see the plan, not just the answer.** Load the trust network (no description). Ask "who is the most trusted
   person?" The screen shows: the profile card (reciprocity 0.3, header `truster,trustee,strength`, integer weights),
   the interpretation (directed, in-degree, weights are strengths), the typed plan as a small dataflow graph, the
   answer, and the verifier's findings. Point: the user sees every decision that produced the number.
2. **Catch a wrong interpretation.** Same graph, ask "who trusts the most people?" and show the plan the system
   produces; then switch to the "flat agent" tab where the same question was answered with the wrong direction, and
   show the verifier flag "question asks for outgoing relations but plan uses in mode". Then the email log: ask
   "how many pairs of people have exchanged email?" and show the multigraph warning (distinct pairs vs rows).
   Point: verification without ground truth is a check between question, interpretation, data and plan.
3. **Ask something ambiguous, get a clarification instead of a guess.** The road network, "what is the shortest
   route from J0 to J299?" with weights in kilometres: the system asks whether distance or hop count is meant, or
   answers with both as variants. Point: the clarification protocol is part of the answer schema.
4. **Scale.** Load the 50M-edge file (pre-loaded in a warm process; the load itself takes five minutes). Ask for the
   top betweenness nodes. Show the planner request 500 pivots, the cost model cut it to 125 with the estimated cost
   displayed, and the answer arrive. Beside it, the recorded transcript of the flat agent fabricating a tool
   dialogue on the same question. Point: structure is what prevents both the timeout and the fabrication.

If time allows, a fifth scene toggles the file facts off for the code-generation executor and shows the row-index
column being read as a node (experiment 3), which is the single most convincing argument for the interpretation
stage.

## 4. What has to be built

| item | status | estimate |
|---|---|---|
| Executors, IR, validator, cost model, verifier, planner prompts | done (prototype) | - |
| Benchmark with ground truth, three sets, scorer | done | - |
| Web UI: question box, profile card panel, plan as dataflow graph, findings panel, answer with variants and clarification, cost panel, system switcher (full / flat / codegen) | not started | 2 weeks |
| Warm server process that keeps large graphs loaded between questions | not started | 2 days |
| Recorded transcripts for the contrast scenes (flat fabrication, codegen without facts) | available in raw results; need a viewer | 1 day |
| Replace the synthetic 50M graph with one or two real graphs (SNAP: LiveJournal, Orkut) | blocked on network access from the dev environment; trivial elsewhere | 1 day |
| Harder benchmark version so accuracy tables are not all 1.00 | not started | 1 week |
| Paper: 4 pages, figures of the UI, one results table | not started | 1 week |

Roughly five weeks of work in sequence, three if the UI and the benchmark are done in parallel.

## 5. Paper outline (4 pages)

1. Introduction: the grounding gap (ambiguous vocabulary, implicit file semantics, no ground truth at query time)
   and why query-language generation does not address it. Half a page.
2. System: the six stages in one figure; profile card, typed IR, validator and cost model, verifier, clarification
   protocol. One page.
3. Demonstration scenarios: the four scenes above with screenshots. One page.
4. Evaluation summary: one table with the three sets, the five systems and the no-facts ablation; one sentence each
   on fault injection and the 50M run. Half a page.
5. Related work and conclusion. Half a page.

## 6. Related work

Positioning rule: do not claim "natural language to graph analytics" as new; GraphSeek and others already do that.
Claim the three visible guarantees and the no-database setting.

Verified from the sources' own pages or official listings:

| work | what it is | relation to us |
|---|---|---|
| GraphSeek (arXiv 2602.11052, Feb 2026) | LLM emits structured operator calls executed by a non-LLM executor over a graph database; argues LLMs cannot write reliable queries on large heterogeneous property graphs; reports a large success-rate gain over a LangChain baseline | closest system. Same separation of planning from execution. Differences to state: it sits on a database; we work on files with no query language; we add interpretation from file facts, verification without ground truth and cost tiering, none of which the summaries mention. Read the full paper before writing this paragraph |
| Analytics-Augmented Generation (arXiv 2602.21604, Feb 2026) | "autonomous graph data analytics"; cites GraphTeam and GraphInstruct | same space; method not yet read. Read the full paper |
| GraphTeam (2024/2025) | multi-agent LLM system for graph analysis, agents for input, search, coding and answering | the multi-agent design we assessed and did not adopt; cite for the coding-agent approach |
| GraphInstruct / GraphWiz / NLGraph / GraphQA (2023 to 2025) | benchmarks and instruction tuning for graph reasoning on small synthetic graphs given in the prompt | the "graph in the prompt" paradigm our benchmark analysis argues against; cite in the benchmark paragraph |
| LLMs for large-scale graph analysis (NeurIPS 2025) | LLM writes NetworkX code; catalogue of NetworkX functions by category; "GraphChain" workflows | our code-generation baseline as a published system; makes the baseline credible |
| PRISM (SIGMOD 2026 demo) | LLM-empowered interactive system for community search on multilayer graphs | shows the demo track takes LLM-driven graph systems; narrower task |
| When the Tool Decides (arXiv 2606.14476, Jun 2026) | agents given a frozen GNN tool copy its output 97.6 to 99.2% of the time | outside evidence that agents do not check tool results; motivates the verifier |
| LLM-generated NetworkX code for network management (HotNets 2023) | early code-generation approach; library reduced errors vs feeding raw graph data to the LLM | historical precedent for codegen over a library |
| TigerGraph CoPilot (product) | maps a question to a pre-built query, runs it, returns results with reasoning; curated queries to limit hallucination | the product-side answer to the same risk, tied to a database and to GSQL |
| Neo4j Aura Copilot (product) | natural-language querying over Neo4j (text to Cypher) | the query-generation paradigm we avoid |
| Text-to-Cypher / text-to-GQL line (SyntheT2C, CypherBench, Text2Cypher datasets, 2024 to 2025) | translation benchmarks and models | define what we are not doing; cite once |
| GraphRAG and knowledge-graph question answering | retrieval over graphs for text generation | different task (text answers from graph context, not computed graph results); one sentence to separate |
| VLDB 2025 LLM+Graph workshop summary (arXiv 2604.02861); Agents+Graph workshop at VLDB 2026 | community venues | fallback venues; cite the summary for the field's open problems |

To verify before submission (not read in full from this environment, arxiv.org was unreachable): GraphSeek,
Analytics-Augmented Generation, When the Tool Decides, the LLM+Graph summary. Also check for anything newer than
June 2026 on "LLM graph analytics agent", "text-to-result" and "graph analysis planning", since the two closest
systems both appeared in February 2026 and the area is moving monthly.

## 7. Risks

- **A reviewer says GraphSeek did this.** Answer in the paper, not in the rebuttal: a side-by-side table of
  guarantees (interpretation shown, verification without ground truth, cost decision shown, no database required),
  and the ablation numbers that show each one matters.
- **All-1.00 tables look like an easy benchmark.** They are. Either ship the harder benchmark version first or
  present the tables as "what did not separate systems" and lead with fault injection, the 50M run and the no-facts
  ablation, which did.
- **Synthetic large graphs.** Replace with real ones before submission; it is a one-day task outside this
  environment.
- **Live LLM calls during the demo.** Cache every planned scene's LLM responses and replay them if the network fails;
  keep one live question for the audience.
- **Model drift.** Pin the model version in the paper and the repo; record which model produced each result file.

## 8. Next actions, in order

1. Read the four unverified papers and rewrite the GraphSeek and AAG rows of section 6 from their full text.
2. Build the web UI and warm server (section 4), driven by the four scenes.
3. Replace the synthetic 50M graph with a real one and rerun the scale tier.
4. Build the harder benchmark version; rerun the five systems on it.
5. Write the paper against the outline in section 5; pick the venue from the current calls.
