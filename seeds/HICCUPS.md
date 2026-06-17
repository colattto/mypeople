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

| mpgen5 batch (per node, Rule-27 harvest — done late, CEO caught the miss) | **mpgen5-1:** J2 onboarding-summary OVERWRITE by Stop hook (real, durability), mp wait-ready string, setsid pidfile under job-control, J25 revive idempotency across re-runs, UTF-8 glyphs in pinned HTML break plain `grep` in Verify. **mpgen5-3:** tailscaled pre-started (§5.6), J2 onboarding-summary VOLATILITY (must be durable), Boss refused an injection-shaped onboarding prompt, first-run dialogs as warned. **mpgen5-2/-4/-5:** no HICCUPS.local written. | ✅ J2 durability folded; tailscaled-pre-start already §5.6; first-run dialogs already §5.5 |
| CEO live HUD 2026-06-17 (gates MISSED) | (1) `hydrating` state label had a zoom/pulse ANIMATION — ugly | ✅ removed all `animation:`/`@keyframes` from both pinned assets (re-pinned: todos `dac5…`, dash `8f9f…`); J29 no-animation gate |
| CEO live HUD 2026-06-17 (gates MISSED) | (2) grid showed TEST/DEMO fixtures (alpha/beta/retiredtest groups, dead hydrating phantoms) left by un-cleaned J11/J25 probes | ✅ J11/J25 must isolate+cleanup; §5.9 queue-server expires stale clients; J26 fresh-grid-is-clean gate |
| CEO live HUD 2026-06-17 (gates MISSED) | (2b) ATTACH link literal `http://x:7681` — unsubstituted placeholder host | ✅ J27 attach-host-is-real gate (never `x`/`100.0.0.0`/empty; matches tailnet IP) |
| CEO live node 2026-06-17 (J14 FALSE GREEN) | (3) RUNNING tmux ≠ his style despite J14-on-disk pass: live server had WheelUpPane BOUND, base-index 0, history 2000, no Dracula — server started before conf placed + TPM/dracula never installed | ✅ §A.1: place conf before server / source-file + install TPM+dracula; J28 gates the RUNNING server config, not just the file |

| CEO 2026-06-17 | unused features to CUT: subtasks, dependencies (blocked-by), hard-gate | ✅ removed from pinned `todos.html` (CSS + `childrenOf`/`unmetDeps` + card relations panel + indicators; re-pinned todos `635b…`, node --check OK) AND from contracts (§6: no `add{parent}`/`parent`/`dependsOn`/`hardGate`); J23 repurposed to a NEGATIVE gate (assert ABSENT); F13 row struck |

| CEO DECISION B 2026-06-17 | exact-pinned-UI (~59% code, fails the adversarial ≤10% bar) REJECTED in favor of truly-generative (almanac/teleprompter level, ≤10% code) | ✅ RE-ARCHITECTED: un-pinned `todos.html`/`dashboard.html` (deleted shipped assets, removed cp/sha256, dropped J14 checksum gate); §7+§A.2 now NL contracts + PLOW **design tokens/consts** (the agent GENERATES components from them); §A.3 verification is behavioral (J9 PLOW + J29 no-anim + J23 no-cut-features + F-gates), not byte-identity. Adversarial gate: seed = **0% pasted code** (0 code fences), ≤10% PASS. |
| CEO DECISION B — tmux tension | his exact `~/.tmux.conf` (verbatim file) vs the no-paste/≤10% bar | ✅ RESOLVED: ship his **settings as consts** in §A.1 (Dracula plugins, base-index 1, history 50000, wheel-unbound, copy-pipe-and-cancel) — small, counts as acceptable spec; the agent GENERATES the conf from them + installs TPM/Dracula + source-file; fidelity gated on the RUNNING server (J28), not a checksum. |

| mpgen7 batch (per node, Rule-27) — UNANIMOUS | TPM clones `dracula/tmux` into `~/.tmux/plugins/**tmux**` (repo basename), NOT `/dracula` — a dir-name check false-negatives | ✅ J28 reworded: verify Dracula by the RUNNING status bar, not a fixed dir |
| mpgen7 batch | Boss onboarding-summary durability (J2) — agents PINNED the summary so the Stop hook can't clobber it (the mpgen5 fix, now applied + confirmed) | ✅ already folded (J2); confirmed working |
| mpgen7 misc | tailscaled pre-running (§5.6 ✓); `claude --append-system-prompt-file` absent in 2.1.168; `bypassPermissionsModeAccepted` IS a top-level key on this image (varies) | noted; non-blocking |

### Batch results log (cont.)
- **mpgen7 (GENERATIVE, Decision B — truly fresh, nothing pre-existing, ≤10% seed): ✅ CONVERGED.** 5/5 nodes, externally verified: serve 200/200, PLOW tokens, NO animations, NO subtasks/deps/hard-gate/reorder, clean grid (only self), attach=real tailnet IP, Boss-on-own-HUD, **RUNNING tmux = his Dracula style** (base-index 1 / wheel-unbound / dracula), feature probe (add·set `state`·`doneCondition`·comment·del) green, SEED_RESULT=DONE. Adversarial ≤10% gate: PASS (0% pasted code).

## OPEN (not yet folded)
- (none — generative seed converged on mpgen7; ready to merge.)

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
