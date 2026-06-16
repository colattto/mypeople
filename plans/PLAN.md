# PLAN — HUD shows RETIRED engineers + per-engineer REVIVE (true session resume)

Card: `1c30d20c3d93` · Author: `daniels-MacBook-Pro-2/hud-revive:eng-1` · Gate: PLAN only (no code yet)

## CEO locked decisions (do not re-litigate)
1. **TRUE session resume by session-id ONLY. NO FALLBACK.** Revive replays the actual prior Claude
   session (`claude --resume <session-id>`) so the engineer wakes mid-task. If a session genuinely
   cannot be resumed, that is an **ERROR surfaced on the HUD** — never a silent fresh re-spawn.
   (Supersedes the earlier "re-spawn fallback" idea — removed entirely.)
2. **Per-engineer revive, ONE at a time.** A revive action per retired engineer. No batch / restore-all.

---

## User Journey (this IS the E2E test)
1. CEO has a team running (Boss + N engineers), each spawned with `mp spawn …` in some `--cwd`.
2. The Mac reboots. Every `tmux` session dies → every agent process is gone.
3. On reboot, the queue-client comes back up, sees its durable roster, notices the tmux windows are
   gone, and marks those engineers **retired (reason: `died-on-reboot`)** — it does **not** delete them.
4. CEO opens the HUD (`/dashboard`). Above/below the live-agents table is a new **"Retired engineers"**
   table. Each row shows: `agent_id`, the exact **spawn command** used, its **card** (derived by looking
   up the board task whose assignee is this engineer — not stored on the engineer), **why it retired**
   (`done-auto-retire` / `killed` / `died-on-reboot`), a **timestamp**, and a **Revive** button.
5. A row whose session is resumable shows an active green **Revive**. A row whose session-id is missing
   or whose transcript file is gone shows a **disabled red "Not resumable — <reason>"** (the error,
   surfaced — never a silent fresh spawn).
6. CEO clicks **Revive** on ONE engineer. The HUD POSTs a single `revive` task for that one agent_id.
7. The engineer's tmux window is recreated in its original `cwd`, launched as
   `claude --resume <persisted-session-id> …`. The Claude TUI renders the prior conversation; the agent
   wakes **remembering what it was doing** (same session, not a fresh one).
8. The row moves from "Retired" to the live table. CEO repeats per engineer to rebuild the team.

The Boss can trigger the identical single-engineer verb: `mp revive <agent_id>` (same code path the
HUD button hits).

---

## Technical approach (grounded in real files)

### Where session-id is captured today, and the robustness gap
- The `emit-event` hook (`plugins/tmux-boss-hooks/hooks/emit-event`) already runs on **SessionStart /
  Stop / SessionEnd / PreToolUse** (registered in the seed, `seeds/mypeople.seed.md:1628-1631`).
- On **Stop** it writes `status/mc-<sess>/<tab>.json` containing **`session_id`**, `timestamp`,
  `summary`, `agent_id`, `boss_id` (`emit-event:107-116`). This file is **durable on disk and survives
  reboot** — verified: `status/mc-main/Boss.json.session_id = 2ebc8599-…` resolves to a real transcript
  at `~/.claude/projects/-Users-delattre/2ebc8599-….jsonl`.
- **Gap 1 — session-id only at Stop.** SessionStart only appends to `run/hook-events.log`
  (`emit-event:42,96-98`); no per-agent record is updated. An engineer that hasn't hit a Stop yet has
  no durable session-id. **Fix:** in `emit-event`, on **SessionStart** (and SessionEnd) also write the
  current `session_id` (+ `cwd` from the hook payload) into the durable roster (below). The hook payload
  carries `session_id`; SessionStart carries `cwd`. This makes the session-id known within seconds of
  spawn and re-current after any `/clear` or resume (each mints a new SessionStart we capture).
- **Gap 2 — `cwd` is never persisted.** `record_agent()` stores only `{backend, boss_id, is_master}`
  (`queue-client.py:167-172`, seed `:796`). But `claude --resume <id>` resolves the transcript from the
  **project dir derived from cwd** (`~/.claude/projects/<cwd-with-slashes-as-dashes>/<id>.jsonl` —
  verified). Resume MUST run in the original cwd. **Fix:** persist `cwd` at spawn.
- **Gap 3 — the literal spawn command isn't stored.** It is deterministically rebuilt in
  `execute_spawn()` (`queue-client.py:456-461` claude branch). **Fix:** persist the reconstructed
  invocation string at spawn so the HUD can show it verbatim.

