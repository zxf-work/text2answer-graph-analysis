# GraphAudit demo video: shot list and narration

Written 2026-11-26. Limit: 5 minutes (the call). Target: 4:50. Every number spoken is one the paper states; the source for each is in `NOTES.md`, section 2.

## Assumptions to confirm

1. **Main session from the recording.** Scenes 2 to 8 use the recorded Pokec session (`prototype/demo/static/session.html`, "Recorded"), which plays the same on every take and needs no server. Only scene 10 uses the live server.
2. **Spoken narration**, with the same text as captions. If you prefer captions only, shorten each block by about a third so it can be read at the pace of the screen.
3. **Reading B stays in force after step 6**, as in the recording.
4. **Capture settings.** Browser window 1280 × 720 at 2× scale (a 2560 × 1440 capture), light theme, page zoom 110% so the answer text is readable in a small player, bookmarks bar and other tabs hidden, cursor shown.

## Timeline

Speaking pace is taken as 140 words a minute. "Hold" is time on screen with no speech, for the viewer to read.

| # | Time | Length | On screen | Action |
|---|---|---|---|---|
| 1 | 0:00 | 0:32 | Title card, then Figure 1 | none |
| 2 | 0:32 | 0:22 | Session page, step 1 | play step 1; point at the plan and the reading of the file |
| 3 | 0:54 | 0:15 | step 2 | play; point at "reused" |
| 4 | 1:09 | 0:15 | step 3 | play; point at "1 step reused", the single executed step |
| 5 | 1:24 | 0:12 | step 4, data-change card | play |
| 6 | 1:36 | 0:28 | step 5 | play; point at "replayed", `data_changed`, the two new leaders |
| 7 | 2:04 | 0:38 | step 6, two-readings card | play; hold 3 s on the card; choose B; open A |
| 8 | 2:42 | 0:32 | step 7 | play; open "Generated code", scroll both functions once |
| 9 | 3:14 | 0:22 | Session details: ledger, audit record | open details; open the audit record |
| 10 | 3:36 | 0:24 | Live session page | type a question, press "Change the data file", ask again |
| 11 | 4:00 | 0:38 | Comparison page | step to turn 5; open details to the quoted code line |
| 12 | 4:38 | 0:12 | Closing card | none |

Total 4:50. The narration is 546 words, about 3:55 of speech at that pace, so each scene has a few seconds of hold.

## Narration

**1. Opening (0:32)**

> An assistant that answers questions about a graph usually keeps state between questions, and that is where a session can go wrong without any sign of it. The data file grows, or the follow-up reads the graph differently, and an old result is used again. GraphAudit puts a typed plan between the question and the computation. The model writes the plan; the engine owns the loading, the result store and every check.

**2. Step 1, a first question (0:22)**

> This is the Pokec social network: 1.6 million users and 30.6 million friendship links. We ask who the ten most influential users are. Before the answer, the page shows the plan, how the file was read, and the measure chosen for "influential", which is PageRank.

**3. Step 2, a drill-down (0:15)**

> Which region is each of them from? The ranking is not computed again. Two steps are marked reused, because they carry the same key as before, and one lookup runs.

**4. Step 3, a changed parameter (0:15)**

> Show the top twenty instead. Only the final cut runs. It is taken from the stored scores, not from the earlier list of ten.

**5. Step 4, the file changes (0:12)**

> Now the edge file grows by 27,466 rows, as it would after a nightly load. Nobody tells the system.

**6. Step 5, the same words again (0:28)**

> We ask the first question again, word for word. The plan is replayed with no call to the model. But nothing computed on the old file is reused: the engine noticed the change from the file itself, and says so. Two users who gained links now lead the ranking.

**7. Step 6, two readings (0:38)**

> The most influential users within one region. This request has two readings. One ranks the whole network and lists the members of the region. The other ranks again inside the region alone. Both are shown as contracts, each with what it would reuse, and nothing runs until one is chosen. We choose the second, then open the first beside it. The two lists share only four users.

**8. Step 7, outside the catalogue (0:32)**

> Among the top twenty, what is the largest group in which every two are friends? No operator computes that, and the system says so. It prepares the twenty-user subgraph with checked steps, then has two functions written separately. They agree on a group of five, so the value is shown, marked as an answer by code. Both functions are one click away.

**9. Ledger and audit record (0:22)**

> The ledger is the session's bill: six steps reused, twenty executed, one turn replayed, fifteen model calls, about one cent. The audit record holds every plan, every reuse decision with its key, and every check.

**10. Live (0:24)**

> This is the same session running live. Visitors type their own questions. This button appends rows to the file on disk and tells the session nothing. On the next question, the change is reported and the answer is computed on the new file.

**11. Side by side (0:38)**

> Here are the same ten questions for GraphAudit and for a code-writing agent that keeps its variables. After the file grows, the agent answers from its stored PageRank vector; the page quotes the line of its own code that does it. In this run it is correct on five of ten turns and stale on three. GraphAudit is correct on all ten. An agent can get this right, with a larger model, a warning, and recomputation. GraphAudit gets it right by construction.

**12. Closing (0:12)**

> GraphAudit: what was assumed, what was reused, and what was not checked is on screen for every answer.

## Before recording (dry run)

- **"Four users" in step 6** is confirmed from the recording (the two top-10 lists share 4 users), and the recording's final ledger reads 6 reused, 20 executed, 1 replayed, 15 model calls. Both only need a glance on screen.
- Figure 2 of the paper shows the ledger at step 6, where the totals are smaller; the video shows it at the end.
- **Scene 8:** see that "Generated code" opens both functions without a long scroll at 110% zoom; if not, show the first function and the two equal values only.
- **Scene 10:** start the demo server on the cluster (`slurm/demo_server.sbatch`) and the SSH tunnel beforehand; a live session takes about 35 seconds to start and turns take 5 to 30 seconds, so record the scene whole and cut the waits in editing. Use a short first question (step 1 of the script) so the wait is the same one the paper quotes.
- **Scene 11:** the comparison page says it is one run on Haiku; leave that line in frame.
- **Pronunciation:** "Pokec" is Slovak, roughly "POH-kets". The region in step 6 need not be read aloud; the screen shows it.

## Recording and editing

1. Record each scene as its own take, in order, with a second of stillness at each end.
2. Record the narration separately, one block per scene, then fit the picture to the voice: speed up waits, never the reading time of an answer.
3. Add the captions from the narration text. Add two labels only: "recorded session" on scenes 2 to 9 and "live" on scene 10, since the paper makes that distinction.
4. Export at 1080p, check the smallest text (the plan steps) is legible at that size, and keep the file under the host's limit.
5. Upload (unlisted link is enough for the call), put the URL in the abstract of `main.tex`, and rebuild.

## Left out on purpose

- "Break the plan, press Audit", "force a reuse" and "no file facts" from the older plan: the paper no longer describes them and they were not confirmed in the current interface.
- The benchmark table: one sentence in scene 11 carries the result; the numbers are in the paper.
- GraphTeam and the question sets: no screen shows them.
