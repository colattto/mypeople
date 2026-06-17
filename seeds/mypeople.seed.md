# SEED: mypeople

> seed-format: 1 · **generative**

> **You are an AI coding agent reading this seed.** This is a GENERATIVE seed (like
> `almanac.seed.md` / the teleprompter seed): it encodes **intent + contracts + acceptance
> journeys**, NOT source code. There is **ZERO pre-baked source here on purpose** — no
> full-program heredocs, no base64 blobs. **You GENERATE** the mypeople runtime from this spec
> with your own reasoning, install it on the host, then run **`## Verify`** — a self-contained
> acceptance harness whose **exit code is the truth**. On all gates green print
> `SEED_RESULT=DONE`; on a blocker print `BLOCKED_REASON=<short reason>` and stop.
>
> The contracts in §4–§8 are the load-bearing part: they are battle-hardened requirements
> (each was a real bug once). Satisfy every one. Because **you author every component in one
> pass, they interoperate by construction** — the protocol below pins only what must be exact
> for the gates and for host-quirk survival. Do not paste this seed's prose as code; write the
> code that satisfies it.

---

## 1. Purpose & mental model

mypeople is a small, self-hostable runtime for orchestrating **Claude Code agents** as a team
through an **HTTP queue**, with a **web HUD** and a **TODO board** as the human's front doors.
One node, self-contained, is the product target here.

Mental model — three moving parts the human sees, one that drives:
- **The Boss** (`main:Boss`): a long-lived Claude agent that owns the board, plans, and
  dispatches workers. Exactly one is always up (a **supervisor** guarantees it).
- **The HUD** (`:9900/dashboard`): a live web page listing agents (alive/dead), their summaries,
  and a per-agent **attach** link into their terminal. Plus a "retired engineers" table.
- **The TODO board** (`:9933/`): the human adds priorities; adding one **pings the Boss**, who
  triages/works it. The board and HUD are **one connected system** (cross-linked).
- **The queue** (`:9900`): the spine. `queue-server` holds the registry + task bus; each host
  runs a `queue-client` that heartbeats, registers its agents, and relays tasks into tmux.

The human's loop: open the TODO → add a task → the Boss is pinged → watch the Boss/work in the
HUD → click an agent's name (in a card thread) or the HUD attach link → land in that agent's
live terminal.

---

## 2. Technical approach (stack, prerequisites, constraints)

- **Language/runtime: Python 3 standard library only** for the daemons (`http.server`,
  `json`, `subprocess`, `threading`, `urllib`) — **no pip installs**. The web pages are static
  HTML+CSS+vanilla-JS served by the daemons. This keeps a bare Debian container sufficient.
- **Agents run in `tmux`**; the browser reaches a terminal via **`ttyd`** (one writable ttyd
  per host, `tmux attach`). Agents are **Claude Code** (`claude`), spawned non-interactively.
- **Tailnet (Tailscale)** gives the node a stable `100.x` IP so the HUD/TODO/ttyd are reachable
  from the human's machine. Userland `tailscaled` (no systemd) on a custom socket.
- **Substrate assumption (bare):** a fresh Debian-ish container with **`claude` installed +
  authenticated**, `python3`, `curl`, `tmux`, `sudo`, and `/dev/net/tun` + `NET_ADMIN`. Anything
  else (`jq`, `procps`, `ttyd`, `tailscale`) the **install step adds** — do not assume present.
- **Ports (fixed):** queue-server `9900`, TODO app `9933`, ttyd `7681`.
- **`$INSTALL_DIR`** defaults to `$HOME/mypeople`; layout `bin/ run/ status/ todos/ plugins/`.

---

## 3. Architecture & data model

- **agent_id = `<host>/<sess>:<tab>`** (e.g. `node-1/main:Boss`, `node-1/main:worker-1`). It maps
  1:1 to a tmux window: **session `mc-<sess>`, window `<tab>`** (so `main:Boss` ⇒ `mc-main:Boss`).
  This mapping is a hard contract — the HUD attach link, `mp peek/send`, and the supervisor all
  rely on it.
- **Registry (in queue-server, in-memory):** clients (hosts) and agents. Each agent record:
  `{agent_id, host, session, tab, backend, state(alive|dead), boss_id, summary, ts, tmux_target}`.
- **Durability:** the registry is in-memory; each `queue-client` owns a **durable roster**
  (`run/roster.json`, every agent it ever spawned + spawn cmd + cwd + session-id + retire state)
  and an **agents.json** of currently-live ones, and **re-announces** them on every heartbeat —
  so a queue-server restart (or a reaper false-prune) **self-heals** within one heartbeat cycle.
- **Status files:** `status/mc-<sess>/<tab>.json` = `{status(idle|busy|blocked), summary,
  timestamp, session_id, boss_id, backend, state}`. The HUD/`/agents` merges `summary` in.
- **TODO board store:** `todos/board.v2.json` = `{version, order:[taskId…], tasks:{taskId:{id,
  text, state, assignee, comments:[{id,by,kind,body,ts}], …}}}`.

---

## 4. Protocol contracts (must be exact — these cross the wire / cross processes)

**Queue-server HTTP API** (bind `0.0.0.0:9900`; every route except `/health` and `/dashboard`
requires header `X-Queue-Secret: <QUEUE_SECRET>`; JSON bodies):
- `GET /health` → `{"status":"ok","uptime":N}` (public).
- `GET /clients` → array of `{hostname, attach_base, substrate_ready, last_seen, purpose,
  node_type, recording_url}` — the last three back the HUD machines-grid (§7.1): `purpose` =
  the hydration/group label (e.g. `mypeople`, `airbnb`); `node_type` ∈ {`one-shot-eng`,
  `long-lived-eng`, `system-agent`, `in-substrate-install-eng`}; `recording_url` = the node's
  seedrec recording link (may be empty).
- `GET /agents` → array of agent records (the HUD's source of truth for who's alive).
- `POST /agents/register` `{agent_id, backend, state, boss_id, is_master}`; `POST
  /agents/unregister` `{agent_id}`.
