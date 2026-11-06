# Headline experiment results

Questions: 27. Systems: full, no_verify, no_interp, flat, codegen, codegen_nofacts. Model: claude-haiku-5-5. Results dir: results_hard_haiku.

## Answer accuracy by family (mean score, 0 to 1)

| family | n | full | no_verify | no_interp | flat | codegen | codegen_nofacts |
|---|---|---|---|---|---|---|---|
| interpretation | 22 | 1.00 | 1.00 | 1.00 | 1.00 | 0.95 | 0.82 |
| metric | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| clarification | 1 | 0.50 | 0.50 | 0.50 | 0.50 | 1.00 | 1.00 |
| topk | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| ALL | 27 | 0.98 | 0.98 | 0.98 | 0.98 | 0.96 | 0.85 |

## Plan correctness (mean, 0 to 1; n/a for codegen)

| family | full | no_verify | no_interp | flat | codegen | codegen_nofacts |
|---|---|---|---|---|---|---|
| interpretation | 0.98 | 0.98 | 0.95 | 0.91 | n/a | n/a |
| metric | 1.00 | 1.00 | 1.00 | 1.00 | n/a | n/a |
| clarification | 1.00 | 1.00 | 1.00 | 1.00 | n/a | n/a |
| topk | 1.00 | 1.00 | 1.00 | 1.00 | n/a | n/a |
| ALL | 0.98 | 0.98 | 0.96 | 0.93 | n/a | n/a |

## Cost per question (means)

| system | LLM calls | tokens | USD | seconds | errors/timeouts |
|---|---|---|---|---|---|
| full | 2.0 | 9832 | 0.001 | 14 | 0 |
| no_verify | 2.0 | 9807 | 0.001 | 15 | 0 |
| no_interp | 2.0 | 9973 | 0.001 | 15 | 0 |
| flat | 4.7 | 28899 | 0.002 | 24 | 0 |
| codegen | 1.0 | 3577 | 0.001 | 10 | 0 |
| codegen_nofacts | 1.0 | 7425 | 0.003 | 27 | 0 |

## Per-question scores

| qid | family | full | no_verify | no_interp | flat | codegen | codegen_nofacts |
|---|---|---|---|---|---|---|---|
| H1 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| H2 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H3 | metric | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H4 | clarification | 0.5 | 0.5 | 0.5 | 0.5 | 1.0 ? | 1.0 ? |
| H5 | metric | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H6 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H7 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H8 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| H9 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H10 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.5 |
| H11 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 ? |
| H12 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 ? |
| H13 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 ? | 1.0 | 1.0 ? |
| H14 | metric | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H15 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5 |
| H16 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H17 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H18 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H19 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H20 | topk | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H21 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H22 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H23 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H24 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H25 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H26 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| H27 | interpretation | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

## Failure notes (score < 1)

- codegen_nofacts H1 (interpretation): score 0.0: got {"length": 90.07, "path": ["J0", "J15", "J16", "J17", "J32", "J33", "J48", "J49" expected 67.24
- full H4 (clarification): score 0.5: value right but assumption not stated
- no_verify H4 (clarification): score 0.5: value right but assumption not stated
- no_interp H4 (clarification): score 0.5: value right but assumption not stated
- flat H4 (clarification): score 0.5: value right but assumption not stated
- codegen_nofacts H8 (interpretation): score 0.0: got "e186"
- codegen_nofacts H10 (interpretation): score 0.5: facts {'n': False, 'm': True}
- codegen_nofacts H11 (interpretation): score 0.0: got 0
- codegen H15 (interpretation): score 0.0: got 1 expected 6
- codegen_nofacts H15 (interpretation): score 0.5: correct only as a variant
