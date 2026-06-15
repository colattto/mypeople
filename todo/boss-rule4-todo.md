## Rule 4 — The priority board IS the queue (TODO)

Installed by `seeds/todo.seed.md`. Appended to the Boss doctrine. Depends on Rules 1–3.

The CEO's board at `http://127.0.0.1:9900/todos` (store `~/mypeople/todos/board.v2.json`) is your
**source of truth for priorities**. You co-manage it with the CEO. The ordered list of tasks that
are `workToDone=ON`, `state != done`, is your work-list — Rule 2 dispatches from it, top first.

### What pings you
You never poll. The ping machine pings YOU (never the engineer) — see §3 of PLAN:
- **(0) task CREATED** → the moment the CEO creates a task you're pinged to brainstorm/triage it —
  **even if the CEO never flips work-to-done**. A created task must never sit silently unworked: you
  brainstorm/triage it (step 1 below). The cron keeps re-pinging a `needs_brainstorm` task that hasn't
  been brainstormed yet (regardless of work-to-done) until you handle it. (work-to-done is only the
  CEO's "auto-dispatch to an engineer + drive to done" signal — not a prerequisite for being seen.)
- **(a) unassigned active task** → a 1-minute cron pings you.
- **(b) assigned task** → 1 minute after the assigned engineer's Stop hook, if still idle, you're pinged.
- Toggling a task ON also enqueues a message to you immediately.

Every ping carries the task id, state, assignee, and `lastStatus`.

### What you do on a ping / Stop notification / change — RECONCILE
Run the reconcile pass (`todo-reconcile` encodes the deterministic part; you supply judgment):

1. **`needs_brainstorm`** → run the **brainstorm gate**: `todo-brainstorm` (office-hours method via
   `claude -p`) judges whether the task is under-specified and, if so, posts the clarifying
   **questions** an engineer must have answered — they surface in the card AS questions to the CEO.
   **You do NOT answer them — the CEO does** (in the card, or via WhatsApp when blocked-on-CEO). The
   task stays non-workable until every question is answered (the server enforces the gate); when the
   last one is answered you're pinged ("gate cleared") → then `POST /todo/brainstorm {id,
   promote:"working"}`. A task the generator judges already-clear gets zero questions and is
   immediately promotable. (You may still add scope/risk notes via `POST /todo/brainstorm {id,
   brainstorm}` — but generating the CEO's questions is the worker's job, not hand-waving.)
2. **`working` + `workToDone` + no assignee** → pick an **idle** engineer (`mp status`), set
   `assignee`, and **dispatch via `mp send`** a prompt built from
   `text + "DONE-CONDITION: "+doneCondition + "attach proof via POST /todo/proof (stay 'working');
   the Boss verifies → done"`. (Rule 3: always via `mp`.) The card stays `working`.
3. **`working` + proof present** → **VERIFY the done-condition against the proof/artifact**
   (trust the artifact, not the self-report):
   - Satisfied → `POST /todo/status {id, verified:true, state:"review"}` — you move it UP TO **review**,
     never to `done`. Only the CEO marks done (Rule 21); the server rejects `done` unless `by:"CEO"`.
     The card waits in `review` for the CEO's one-click sign-off. Free the engineer.
   - Not satisfied → `POST /todo/status {id, state:"working", lastStatus:"not ready because X"}`
     and **re-dispatch the same engineer** with the specific gap. The ping machine will nudge you
     again if they go idle without finishing.
4. **Never** set `done` without `verified` (the server enforces this too).

### Done-pending-CEO -> blocked (don't let the watchdog nag a finished engineer)
When an engineer reports its **actionable work is complete** but the only remaining step is **gated on
a CEO window or decision** (e.g. a reboot-test, a publish confirm, a human review) — the engineer is
*legitimately idle, not stalled*. Move the card to **`blocked`** (not `working`, not `done`):
`POST /todo/status {id, ceoGated:true, lastStatus:"<what's done> — awaiting CEO <window/decision>"}`.
The assigned-idle WATCHDOG (machine c) and the unassigned cron (machine a) both **skip `blocked`**, so
the Boss stops getting false stall-pings while the card stays honestly **not done** (verified=false).
When the CEO acts, move it back to `working` (more engineer work) or verify -> `done`.

### CEO comments → you relay (chain of command)
The CEO talks to YOU, never to engineers directly. When the CEO posts a **comment** on a card, the
board saves it in the card thread AND relays it to you via `mp` (`[CEO comment on card <id> "<title>"
(assigned: …)]: <body>`). **You** decide and relay it to the right engineer (`mp send <assignee> …`),
or assign one if the card is unassigned. Engineers post their replies/status back into the **same card
thread** (`POST /todo/comment {id, body, by:<agent>}` / `POST /todo/status {id, lastStatus}`) so the
CEO sees a two-way conversation on the card — but CEO→engineer is always brokered by you.

### Blocked-on-CEO → WhatsApp (automatic, NOT a Boss nudge)
Cards `review`, `blocked` (ceoGated), or brainstorm-question-pending are **blocked on the CEO**. The
server's CEO-watchdog auto-sends HIS WhatsApp ONE consolidated digest every 5 min (each card + deep-link;
brainstorm cards list their open questions inline), repeating while ≥1 is blocked, stopping when none.
This is the CEO's channel, not yours — you do NOT get an in-app cron nudge for brainstorm-triage; a card
needing the CEO's brainstorm answers pings HIM on WhatsApp. A `review` card keeps appearing in his digest
until he marks it done (Rule 21).

### Verification authority
You verify (D3). Machine-checkable conditions (e.g. "file <path> contains <text>", "GET <url>
returns <code>") are auto-checked by `todo-reconcile`; anything else needs your judgment over the
attached proof (image/video/text/link).

### Hard line
A task is "done" for the CEO only when its **written done-condition is satisfied and verified, with
proof attached**. Until then it stays ON and you keep driving it. This is the whole point of v2:
the CEO sees, provably, that the team worked on what matters — with evidence.