- `POST /heartbeat` `{hostname, attach_base, substrate_ready, purpose, node_type,
  recording_url, state}` → liveness + the host's re-announced agents. **`attach_base` contract:
  see §5.2.** `purpose`/`node_type`/`recording_url` are read from the node's config
  (`NODE_PURPOSE` / `NODE_TYPE` / `NODE_RECORDING_URL` in `queue.env`; `purpose` defaults to
  `mypeople`, `node_type` to `system-agent`). **`state` ∈ {`hydrating`,`ready`,`failed`}** is the
  node's hydration lifecycle (§5.11) — `hydrating` from bring-up, `ready` once the inner Verify
  passes. All surface in `/clients` for the §7.1 grid (which shows each node's `state`).
- `POST /task/submit` `{type(send|peek|kill|spawn|answer|revive), target_agent, payload}` →
  `{task_id}`; `GET /task/poll?hostname=<h>` (clients long/short-poll their tasks); `POST
  /task/result` `{task_id, ok, result}`; `GET /task/<id>` → task status+result (submitters wait
  on this).
- `GET /roster` → JSON array (retired/known engineers, for the HUD revive table).
- `GET /dashboard` → the HUD HTML (**public**, no secret) with `__INJECT_SECRET__` replaced by
  the live secret so its JS can call the gated endpoints.

**`mp` CLI** (in `$INSTALL_DIR/bin/mp`, on `PATH`): verbs `status, spawn, send, peek, kill,
answer, revive`.
- `mp spawn <agent_id> [--backend claude] [--cwd PATH] [--boss <agent_id>] [--master]` — creates
  the tmux window `mc-<sess>:<tab>`, launches the backend, registers the agent. `--master` also
  sends the Boss its onboarding prompt (read `boss-CLAUDE.md`). **Idempotent:** spawning an
  agent_id whose window already exists reuses it, never double-launches.
- `mp send <agent_id> <msg>` — delivers `msg` into the agent's tmux composer and submits it
  (bracketed-paste + Enter, with retry). `mp peek <agent_id>` — returns the agent's live pane +
  a classified state (IDLE/BUSY/BLOCKED). `mp kill <agent_id> [--reason …]` — retires it.
  `mp answer <agent_id> <N>` — selects option N of a pending AskUserQuestion. `mp status` — lists
  agents + heartbeating clients.

**Claude Code hooks plugin** (`plugins/tmux-boss-hooks`, installed per-spawn via
`claude … --plugin-dir`): emits lifecycle events `SessionStart, Stop, PreToolUse, SessionEnd`
to the queue/status files. The **Stop hook** writes the agent's status+summary and, if the
agent has a `boss_id`, routes an `[AGENT NOTIFICATION] <agent_id> finished: <summary>` line into
the **Boss's tmux pane** (`mc-<boss-sess>:<boss-tab>`). This is the JOIN/notification proof.
**Stop-hook flush race (folded 2026-06-17):** the Stop hook can fire BEFORE the final assistant
message is flushed to the transcript → empty summary. The hook must **retry reading the transcript
(~4×/0.5s)** and fall back to locating it by `session_id` under `~/.claude/projects` before giving
up — never emit an empty summary on the first miss.

---

## 5. Hard-won CONTRACTS (battle-hardened — each was a real bug; satisfy ALL)

**5.1 `mp` must be on the PATH of every long-running daemon that calls it.** The TODO server
pings the Boss by shelling `mp send main:Boss …`, resolving `mp` via `shutil.which("mp")`. A
nohup'd daemon does **not** inherit an interactive shell's PATH, so it MUST be launched with
`PATH="$HOME/.local/bin:$INSTALL_DIR/bin:$PATH"`. **If `mp` is not on PATH, `boss_ping` silently
no-ops and add-task never reaches the Boss** (the worst kind of bug — board updates, Boss never
told). Generated launchers must guarantee this; Verify asserts the ping lands (§15 J3).

**5.2 `attach_base` must advertise the node's TAILNET IP, never a docker-internal/LAN IP.** The
HUD builds each agent's attach link from the owning client's `attach_base`. If the client
advertises `http://172.17.0.x:7681` (docker bridge) the link is dead from the human's machine.
The client must publish `http://<tailscale-100.x-ip>:7681`. Get the tailnet IP from
`tailscale ip -4`; **for that to work on a userland/no-systemd tailscaled, symlink the default
socket → the custom socket** (see 5.6) so the bare `tailscale` CLI resolves it.

**5.3 Boss supervisor — always exactly one Boss is up.** A tiny userland loop (own pidfile,
`setsid`, survives the installing shell) checks every ~15s whether the tmux window
`mc-main:Boss` exists; if **absent**, it auto-respawns `mp spawn <host>/main:Boss --master`
(re-onboards from `boss-CLAUDE.md`) — **no human, no "ask another agent."** It must be idempotent
(only spawns when genuinely absent) and key off the **tmux window** (source of truth), not the
queue (a transient queue blip must not trigger a double-spawn). If a Boss can't be brought up,
surface a loud error. Verify kills the Boss and asserts it reappears (§15 J4).

**5.4 Per-node fresh Claude login; NEVER copy a token/volume between nodes.** Each node device-
logs into its OWN credential store once. Copying a live token to a second node rotates refresh
tokens and breaks BOTH (incl. a shared upstream). Generated code/process must never copy auth.
(Auth itself is the substrate's one human step; this seed assumes `claude` is already authed.)

**5.5 Suppress Claude's first-run gates so spawned agents don't hang OR get killed.** A fresh
credential store has no onboarding flag, so the first in-container `claude` shows the theme/
onboarding dialog and `mp spawn` blocks. Set **`hasCompletedOnboarding: true`** (+
`lastOnboardingVersion`, `theme:"dark"`) in `~/.claude.json` (and the cached app-config) BEFORE
any spawn. **BUT THAT IS NOT ENOUGH (folded 2026-06-17, hit by 3/5 fresh nodes):** `claude
--dangerously-skip-permissions` (needed for an autonomous Boss) ALSO shows a SECOND, separate
**"Bypass Permissions mode — 1. No, exit / 2. Yes, I accept"** dialog on first launch, and the
folder-trust dialog. The onboarding paste lands on the bypass dialog and its Enter selects **"No,
exit" — silently killing the very first Boss** (it's the only window in the session, so the session
dies). The persisted accept flag is **opaque** (not a plain top-level `~/.claude.json` key), so the
robust fix is **`mp spawn`'s wait-ready must auto-detect + dismiss BOTH dialogs (send `2`+Enter for
bypass, accept the trust dialog) BEFORE pasting the agent's prompt.** **5.5b — bracketed paste needs
a second Enter:** a multi-line prompt renders collapsed as `[Pasted text #1]` and a single Enter
does NOT reliably submit; `mp send`/`spawn` must send Enter, wait ~0.4s, then send a **second
Enter** (a redundant Enter on an empty composer is a harmless no-op). Verify proves a Boss actually
spawns AND survives (§15 J2/J4).

**5.6 Tailnet on a no-systemd container = userland `tailscaled` on a custom socket + a default-
socket symlink.** Start `tailscaled --state=<dir>/tailscaled.state --socket=<dir>/tailscaled.sock`
under `$INSTALL_DIR/run/tailscale-state/`, `tailscale --socket=<sock> up …`, then
`ln -sf <sock> /var/run/tailscale/tailscaled.sock` so the **bare** `tailscale` CLI (and 5.2's
`tailscale ip -4`) work. Needs `/dev/net/tun` + `NET_ADMIN`.

**5.7 ttyd: one writable instance, `tmux attach`, per-tab attach via URL args.** Run
`ttyd -W -a -p 7681 … tmux attach`. `-a` (allow URL args) is mandatory so
`?arg=-t&arg=mc-<sess>:<tab>` attaches to a specific window. **Verify ttyd FUNCTIONALLY (HTTP
200 on the attach URL) and by bare option name — ttyd 1.7.x rewrites argv for `ps`
(`-t key=value` shows as `key value`), so never grep for `disableLeaveAlert=true`.** A stray
`pkill` must not blank the human's window: run ttyd under a supervisor (respawn within ~2s).

