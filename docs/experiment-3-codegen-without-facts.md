# Experiment 3: Code Generation Without File Facts

Date: 2026-11-06. The one ablation experiment 2 left open: does the interpretation stage matter once the model no
longer receives the file statistics that every system in experiments 1 and 2 shared? Code in `prototype/`
(system `codegen_nofacts`); summaries in `prototype/results_hard/summary.md`,
`prototype/results_hard_haiku/summary.md`, `prototype/results/summary.md`.

## 1. What was run

`codegen_nofacts` is the code-generation baseline with the file facts removed from the prompt. The model gets the
file path, the dataset description (none on the hard set) and the question, and is told that its script must
inspect the file itself: delimiter, header, column roles, whether both directions of an edge are listed, repeated
rows, weight column and what the weights look like. One script, one retry on failure, same answer schema and
scorer as before. Run on the hard interpretation set (27 questions, descriptions withheld) with Opus and Haiku, and
on the base set (60 questions, descriptions given) with Opus. The other columns are the experiment 1 and 2 runs.

## 2. Results

Answer accuracy (mean score, 0 to 1):

| set | model | full | no_verify | no_interp | flat | codegen | codegen_nofacts |
|---|---|---|---|---|---|---|---|
| hard (27) | Opus | 1.00 | 0.98 | 0.98 | 0.94 | 1.00 | 0.96 |
| hard (27) | Haiku | 0.98 | 0.98 | 0.98 | 0.98 | 0.96 | 0.85 |
| base (60) | Opus | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 | 0.97 |

Cost per question, hard set:

| system | model | tokens | USD | seconds |
|---|---|---|---|---|
| codegen | Opus | 3104 | 0.029 | 11 |
| codegen_nofacts | Opus | 4550 | 0.062 | 25 |
| codegen | Haiku | 3577 | 0.001 | 10 |
| codegen_nofacts | Haiku | 7425 | 0.003 | 27 |

Removing the facts costs 4 points with Opus and 11 points with Haiku on the hard set, 2 points on the base set, and
roughly doubles tokens and wall time: the script now has to carry its own file inspection, which the model writes
out at length every time.

## 3. What failed, and why

Every failure is a semantic misreading that the file facts would have prevented:

- **Row-index column taken as a node** (H10, H11, both models). The file has a running row number in the first
  column. With facts, `row_index_column` says so; without them, the scripts read columns 1 and 2 as the edge and
  reported node "0" as the highest-degree node (Opus and Haiku) and 78 nodes instead of 34 (Haiku).
- **Undirected roads read as directed** (H1, Haiku). The script decided "directed" because no reverse rows exist
  and returned a 90.07 km route where the shortest is 67.24 km. The facts give reciprocity and the header names,
  and the description-free interpretation stage still reads `from_junction,to_junction,distance_km` as a road
  network.
- **Timestamps summed as weights** (H8, Haiku). The email log's epoch timestamp column was taken for a weight and
  summed per sender. The facts flag the column as not a weight; the answer happened to name the right sender, in a
  different letter case, and the scorer counted it wrong.
- **Components instead of communities** (H15, Haiku). Asked for communities of customers who bought the same
  product, the script returned the number of connected components of the projection (1). This one is not about
  file facts; it is the kind of measure confusion the verifier's question/plan consistency check is for.
- **Script runtime error after the retry** (CL4, Opus, base set): the one error in 114 runs.

## 4. What this settles

- The interpretation stage's value is the file statistics it computes and surfaces, as experiment 2 concluded. The
  ablation now shows the other side: take the statistics away and code generation makes the exact errors the stage
  was designed to prevent, four to eleven points' worth depending on the model, and at twice the cost.
- The profile card is therefore not optional scaffolding; it is the cheapest part of the system with the largest
  measured effect, and it must be computed by the system, not left to the generated script.
- Against the full system the ranking on the hard set is now: full 1.00 / 0.98, codegen with facts 1.00 / 0.96,
  codegen without facts 0.96 / 0.85 (Opus / Haiku). The decision from experiment 2 stands: shared scaffold (profile
  card with file facts, cost model, verifier, clarification protocol) around both executors.

## 5. Reproduce

```bash
cd prototype
T2R_QUESTIONS=questions_hard.json T2R_DATASETS=datasets_hard.json T2R_RESULTS=results_hard \
  python3 run_experiment.py --systems codegen_nofacts --qids all --workers 3
T2R_MODEL=claude-haiku-5-5 T2R_QUESTIONS=questions_hard.json T2R_DATASETS=datasets_hard.json \
  T2R_RESULTS=results_hard_haiku python3 run_experiment.py --systems codegen_nofacts --qids all --workers 3
T2R_RESULTS=results python3 run_experiment.py --systems codegen_nofacts --qids all --workers 3
```
