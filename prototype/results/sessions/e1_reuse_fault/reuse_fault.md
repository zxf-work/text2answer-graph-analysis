# Reuse fault injection (E1)

9 graphs (trust, follows, citations, roads, facebook, epinions, pokec_bratislavsky, pokec_trenciansky, pokec_trnavsky); 246 fault scenarios and 201 valid-reuse scenarios, each run under 7 key schemes. No model calls.

## Faults: scenarios where a wrong value was served (and where the final answer changed)

| key scheme | approximation changed upstream | different group under the same step name | different random seed | different subgraph under the same step name | graph file changed | input changed upstream (short list extended) | node attributes changed | other reading of the graph | all | answer changed | crashed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full lineage key | 0/18 | 0/36 | 0/27 | 0/36 | 0/36 | 0/43 | 0/12 | 0/38 | 0/246 | 0 | 0 |
| without input lineage | 18/18 | 36/36 | 0/27 | 20/36 | 0/36 | 43/43 | 0/12 | 0/38 | 117/246 | 105 | 0 |
| without graph reading | 0/18 | 0/36 | 0/27 | 0/36 | 0/36 | 0/43 | 0/12 | 32/38 | 32/246 | 32 | 0 |
| without content hash | 0/18 | 0/36 | 0/27 | 0/36 | 36/36 | 0/43 | 12/12 | 0/38 | 48/246 | 44 | 0 |
| without node table | 0/18 | 0/36 | 0/27 | 0/36 | 0/36 | 0/43 | 12/12 | 0/38 | 12/246 | 12 | 0 |
| without seed | 0/18 | 0/36 | 27/27 | 0/36 | 0/36 | 0/43 | 0/12 | 0/38 | 27/246 | 26 | 0 |
| original cache | 0/18 | 0/36 | 27/27 | 0/36 | 0/36 | 0/43 | 12/12 | 32/38 | 71/246 | 70 | 0 |

In 207 of 246 fault scenarios the history's answer and the target's fresh answer differ; in the rest the fault happens not to change the final answer on that graph.

## Valid reuse: steps reused out of steps that could be reused (and scenarios with a wrong answer)

| key scheme | defaults written out | extended with new steps | parameter changed downstream | repeat | same group rebuilt in a longer plan | same steps, other names | same steps, other order | all | wrong answers |
|---|---|---|---|---|---|---|---|---|---|
| full lineage key | 18/18 | 72/72 | 36/36 | 72/72 | 48/48 | 72/72 | 72/72 | 390/390 | 0 |
| without input lineage | 18/18 | 72/72 | 36/36 | 72/72 | 12/48 | 36/72 | 72/72 | 318/390 | 36 |
| without graph reading | 18/18 | 72/72 | 36/36 | 72/72 | 48/48 | 72/72 | 72/72 | 390/390 | 0 |
| without content hash | 18/18 | 72/72 | 36/36 | 72/72 | 48/48 | 72/72 | 72/72 | 390/390 | 0 |
| without node table | 18/18 | 72/72 | 36/36 | 72/72 | 48/48 | 72/72 | 72/72 | 390/390 | 0 |
| without seed | 18/18 | 72/72 | 36/36 | 72/72 | 48/48 | 72/72 | 72/72 | 390/390 | 0 |
| original cache | 9/18 | 36/72 | 36/36 | 36/72 | 12/48 | 36/72 | 72/72 | 237/390 | 0 |

## Scope-reading rule

- Group restrictions tested: 60 (measure x group x graph). The two readings give a different top-10 set in 60 and a different order in 60; mean overlap 3.7 of 10.
- The rule identifies the reading of both plans in 60 of 60.

| measure | cases | different top-10 set | mean shared of 10 |
|---|---|---|---|
| closeness | 15 | 15 | 0.5 |
| core_number | 15 | 15 | 3.0 |
| degree | 15 | 15 | 5.6 |
| pagerank | 15 | 15 | 5.5 |

- Plans with no group restriction: 387; flagged by the rule: 0.