### Data model — durable roster (`run/roster.json`)
New durable file owned by the queue-client, sibling to `run/agents.json`, written atomically (reuse the
`_save_agents` tmp+`os.replace` pattern, `queue-client.py:159-164`). Keyed by `agent_id`:
```
{
  "<agent_id>": {
    "backend": "claude",
    "cwd": "/Users/delattre/mypeople",          // NEW — required for resume
    "boss_id": "…", "is_master": false,
    "spawn_cmd": "claude --dangerously-skip-permissions … --plugin-dir …",  // literal invocation shown on HUD
    "session_id": "2ebc8599-…",                  // latest, updated by emit-event on SessionStart+Stop
    // NO last_card — the engineer→card link is DERIVED from the board (the card stores its assignee),
    // never duplicated onto the engineer record. (CEO)
    "state": "alive" | "retired",
    "retire_reason": "done-auto-retire" | "killed" | "died-on-reboot" | "",
    "spawned_ts": "…", "retired_ts": ""
  }
}
```
- **Write at spawn** (`execute_spawn`, end of the success path near `record_agent`, `queue-client.py:1192`):
  upsert the roster entry with `state:"alive"`, `cwd`, `spawn_cmd`, `session_id:""`.
- **Update by hook** (`emit-event` SessionStart/Stop): set `session_id` (latest) only.
- **Card link is derived, never stored:** the engineer's card is found by scanning the board for the
  task whose `assignee == agent_id` (`todo/todo-server.py` tasks carry `assignee`). The HUD resolves
  this at render time via `/todo/board` — the roster record holds no card reference.
- **Mark retired, never delete:** `execute_kill` (`queue-client.py:638-665`) and the board's
  `retire_on_done` (`todo/todo-server.py:599-632`, which calls `mp kill`) currently *forget* the agent.
  Change: on kill, set `state:"retired"`, `retired_ts`, and `retire_reason` (`killed` for manual,
  `done-auto-retire` when the kill originates from a DONE transition). The live registry
  (`agents.json` / server `/agents`) still drops it from the live table; the roster keeps the record.
- **Reboot detection:** on queue-client startup (in `main()` before the loops, `queue-client.py:758`),
  scan roster entries with `state:"alive"` whose tmux window is gone (`_window_alive`, `:182-190`) and
  flip them to `state:"retired"`, `retire_reason:"died-on-reboot"`. This is what populates the HUD after
  a reboot with zero manual steps.

### Revive verb (resume ONLY — no fallback)
- New action `revive` end-to-end: `mp revive <agent_id>` → `mp` client (new `cmd_revive`, mirrors
  `cmd_kill`, `bin/mp:155-164`) → server `/task/submit` allows `"revive"` (`queue-server.py:222`) →
  queue-client `execute_revive` (new `HANDLERS` entry, `:720`).
- `execute_revive(agent_id)` logic — **hard preconditions, loud errors, no silent spawn:**
  1. Load roster entry. If missing or `state != "retired"` → error.
  2. `session_id` must be non-empty → else error `"not resumable: no session-id captured"`.
  3. The transcript file must exist:
     `~/.claude/projects/<encode(cwd)>/<session_id>.jsonl` where `encode` = cwd with `/`→`-`
     (verified mapping). If absent → error `"not resumable: session transcript missing"`.
  4. Only then: recreate the tmux window in the original `cwd` (reuse `execute_spawn`'s tmux
     new-session/new-window block, `:424-454`) and launch with the spawn_cmd's **claude** replaced by
     `claude --resume <session_id> …` (keep `--dangerously-skip-permissions`, `--settings`,
     `--plugin-dir`). Wait for the `bypass permissions on` banner (`:501-509`), then re-register
     (`state:"alive"`, same `session_id`) and update the roster.
  - There is **no else-branch that spawns fresh.** Any failed precondition returns
    `(False, "<reason>")`; the HUD shows the reason on the row.

### HUD changes (`bin/dashboard.html` + `queue-server.py`)
- New server endpoint **`GET /roster`** (secret-guarded, like `/agents`, `queue-server.py:125-155`):
  reads `run/roster.json`, returns entries with `state:"retired"`, each enriched with a computed
  **`resumable`** bool + `resume_error` (server-side existence check of the transcript file).
- `dashboard.html`: add a second table **"Retired engineers"** (cols: agent_id, spawn cmd, **card**
  (derived), why retired, when, action). The **card** cell is computed in-page by scanning the
  `/todo/board` tasks for the one whose `assignee == agent_id` — not read from the roster. Action cell =
  a **Revive** button that POSTs `{action:"revive", target_agent:<id>}` to `/task/submit`. If
  `resumable:false`, render a disabled red pill with `resume_error` instead of a button. Poll `/roster`
  (+ `/todo/board` for the card lookup) alongside the existing `/agents` + `/clients`
  (`dashboard.html:30-62`). One button = one agent (no select-all control exists or is added).

### Seed fold-back (mandatory per `CLAUDE.md` doctrine)
Every change above is to files **inlined as heredocs** in `seeds/mypeople.seed.md` (queue-client `:645+`,
queue-server `:435`, dashboard `:69`, emit-event `:1636-1779`). The change is not shippable until the
edits are folded into the seed and a **clean container pastes-and-Verifies** it. Runtime files under
`/Users/delattre/mypeople/bin` are edited in lockstep for local iteration.

---

