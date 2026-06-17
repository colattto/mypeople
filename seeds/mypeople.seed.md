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
- `GET /clients` → array of `{hostname, attach_base, substrate_ready, last_seen}`.
- `GET /agents` → array of agent records (the HUD's source of truth for who's alive).
- `POST /agents/register` `{agent_id, backend, state, boss_id, is_master}`; `POST
  /agents/unregister` `{agent_id}`.
- `POST /heartbeat` `{hostname, attach_base, substrate_ready}` → liveness + the host's
  re-announced agents. **`attach_base` contract: see §5.2.**
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

**5.5 Suppress Claude's first-run onboarding so spawned agents don't hang.** A fresh credential
store has no onboarding flag, so the first in-container `claude` shows the theme/onboarding
dialog and `mp spawn` blocks. The install must set **`hasCompletedOnboarding: true`** (+
`lastOnboardingVersion`, `theme:"dark"`) in `~/.claude.json` (and the cached app-config) BEFORE
any spawn. Verify proves a Boss actually spawns (§15 J2).

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

---

## 6. The TODO board (state + API + the board→Boss ping)

The TODO app (`todo-server.py`, `:9933`) serves `todos.html` at `/` and `/todos`, and a JSON API
(all gated by `X-Queue-Secret` except the page + `/health`):
- `GET /todo/board` → the board JSON. `POST /todo/update` ops: **`add` `{text}`** (creates a task
  in `needs_brainstorm`, prepends to `order`, returns `{ok,id}`), `del {id}`, `set {id,…}`,
  `reorder {order}`, `addsub {id,text}`.
- `POST /todo/comment {task_id, by, body}` — append a thread comment; **`by` is the author's
  agent_id** for agent comments (`host/sess:tab`), or `"CEO"` for the human.
- `GET /todo/attach?agent=<agent_id>` → `{ok, target:"mc-<sess>:<tab>", base:"<attach_base>"}` —
  resolves an agent to its ttyd attach target (looks up the host's `attach_base` from
  `/clients`). This is the resolver behind click-to-terminal (§7).
- `POST /todo/status`, `/todo/brainstorm`, `/todo/proof`, `/todo/answer` — thread/state events.

**board→Boss ping (the core value):** on a **non-test** `add` (and on work-state transitions),
the server **pings the Boss**: `mp send <BOSS_AGENT> "[todo] task <id> \"<title>\": <reason>…"`.
`BOSS_AGENT` defaults to `main:Boss`. Test tasks (`{test:true}`) are EXEMPT from the ping — so a
real board→Boss Verify gate MUST add a non-test task (§15 J3). The server logs each ping +
its `mp send` result to `todos/boss-inbox.log` (write `MP_SEND -> main:Boss rc=<n> :: …`). Per
5.1, the ping only works if `mp` is on the server's PATH.

---

## 7. UI/UX + PLOW design system (HUD + TODO share PLOW identity)

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

**Step 0 — Interview (mandatory):** detect each; send ONE consolidated message (✓ satisfied / ✗
needed / ⚠ prior install to confirm), then build autonomously to `SEED_RESULT=DONE` or one
`BLOCKED_REASON=`.

---

## 11. Components (what YOU generate — no pre-baked source)

Author each from §3–§8. They interoperate because you write them together to the §4 contracts.
- `bin/queue-server.py` — the HTTP queue + registry + reaper + `/dashboard` + `/roster` (§4,§5.9).
- `bin/queue-client.py` — heartbeat (with tailnet `attach_base`, §5.2), agent re-announce,
  task poll→tmux relay, durable roster/agents (§3).
- `bin/mp` — the CLI (§4 verbs), incl. idempotent spawn + the §4 tmux mapping.
- `bin/todo-server.py` + `bin/todos.html` — the TODO board + API + board→Boss ping (§6) + PLOW
  identity + cross-nav + click-to-terminal (§7).
- `bin/dashboard.html` — the HUD (§7), served by queue-server at `/dashboard`.
- `bin/boss-supervisor.sh` — always-one-Boss loop (§5.3).
- `boss-CLAUDE.md` — generated doctrine (§8).
- `plugins/tmux-boss-hooks/` — the Claude hooks plugin emitting lifecycle events (§4).
- `~/.tmux.conf` + TPM — usable tmux (mouse, status bar, UTF-8).

---

## 12. Steps — generate & run (zero pre-baked)

Bare host (shell + authed `claude`). State intent; adapt commands to the host.
0. **Interview** (§10).
1. **OS deps.** Ensure `python3, jq, procps(ps), curl, tmux, ttyd, tailscale` — install the
   missing ones (apt / `ttyd` release binary / `tailscale` install script). (On a clean base
   `jq/procps/ttyd/tailscale` ARE missing — install them for real; do not assume.)
2. **Layout + config.** Create `$INSTALL_DIR/{bin,run,status,todos,plugins}`; write
   `~/.config/mypeople/queue.env` (`QUEUE_SECRET` auto-gen if unset, ports, `HOST_ID`,
   `LANG/LC_ALL=C.UTF-8`); set `hasCompletedOnboarding:true` in `~/.claude.json` (§5.5).
3. **GENERATE the components** (§11) from the spec — write the code now, to the §4–§8 contracts.
4. **Tailnet** (§5.6): userland `tailscaled` + `tailscale up` + default-socket symlink; capture
   the `100.x` IP for `attach_base`.
5. **Start daemons** (§5.8): `queue-server` (wait `/health`), `queue-client` (heartbeat with the
   tailnet `attach_base`), **`ttyd` (§5.7)**, **`todo-server` with `mp` on PATH (§5.1)**.
6. **Spawn the Boss** (`mp spawn <host>/main:Boss --master`), wait for its onboarded summary,
   then **start the Boss supervisor** (§5.3).
7. **Verify** (§14) — exit code is the truth.

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