**5.8 Daemons are detached + pid-tracked + idempotently restartable.** Start with `setsid …
</dev/null &`, write a pidfile, and a reinstall stops the prior by pidfile then restarts — never
leave a duplicate. A self-install must not kill the very channel that is driving it: stop a
prior daemon only immediately before relaunching it (graceful in-place handoff), not pre-emptively.

**5.9 Heartbeat-based liveness + self-healing registry.** queue-server reaps an agent whose host
has been silent `QUEUE_DEAD_AFTER` (≈4 missed heartbeats); clients re-announce their live agents
every heartbeat so a server restart / false-prune repopulates within one cycle. No zombie
"alive" agents after a host dies.

**5.10 UTF-8 everywhere.** Set `LANG=C.UTF-8`/`LC_ALL=C.UTF-8` for the queue-client/tmux so the
TUI glyphs (`❯ ● ✻ …`) aren't mangled to underscores.

**5.11 TWO ISOLATED PLANES — the node is ALWAYS visible on the central grid (never an island).**
> **FLEET-MODE ONLY.** This whole contract applies **only when `UPSTREAM_QUEUE_URL` is set** (the
> node is JOINing an existing fleet central). **A STANDALONE install (no upstream — the default
> product, §1, what a fresh-from-zero user gets) does NOT run the OUTER plane at all:** there is no
> uplink, and **J12/J13 are SKIPPED**. Standalone, the node's OWN inner `:9900` HUD is the central
> and its `/dashboard` grid shows its own agents. Never require a pre-existing hub to pass Verify.

When fleet mode IS on, a substrate runs **two mypeople setups that must not touch each other:**

- **OUTER — fleet uplink (JOIN), UPLINK-FIRST.** A thin queue-client in its **OWN dir + config**
  (`$UPLINK_DIR`, default `$HOME/mypeople-uplink`; config `~/.config/mypeople/upstream.env`) that
  **only connects OUT** to the central queue (`UPSTREAM_QUEUE_URL` + `UPSTREAM_QUEUE_SECRET`) —
  it **binds NO local ports** and runs **no** local queue-server.
  **It MUST start FIRST — the very first action of the build (Step 1), BEFORE OS-deps / before
  generating the inner product / before the inner is up** — and register the node immediately
  with **`state=hydrating`** + `purpose` (and `hostname`, tailnet `attach_base` when available,
  `node_type`). It heartbeats **throughout** the whole hydration and **re-announces the node's
  live agents — including the INNER product's `main:Boss` once spawned**, so the node + its Boss
  show on the **central HUD machines-grid (§7.1)**. **State lifecycle:** `hydrating` (from
  bring-up, while generating/installing) → **`ready`** (only when the inner `## Verify` passes) →
  or **`failed`** (on a blocker). **WHY uplink-first:** the CEO must SEE "N substrates hydrating"
  *while* they hydrate — a node must appear on the grid **the moment it starts**, not ~minutes
  later when its inner finishes. (Gap that forced this: the uplink started late → a node was
  invisible on the hub for the entire ~build, so 5 generating nodes showed as 1.) This is the
  plane the install **engineer** lives on and the CEO watches from the first second.
- **INNER — the product (self-contained).** The mypeople the agent installs: its own
  queue-server/HUD/TODO/Boss in `$INSTALL_DIR` (`$HOME/mypeople`), owning the **local ports
  9900/9933/7681**, queue.env → `127.0.0.1`.

