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

> We ask the first question again, word for word. The plan is replayed with no planning call. But nothing computed on the old file is reused: the engine noticed the change from the file itself, and says so. Two users who gained links now lead the ranking.

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

## Dry run (done 2026-11-26)

All scenes were played in a browser at the capture size (a 1164 × 655 viewport, which is 1280 × 720 at 110% zoom): the recorded session, the comparison page, and the live scene against the server on the cluster (Haiku, about one cent). Scene lengths were not clocked against spoken narration; they are still estimates from word counts.

Fixed in the pages during the dry run:

- **Link count.** The recorded session showed the link count from after the file change (30,650,030) from step 1 on, and listed the change in the session details before it happened. It now shows 30,622,564 until the change is noticed. Live, the header kept the old count after a change; it now shows the new one.
- **New cards hidden behind the question box.** On both pages the last lines of a new turn (what was reused, the agent's code line, the session totals) sat behind the docked box at the bottom. New cards are now scrolled clear of it.
- **Replay was not visible on the turn.** The repeated question (step 5) now says "plan of turn 1 replayed, no planning call" under its answer.
- **"No model call" was wrong.** A replayed turn skips the planning call but still makes one model call for the written explanation. Corrected on the page, in the presenter's line, in this narration and in one sentence of the paper.
- The end-of-recording text in the question box was cut off; shortened. A page that is not found on the demo server returned an error trace; fixed in `server.py` (takes effect at the next server start).

What to do by hand while recording:

- **Scene 2:** the plan and the reading of the file are under "Details" on the turn; open it before pointing at them.
- **Scene 5:** the counter under the question box reads "step 5 of 9" (the recording has nine entries for the paper's seven steps). Keep that line out of frame or do not point at it.
- **Scene 7:** the two-readings card is taller than the window; scroll once to reach the two "Use reading" buttons. After B is chosen, "Next" shows A with the line "the two top-10 lists share 4 of 10 nodes".
- **Scene 8:** open "Details", then "Generated code". The dialog shows the task statement, the inputs and the first function; scroll once for the second.
- **Scene 9:** scroll once inside the session details to bring the last ledger lines above the question box. In the audit record the lineage keys wrap onto two lines at this width; they are readable.
- **Scene 10:** the page is at `/session.html` on the tunnelled server (not `/static/session.html`). A live session took 35 s to start and a question 14 s. "Change the data file" takes several seconds, with the Ask button disabled until the change card appears; cut the wait in editing. The repeated first question came back replayed, with the change reported and users 27511 and 25855 leading. Live answers can be laid out differently from the recording (this run listed PageRank and in-degree side by side).
- **Scene 11:** open "Details" on turn 5 and scroll once to bring the agent's quoted code line fully into view. The page's "one run of each system on Haiku" line is in the totals at the end, not at turn 5; add it as a caption.
- **Tunnel:** a direct jump to the compute node failed on host-key checking from this Mac; the two-step form worked: `ssh -L 8772:localhost:18765 <login node> 'ssh -N -L 18765:localhost:8765 <compute node>'`.
- **Pronunciation:** "Pokec" is Slovak, roughly "POH-kets". The region in step 6 need not be read aloud.

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
