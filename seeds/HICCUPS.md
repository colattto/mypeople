# mypeople SEED — in-container engineer hiccup ledger (Rule 27)

Systematic per-run collection of where **blind generation missed** / what each in-container
engineer had to fix beyond the seed. Every entry must be **folded back** into the seed (cite the §)
or marked OPEN. Harvest sources per run: each gen agent's transcript + pane, its agent-wiki, and
the Verify failures/retries it hit before exit 0.

**Status of collection before 2026-06-17:** NOT systematic. Hiccups were folded ad-hoc from MY
driving observations, not harvested per in-container engineer. This ledger + `harvest-hiccups.sh`
close that gap going forward; the table below backfills what is recoverable.

| Run | Hiccup (what blind gen missed / engineer had to fix) | Folded? → § |
|---|---|---|
| install-flow (pre-gen) | Step-2 `pkill` killed the driver's queue-client; Verify cleanup killed `main:Boss` → node dropped off central | ✅ §5.11 two-plane isolation + §5.3 |
| install-flow | `docker exec … bash -s` missing `-i` → heredoc never reached stdin (no-op install) | ✅ driver (`install-seed.sh`) |
| install-flow | block extractor skipped an indented ```bash block → Step 9 ran twice → "Address already in use" / stale pidfile | ✅ §5.9 liveness/self-heal + driver dedent-walk |
| round-1 | bypass-permissions + trust-folder consent dialogs; arrow keys typed as literal `^[[A` | ✅ launcher pre-accepts `~/.claude.json` + `--settings skipDangerous` |
| round-1 | seedrec recorded 0 segments — Playwright Chromium not installed | ✅ seedrec Step 2 `playwright install chromium` |
| round-2 | `purpose=None` on central — Mac central ran OLD code lacking the field | ✅ → fleet-hub design; §4 heartbeat carries `purpose` |
| round-2 | self-contained install pointed queue-client at 127.0.0.1 → node left the central grid (invisible) | ✅ §5.11 OUTER uplink always re-announces to central |
| uplink | outer uplink registered LATE (after generation) → N nodes invisible while hydrating | ✅ §5.11 UPLINK-FIRST (register `state=hydrating` at bring-up) |
| batch-of-5 | monitor false-green: grep matched `SEED_RESULT=DONE` / `BLOCKED=reason` in the prompt-echo | ⚠️ driver-side (node-state monitoring + `grep -vE`); not a seed gate |
| batch-of-5 | generated TODO UI is a functional **look-alike**, not our product (823→131 lines) | ✅ §A canonical UI asset + checksum gate (J14) |
| CEO 2026-06-17 | generated tmux is generic, not his Dracula+TUI-fix config | ✅ §A.1 `~/.tmux.conf` asset + gate (J14) |

| batch 2026-06-17 (mpgen3 reset) | blind agents IGNORED "copy verbatim" and re-generated their own UI/tmux look-alikes (todos 159 vs 820 lines, tmux 21 vs 43), then self-reported `ready` → FALSE GREEN | ✅ §12 Step 3.5 (literal cp, NOT generate) + J14 (disk-sha, "if you generated your own, you FAILED") + external operator gate |
| batch 2026-06-17 | secret-injection token was an UNSPECIFIED fork — servers replace `__INJECT_SECRET__`, canonical todos used `__QUEUE_SECRET__`, authored HUD used `?s=` → 3 incompatible tokens, parity impossible | ✅ §A secret-injection contract: token pinned `__INJECT_SECRET__`, J14 compares ON-DISK (not served) bytes |
| batch 2026-06-17 (method) | "reset-to-pristine" reused containers — a SHORTCUT, not a true fresh-from-0 hydrate (Rule 14/28: reused container/auth can carry hidden state → false pass) | ✅ batch driver now TEARS DOWN + `docker run` fresh per node + fresh per-node device-login (no auth/container reuse) |

| batch 2026-06-17 (fresh mpgen4) | pinning the UI surfaced a SEED CONTRACT BUG: the pinned `todos.html` sends `doneCondition/dependsOn/workToDone/hardGate/state` (+ `add{text,parent}` subtasks), but §6/§A.2 documented `cond/deps/status/done` — gates J16/J17/J23 tested the WRONG field names → false-green risk. (mpgen4-5 caught it: "I'll make the server accept both name sets.") | ✅ §6 + §A.2 F3/F4/F5/F13 + J16/J17/J18/J23 corrected to the REAL names; "pinned todos.html is source of truth, verify against it not prose" |

| test-method 2026-06-17 | substrates registered to mpgen2-1, a PRE-EXISTING hub from a prior generation — a real fresh-from-zero user has NO hub, so J12/J13 only passed because of a survivor container → CONTAMINATED test. Seed also marked UPSTREAM **Required:yes**, making the standalone product (the actual fresh install) untestable. | ✅ §10 UPSTREAM now optional (standalone default); §5.11 + Step 1 + J12/J13 guarded FLEET-MODE-ONLY (skip when no upstream); §14 canonical test = SINGLE standalone node, nothing pre-existing |

| batch 2026-06-17 (fresh mpgen4, UNANIMOUS 3/5) | `claude --dangerously-skip-permissions` shows a SECOND "Bypass Permissions mode — Yes, I accept" dialog beyond §5.5 onboarding; the onboarding paste's Enter hit "No, exit" → killed the FIRST Boss. Persisted-accept flag is opaque. | ✅ §5.5: `mp spawn` wait-ready auto-detects+dismisses bypass (send `2`+Enter) + trust dialog BEFORE pasting |
| batch 2026-06-17 (fresh mpgen4) | multi-line bracketed paste renders as `[Pasted text #1]`; single Enter doesn't reliably submit (I hit this manually on mpgen3-3 too) | ✅ §5.5b: `mp send`/`spawn` sends Enter, waits ~0.4s, sends a 2nd Enter |
| batch 2026-06-17 (fresh mpgen4) | Stop hook fires before the transcript flushes → empty summary | ✅ §4: Stop hook retries ~4×/0.5s + falls back to session_id transcript lookup |
| batch 2026-06-17 (fresh mpgen4) | field-name bug did NOT trip a gate — agents wrote BOTH server + self-Verify with their own (consistent) names → false-green confirmed; only an EXTERNAL/seed-pinned gate catches it | ✅ already folded (§6 real names); next batch's gates test the pinned names |

### Batch results log
- **mpgen3 (reset-in-place, INVALID method):** all regenerated UI/tmux → parity ✗✗✗. Caught by external gate.
- **mpgen4 (fresh containers, fleet-mode, CONTAMINATED by pre-existing hub + pre-fix seed):** asset parity ✓✓✓ + reorder-gone ✓ on all 5; all 5 self-report J1–J25 pass. Does NOT count (J12/J13 hub-dependent; field-names pre-fix). Yielded the 3 findings above.
- **mpgen5 (STANDALONE, GENUINE — nothing pre-existing, hub destroyed, UPSTREAM unset, fixed seed): ✅ CONVERGED.** 5/5 fresh-from-zero nodes, externally verified (operator, not self-report): disk==canonical (todo✓ dash✓ tmux✓) ×5, reorder-gone ×5, serve 200/200 ×5, Boss-alive-on-own-HUD ×5, and an external feature probe (add · set `state` · `doneCondition` · comment · del — REAL field names) passed ×5. This is the valid one-shot a real user gets. (mpgen5-2 printed no DONE sentinel but is objectively clean on every external gate → pass per "trust the pane, not the self-report".)

## OPEN (not yet folded)
- (none — loop converged on mpgen5: a genuinely-fresh STANDALONE batch one-shots FULLY clean.)

## Mechanism (per run, going forward)
Run `seeds/harvest-hiccups.sh <node...>` after each gen batch. It pulls, per node: Verify
retry/FAIL lines, the gen agent's wiki, and any divergence the agent self-noted; appends a dated
block here for triage. Triage = fold into the seed (cite §) or mark OPEN. A run is not "clean"
until its harvested hiccups are all folded.

## HARVEST 2026-06-17T16:45Z
### mpgen-1
- verify FAIL/retry lines:
- gen agent wiki tail:
- self-noted divergences (NOTE:/HICCUP:/had to):
### mpgen3-1
- verify FAIL/retry lines:
- gen agent wiki tail:
- self-noted divergences (NOTE:/HICCUP:/had to):
_triage: fold each into the seed (cite §) or move to OPEN above._