**Isolation contract (this is the whole point — the prior bug was the planes shared state):**
the two planes have **separate dirs, configs, pidfiles, and queue.env files**; the OUTER binds
no ports (so no port clash) and the INNER's lifecycle (Step 2 daemon-stops, Step 8 queue.env
rewrite, Step 9 graceful handoff, §5.8) **may only touch INNER state — never the OUTER uplink.**
Installing/restarting the inner product must be **incapable** of stopping, rewriting, or
re-pointing the outer uplink. Result: the node **never goes dark on the central grid** while it
self-hosts. (Root cause of the defect: the install-flow reused ONE `queue.env`/queue-client/dir/
ports for both, so installing the inner clobbered the outer JOIN → the node vanished from the
CEO's HUD.) "I asked for X substrates, I see X" (§7.1) depends on this isolation holding.

---

## 6. The TODO board (state + API + the board→Boss ping)

The TODO app (`todo-server.py`, `:9933`) serves `todos.html` at `/` and `/todos`, and a JSON API
(all gated by `X-Queue-Secret` except the page + `/health`):
- `GET /todo/board` → the board JSON. `POST /todo/update` ops: **`add` `{text}`** (creates a task
  in `needs_brainstorm`, prepends to `order`, returns `{ok,id}`) and **`add {text, parent}`** (a
  **subtask** of `parent`), **`del {id}`**, **`set {id,…}`**. **FIELD NAMES — the pinned
  `assets/todos.html` is the SOURCE OF TRUTH; verify against it, NOT this prose.** The EXACT `set`
  fields the UI sends are **`text`, `doneCondition`, `workToDone`, `dependsOn`, `hardGate`, `state`,
  `done`, `assignee`** — note **`state`** (the status field, NOT `status`), **`doneCondition`** (NOT
  `cond`), **`dependsOn`** (NOT `deps`). `GET /todo/board` returns these SAME names per task. (The
  earlier `cond`/`deps`/`status` naming was a spec error — folded 2026-06-17.) **Manual reorder is
  REMOVED — no `reorder` op, no up/down control** (CEO 2026-06-17); the board renders in `order`
  (newest-first), sorted-visible-then-hidden client-side only.
- `POST /todo/comment {task_id, by, body}` — append a thread comment; **`by` is the author's
  agent_id** for agent comments (`host/sess:tab`), or `"CEO"` for the human.
- `GET /todo/attach?agent=<agent_id>` → `{ok, target:"mc-<sess>:<tab>", base:"<attach_base>"}` —
  resolves an agent to its ttyd attach target (looks up the host's `attach_base` from
  `/clients`). This is the resolver behind click-to-terminal (§7).
- `POST /todo/brainstorm {task_id, body}`, `POST /todo/answer {task_id, body}` (answers the open
  question → promotes out of `needs_brainstorm`), `POST /todo/status {task_id, state}`,
  `POST /todo/proof {task_id, kind, url|body}` (kind ∈ image|video|link|text) — thread/state events.

**The UI is a PINNED asset (§A), not generated** — so every front-end feature is present by
construction. What YOU generate is the **backend that satisfies the exact API the pinned
`todos.html` calls**: the routes above, the exact `set` field names (`doneCondition`/`dependsOn`/
`state` — see above), the `state` enum `needs_brainstorm|working|review|blocked|done|cancelled`,
the board shape (per-task `text`, `state`, `assignee`, `doneCondition`, `workToDone`, `hardGate`,
`dependsOn`, `parent`, `brainstorm`, `comments[]`, `proofs[]`, `unread`, `verified`, `pingsToBoss`),
and the board→Boss ping. **§A.2 lists every feature as a MANDATORY
contract with its Verify gate — none is optional, the blind agent may skip nothing.**

**board→Boss ping (the core value):** on a **non-test** `add` (and on work-state transitions),
the server **pings the Boss**: `mp send <BOSS_AGENT> "[todo] task <id> \"<title>\": <reason>…"`.
`BOSS_AGENT` defaults to `main:Boss`. Test tasks (`{test:true}`) are EXEMPT from the ping — so a
real board→Boss Verify gate MUST add a non-test task (§15 J3). The server logs each ping +
its `mp send` result to `todos/boss-inbox.log` (write `MP_SEND -> main:Boss rc=<n> :: …`). Per
5.1, the ping only works if `mp` is on the server's PATH.

---

## 7. UI/UX + PLOW design system (HUD + TODO share PLOW identity)

> **The two pages are PINNED canonical ASSETS (§A.2), served verbatim — do NOT generate or
> re-theme them.** This section documents what those assets contain + the backend they require; it
> is the spec for the generated server, not a license to re-draw the UI. The §A checksum gate (J14)
> fails any look-alike. The PLOW identity below is already baked into the pinned bytes.

Both pages carry the **Plow Design System v2.0** brand identity (source of truth:
`plow.co/STYLE-GUIDE.md` in the Plow repo). They are **dark product-UI** (audit/terminal
aesthetic), not the light marketing palette.

**Design tokens (exact):** Midnight `#01000A`, **Volt `#D5EF8A`** (signature lime — on dark
backgrounds ONLY), Grove `#5E7A5E`, Iris `#C4BFFF`; surfaces `--dark-bg #111110`,
`--dark-card #1A1A18`, glass `rgba(255,255,255,0.05)`; **warm-white text `#F0F0E8` (never pure
#fff)**, muted `rgba(240,240,232,0.45)`; semantic `--danger #FF3B30`, `--warning #FEBC2E`.
**Fonts (Google Fonts):** **Instrument Serif** (display/headings ≥26px, weight 400),
**DM Sans** (UI/body), **DM Mono** (eyebrow labels, code, agent-ids, timestamps — uppercase
+0.06em). Volt buttons: Volt bg + Midnight text; hover adds a volt glow box-shadow.

**HUD (`/dashboard`):** Instrument-Serif title "mypeople — HUD"; a DM-Mono meta line
(refreshed + client count); the **agents table** (AGENT_ID, STATE, BACKEND, BOSS, SUMMARY,
ATTACH) where `alive` renders in Volt; an **ATTACH** link per agent =
`<attach_base>/?arg=-t&arg=<tmux_target>` (opens the live pane); a **"Retired engineers"** table
with a per-engineer **Revive** (Volt) button. Polls `/agents`+`/clients`+`/roster` every ~3s.

**§7.1 Machines grid (CEO requirement — confirm "I asked for X, I see X").** The HUD must render
a **grid of every machine/container connected to the grid** (one card per `/clients` entry),
**GROUPED BY `purpose`/hydration, with a per-group COUNT in the group header** — e.g. a
`mypeople hydration · 5` group and an `airbnb hydration · 3` group, **never a single flat
total**. The grouping + counts are the whole point: the CEO asks for X substrates of a hydration
and visually confirms exactly X cards under that group. Each node card shows: **type**
(`node_type`: one-shot eng / long-lived eng / always-running system agent / in-substrate install
eng), **machine** (`hostname`), **state** — the hydration lifecycle **`hydrating`** (Volt/pulsing,
inner not up yet) / **`ready`** (inner Verify passed) / **`failed`**, plus alive/dead liveness —
so the CEO sees nodes appear as **hydrating the moment they start**, an **attach link** (`<attach_base>/?arg=-t&arg=mc-main:Boss`, or the node's primary agent), and the
**seedrec recording link** (`recording_url`, shown only when present). Counts are derived live
from `/clients` (group by `purpose`, count members) — they update as nodes join/leave.

**TODO (`/`):** Instrument-Serif "Priorities"; add-a-task input (Enter to add); the board
columns/cards; a **card modal** with the comment **thread**.

**ITEM 2 — cross-navigation (one connected system):** the TODO page has a visible **HUD ↗** link
to `http://<same-host>:9900/dashboard`, and the HUD has a **TODO ↗** link to
`http://<same-host>:9933/`. Build the href from the page's own `location.hostname` so it works
on any node. Verify asserts both links present (§15 J6).

**ITEM 3 — click a commenter's agent name → opens its terminal.** In a card's comment thread,
when a comment's author (`by`) is an **attachable agent_id** (`…/<sess>:<tab>` form), render the
name as a clickable control that calls the attach resolver (`GET /todo/attach?agent=<by>`) and
opens `<base>/?arg=-t&arg=<target>` in a new tab (the §5.7 ttyd attach). Non-agent authors
(`CEO`) are plain text. Verify asserts the wiring + that the resolver returns a live target
(§15 J7).

---

## 8. Boss role & supervisor

- **`boss-CLAUDE.md` (generated doctrine):** the Boss's job description, internalized on
  `--master` spawn. Capture the doctrine **intent** (do not paste a fixed essay): (1) plan-gate —
  no engineering without a brainstorm + plan + verify; (2) autonomous loop — keep the team
  working off the TODO board; (3) fire-and-forget through the queue (`mp`), never raw tmux;
  (4) the board (`:9900/dashboard` + the TODO) is the source of truth. The onboarding turn must
  end with the Boss summarizing its role (Verify can assert the summary carries ≥2 doctrine
  keywords — proves it actually read the doctrine).
- **Supervisor:** §5.3.

---

## 9. Out-of-scope (host-specific — NOT generated by this seed)

Knowledge preserved so it isn't lost, but **not** part of the gated generative build:
- **WhatsApp drain** (`/todo/wa*`, Hermes last-hop): a host-specific notification bridge.
- **Codex backend** (`--backend codex`): the default/only generated backend is `claude`.
- **agentsview / tkmx token-burn + dev-stats reporting:** a separate fleet-telemetry concern
  (installed by the seedbed substrate layer, not the mypeople app).
- **AskUserQuestion remote-answer (`mp answer` widget driving):** `mp answer` is in the CLI
  contract (§4) but its deep widget-driving E2E is not a gate here.

A generated build MAY stub these (e.g. `/todo/wa` returns 501) without failing any §15 gate.

---

## 10. Inputs (Interview)

**Default posture = bare container, paste-and-run.** Assume only a shell + authed `claude` +
`python3`. `## Steps` installs/creates everything else.

| name | required | default | detect | how the seed satisfies it |
|---|---|---|---|---|
| `claude` present + authed | yes | — | `claude auth status` shows "Login method:" | Substrate's one human step (per-node, §5.4). Not done by this seed. |
| `python3` | yes | — | `command -v python3` | Base image; else host pkg mgr. |
| `jq`, `procps`, `ttyd`, `tailscale` | yes | — | `command -v` each | **Steps install** (apt / binary download / install script). NOT assumed present. |
| `/dev/net/tun` + `NET_ADMIN` | yes (tailnet) | — | `[ -c /dev/net/tun ]` | Container must be started with them (§5.6). |
| `QUEUE_SECRET` | no | auto-generate | `grep` `queue.env` | Steps generates if unset. |
| `TS_AUTHKEY` | yes (tailnet) | — | env | Tailscale auth key for `tailscale up` (§5.6). |
| `INSTALL_DIR` | no | `$HOME/mypeople` | — | — |
| `HOST_ID` | no | `$(hostname -s)` | — | Stable node id used in every agent_id. |
| `UPSTREAM_QUEUE_URL` + `UPSTREAM_QUEUE_SECRET` | **no (optional — FLEET mode only)** | — | env / `queue.env` | **STANDALONE is the default product (§1): a fresh install with these UNSET is a complete, self-sufficient node — its OWN inner `:9900` is its central + HUD.** Set them ONLY to JOIN an existing fleet central; then the OUTER uplink registers the node there (§5.11) and J12/J13 apply. **A real user's fresh-from-zero install has NO upstream** — never assume one pre-exists. |
| `NODE_PURPOSE` / `NODE_TYPE` / `NODE_RECORDING_URL` | no | `mypeople` / `system-agent` / `` | env | The node's grid grouping label, type, and seedrec link (§4, §7.1). |
| `UPLINK_DIR` | no | `$HOME/mypeople-uplink` | — | Own dir for the OUTER fleet-uplink (§5.11) — isolated from `$INSTALL_DIR` so the inner install can't touch it. |

**Step 0 — Interview (mandatory):** detect each; send ONE consolidated message (✓ satisfied / ✗
needed / ⚠ prior install to confirm), then build autonomously to `SEED_RESULT=DONE` or one
`BLOCKED_REASON=`.

---

## 11. Components (what YOU generate — no pre-baked source)

Author each from §3–§8. They interoperate because you write them together to the §4 contracts.
- `bin/queue-server.py` — the HTTP queue + registry + reaper + `/dashboard` + `/roster` (§4,§5.9).
- `bin/queue-client.py` — heartbeat (with tailnet `attach_base`, §5.2), agent re-announce,
  task poll→tmux relay, durable roster/agents (§3). **INNER plane** (→ local queue-server).
- **OUTER fleet-uplink (§5.11)** — a thin client in `$UPLINK_DIR` (own config/pidfile, **no
  local ports**) that connects OUT to the central queue and re-announces the node + the inner
  `main:Boss`. (May reuse the queue-client code pointed at `UPSTREAM_QUEUE_URL`, but fully
  isolated from the inner: separate dir, config, pidfile — the inner's lifecycle never touches it.)
- `bin/mp` — the CLI (§4 verbs), incl. idempotent spawn + the §4 tmux mapping.
- `bin/todo-server.py` — GENERATED: the TODO board API + board→Boss ping (§6), serving the PINNED
  `bin/todos.html` at `/`+`/todos`. Must satisfy every API contract the pinned UI calls (§A.2).
- `bin/todos.html` — **NOT generated. PINNED canonical ASSET** (§A.2), served verbatim.
- `bin/dashboard.html` — **NOT generated. PINNED canonical ASSET** (§A.2), served verbatim by
  queue-server at `/dashboard`; queue-server must satisfy the HUD API contract (`/clients`+`/agents`+
  `/roster`+`/revive`, §A.2 F17–F22).
- `bin/boss-supervisor.sh` — always-one-Boss loop (§5.3).
- `boss-CLAUDE.md` — generated doctrine (§8).
- `plugins/tmux-boss-hooks/` — the Claude hooks plugin emitting lifecycle events (§4).
- `~/.tmux.conf` — **NOT generated. Shipped canonical ASSET** (§A) installed verbatim + TPM
  (`~/.tmux/plugins/tpm` + `tmux run '…/tpm'` so Dracula renders). Verify gate asserts
  `sha256(installed ~/.tmux.conf) == canonical` (§A / §15 J14).

---

## 12. Steps — generate & run (zero pre-baked)

Bare host (shell + authed `claude`). State intent; adapt commands to the host.
0. **Interview** (§10).
1. **UPLINK-FIRST (§5.11) — FLEET MODE ONLY; do this BEFORE anything else *if* `UPSTREAM_QUEUE_URL`
   is set. If it is UNSET (standalone — the default fresh install), SKIP this step entirely and go
   to Step 2.** Generate the small outer fleet-uplink
   and **start it immediately** in `$UPLINK_DIR` (own config from `~/.config/mypeople/upstream.env`,
   no local ports), registering the node to `UPSTREAM_QUEUE_URL` with **`state=hydrating`** +
   `purpose`/`node_type`/`hostname` (enrich `attach_base` once the tailnet is up in Step 5). It
   heartbeats throughout. **The node MUST appear on the central hub grid now — before OS-deps,
   before the inner is built** — so the CEO sees it hydrating from the first second. Keep it
   isolated (nothing below may stop/rewrite it).
2. **OS deps.** Ensure `python3, jq, procps(ps), curl, tmux, ttyd, tailscale` — install the
   missing ones (apt / `ttyd` release binary / `tailscale` install script). (On a clean base
   `jq/procps/ttyd/tailscale` ARE missing — install them for real; do not assume.)
3. **Layout + config.** Create `$INSTALL_DIR/{bin,run,status,todos,plugins}`; write
   `~/.config/mypeople/queue.env` (`QUEUE_SECRET` auto-gen if unset, ports, `HOST_ID`,
   `LANG/LC_ALL=C.UTF-8`); set `hasCompletedOnboarding:true` in `~/.claude.json` (§5.5).
3.5 **INSTALL THE PINNED ASSETS — COPY, DO NOT GENERATE (§A).** Before writing any UI/tmux,
   **copy the shipped bytes verbatim**: `cp assets/todos.html $INSTALL_DIR/bin/todos.html`,
   `cp assets/dashboard.html $INSTALL_DIR/bin/dashboard.html`, `cp assets/tmux.conf ~/.tmux.conf`
   (+ install TPM). **These three files are NOT yours to author.** A prior batch IGNORED this and
   re-generated its own UI/tmux look-alikes, then self-reported DONE — a FALSE GREEN. **If
   `sha256(bin/todos.html|bin/dashboard.html|~/.tmux.conf)` ≠ the §A pin, you have FAILED J14** —
   do not "improve", re-theme, or regenerate them. The only code you write for the UI is the
   *server* that serves these files (replacing `__INJECT_SECRET__`, §A).
4. **GENERATE the remaining components** (§11 — servers, `mp`, supervisor, hooks, doctrine) from the
   spec — write the code now, to the §4–§8 contracts. **The UI/tmux are already installed (Step 3.5);
   never overwrite them.**
5. **Tailnet** (§5.6): userland `tailscaled` + `tailscale up` + default-socket symlink; capture
   the `100.x` IP — the uplink's `attach_base` updates to it on the next heartbeat.
6. **Start INNER daemons** (§5.8): `queue-server` (wait `/health`), `queue-client` (heartbeat with
   the tailnet `attach_base`), **`ttyd` (§5.7)**, **`todo-server` with `mp` on PATH (§5.1)**.
7. **Spawn the Boss** (`mp spawn <host>/main:Boss --master`), wait for its onboarded summary,
   then **start the Boss supervisor** (§5.3). The outer uplink (Step 1) re-announces the Boss.
8. **Verify** (§14) — exit code is the truth.
9. **Flip the uplink state** `hydrating`→**`ready`** when Verify passes (or `failed` on a blocker).
   Confirm the node + Boss show on `$UPSTREAM_QUEUE_URL/clients`+`/agents` as `ready`. Keep the
   uplink up for the node's life.

---

## 13. Done (observable)

- `curl :9900/health` ok; `:9900/dashboard` and `:9933/` serve 200 and are reachable on the
  node's **tailnet IP** from another tailnet machine.
- `mp status` lists `<host>/main:Boss [alive]`; the HUD `/agents` shows it alive.
- Adding a task on the TODO pings the Boss (the Boss pane receives `[todo] …`).
- Killing the Boss → the supervisor brings it back into the HUD with no human.
- The HUD attach link / a card commenter's name opens that agent's live terminal.
- Both pages carry the PLOW identity and cross-link to each other.

---

## 14. Verify (runnable acceptance harness — exit code = truth, self-contained)

`## Verify` is a script you generate; **its exit code is the truth (0 = Done)**. It runs on the
host after `## Steps`, **self-installs any tool it needs** (never assume a pre-baked browser/jq),
and asserts the §15 journeys against **absolute values in this spec** — it must NOT diff against
any reference mypeople instance or golden screenshot. A blind generate on a clean node must reach
exit 0 on its own merit. Print each gate's pass/fail line; finish the core path in < 5 min.
Cleanup must **leave the master Boss alive** (the done-condition needs it in the HUD) and only
kill ephemeral test workers.

> **CANONICAL ACCEPTANCE = a SINGLE STANDALONE node with NOTHING pre-existing.** The real test is
> one fresh host, `UPSTREAM_QUEUE_URL` UNSET, no hub/fleet anywhere, reaching exit 0 on J1–J11 +
> J14–J25 (its own inner `:9900` is the central + HUD). **Verify must NOT depend on any
> pre-existing hub** — if a gate only passes because a prior-generation central happens to exist,
> the test is contaminated (CEO 2026-06-17). FLEET mode (J12/J13) is a SEPARATE, opt-in scenario:
> to test it, generate a FRESH hub from THIS seed first (a standalone node = a central), then JOIN
> fresh nodes to it — never to a survivor container.

---

## 15. Verification journeys (the gates — ALL must pass, asserted on this node only)

1. **Install one-shot.** From a fresh bare node, `## Steps` runs to `SEED_RESULT=DONE` with no
   ad-hoc fixes; `:9900/health` ok; `bin/` has the generated components.
2. **Boss in the HUD.** `mp status` shows `<host>/main:Boss [alive]`; `GET /agents` (with secret)
   contains it with `state=alive`; the Boss's onboarding summary carries ≥2 doctrine keywords
   (plan/approve/queue/mp/fire-and-forget/autonomous). *(Assert the INSTALLED Boss — do not spawn
   a fresh one to mask a missing one. No Boss in the HUD = FAIL, even if everything else passes.)*
3. **Board → Boss ping.** Add a **non-test** task via `POST /todo/update {op:add,text:…}` while
   the Boss is idle. *Expect:* it lands on `/todo/board` AND the **Boss pane receives the
   `[todo] … <taskId> …` ping** within ~30s (key off pane-delivery; a busy Boss may rc=1 yet the
   ping still pastes). An EMPTY Boss pane = the §5.1 `mp`-not-on-PATH regression ⇒ FAIL.
4. **Supervisor resurrection.** The supervisor daemon is alive; kill `mc-main:Boss`; *Expect:* it
   **auto-respawns** and reappears `alive` in `/agents` within the supervisor cycle (no human).
5. **TODO add-task round-trips.** A task created via the API is read back on `/todo/board` and
   shown on the page; the app serves 200 on `:9933`.
6. **Cross-nav.** `:9933/` HTML links to `:9900/dashboard`; `:9900/dashboard` links to `:9933`.
7. **Click-to-terminal.** The TODO comment thread wires an attachable commenter's name to the
   attach action, and `GET /todo/attach?agent=<host>/main:Boss` returns `ok` + a
   `mc-<sess>:<tab>` target. (Strongest: opening the attach URL renders the live pane.)
8. **Attach opens the LIVE pane.** ttyd is bound on the **advertised** port; the attach URL
   `<attach_base>/?arg=-t&arg=mc-main:Boss` returns 200 and the target is a **live (non-dead)**
   pane; a stray `pkill -x ttyd` is respawned (still 200 after ~5s) per §5.7.
9. **PLOW identity.** BOTH `:9933/` and `:9900/dashboard` carry **Volt `#D5EF8A`** + the Plow
   typefaces (`Instrument Serif`/`DM Sans`/`DM Mono`).
10. **Reachable from the human's machine.** The HUD + TODO answer 200 on the node's **tailnet
    IP** (not just localhost) — i.e. `attach_base`/pages use the `100.x` address (§5.2).
11. **Machines grid grouped by purpose with counts (§7.1).** The HUD renders a grid of every
    connected machine (one card per `/clients` entry) **grouped by `purpose` with a per-group
    count header**, NOT a flat total. *Assert:* `GET /clients` carries `purpose`/`node_type`/
    `recording_url`; the served HUD HTML implements per-`purpose` grouping + counts and per-card
    `type/machine/state/attach/recording`; and seeding two heartbeats with distinct purposes
    (e.g. `POST /heartbeat purpose=mypeople` ×N and `purpose=airbnb` ×M) yields exactly two
    groups whose counts are N and M (e.g. `mypeople hydration · N`). This is the "I asked for X,
    I see X" check — the CEO counts the cards under a hydration's group.
12. **Two-plane isolation — inner install never knocks the node off the central grid (§5.11).**
    **(FLEET-MODE ONLY — SKIP this gate entirely when `UPSTREAM_QUEUE_URL` is unset; a standalone
    install has no OUTER plane and is still fully Done.)** Prove the OUTER uplink and INNER product
    are isolated and the node stays visible:
    (a) `GET $UPSTREAM_QUEUE_URL/clients` lists this `hostname` (with `purpose` + tailnet
    `attach_base`) and `GET $UPSTREAM_QUEUE_URL/agents` lists `<host>/main:Boss` `alive` — i.e.
    the node + its INNER Boss show on the **central** grid, not just locally;
    (b) the OUTER uplink runs from `$UPLINK_DIR` (separate dir/config/pidfile from `$INSTALL_DIR`)
    and binds **no** local ports;
    (c) **re-run the INNER install AND restart the inner daemons (queue-server/client/ttyd/todo),
    then re-assert (a) still holds within one heartbeat** — the inner lifecycle must be incapable
    of stopping or re-pointing the outer uplink. A node serving its own HUD/TODO but absent from
    the central `/clients`+`/agents` (or whose outer uplink died when the inner restarted) = the
    island regression ⇒ FAIL.
13. **Uplink-FIRST hydration visibility (§5.11).** **(FLEET-MODE ONLY — SKIP when `UPSTREAM_QUEUE_URL`
    is unset.)** The node must appear on the central hub grid
    as **`hydrating` BEFORE its inner is up** — so the CEO sees it the moment it starts. *Assert:*
    the outer uplink started first (its pidfile/first heartbeat predates the inner queue-server's
    start; equivalently, during a fresh bring-up the node shows on `$UPSTREAM_QUEUE_URL/clients`
    with `state=hydrating` while `:9900` is still down), and after install it shows `state=ready`.
    A node that only appears on the hub AFTER its inner is up = the uplink-late regression ⇒ FAIL.
    (N substrates must show as `hydrating` on the grid concurrently while they build — not 1.)
14. **Asset parity — ON-DISK == canonical (§A).** Verify computes `sha256` of the installed
    `~/.tmux.conf`, `bin/todos.html`, `bin/dashboard.html` and asserts each equals the §A pin
    (`9169…d920e`, `e8fb…ff95`, `cf32…1f6e`). **Compare the on-disk file (it keeps the
    `__INJECT_SECRET__` token), NOT the served bytes** (the server injects the live secret at
    serve-time, so served ≠ disk by design). ANY mismatch (a re-themed/re-generated look-alike, or a
    stale asset) = FAIL. The asset MUST be installed by **copying the shipped bytes** (`cp
    assets/… bin/…`), never authored — **if you generated your own UI/tmux, J14 fails** (this is the
    look-alike regression; CEO 2026-06-17). **Also assert manual reorder is GONE:** the disk
    `todos.html` contains no `op:'reorder'` / `.ictrl up` / `.ictrl down`, and `update{op:reorder}`
    is unsupported.
15. **Delete task.** `update{op:del,id}` removes the task from `/todo/board` (tasks + order). (F2)
16. **Inline edit.** `update{op:set,id,text|doneCondition|assignee}` patches that field (note the
    REAL names per §6); read back on the board. (F3)
17. **State enum.** Setting each of `working|review|blocked|done|cancelled|needs_brainstorm` via
    `set{state}` (field is **`state`**, NOT `status`)/`/todo/status` persists + reads back; an
    invalid value is rejected. (F4)
18. **Done toggle.** `set{done:true}`/`set{workToDone:true}` moves the task to `state=done`; the
    board reflects it. (F5)
19. **Brainstorm + gating.** `/todo/brainstorm{task_id,body}` stores the body; a `needs_brainstorm`
    task is flagged not-workable on the board. (F6)
20. **Answer promotes.** `/todo/answer{task_id,body}` records the answer AND moves the task out of
    `needs_brainstorm`. (F7)
21. **Unread count.** `/todo/board` returns a per-task `unread` integer that rises when a new
    comment is added by someone other than the reader. (F9)
22. **Proofs.** `/todo/proof{task_id,kind,url|body}` (kind ∈ image|video|link|text) appends to the
    task's `proofs[]`, returned on the board. (F10)
23. **Dependencies.** `set{id,dependsOn:[ids]}` persists; the board returns `dependsOn` for the task
    (field is **`dependsOn`**, NOT `deps`). (F13)
24. **Verified badge.** A task with `verified=true` on the board is served with the "verified"
    badge in the page. (F16)
25. **Retired + revive.** `/roster` carries `retired` entries; `POST /revive{agent_id}` clears the
    retired flag (agent re-eligible), reflected on the next `/roster`. (F21)

> Gates J14–J25 are NON-OPTIONAL (CEO 2026-06-17): the Verify harness MUST assert every one. A
> green run with any F-feature unexercised is a FALSE GREEN — the harness itself fails the check.

---

## 16. Failure modes (host quirks — guidance, not code)

- **add-task never reaches the Boss** → `mp` not on todo-server's PATH (§5.1); the server's
  `shutil.which("mp")` was None and `boss_ping` silently skipped. Launch with PATH set.
- **HUD attach link dead from the human's machine** → `attach_base` is a docker/LAN IP (§5.2);
  fix the tailnet-IP resolution (+ §5.6 socket symlink).
- **No Boss in the HUD after a green Verify** → cleanup killed the master Boss, or no supervisor
  (§5.3). Verify must leave the Boss alive and assert it (J2/J4).
- **Spawned agent hangs / `mp spawn` blocks** → first-run onboarding dialog (§5.5).
- **`tailscale ip -4` empty on a no-systemd node** → missing default-socket symlink (§5.6).
- **ttyd "not running" false-fail** → grepped `disableLeaveAlert=true`; ttyd rewrote argv —
  verify functionally (HTTP 200) and by bare option name (§5.7).
- **Self-install kills its own driver** → a daemon stop was pre-emptive; do graceful in-place
  handoff right before relaunch (§5.8).

---

## 17. Convergence notes (read before building)

- **You write every component in one pass → they interoperate by construction.** The §4 protocol
  pins only what must be exact (agent_id↔tmux, the gated endpoints, heartbeat `attach_base`).
- **The contracts in §5 are non-negotiable** — each is a real bug that bit a prior build. The
  fastest path to a clean one-shot is to satisfy all of §5 up front, not rediscover them.
- **Verify against §-values, never a reference app** (§14). A blind agent on a clean node with no
  other mypeople anywhere must reach exit 0.
- **Stay in scope (§9).** Stub the out-of-scope surfaces; don't let them block a gate.

---

## A. Canonical ASSETS — shipped verbatim, NOT generated (the design-vs-spec exception)

Behavior/protocol/runtime are **generated** from §4–§8 (they ARE specs → reproduce faithfully).
But **bespoke design artifacts are NOT generatable from prose** — blind generation yields a
functional look-alike, not *our* product. So these files are **shipped verbatim** and
**sha256-pinned**; the generated runtime must *serve them unchanged* and satisfy the API contract
they call. Install each by writing the exact bytes below (do not re-design, re-theme, or
"improve"). Each has a Verify gate asserting `sha256(installed) == canonical`.

| Asset | Install path | Canonical sha256 |
|---|---|---|
| `tmux.conf` | `~/.tmux.conf` | `9169409877764c61de2d29b3bc72c36523617b3d24f95689f40ca1ac47ed920e` |
| `todos.html` | `bin/todos.html` (served at TODO `/` + `/todos`) | `e8fb75453e215672cb3d6a8e78ceb09ea39c38460959c02b7d7ed81e5111ff95` |
| `dashboard.html` | `bin/dashboard.html` (served at `/dashboard`) | `cf3215effbac35fda062408790293925eec882782aa261f5f7c7c3e0d6b91f6e` |

**Secret-injection contract (pinned — was an unspecified fork that broke parity):** both pinned
pages contain the literal token **`__INJECT_SECRET__`** (`const SECRET="__INJECT_SECRET__"`). The
generated `todo-server.py` and `queue-server.py` MUST serve each page with `__INJECT_SECRET__`
replaced by the live `QUEUE_SECRET` at serve-time (so the page's gated API calls authenticate).
**The checksum gate (J14) is computed on the ON-DISK asset (which still contains the token), NOT on
the served bytes** (served bytes differ by the injected secret, by design).

The verbatim bytes of all three ship with this seed in `seeds/assets/{tmux.conf,todos.html,dashboard.html}`.
A blind paste installs each by copying those bytes unchanged (the tmux.conf is also inlined at §A.1).

**§A.1 `~/.tmux.conf` (the CEO's tmux style — Dracula + the hard-won TUI fixes).** Write exactly:

```tmux
# ── Dracula Theme ──────────────────────────────────────────
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'dracula/tmux'

set -g @dracula-plugins "cpu-usage ram-usage time"
set -g @dracula-show-powerline false
set -g @dracula-show-left-icon session
set -g @dracula-military-time true
set -g @dracula-day-month false
set -g @dracula-cpu-usage-label "CPU"
set -g @dracula-ram-usage-label "RAM"
set -g @dracula-show-timezone false

# ── General ───────────────────────────────────────────────
set -g default-terminal "tmux-256color"
set -ga terminal-overrides ",xterm-256color:Tc"
set -g mouse on
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on
set -g history-limit 50000
set -sg escape-time 10

# ── Mouse selection ───────────────────────────────────────
unbind-key -T copy-mode    MouseDown1Pane
unbind-key -T copy-mode-vi MouseDown1Pane
# copy-pipe-and-cancel (NOT copy-pipe) — without -and-cancel the pane stays
# in copy-mode after every mouse-drag selection and silently swallows the
# user's next keystrokes until they press Escape.
bind-key   -T copy-mode    MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "pbcopy"
bind-key   -T copy-mode-vi MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "pbcopy"

# ── Mouse-wheel scroll ────────────────────────────────────
# Claude TUI renders on the MAIN screen (alternate_on=0) and does not
# request mouse mode, so tmux's default WheelUpPane binding falls through
# to `copy-mode -e` and silently traps every subsequent keystroke until
# Escape. Kill the wheel→copy-mode path entirely. Use `prefix [` for
# explicit scrollback when needed.
unbind-key -T root WheelUpPane
unbind-key -T root WheelDownPane

# ── TPM (must be last) ────────────────────────────────────
run '~/.tmux/plugins/tpm/tpm'
```

Then install TPM + plugins so the Dracula status bar actually renders:
`git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm` and, in a tmux server,
`~/.tmux/plugins/tpm/bin/install_plugins`. **Caveat:** `pbcopy` is macOS-only — in the Linux
container the copy binding is a harmless no-op (fails silently on drag, never at config-load); the
substantive fixes (wheel/copy-mode un-trap, escape-time, base-index, Dracula) all apply. Ship the
file **byte-for-byte** so the checksum gate passes; do not substitute a Linux clipboard tool.

**§A.2 `bin/todos.html` + `bin/dashboard.html` (the real product UI) — served verbatim, every
feature a MANDATORY gated contract.** Both ship verbatim from `seeds/assets/`, sha256-pinned, served
unchanged. Because the UI is pinned, every front-end feature is present by construction; the blind
agent generates the **backend** that satisfies the exact API each pinned page calls. **NO feature is
optional. NO "endpoint exists but UI unspecified."** Each row below is a contract; Verify has a gate
(J-id) that exercises it; any missing/wrong = FAIL.

**TODO backend (`todo-server.py`, `:9933`) — every gate:**

| # | Feature (what the pinned UI does) | Backend contract | Gate |
|---|---|---|---|
| F1 | add task (Enter) | `update{op:add,text}` → task in `needs_brainstorm`, prepended to `order` | J3 |
| F2 | delete task | `update{op:del,id}` removes from tasks+order | J15 |
| F3 | edit text / done-condition / assignee inline | `update{op:set,id,text\|doneCondition\|assignee}` patches the field (REAL names, §6) | J16 |
| F4 | state change (6-enum) | `update{op:set,id,state}` (field **`state`**) or `/todo/status`; enum `needs_brainstorm\|working\|review\|blocked\|done\|cancelled` | J17 |
| F5 | done checkbox / work-to-done toggle | `set{done}`/`set{workToDone}` flips `state`→`done`, renders strikethrough | J18 |
| F6 | brainstorm block + needs_brainstorm gating | `/todo/brainstorm` stores body; `needs_brainstorm` tasks show the ⚠ needbrain banner | J19 |
| F7 | answer the open question → promote | `/todo/answer` records answer + moves task out of `needs_brainstorm` | J20 |
| F8 | comment thread (card modal) | `/todo/comment{task_id,by,body}` appends to `comments[]`, `by`=agent_id\|CEO | J5 |
| F9 | unread badge | board returns per-task `unread` count; UI reads localStorage READ_KEY | J21 |
| F10 | proofs (image/video/link/text + more) | `/todo/proof{task_id,kind,url\|body}` appends to `proofs[]`; board returns them | J22 |
| F11 | assignee chip → attach to that engineer's terminal | `/todo/attach?agent=` resolves `{target,base}` (live) | J7 |
| F12 | ITEM 3 — clickable commenter agent name → terminal | same resolver; non-agent (`CEO`) authors are plain text | J7 |
| F13 | dependencies + subtasks | `set{dependsOn:[ids]}` (field **`dependsOn`**); `add{text,parent}` for subtasks; board returns `dependsOn`/`parent` | J23 |
| F14 | board→Boss ping on non-test add | `mp send <BOSS_AGENT>` logged to `boss-inbox.log` (§6); test tasks exempt | J3 |
| F15 | ITEM 2 — cross-nav HUD ↗ | static link to `:9900/dashboard` (built from `location.hostname`) | J6 |
| F16 | verified badge | board returns `verified`; UI shows the "verified" badge | J24 |

**HUD backend (`queue-server.py`, `/dashboard`) — every gate:**

| # | Feature | Backend contract | Gate |
|---|---|---|---|
| F17 | machines grid grouped by `purpose` + per-group COUNT | `/clients` carries `purpose`; ≥1 group header `"<purpose> hydration · N"` | J11 |
| F18 | per-node state `hydrating\|ready\|failed` + alive/dead | `/clients` carries `state` + `last_seen` (§5.11) | J11 |
| F19 | per-node type / machine / attach / recording | `/clients` carries `node_type`,`hostname`,`attach_base`,`recording_url` | J11 |
| F20 | agents table (id/state/backend/boss/summary/attach) | `/agents` carries those fields + `tmux_target` | J8 |
| F21 | retired engineers + Revive button | `/roster` carries `retired`; `POST /revive{agent_id}` works | J25 |
| F22 | ITEM 2 — cross-nav TODO ↗ + live/stale pill + counts | static link to `:9933`; counts from `/clients`+`/agents` | J6 |

**§A.3 Gate (J14) — checksum, the parity guarantee.** Verify computes `sha256` of each installed
asset (`~/.tmux.conf`, `bin/todos.html`, `bin/dashboard.html`) and asserts equality with the §A
table; ANY mismatch = FAIL. This is what makes "generated == OUR EXACT product," not a look-alike.
The F-gates above then prove the generated backend satisfies every feature the pinned UI invokes.