## Smallest meaningful slice (delivers the full journey E2E)
Single host, **claude backend**, manual-reboot simulation (`tmux kill-server`):
1. Persist `cwd` + `spawn_cmd` + `session_id` in `run/roster.json` at spawn; update `session_id` from
   `emit-event` on SessionStart+Stop.
2. `execute_kill` / `retire_on_done` mark `state:"retired"` (+reason) instead of forgetting.
3. Reboot-detect alive-but-window-gone → `died-on-reboot` on queue-client startup.
4. `GET /roster` + the "Retired engineers" table with per-row **Revive** (resumable) / red error pill.
5. `mp revive` / `execute_revive` = **resume-only** with the three hard preconditions; recreate window
   with `claude --resume <session_id>`.

That is the minimum that takes the CEO from "rebooted, team dead" to "click Revive, engineer wakes in
its old session" — with non-resumable cases shown as errors, not silently masked.

## Non-goals (explicit)
- **NO auto restore-all / batch revive.** No "revive everyone" button or verb. One engineer per action. (CEO)
- **NO re-spawn + reload-from-wiki fallback.** Resume-by-session-id is the only revive path; failure to
  resume is a surfaced HUD error, never a fresh spawn. (CEO correction)
- Not in this slice: codex-backend revive (claude first), cross-host revive UX polish, reviving an agent
  whose card is already DONE (roster keeps it but it's expected to stay retired).

---

## E2E Verify (runnable)
```bash
#!/usr/bin/env bash
# Proves: spawn → session-id persisted → retire → HUD lists it w/ spawn cmd → revive → SAME session.
set -euo pipefail
source ~/.config/mypeople/queue.env            # QUEUE_URL, QUEUE_SECRET, INSTALL_DIR
H="$(hostname)"; AID="$H/revive-e2e:eng-1"; CWD="$INSTALL_DIR"
hdr=(-H "X-Queue-Secret: $QUEUE_SECRET" -H "Content-Type: application/json")
roster() { python3 -c "import json,sys;d=json.load(open('$INSTALL_DIR/run/roster.json'));print(json.dumps(d.get('$AID',{})))"; }

# 1. Spawn a claude engineer in a known cwd.
mp spawn "revive-e2e:eng-1" --cwd "$CWD"

# 2. Plant a unique fact in its session, then let it Stop (so session-id is persisted).
CODE="BANANA-$RANDOM"
mp send "revive-e2e:eng-1" "Remember this codeword exactly: $CODE. Reply only: stored."
sleep 8                                         # allow the turn + Stop hook to fire
SID="$(roster | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_id"])')"
test -n "$SID" && echo "PASS: session-id persisted: $SID"
test -f "$HOME/.claude/projects/$(echo "$CWD"|sed 's#/#-#g')/$SID.jsonl" && echo "PASS: transcript on disk"

# 3. Retire it (manual kill) — roster must KEEP it as retired, not forget it.
mp kill "revive-e2e:eng-1"
ST="$(roster | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("state"),d.get("retire_reason"))')"
echo "$ST" | grep -q "retired" && echo "PASS: roster kept it retired ($ST)"

# 4. HUD /roster lists it WITH the spawn command + resumable=true.
curl -s "${hdr[@]}" "$QUEUE_URL/roster" \
 | python3 -c "import json,sys;r=[x for x in json.load(sys.stdin) if x['agent_id']=='$AID'][0];assert 'claude' in r['spawn_cmd'] and r['resumable'];print('PASS: HUD lists retired w/ spawn_cmd + resumable')"

# 5. Revive — must reuse the SAME session-id (resume), not mint a fresh one.
mp revive "revive-e2e:eng-1"
sleep 6
SID2="$(roster | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_id"])')"
test "$SID" = "$SID2" && echo "PASS: revived with SAME session-id ($SID2)"
# the launch command literally contains --resume <SID>:
tmux capture-pane -p -t "mc-revive-e2e:eng-1" -S -200 | grep -q -- "--resume $SID" \
 && echo "PASS: launched via claude --resume $SID" || true

# 6. Prove memory carried over: ask for the codeword; only a resumed session knows it.
mp send "revive-e2e:eng-1" "What was the exact codeword I told you? Reply only the codeword."
sleep 8
tmux capture-pane -p -t "mc-revive-e2e:eng-1" -S -50 | grep -q "$CODE" \
 && echo "PASS: revived agent recalled $CODE → TRUE session resume" \
 || { echo "FAIL: codeword not recalled — not a true resume"; exit 1; }

# 7. Negative path: a roster entry with a missing transcript must ERROR, not spawn fresh.
#    (delete the transcript, attempt revive, expect a 'not resumable' error and NO new window.)
mp kill "revive-e2e:eng-1"
rm -f "$HOME/.claude/projects/$(echo "$CWD"|sed 's#/#-#g')/$SID.jsonl"
mp revive "revive-e2e:eng-1" 2>&1 | grep -qi "not resumable" \
 && echo "PASS: missing transcript surfaced as error (no silent fresh spawn)" \
 || { echo "FAIL: revive did not error on missing session"; exit 1; }

echo "E2E COMPLETE"
```
