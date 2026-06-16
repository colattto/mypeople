# SEED: mypeople

> seed-format: 1

> **You're an AI agent reading this seed.** Your job: run `## Step 0 Interview` to gather inputs, then execute every Step in order, then run the `## Verify` block in a sub-shell. On exit code 0 print `SEED_RESULT=DONE` and stop. On any blocker print `BLOCKED_REASON=<short reason>` and stop. Do not ask the user what to do with this file — that's already specified below.

## Goal

Install the mypeople runtime on this host with claude already installed: a small HTTP queue (queue-server), a heartbeat/dispatch client (queue-client), a CLI (`mp`) for `spawn / send / peek / kill / status`, a per-spawn Claude Code hooks plugin so agents emit lifecycle events, a Boss role that internalizes a doctrine on spawn, a HUD + per-tab browser-attach (ttyd), and a Tailscale tailnet join so the HUD + ttyd are reachable from anywhere on the tailnet via a stable hostname.

The agent backend is pluggable: `--backend claude` (default) and `--backend codex` (OpenAI Codex CLI) share the same queue, tmux, notification pipeline, and `mp` verbs. The queue-client carries a per-backend TUI-marker table so spawn/peek/send work for either; Codex turn-end is bridged to the same Stop-hook contract via the `codex-notify` hook. Codex support is install-complete out of the box, but a working `--backend codex` agent additionally requires the `codex` CLI to be installed AND logged in on this host (see Step 7.6).

After install: `http://<TS_HOSTNAME>.<tailnet>.ts.net:9900/dashboard` (HUD) and `http://<TS_HOSTNAME>.<tailnet>.ts.net:7681/?arg=-t&arg=mc-main:Boss` (ttyd attach) Just Work from any tailnet node.

The seed describes **intent**; the agent reading it adapts to whatever OS / package manager / privilege model the host has. macOS, Debian, Ubuntu, RHEL — pick the right install incantation for each component named in `## Components`. If you're inside a sandboxed Linux container without TUN, that's a sandbox issue you resolve outside the seed (e.g. `--cap-add NET_ADMIN --device /dev/net/tun`).

## Done

Each independently verifiable from a fresh shell.

**JOIN-mode done** (when `UPSTREAM_QUEUE_URL` is set): the node runs a `queue-client` (+ `ttyd`) but NO local `queue-server` / Boss / tailnet identity; it appears in the UPSTREAM's `/clients` (and `mp status`) as a heartbeating client under `HOST_ID`; and a task submitted upstream targeting `HOST_ID/...` round-trips to this node's client. The self-contained criteria below apply only when `UPSTREAM_QUEUE_URL` is unset.

**Runtime (self-contained):**
- `curl http://127.0.0.1:9900/health` returns 200 with `{"status": "ok"}`.
- `queue-server` and `queue-client` processes both alive in `ps`.
- `ttyd` running with `tmux attach` so per-tab attach URLs work.
- tailscaled running, node online on the tailnet, HUD + ttyd reachable on the tailscale IP.
- **Liveness is heartbeat-based**: an agent whose host stops heartbeating (e.g. its container is removed) auto-drops from `/agents` and the HUD within `QUEUE_DEAD_AFTER` seconds — no zombie agents lingering as `alive` after `mp kill` times out on a dead host. The reaper also prunes the dead host from `/clients`.
- **Registry survives a server restart**: the in-memory registry is rebuilt automatically — each queue-client owns a durable record of its agents (`run/agents.json`) and re-announces them every heartbeat, so after a queue-server restart (or a reaper false-prune) the HUD repopulates with the still-running agents within one heartbeat cycle, with no manual re-registration.
- **Retired engineers survive a reboot and can be REVIVED (true session resume)**: every spawned engineer is recorded in a durable roster (`run/roster.json`) with its exact spawn command and `cwd`; the `emit-event` hook persists its Claude **session-id** at SessionStart. `mp kill` (manual or the board's DONE→auto-retire) marks the engineer `retired` instead of forgetting it; on queue-client startup any roster engineer whose tmux window is gone (e.g. a reboot) is flagged `died-on-reboot`. The HUD's **"Retired engineers"** table lists each with its spawn command, why it retired, when, and its card (derived from the board by assignee). **Revive** (`mp revive <agent_id>` or the per-engineer HUD button — one at a time, NO restore-all) resumes the engineer's ACTUAL prior session via `claude --resume <session-id>`. Resume-by-session-id ONLY: if it can't resume (no session-id, or transcript gone) the HUD shows a hard error — there is **no** silent fresh-spawn fallback.

**Boss role:**
- `~/mypeople/boss-CLAUDE.md` is installed (the Boss's job description, inlined in this seed).
- `mp spawn <host>/main:Boss --master --backend claude` creates the Boss tab AND sends an onboarding prompt that has the agent read `boss-CLAUDE.md`.
- After the Boss's onboarding turn, `~/mypeople/status/mc-main/Boss.json` exists with `status: "idle"` and a `summary` that mentions ≥2 doctrine keywords (`plan`, `approve`, `queue`, `mp`, `fire-and-forget`, `autonomous`).

**Agent loop:**
- `mp spawn <host>/main:worker-1 --backend claude --boss <host>/main:Boss` creates a worker tab whose env has `BOSS_ID=<host>/main:Boss`.
- `mp send <host>/main:worker-1 "msg"` types the message into the worker's pane via bracketed-paste, intact.
- `mp peek <host>/main:worker-1` reports the agent's TRUE live state: a header `state=BUSY` while a turn is running (even if its composer holds a freshly-queued message) and `state=IDLE` when awaiting input — derived from the Claude TUI footer, not inferred from a raw buffer dump. The Boss can always tell a working agent from a stuck one.
- When the worker's Stop hook fires: status JSON written, `[AGENT NOTIFICATION]` line typed into the Boss's pane via the queue.
- When a worker raises an **AskUserQuestion** form (a blocked turn, not a Stop): the `PreToolUse` hook fires `[AGENT QUESTION]` to the Boss carrying the question + the exact offered options, and the Boss can unblock it remotely with `mp answer <agent> <option-number | text>` — which actually selects/submits the form so the agent proceeds. No silent hang on an interactive question.

## Inputs

| name | required | default | detect | ask |
|---|---|---|---|---|
| `QUEUE_PORT` | no | `9900` | port free or our own server | "TCP port (default 9900)" |
| `QUEUE_SECRET` | no | (auto) | existing key in `queue.env` | "Reuse or auto-gen" |
| `UPSTREAM_QUEUE_URL` | no | (empty ⇒ self-contained) | env / `queue.env` | "JOIN-mode switch. URL of an EXISTING upstream queue-server to register with, e.g. `http://mac-pro.<tailnet>.ts.net:9900`. When SET, this host installs as a JOIN node: it runs ONLY a queue-client (+ttyd) pointed at the upstream — no local queue-server, no local Boss, no own tailnet identity. When EMPTY (default), this host is a self-contained central node (original behavior)." |
| `UPSTREAM_QUEUE_SECRET` | cond. | none | env / `queue.env` | "JOIN-mode only, then REQUIRED: the upstream queue-server's `QUEUE_SECRET` — the join node MUST present the SAME secret or every request is 401. Handle securely — never echo or log it. If unset in JOIN-mode: `BLOCKED_REASON=upstream_secret_not_set`." |
| `QUEUE_DEAD_AFTER` | no | `4 × QUEUE_HEARTBEAT` (120s) | env | (no prompt — secs a host can be silent before its agents are reaped from the HUD; 4 missed heartbeats is generous so a loaded host isn't false-reaped) |
| `INSTALL_DIR` | no | `$HOME/mypeople` | dir exists | default |
| `HOST_ID` | no | `$(hostname -s)` | `hostname -s` works | "Stable host id used in every agent address (`<HOST_ID>/<sess>:<tab>`) and as the heartbeating-client name upstream. Use a durable name with NO transient/state words (e.g. `server`, not `server-temp`). Default: `hostname -s`." |
| OS deps (`tmux python3 jq procps`) | yes | apt | `command -v` each | (no prompt — agent runs apt install non-interactively) |
| claude CLI | yes | present **and `--plugin-dir`-capable** | `command -v claude` AND `claude --help \| grep -q -- --plugin-dir` | `BLOCKED_REASON=claude_not_installed`; if present but too old (no `--plugin-dir`): upgrade in Step 1 (don't block). A pre-installed claude on bare metal can be MONTHS old — `--plugin-dir` landed in 2.1.x. Spawn execs `claude … --plugin-dir <plugindir>`; an older claude rejects it with `error: unknown option '--plugin-dir'` and exits, which the spawn surfaces only as the generic `claude TUI didn't show 'bypass permissions on' banner within 30s` (see Failure modes). |
| `TS_AUTHKEY` | cond. | none | `[ -n "$TS_AUTHKEY" ]` (env or queue.env) | "Tailscale auth key — generate at https://login.tailscale.com/admin/settings/keys (reusable, ephemeral OFF, tag is fine). REQUIRED in self-contained mode (the seed cannot proceed without one). In JOIN-mode it's needed ONLY if this host can't already reach `UPSTREAM_QUEUE_URL` — if `curl $UPSTREAM_QUEUE_URL/health` already returns 200 (host already on the tailnet/LAN), the tailnet-join is skipped and no authkey is required." |
| `TS_HOSTNAME` | no | `mypeople-$(hostname -s)` | always available | "Stable hostname to announce on the tailnet. Default: `mypeople-<short hostname>`. Reachable as `<hostname>.<tailnet>.ts.net`." |
| TUN device (Linux only) | conditional | host-provided | `[ -c /dev/net/tun ]` on Linux | If missing on Linux *and Tailscale is being brought up here*: `BLOCKED_REASON=no_tun_device` — Tailscale needs a kernel TUN device. Sandboxed containers must be started with `--device /dev/net/tun --cap-add NET_ADMIN`. On macOS Tailscale uses the system extension instead; this input is N/A. JOIN-mode exception: if `UPSTREAM_QUEUE_URL` is already reachable, Tailscale is not started here, so the TUN check is N/A — skip it. |

## Components

| Component | Source | Notes |
|---|---|---|
| `queue-server.py` | inline | HTTP queue: clients, agents, task submit/poll/result, dashboard; heartbeat reaper auto-prunes agents on hosts that stop heartbeating |
| `queue-client.py` | inline | heartbeat + task dispatcher; tmux input via bracketed-paste; per-backend marker table drives spawn/peek/send for BOTH `claude` and `codex` (unknown backend falls back to claude) |
| `mp` CLI | inline | `spawn / send / peek / kill / status / answer` (peek classifies BUSY/IDLE; answer submits an AskUserQuestion form) |
| `plugins/tmux-boss-hooks/` | inline | lifecycle hooks. Claude: `emit-event` on SessionStart / Stop / SessionEnd → status file + boss notification; PreToolUse/AskUserQuestion → `[AGENT QUESTION]`. Codex: `codex-notify` on `agent-turn-complete` → the SAME Stop-hook contract (status file + boss notification) |
| `boss-CLAUDE.md` | inline | doctrine read by every Boss at spawn |
| `dashboard.html` | inline | HUD page, served from queue-server, polls /agents + /clients + /roster; live agents table PLUS a "Retired engineers" table with a per-engineer Revive button |
| `run/roster.json` | runtime | durable roster of every engineer ever spawned (spawn cmd, cwd, session-id, state, retire reason) — backs the HUD's retired list and `mp revive` |
| OS pkgs | apt: `tmux python3 jq procps ttyd tailscale` (with ttyd binary fallback) | |

## Steps

### Install mode: self-contained (default) vs JOIN

This seed installs in one of two modes, decided solely by whether `UPSTREAM_QUEUE_URL` is set. Convention used throughout the Steps: **`MODE=join` iff `[ -n "$UPSTREAM_QUEUE_URL" ]`**, else `MODE=self`.

- **self-contained** (`UPSTREAM_QUEUE_URL` empty — default): this host is a central node — local queue-server + queue-client + ttyd + its own tailnet identity + a Boss. Original behavior; unchanged.
- **JOIN** (`UPSTREAM_QUEUE_URL` set): this host is a worker node that registers with an EXISTING upstream queue-server (e.g. a laptop running self-contained). It runs ONLY queue-client + ttyd, pointed at `UPSTREAM_QUEUE_URL` using `UPSTREAM_QUEUE_SECRET`. It does **NOT** start a local queue-server, does **NOT** create a local Boss, and does **NOT** claim its own tailnet identity (it only needs to *reach* the upstream). This is what satisfies capability §12 (cross-host routing): from the upstream, `mp spawn <this-host>/<sess>:<tab> --boss <upstream-host>/main:Boss` lands a tmux window HERE and routes this agent's Stop notifications back to that Boss.

A step tagged **[self-contained only]** is SKIPPED in JOIN-mode; a branch tagged **[JOIN]** runs only in JOIN-mode. (Rule 13 still holds in JOIN-mode: any Claude agents spawned on this node get their OWN fresh device-login — no token/auth volume is copied. The queue-client itself needs no Claude auth.)

### 0. Interview (mandatory)

Detect all inputs. Send ONE consolidated Interview message. Wait for CEO reply. Then run autonomously.

### 1. Install OS deps

**Intent**: ensure `tmux`, `python3` (>= 3.8, stdlib only — no pip deps), `jq`, `ps` (procps on Linux; built-in on macOS), `curl`, `tailscale`, and `ttyd` are all on `PATH`. Use whatever package manager the host has.

Detect what's missing with `command -v <name>`; install only what's absent. Suggested commands per platform — the agent picks the right one for THIS host:

- **macOS** (Homebrew): `brew install tmux jq ttyd`. `python3` ships with the OS or via Xcode CLT; `ps` is built-in.
  - **Tailscale CLI on macOS — IMPORTANT**: if Tailscale.app is already installed (Mac App Store / direct download), the `tailscale` CLI is bundled inside the app but NOT on `PATH` by default. Don't reinstall via `brew install tailscale` — that creates a competing install path. Instead:
    1. Open Tailscale.app → settings/preferences → enable "Install CLI" (or equivalent menu item). This creates a symlink at `/usr/local/bin/tailscale` pointing to the app's bundled binary. The user must click this manually on first install of mypeople — surface it in the Interview if `command -v tailscale` returns nothing and `/Applications/Tailscale.app` exists.
    2. If Tailscale.app is NOT installed at all: `brew install --cask tailscale` (preferred — keeps a single source of truth) or `brew install tailscale` for CLI-only.
  - After whichever path: verify `command -v tailscale` resolves. Do NOT proceed with two install paths fighting each other.
- **Debian / Ubuntu**: `sudo apt-get update && sudo apt-get install -y tmux python3 jq procps curl ttyd tailscale`. If `ttyd` isn't in this distro's repos, download the prebuilt binary from `https://github.com/tsl0922/ttyd/releases/latest` (architectures: `ttyd.x86_64`, `ttyd.aarch64`) and place it on `PATH`. Tailscale install per `https://tailscale.com/download/linux/` (sets up its own apt repo).
- **RHEL/Fedora**: `sudo dnf install tmux jq procps-ng ttyd tailscale` (Tailscale repo per `https://tailscale.com/download/`).
- **Other**: install each by name from the host's native package manager.

Stop with `BLOCKED_REASON=<tool>_install_failed` if any of `tmux jq ttyd tailscale` is unreachable after install.

On **Linux only**, also verify `[ -c /dev/net/tun ]`. If missing, you're in a sandboxed container without the right permissions — stop with `BLOCKED_REASON=no_tun_device` (caller fixes by re-creating the container with `--device /dev/net/tun --cap-add NET_ADMIN`). On macOS the TUN check is N/A. **JOIN-mode exception**: if `UPSTREAM_QUEUE_URL` is already reachable (`curl -fsS "$UPSTREAM_QUEUE_URL/health"` returns 200), this node will NOT bring up Tailscale, so the TUN check is N/A — skip it.

**Deterministic install (paste-and-run).** The prose above is the intent; this block makes a clean container actually install everything so the one-shot needs no human to "pick the command". Idempotent (installs only what's missing) and portable (apt/brew/dnf). `ttyd` is frequently absent from distro repos, so on Debian/Ubuntu it falls back to the static GitHub binary (x86_64/aarch64). A clean container that lacked `ttyd` made Step 9 fail `ttyd_failed_to_bind` — this is the root-cause fix.

```bash
need(){ command -v "$1" >/dev/null 2>&1; }
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq 2>/dev/null || true
  sudo apt-get install -y -qq tmux python3 jq procps curl ca-certificates >/dev/null 2>&1 || true
  if ! need ttyd; then
    case "$(uname -m)" in aarch64|arm64) TA=ttyd.aarch64;; *) TA=ttyd.x86_64;; esac
    sudo curl -fsSL -o /usr/local/bin/ttyd "https://github.com/tsl0922/ttyd/releases/latest/download/$TA" 2>/dev/null && sudo chmod +x /usr/local/bin/ttyd
  fi
elif command -v brew >/dev/null 2>&1; then
  for p in tmux jq ttyd; do brew list "$p" >/dev/null 2>&1 || brew install "$p" || true; done
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y tmux jq procps-ng ttyd curl >/dev/null 2>&1 || true
fi
# tailscale — needed for self-contained tailnet identity; skip in JOIN mode when the upstream is already reachable.
if [ -z "${UPSTREAM_QUEUE_URL:-}" ] || ! curl -fsS "${UPSTREAM_QUEUE_URL:-http://255.255.255.255:1}/health" >/dev/null 2>&1; then
  need tailscale || { curl -fsSL https://tailscale.com/install.sh | sudo sh >/dev/null 2>&1 || true; }
fi
for t in tmux jq ttyd python3 curl; do need "$t" || { echo "BLOCKED_REASON=${t}_install_failed"; exit 1; }; done
echo "OS deps OK: tmux jq ttyd python3 curl$(need tailscale && printf ' tailscale')"
```

**Also ensure `claude` is new enough to support `--plugin-dir`** (the spawn path passes it; an older claude rejects it and every spawn fails with a misleading banner-timeout — surfaced live on a Raspberry Pi whose pre-installed claude was 2.0.5). `--plugin-dir` landed in claude **2.1.x**. Detect + upgrade:

```bash
if command -v claude >/dev/null 2>&1 && ! claude --help 2>&1 | grep -q -- '--plugin-dir'; then
  echo "claude $(claude --version 2>&1 | head -1) lacks --plugin-dir — upgrading"
  # global npm install (symlink in /usr/local/bin) needs root; native/local installs can self-update.
  claude update 2>/dev/null \
    || sudo npm install -g @anthropic-ai/claude-code@latest 2>/dev/null \
    || claude install latest 2>/dev/null \
    || { echo "BLOCKED_REASON=claude_too_old_no_plugin_dir"; exit 1; }
  claude --help 2>&1 | grep -q -- '--plugin-dir' || { echo "BLOCKED_REASON=claude_too_old_no_plugin_dir"; exit 1; }
fi
```

A `claude update` / npm upgrade preserves the node's auth (`~/.claude/.credentials.json` is untouched), so re-auth is not needed afterward.

### 2. Stop any prior mypeople daemons (idempotent reinstall)

**Intent**: previous installs may have running queue-server, queue-client, ttyd, and (Linux-no-systemd only) a user-launched `tailscaled`. Kill them so this Step's re-write of code and config is clean.

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
for name in queue-client queue-server ttyd tailscaled; do
  pidfile="$INSTALL_DIR/run/$name.pid"
  [ -f "$pidfile" ] && { sudo kill "$(cat $pidfile)" 2>/dev/null || kill "$(cat $pidfile)" 2>/dev/null || true; }
done
pkill -f "$INSTALL_DIR/bin/queue-client.py" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/queue-server.py" 2>/dev/null || true
pkill -f "ttyd -W -p" 2>/dev/null || true
# DO NOT kill a system-managed tailscaled (macOS Tailscale.app, Linux systemd).
# Only kill a userland tailscaled this install previously started.
[ -f "$INSTALL_DIR/run/tailscaled.pid" ] && sudo kill "$(cat $INSTALL_DIR/run/tailscaled.pid)" 2>/dev/null || true
```

### 3. Create directory layout

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/run" "$INSTALL_DIR/status" "$INSTALL_DIR/plugins/tmux-boss-hooks/.claude-plugin" "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks"
mkdir -p "$HOME/.config/mypeople" "$HOME/.local/bin"
```

### 3.5. Pre-accept the trust dialog in `~/.claude.json` for spawn directories

```bash
python3 - <<'PY'
import json, os
from pathlib import Path
path = Path.home() / ".claude.json"
try:
    data = json.loads(path.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    data = {}
data.setdefault("projects", {})
for d in [str(Path.home()), os.environ.get("INSTALL_DIR", str(Path.home() / "mypeople"))]:
    data["projects"].setdefault(d, {})
    data["projects"][d]["hasTrustDialogAccepted"] = True
path.write_text(json.dumps(data, indent=2))
path.chmod(0o600)
print("trusted:", list(data["projects"].keys()))
PY
```

### 3.6. Install the Boss doctrine (`boss-CLAUDE.md`)

**Why**: `mp spawn --master` will send an onboarding prompt that tells the new agent to read this file. Without the doctrine on disk, a spawned "Boss" is a vanilla claude with no idea it's a Boss.

```bash
cat > "$INSTALL_DIR/boss-CLAUDE.md" <<'EOF'
# Boss CLAUDE.md — doctrine

This is your job description. You are the Boss for this mypeople deployment.

## Rule 1 — Plan gate (no engineering without a plan)

You do not start engineering work, and you do not let your team start, until ALL four conditions are met:

1. Brainstorm complete (CEO + you explored the problem).
2. PLAN written (markdown doc: user journey, scope, smallest meaningful slice, non-goals, agents involved).
3. E2E Verify drafted (a runnable shell script proving the feature from the pane).
4. CEO explicitly approves ("approved" / "go" / "ship it"). Silence is not approval.

If anyone asks to start coding before these four are met: "Stop. We don't have a plan yet." Walk them through which is missing.

## Rule 2 — Autonomous loop (keep the team working)

Triggers you must respond to:
- `[AGENT NOTIFICATION] ...` arrives → read result, update PLAN, assign next task.
- All agents idle + work in PLAN → dispatch next task.
- All idle + no work → send CEO one short message: "Team idle. Next: <propose>?"
- Task failed → mp peek, then reassign or escalate.

Pacing: act on notifications within 30s. No "exploring" without a deliverable.

## Rule 3 — Fire-and-forget through the system (never bypass)

Every action on another agent goes through the `mp` CLI / queue. NEVER `tmux send-keys` or `tmux capture-pane` directly. Not even to read.

Available verbs:
- `mp spawn <host>/<session>:<tab> --backend claude [--boss <agent_id>]` — create an agent. Pass `--boss $AGENT_ID` so worker Stop notifications route back to you.
- `mp send <agent_id> "msg"` — queue a message.
- `mp peek <agent_id>` — queued peek; response returns via the queue.
- `mp status` — list agents.
- `mp kill <agent_id> [--reason <killed|done-auto-retire>]` — graceful exit; the engineer is kept on the roster as `retired` so it can be revived.
- `mp revive <agent_id>` — bring a retired engineer back by RESUMING its actual Claude session (`claude --resume <session-id>`). Resume-only: errors if the session can't be resumed (no fresh-spawn fallback). One engineer at a time; no batch restore.

Fire-and-forget: every verb returns immediately. You wait for notifications; you don't poll. If you reach for raw tmux, stop — find the mp verb or flag a missing feature.

## Your environment

- `$AGENT_ID` — your own address; use it as `--boss $AGENT_ID` when spawning workers.
- `$BOSS_ID` — your boss's address (empty if you ARE the top-level Boss).
- The mypeople runtime lives at `$INSTALL_DIR`.
EOF
chmod 644 "$INSTALL_DIR/boss-CLAUDE.md"
```

### 3.7. Install TPM + Dracula tmux config (CEO's preferred look)

**Why**: tmux defaults are bad (no mouse, no status bar, 0-indexed windows). When the human attaches via ttyd in the HUD, this is what they see. Install Tmux Plugin Manager + Dracula theme so the UX is usable out of the box.

```bash
# Clone TPM if missing
[ -d "$HOME/.tmux/plugins/tpm" ] || git clone --depth 1 https://github.com/tmux-plugins/tpm "$HOME/.tmux/plugins/tpm"

# Write tmux config (matches host's Dracula setup)
cat > "$HOME/.tmux.conf" <<'EOF'
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
# Default MouseDown1Pane (begin-selection) is what we want — do NOT rebind
# it to cancel/exit-copy-mode or click-drag will snap the view away.
# unbind here to clear any prior server state.
unbind-key -T copy-mode    MouseDown1Pane
unbind-key -T copy-mode-vi MouseDown1Pane
# copy-pipe-and-cancel (NOT copy-pipe) — without -and-cancel the pane stays
# in copy-mode after every mouse-drag selection and silently swallows the
# user's next keystrokes until they press Escape. On macOS pbcopy lands the
# selection on the host clipboard; on Linux the pipe silently no-ops
# (acceptable — ttyd's own browser selection handles host clipboard).
bind-key   -T copy-mode    MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "pbcopy"
bind-key   -T copy-mode-vi MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "pbcopy"

# ── Mouse-wheel scroll ────────────────────────────────────
# Claude TUI renders on the MAIN screen (alternate_on=0) and does not
# request mouse mode, so tmux's default WheelUpPane binding falls through
# to `copy-mode -e` and silently traps every subsequent keystroke until
# Escape. Kill the wheel→copy-mode path entirely. Users who want scrollback
# can still enter copy-mode explicitly via `prefix [`.
unbind-key -T root WheelUpPane
unbind-key -T root WheelDownPane

# ── TPM (must be last) ────────────────────────────────────
run '~/.tmux/plugins/tpm/tpm'
EOF
chmod 644 "$HOME/.tmux.conf"

# Clone the one plugin TPM would install on first prefix-I anyway.
# TPM's install_plugins.sh requires an already-running tmux server with
# the conf loaded — chicken-and-egg at install time. Direct clone bypasses
# that and makes first attach instant instead of "wait for clone".
# Convention: a TPM plugin `<owner>/<repo>` clones to ~/.tmux/plugins/<repo>.
[ -d "$HOME/.tmux/plugins/tmux" ] || git clone --depth 1 https://github.com/dracula/tmux "$HOME/.tmux/plugins/tmux"

# If a tmux server is already running from a prior install, re-source the
# conf so the new look takes effect immediately.
tmux source-file "$HOME/.tmux.conf" 2>/dev/null || true
```

### 4. Write `queue-server.py` [self-contained only]

In JOIN-mode this Step is skipped — the node registers with the upstream queue-server instead of running its own.

```bash
# [self-contained only] — JOIN nodes use the upstream's queue-server, not a local one.
if [ -n "${UPSTREAM_QUEUE_URL:-}" ]; then
  echo "[JOIN] skipping local queue-server (will use upstream $UPSTREAM_QUEUE_URL)"
else
cat > "$INSTALL_DIR/bin/queue-server.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople queue-server."""

import glob, http.server, json, os, sys, threading, time, urllib.request, uuid
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("QUEUE_PORT", "9900"))
SECRET = os.environ.get("QUEUE_SECRET", "")
HEARTBEAT = int(os.environ.get("QUEUE_HEARTBEAT", "30"))
# Heartbeat-based liveness. An agent's host re-heartbeats every HEARTBEAT secs;
# a removed container stops heartbeating, so we mark its agents dead once the
# host has been silent for DEAD_AFTER secs (default = 4 missed heartbeats —
# generous so a loaded host isn't false-reaped) and the reaper drops them from
# the registry / HUD. Without this an agent whose container is gone shows
# 'alive' forever, because `state` is written once at register and `mp kill`
# times out on a dead host. Tune via QUEUE_DEAD_AFTER / QUEUE_REAP_INTERVAL.
DEAD_AFTER = float(os.environ.get("QUEUE_DEAD_AFTER", str(HEARTBEAT * 4)))
REAP_INTERVAL = float(os.environ.get("QUEUE_REAP_INTERVAL", str(max(5, HEARTBEAT // 2))))
# Idempotency dedup window. A submit carrying an idempotency_key we've already
# seen within this many seconds is collapsed onto the original task instead of
# enqueuing a duplicate — exactly-once notification delivery even if a Stop hook
# double-fires or a submit is retried. Tune via QUEUE_DEDUP_WINDOW.
DEDUP_WINDOW = float(os.environ.get("QUEUE_DEDUP_WINDOW", "45"))
START_TS = time.time()

_lock = threading.Lock()
clients = {}
agents = {}
tasks = {}
idem_seen = {}   # idempotency_key -> (task_id, ts), pruned on submit


def _host_of(agent_id):
    if "/" in agent_id and ":" in agent_id:
        return agent_id.split("/", 1)[0]
    return ""


TODO_URL = os.environ.get("QUEUE_TODO_URL", "http://127.0.0.1:9933")


def _roster_session_id(install_dir, aid):
    """Latest session-id for an engineer: roster (hook-written) first, then the
    durable status file as fallback. Both survive reboot."""
    sid = ""
    try:
        with open(os.path.join(install_dir, "run", "roster.json")) as f:
            sid = (json.load(f).get(aid) or {}).get("session_id", "") or ""
    except (FileNotFoundError, ValueError):
        pass
    if sid:
        return sid
    try:
        host, rest = aid.split("/", 1); sess, tab = rest.split(":", 1)
    except ValueError:
        return ""
    try:
        with open(os.path.join(install_dir, "status", f"mc-{sess}", f"{tab}.json")) as f:
            return (json.load(f) or {}).get("session_id", "") or ""
    except (FileNotFoundError, ValueError):
        return ""


def _find_transcript(session_id):
    """The Claude transcript file for a session-id, or None — globbed across all
    project dirs (UUID is globally unique, so cwd→project-dir encoding is moot)."""
    if not session_id:
        return None
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    return hits[0] if hits else None


def _board_assignee_cards():
    """Best-effort {agent_id: {id,title}} from the todo board — DERIVES the
    engineer→card link server-side (no CORS, no secret in the browser); the link
    is never stored on the roster. Empty map if the board is unreachable."""
    try:
        req = urllib.request.Request(f"{TODO_URL}/todo/board", headers={"X-Queue-Secret": SECRET})
        with urllib.request.urlopen(req, timeout=2) as r:
            board = json.loads(r.read().decode())
    except Exception:
        return {}
    out = {}
    for tid, t in (board.get("tasks") or {}).items():
        a = (t.get("assignee") or "").strip()
        if a:
            out[a] = {"id": tid, "title": (t.get("text") or "")[:70]}
    return out


def _agent_alive(v, now):
    """True iff the agent's host heartbeated within DEAD_AFTER seconds.

    The host's queue-client heartbeats on a fixed interval; when its container
    is removed the heartbeats stop, so its agents age out of 'alive'. Falls back
    to the agent's own register ts when the host has no heartbeat yet (the
    spawn/heartbeat race right after register), so a just-registered agent on a
    not-yet-heartbeated host isn't reaped. Call under _lock."""
    c = clients.get(v.get("host", ""))
    last = c.get("ts", 0) if c else v.get("ts", 0)
    return (now - last) <= DEAD_AFTER


def reaper_loop():
    """Drop agents whose host stopped heartbeating, plus stale clients, so the
    registry and the HUD reflect true current liveness instead of last-known
    state. This is what keeps a removed container's agent from showing 'alive'
    forever (the zombie-agent bug)."""
    while True:
        time.sleep(REAP_INTERVAL)
        now = time.time()
        with _lock:
            dead_agents = [k for k, v in agents.items() if not _agent_alive(v, now)]
            for k in dead_agents:
                agents.pop(k, None)
            dead_clients = [h for h, c in clients.items()
                            if now - c.get("ts", 0) > DEAD_AFTER]
            for h in dead_clients:
                clients.pop(h, None)
        if dead_agents or dead_clients:
            sys.stderr.write(
                f"{time.strftime('%H:%M:%S')} reaper pruned "
                f"agents={dead_agents} clients={dead_clients}\n")


class Handler(http.server.BaseHTTPRequestHandler):
    def _json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ok_secret(self):
        return self.headers.get("X-Queue-Secret", "") == SECRET

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} {fmt % args}\n")

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode() if length else "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p == "/health":
            return self._json(200, {"status": "ok", "uptime": int(time.time() - START_TS)})
        # /dashboard is PUBLIC (no secret check) — secret is injected into HTML
        # for the in-page fetch calls. Browser users don't have the secret.
        if p == "/dashboard":
            install_dir = os.environ.get("INSTALL_DIR", os.path.expanduser("~/mypeople"))
            html_path = os.path.join(install_dir, "bin", "dashboard.html")
            try:
                with open(html_path) as f:
                    html = f.read().replace("__INJECT_SECRET__", SECRET)
            except FileNotFoundError:
                html = "<h1>dashboard.html not found</h1>"
            data = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if not self._ok_secret():
            return self._json(401, {"error": "unauthorized"})
        if p == "/clients":
            with _lock:
                return self._json(200, [{"hostname": h, **v} for h, v in clients.items()])
        if p == "/agents":
            install_dir = os.environ.get("INSTALL_DIR", os.path.expanduser("~/mypeople"))
            now = time.time()
            with _lock:
                items = []
                for k, v in agents.items():
                    # Heartbeat-based liveness: never surface an agent whose host
                    # has gone silent (removed container) even if the reaper
                    # hasn't swept it yet — the HUD must show TRUE current state.
                    if not _agent_alive(v, now):
                        continue
                    item = {"agent_id": k, **v}
                    # `session` in the registry is the BARE session name (e.g.
                    # "main"); the tmux session name and status-dir name both
                    # use the "mc-" prefix consistently. Build the mc-prefixed
                    # form once and use it everywhere.
                    bare_sess = v.get("session", "")
                    mc_sess = bare_sess if bare_sess.startswith("mc-") else f"mc-{bare_sess}"
                    tab = v.get("tab", "")
                    status_path = os.path.join(install_dir, "status", mc_sess, f"{tab}.json")
                    try:
                        import json as _json
                        with open(status_path) as f:
                            sf = _json.load(f)
                        item["summary"] = sf.get("summary", "")
                        item["last_stop_ts"] = sf.get("timestamp", "")
                    except (FileNotFoundError, ValueError):
                        item["summary"] = ""
                    item["tmux_target"] = f"{mc_sess}:{tab}"
                    items.append(item)
                return self._json(200, items)
        if p == "/roster":
            # RETIRED engineers for the HUD: each with the exact spawn command, why
            # it retired, when, its DERIVED card (from the board), and whether its
            # session is resumable (session-id captured + transcript on disk). A
            # non-resumable row is surfaced with resume_error — never silently
            # masked, because revive is resume-by-session-id ONLY (no fresh spawn).
            install_dir = os.environ.get("INSTALL_DIR", os.path.expanduser("~/mypeople"))
            try:
                with open(os.path.join(install_dir, "run", "roster.json")) as f:
                    roster = json.load(f)
            except (FileNotFoundError, ValueError):
                roster = {}
            cards = _board_assignee_cards()
            out = []
            for aid, e in roster.items():
                if e.get("state") != "retired":
                    continue
                sid = _roster_session_id(install_dir, aid)
                transcript = _find_transcript(sid)
                if not sid:
                    err = "no session-id captured for this engineer"
                elif not transcript:
                    err = f"session transcript {sid}.jsonl not found on disk"
                else:
                    err = ""
                card = cards.get(aid, {})
                out.append({
                    "agent_id": aid, "backend": e.get("backend", ""), "cwd": e.get("cwd", ""),
                    "boss_id": e.get("boss_id", ""), "spawn_cmd": e.get("spawn_cmd", ""),
                    "retire_reason": e.get("retire_reason", ""), "retired_ts": e.get("retired_ts", ""),
                    "spawned_ts": e.get("spawned_ts", ""), "session_id": sid,
                    "resumable": bool(sid and transcript), "resume_error": err,
                    "card_id": card.get("id", ""), "card_title": card.get("title", ""),
                })
            out.sort(key=lambda x: x.get("retired_ts", ""), reverse=True)
            return self._json(200, out)
        if p == "/task/poll":
            qs = parse_qs(u.query)
            host = (qs.get("hostname", [""])[0]).strip()
            if not host:
                return self._json(400, {"error": "hostname required"})
            with _lock:
                for tid, t in tasks.items():
                    if t["status"] == "pending" and t.get("target_host", "") == host:
                        t["status"] = "running"
                        t["picked_ts"] = time.time()
                        return self._json(200, {"task_id": tid, **t})
            return self._json(200, {})
        if p.startswith("/task/"):
            tid = p.split("/")[-1]
            with _lock:
                t = tasks.get(tid)
                if not t:
                    return self._json(404, {"error": "no such task"})
                return self._json(200, {"task_id": tid, **t})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._ok_secret():
            return self._json(401, {"error": "unauthorized"})
        u = urlparse(self.path)
        p = u.path
        data = self._read_json()
        if data is None:
            return self._json(400, {"error": "bad json"})

        if p == "/heartbeat":
            host = (data.get("hostname") or "").strip()
            if not host:
                return self._json(400, {"error": "hostname required"})
            with _lock:
                entry = {"ts": time.time()}
                attach_base = (data.get("attach_base") or "").strip()
                if attach_base:
                    entry["attach_base"] = attach_base
                clients[host] = entry
            return self._json(200, {"ok": True})

        if p == "/agents/register":
            aid = data.get("agent_id", "").strip()
            if not aid or "/" not in aid or ":" not in aid:
                return self._json(400, {"error": "agent_id must be <host>/<session>:<tab>"})
            host_part, rest = aid.split("/", 1)
            sess, tab = rest.split(":", 1)
            with _lock:
                agents[aid] = {
                    "host": host_part, "session": sess, "tab": tab,
                    "backend": data.get("backend", ""),
                    "state": data.get("state", "alive"),
                    "boss_id": data.get("boss_id", ""),
                    "ts": time.time(),
                }
            return self._json(200, {"ok": True})

        if p == "/agents/unregister":
            aid = data.get("agent_id", "").strip()
            with _lock:
                agents.pop(aid, None)
            return self._json(200, {"ok": True})

        if p == "/task/submit":
            action = data.get("action", "")
            if action not in ("spawn", "send", "peek", "kill", "answer", "revive"):
                return self._json(400, {"error": f"unknown action {action!r}"})
            tid = uuid.uuid4().hex
            t = {
                "status": "pending",
                "action": action,
                "target_host": data.get("target_host", "") or _host_of(data.get("target_agent", "")),
                "target_agent": data.get("target_agent", ""),
                "payload": data.get("payload", {}),
                "result": None,
                "error": "",
                "submitted_ts": time.time(),
            }
            if not t["target_host"]:
                return self._json(400, {"error": "target_host or target_agent required"})
            ikey = (data.get("idempotency_key") or "").strip()
            with _lock:
                now = time.time()
                if ikey:
                    # Prune expired keys, then collapse a duplicate onto the
                    # original task so a re-fired/retried notification is never
                    # enqueued (and thus never delivered) twice.
                    for k in [k for k, (_, ts) in idem_seen.items()
                              if now - ts > DEDUP_WINDOW]:
                        idem_seen.pop(k, None)
                    prev = idem_seen.get(ikey)
                    if prev and now - prev[1] <= DEDUP_WINDOW:
                        sys.stderr.write(
                            f"{time.strftime('%H:%M:%S')} dedup: dropped duplicate "
                            f"submit key={ikey[:12]} -> task {prev[0][:8]}\n")
                        return self._json(200, {"task_id": prev[0], "deduped": True})
                    idem_seen[ikey] = (tid, now)
                tasks[tid] = t
            return self._json(200, {"task_id": tid})

        if p == "/task/result":
            tid = data.get("task_id", "")
            with _lock:
                t = tasks.get(tid)
                if not t:
                    return self._json(404, {"error": "no such task"})
                t["status"] = "done" if data.get("ok") else "failed"
                t["result"] = data.get("result")
                t["error"] = data.get("error", "")
                t["completed_ts"] = time.time()
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "not found"})


class ThreadingServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    if not SECRET:
        print("FATAL: QUEUE_SECRET not set", file=sys.stderr)
        sys.exit(1)
    # Bind to all interfaces (not just loopback) so the HUD page is
    # reachable from outside this host (e.g. another tailnet node) via
    # the tailscale IP after Step 8.5.
    server = ThreadingServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=reaper_loop, daemon=True).start()
    print(f"queue-server listening on 0.0.0.0:{PORT} "
          f"(reaper: dead_after={DEAD_AFTER:.0f}s every {REAP_INTERVAL:.0f}s)", flush=True)
    server.serve_forever()
PY_EOF
chmod +x "$INSTALL_DIR/bin/queue-server.py"
fi
```

### 5. Write `queue-client.py`

```bash
cat > "$INSTALL_DIR/bin/queue-client.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople queue-client."""

import json, os, shlex, socket, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request

QUEUE_URL = os.environ.get("QUEUE_URL", "http://127.0.0.1:9900")
SECRET = os.environ.get("QUEUE_SECRET", "")
HEARTBEAT = int(os.environ.get("QUEUE_HEARTBEAT", "30"))
POLL_INTERVAL = float(os.environ.get("QUEUE_POLL_INTERVAL", "1.0"))
HOSTNAME = os.environ.get("HOST_ID", "") or socket.gethostname()
TTYD_PUBLIC_URL = os.environ.get("TTYD_PUBLIC_URL", "")  # browser-reachable ttyd base for this host (e.g. its Tailscale addr); empty -> HUD falls back to localhost
INSTALL_DIR = os.environ.get("INSTALL_DIR", os.path.expanduser("~/mypeople"))
PLUGIN_DIR = os.path.join(INSTALL_DIR, "plugins", "tmux-boss-hooks")

# Durable local record of the agents THIS client manages. The central server's
# registry is in-memory: a server restart — or a heartbeat gap that trips its
# liveness reaper — drops every registration, and agents only register at spawn,
# so the HUD goes empty while the agents are still running. This client owns the
# list and RE-ANNOUNCES it on every heartbeat (see reannounce_agents), making the
# server's agent set a self-healing projection of the live clients.
AGENTS_FILE = os.path.join(INSTALL_DIR, "run", "agents.json")
_agents_lock = threading.Lock()

PASTE_START = "\x1b[200~"
PASTE_END = "\x1b[201~"

# Per-backend TUI marker table. The tmux send/peek mechanism is backend-generic
# (bracketed paste + Enter); only the on-screen chrome it keys off differs.
# Markers captured live from each TUI (Codex strings from codex-cli 0.132.0):
#   - "ready":  substring present once the agent's TUI is up and accepting input
#               (Claude startup banner/footer; Codex startup box ">_ OpenAI Codex").
#   - "busy":   substring shown ONLY while a turn is actively running.
#               Both TUIs print "esc to interrupt"; Codex wraps it as
#               "* Working (Ns * esc to interrupt)".
#   - "prompt": the composer prompt glyph. Claude is U+276F; Codex is U+203A
#               — DIFFERENT glyphs.
#   - "idle":   substrings proving an idle composer is present (prompt glyph, or
#               a stable footer token). Claude "bypass permissions on"; Codex
#               footer "<model> SEP <cwd>" where SEP is U+00B7 surrounded by spaces.
#   - "region_end": line substring bounding the BOTTOM of the composer region for
#               paste-draft detection (the footer just under the composer).
#   - "paste":  lowercased paste-draft tag a stuck multiline draft collapses to.
MARKERS = {
    "claude": {
        "ready": "bypass permissions on",
        "busy": "esc to interrupt",
        "prompt": "❯",
        "idle": ("❯", "bypass permissions on"),
        "region_end": "bypass permissions on",
        "paste": "[pasted text",
    },
    "codex": {
        "ready": "OpenAI Codex",            # startup box: ">_ OpenAI Codex (vX)"
        "busy": "esc to interrupt",         # "* Working (Ns * esc to interrupt)"
        "prompt": "›",
        "idle": ("›", " · "),     # prompt glyph, or "<model> · <cwd>" footer
        "region_end": " · ",           # footer "<model> · <cwd>"
        "paste": "[pasted text",
    },
}
DEFAULT_BACKEND = "claude"


def markers_for(backend):
    return MARKERS.get(backend or DEFAULT_BACKEND, MARKERS[DEFAULT_BACKEND])


def _agent_backend(aid):
    """Backend for an agent id from this client's durable record (agents.json).
    Falls back to 'claude' so existing/unknown agents behave exactly as before."""
    with _agents_lock:
        meta = _load_agents().get(aid) or {}
    return meta.get("backend") or DEFAULT_BACKEND


def post_json(path, data):
    req = urllib.request.Request(
        f"{QUEUE_URL}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-Queue-Secret": SECRET},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def get_json(path):
    req = urllib.request.Request(f"{QUEUE_URL}{path}", headers={"X-Queue-Secret": SECRET})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        return json.loads(body) if body.strip() else {}


def heartbeat_loop():
    while True:
        try:
            post_json("/heartbeat", {"hostname": HOSTNAME, "attach_base": TTYD_PUBLIC_URL})
        except urllib.error.URLError as e:
            print(f"{time.strftime('%H:%M:%S')} heartbeat FAIL: {e}", file=sys.stderr, flush=True)
        # Re-announce our agents so a restarted/empty server rebuilds the live
        # set within one heartbeat cycle — no manual re-registration ever needed.
        try:
            reannounce_agents()
        except Exception as e:
            print(f"{time.strftime('%H:%M:%S')} reannounce FAIL: {e}", file=sys.stderr, flush=True)
        time.sleep(HEARTBEAT)


def tmux_run(*args, timeout=5):
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=timeout)


def _pane_backend(target):
    """Best-effort: which backend binary is ACTUALLY RUNNING in this pane?

    Returns 'claude', 'codex', or None (bare shell / can't classify). After the
    spawn's `exec <backend>`, tmux's #{pane_pid} IS the backend process, so its
    command line is ground truth; we also scan its direct children (codex's node
    launcher re-execs a vendored `codex` binary as a child). This is what lets
    the idempotent re-spawn path REFUSE to relabel a pane as a backend it isn't
    running — the 'registry says codex but the process is claude' bug: a
    --backend codex spawn onto a window already holding a claude pane used to
    take the reuse short-circuit, flip the registry label to codex, and return
    success while claude kept running. Verify by the process, never the label."""
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_pid}")
    if r.returncode != 0 or not r.stdout.strip():
        return None
    pid = r.stdout.strip()
    try:
        cmds = subprocess.run(["ps", "-o", "command=", "-p", pid],
                              capture_output=True, text=True, timeout=5).stdout
        kids = subprocess.run(["pgrep", "-P", pid],
                              capture_output=True, text=True, timeout=5).stdout.split()
        for k in kids:
            cmds += "\n" + subprocess.run(["ps", "-o", "command=", "-p", k],
                                          capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    low = cmds.lower()
    # The codex exec line carries `codex ...` (and the codex-notify path); the
    # claude exec line carries `claude ...` (+ the tmux-boss-hooks plugin path,
    # which contains no 'codex' token). So each backend's command matches only
    # its own name — no cross-false-positive.
    if "codex" in low:
        return "codex"
    if "claude" in low:
        return "claude"
    return None


def _load_agents():
    try:
        with open(AGENTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save_agents(d):
    os.makedirs(os.path.dirname(AGENTS_FILE), exist_ok=True)
    tmp = AGENTS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, AGENTS_FILE)   # atomic


def record_agent(aid, backend, boss_id, is_master=False):
    """Persist an agent this client just spawned so we can re-announce it later."""
    with _agents_lock:
        d = _load_agents()
        d[aid] = {"backend": backend, "boss_id": boss_id, "is_master": bool(is_master)}
        _save_agents(d)


def forget_agent(aid):
    with _agents_lock:
        d = _load_agents()
        if d.pop(aid, None) is not None:
            _save_agents(d)


# --- Durable ROSTER: every engineer ever spawned, kept across kill AND reboot ---
# agents.json tracks only LIVE agents (and is pruned the moment a window dies).
# The roster is the opposite: a permanent record so the HUD can list a RETIRED
# engineer with the exact command to revive it (resume-by-session-id). The
# engineer→card link is NOT stored here — it is derived from the board (the card
# carries its assignee). session_id is written by the emit-event hook (authoritative)
# and read-merge-preserved here so a python roster write never clobbers it.
ROSTER_FILE = os.path.join(INSTALL_DIR, "run", "roster.json")
_roster_lock = threading.Lock()


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_roster():
    try:
        with open(ROSTER_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save_roster(d):
    os.makedirs(os.path.dirname(ROSTER_FILE), exist_ok=True)
    tmp = ROSTER_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, ROSTER_FILE)   # atomic


def roster_record_spawn(aid, backend, cwd, boss_id, is_master, spawn_cmd):
    """Persist/refresh a spawned engineer's revive metadata. Preserves any
    session_id already written by the emit-event hook (merge, never clobber)."""
    with _roster_lock:
        d = _load_roster()
        e = d.get(aid, {})
        e.setdefault("session_id", "")
        e.update({
            "agent_id": aid, "backend": backend, "cwd": cwd,
            "boss_id": boss_id, "is_master": bool(is_master),
            "spawn_cmd": spawn_cmd, "state": "alive",
            "retire_reason": "", "spawned_ts": _now_iso(), "retired_ts": "",
        })
        d[aid] = e
        _save_roster(d)


def roster_mark_retired(aid, reason):
    """Flag an engineer retired (NOT deleted) so the HUD can offer a revive."""
    with _roster_lock:
        d = _load_roster()
        e = d.get(aid)
        if not e:
            return
        e["state"] = "retired"
        e["retire_reason"] = reason
        e["retired_ts"] = _now_iso()
        _save_roster(d)


def roster_mark_alive(aid):
    with _roster_lock:
        d = _load_roster()
        e = d.get(aid)
        if e:
            e["state"] = "alive"
            e["retire_reason"] = ""
            e["retired_ts"] = ""
            _save_roster(d)


def detect_reboot_retirements():
    """On client startup, any roster engineer still marked alive whose tmux window
    is gone (the machine rebooted and killed every session) is retired with reason
    'died-on-reboot' so the HUD lists it as revivable. No-op for windows still up."""
    with _roster_lock:
        d = _load_roster()
    gone = [aid for aid, e in d.items()
            if e.get("state") == "alive" and not _window_alive(aid)]
    for aid in gone:
        roster_mark_retired(aid, "died-on-reboot")
    if gone:
        print(f"reboot-detect: retired {len(gone)} engineer(s) whose window is gone: {gone}", flush=True)


def _session_transcript(session_id):
    """Path to the Claude transcript for a session-id, or None. Globs across all
    project dirs (the session-id is a UUID → globally unique) so we don't depend on
    the cwd→project-dir encoding."""
    if not session_id:
        return None
    import glob
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    return hits[0] if hits else None


def _roster_session_id(aid):
    """Latest session-id for an engineer: roster (hook-written) first, then the
    durable status file as fallback — both survive reboot."""
    with _roster_lock:
        sid = (_load_roster().get(aid) or {}).get("session_id", "") or ""
    if sid:
        return sid
    parsed = parse_agent_id(aid)
    if not parsed:
        return ""
    _, sess, tab = parsed
    path = os.path.join(INSTALL_DIR, "status", f"mc-{sess}", f"{tab}.json")
    try:
        with open(path) as f:
            return (json.load(f) or {}).get("session_id", "") or ""
    except (FileNotFoundError, ValueError):
        return ""


def _window_alive(aid):
    """aid = host/session:tab — alive iff its tmux window still exists here."""
    try:
        rest = aid.split("/", 1)[1]
        sess, tab = rest.split(":", 1)
    except (IndexError, ValueError):
        return False
    r = tmux_run("list-windows", "-t", f"mc-{sess}", "-F", "#{window_name}")
    return r.returncode == 0 and tab in r.stdout.split()


def reannounce_agents():
    """Re-register every agent this client manages whose tmux window is still
    alive; forget the ones whose window is gone (per-agent self-cleanup). Called
    each heartbeat so the server's registry self-heals after any restart/wipe."""
    with _agents_lock:
        d = _load_agents()
    if not d:
        return
    gone = []
    for aid, meta in d.items():
        if not _window_alive(aid):
            gone.append(aid)
            continue
        try:
            post_json("/agents/register", {
                "agent_id": aid, "backend": meta.get("backend", ""), "state": "alive",
                "boss_id": meta.get("boss_id", ""), "is_master": meta.get("is_master", False)})
        except urllib.error.URLError:
            pass  # server unreachable → next heartbeat retries
    if gone:
        with _agents_lock:
            d = _load_agents()
            for aid in gone:
                d.pop(aid, None)
            _save_agents(d)


def _is_busy(target, backend=DEFAULT_BACKEND):
    """True if a turn is actively running in this pane (busy marker on screen)."""
    m = markers_for(backend)
    r = tmux_run("capture-pane", "-t", target, "-p")
    return r.returncode == 0 and m["busy"] in r.stdout.lower()


def _composer_draft(target, backend=DEFAULT_BACKEND):
    """Classify any UN-submitted draft sitting in the composer.

    Returns 'none' (composer empty → text submitted/queued), 'literal' (typed or
    pasted text still in the box), or 'chip' (a collapsed '[Pasted text #N]'
    placeholder). This is the ground-truth signal `tmux_send_text` keys off to
    decide whether the message actually fired a turn.

    The composer region is the LAST prompt-glyph line down to the FIRST boundary
    below it — the composer's bottom separator RULE ('────') or the footer,
    whichever comes first. Terminating ONLY at the footer (the old bug) swallowed
    the rule line itself as 'draft content', so EVERY idle/empty composer read as
    a stuck draft: verification could never tell "submitted" from "stuck", the
    BSpace+Enter recovery fired blindly on every send, and a paste chip could be
    BSpace-deleted into a lost message. Stopping at the rule fixes the predicate.

    NO busy short-circuit: a draft can sit in the composer while a PRIOR turn is
    still running (paste lands mid-turn, the follow-up Enter absorbed) — that
    orphaned draft, left unsubmitted when the prior turn ends, is the exact
    "agent idle with queued text" bug, so we classify composer content regardless
    of the busy marker. Glyph / footer / paste tag are backend-specific (MARKERS).
    """
    m = markers_for(backend)
    prompt, region_end, paste = m["prompt"], m["region_end"], m["paste"]
    r = tmux_run("capture-pane", "-t", target, "-p")
    if r.returncode != 0:
        return "none"
    lines = r.stdout.splitlines()
    pi = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith(prompt):   # composer prompt glyph
            pi = i
            break
    if pi is None:
        return "none"
    region = []
    for l in lines[pi:]:
        s = l.strip()
        if region_end in l.lower() or (s and set(s) <= {"─"}):  # footer OR rule
            break
        region.append(l)
    if not region:
        return "none"
    text = "\n".join(region)
    if paste in text.lower():
        return "chip"
    first_after_prompt = region[0].split(prompt, 1)[1] if prompt in region[0] else ""
    if backend == "codex" and not "\n".join(region[1:]).strip():
        codex_placeholders = {
            "Explain this codebase",
            "Find and fix a bug in @filename",
            "Write tests for @filename",
            "Summarize recent commits",
            "Use /skills to list available skills",
            "Implement {feature}",
        }
        if first_after_prompt.strip() in codex_placeholders:
            return "none"
    if first_after_prompt.strip() or "\n".join(region[1:]).strip():
        return "literal"
    return "none"


def tmux_send_text(target, text, backend=DEFAULT_BACKEND):
    """Bracketed-paste send that reliably SUBMITS a turn, with copy-mode defense.

    Three failure modes are handled:
    1. copy-mode: typing into a pane in tmux's view-mode types INTO copy-mode
       commands, not the composer. Cancel it before AND after.
    2. absorbed Enter / paste-draft: a paste landing at/after turn-end (or under
       heavy load) captures the follow-up Enter as a trailing newline, so the
       message becomes an un-submitted draft. We DELAY the Enter so it settles as
       a submit, then VERIFY the composer actually emptied; while a draft
       persists we resubmit it — Enter-only for a '[Pasted text #N]' chip (BSpace
       would DELETE the whole chip → lost message), BSpace+Enter for a literal
       multiline draft (eat the trailing newline, then submit).
    3. silent no-fire: text delivered but never became a turn. The success gate
       is POSITIVE — the agent goes busy (our turn started) OR the composer is
       empty across two consecutive reads (submitted / queued behind a running
       turn). So an `mp send` that returns ok has provably fired a turn — or
       fails loudly — instead of leaving text idle in the composer.

    EXACTLY-ONCE submission — do NOT press Up here. `Up` recalls the last
    submitted message back INTO the composer; the draft-check then reads it as a
    fresh draft and resubmits it (the duplicate-notification bug). The recovery
    only ever resubmits the draft ALREADY in the composer, and Enter on an empty
    composer is a harmless no-op (Claude never submits an empty composer), so a
    given message is delivered exactly once.
    """
    # Exit copy-mode / view-mode if active.
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_in_mode}")
    if r.returncode == 0 and r.stdout.strip() == "1":
        tmux_run("send-keys", "-t", target, "-X", "cancel")
        time.sleep(0.1)

    # Was a turn already running before we sent? If so, our message can only be
    # QUEUED (composer empty), never drive a fresh busy-edge of its own — so we
    # must NOT read the prior turn's busy marker as proof OUR message submitted.
    busy_before = _is_busy(target, backend)

    # Bracketed-paste send (strip any trailing newline so we control submission).
    safe = text.replace(PASTE_END, "").replace(PASTE_START, "").rstrip("\n")
    payload = f"{PASTE_START}{safe}{PASTE_END}"
    r = tmux_run("send-keys", "-t", target, "-l", "--", payload)
    if r.returncode != 0:
        return False, r.stderr.strip()

    # DELAYED submit: let the paste fully settle before Enter so the Enter is
    # processed as a submit instead of being absorbed into the paste buffer.
    # 0.6s (was 0.4): a large paste under load needs longer to settle before the
    # Enter registers as a submit rather than being eaten by the paste buffer.
    time.sleep(0.6)
    r = tmux_run("send-keys", "-t", target, "Enter")
    if r.returncode != 0:
        return False, r.stderr.strip()

    # VERIFY + RESUBMIT until the message provably fired. Check the draft FIRST
    # (so an orphaned draft sitting under a still-running PRIOR turn is caught,
    # not masked by that turn's busy marker), then accept on a busy-edge of our
    # own or a stably-empty composer. Loud failure if it never clears.
    #
    # PATIENCE under a running turn: when a turn is in flight the pasted message
    # is QUEUED (or held) and the composer clears on its own once the turn ends —
    # so if a draft persists WHILE the target is busy we WAIT for the turn to
    # finish instead of hammering BSpace+Enter. The old code fought every draft
    # with BSpace within an 8×0.4s≈3.2s window: too short for a busy peer, so it
    # reported "never submitted" on messages that were actually queued (a FALSE
    # negative → the caller re-sent → duplicate), and the blind BSpace churn could
    # merge/corrupt a queued message under contention. The wider 20×0.5s≈10s
    # budget + the busy-wait reserves the active key-recovery (BSpace+Enter) for a
    # genuinely absorbed Enter on an IDLE composer. A genuinely stuck draft still
    # persists across the whole budget → still a loud, honest failure.
    ok = False
    empty_idle_seen = 0
    for attempt in range(20):
        time.sleep(0.5)
        kind = _composer_draft(target, backend)
        if kind != "none":                       # a draft is still sitting in the composer
            empty_idle_seen = 0
            if _is_busy(target, backend):        # turn running → msg is queued/held; wait it out, don't corrupt it
                continue
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} mp send: {kind} draft did not submit, resubmitting (attempt {attempt + 1}) -> {target}\n")
            if kind == "chip":
                tmux_run("send-keys", "-t", target, "Enter")    # submit chip (BSpace would delete it)
            else:
                tmux_run("send-keys", "-t", target, "BSpace")   # eat the trailing newline
                time.sleep(0.15)
                tmux_run("send-keys", "-t", target, "Enter")    # then submit the draft
            continue
        # Composer is empty → the text left the input (submitted or queued).
        if busy_before or _is_busy(target, backend):
            ok = True                            # queued behind a running turn (prior or our own) → fired
            break
        empty_idle_seen += 1                     # idle + empty: text submitted; want it stable
        if empty_idle_seen >= 2:
            ok = True
            break

    # Post-injection mirror: ensure pane is left in text-editing mode.
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_in_mode}")
    if r.returncode == 0 and r.stdout.strip() == "1":
        tmux_run("send-keys", "-t", target, "-X", "cancel")

    if not ok:
        return False, "message never submitted (composer still held a draft after 20 retries)"
    return True, ""


def parse_agent_id(aid):
    if "/" not in aid or ":" not in aid:
        return None
    host, rest = aid.split("/", 1)
    if ":" not in rest:
        return None
    sess, tab = rest.split(":", 1)
    return host, sess, tab


def claude_spawn_cmd(resume_sid=None):
    """The claude launch command. With resume_sid it RESUMES that session by id
    (--resume) — the revive path's only mechanism; without it, a fresh session.
    Shared by execute_spawn and execute_revive so the two never drift."""
    resume = f"--resume {shlex.quote(resume_sid)} " if resume_sid else ""
    return (
        f"claude {resume}--dangerously-skip-permissions "
        f"--settings {shlex.quote(json.dumps({'skipDangerousModePermissionPrompt': True}))} "
        f"--plugin-dir {shlex.quote(PLUGIN_DIR)}"
    )


def _env_exports(aid, mc_sess, tab, boss_id):
    parts = [
        f"export AGENT_NAME={shlex.quote(tab)}",
        f"export AGENT_SESSION={shlex.quote(mc_sess)}",
        f"export AGENT_ID={shlex.quote(aid)}",
        f"export QUEUE_URL={shlex.quote(QUEUE_URL)}",
        f"export QUEUE_SECRET={shlex.quote(SECRET)}",
        f"export HOST_ID={shlex.quote(HOSTNAME)}",
        f"export INSTALL_DIR={shlex.quote(INSTALL_DIR)}",
    ]
    if boss_id:
        parts.append(f"export BOSS_ID={shlex.quote(boss_id)}")
    return parts


def execute_spawn(task):
    payload = task.get("payload", {})
    aid = payload.get("agent_id", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad agent_id"
    _, sess, tab = parsed
    backend = payload.get("backend", "claude")
    cwd = payload.get("cwd", os.path.expanduser("~"))
    # Reject non-existent cwd upfront — otherwise `cd ...` fails inside the
    # shell command, `exec claude` runs in the wrong directory, and the
    # caller sees a confusing partial-failure with no clean error. This is
    # the kind of silent fallthrough we never want.
    if not os.path.isdir(cwd):
        return False, f"cwd does not exist on this host: {cwd!r}"
    boss_id = payload.get("boss_id", "")
    is_master = bool(payload.get("is_master", False))
    mc_sess = f"mc-{sess}"

    has_sess = tmux_run("has-session", "-t", mc_sess).returncode == 0
    if not has_sess:
        r = tmux_run("new-session", "-d", "-s", mc_sess, "-n", tab, "-c", cwd)
        if r.returncode != 0:
            return False, f"new-session failed: {r.stderr.strip()}"
    else:
        wins = tmux_run("list-windows", "-t", mc_sess, "-F", "#{window_name}").stdout.splitlines()
        if tab in wins:
            # Idempotent re-spawn: window already exists. Callers (e.g. a Boss
            # orchestrating workers) may legitimately re-spawn the same id if a
            # worker disconnected but its tmux window survived — so reuse is OK
            # *only* when the pane is actually running the requested backend.
            # NEVER silently relabel: if the pane runs a DIFFERENT backend than
            # asked for, reusing it would flip the registry label (e.g. to
            # 'codex') while the process stays 'claude' — the exact CEO-caught
            # bug. Verify by the RUNNING PROCESS and refuse the mismatch loudly
            # instead of lying in the registry.
            running = _pane_backend(f"{mc_sess}:{tab}")
            if running is not None and running != backend:
                return False, (f"window {mc_sess}:{tab} already runs backend={running!r}; "
                               f"refusing to relabel it as {backend!r} (that would make the "
                               f"registry lie). `mp kill {aid}` then re-spawn --backend {backend}.")
            record_agent(aid, backend, boss_id, is_master)
            roster_record_spawn(aid, backend, cwd, boss_id, is_master, claude_spawn_cmd() if backend == "claude" else f"{backend} (backend)")
            try:
                post_json("/agents/register", {"agent_id": aid, "backend": backend, "state": "alive", "boss_id": boss_id, "is_master": is_master})
            except urllib.error.URLError as e:
                return False, f"re-register failed: {e}"
            return True, {"agent_id": aid, "tmux_target": f"{mc_sess}:{tab}", "boss_id": boss_id, "is_master": is_master, "reused_existing": True, "running_backend": running}
        r = tmux_run("new-window", "-t", mc_sess, "-n", tab, "-c", cwd)
        if r.returncode != 0:
            return False, f"new-window failed: {r.stderr.strip()}"

    if backend == "claude":
        spawn_cmd = claude_spawn_cmd()
    elif backend == "codex":
        # Codex's turn-end signal is its `notify` program (NOT a Stop hook).
        # Point it at the codex-notify shim per-spawn so no global ~/.codex
        # config edit is required; the shim re-emits emit-event's Stop-branch
        # notification on the SAME queue contract. `-c key=value` parses value
        # as TOML — a JSON array is valid TOML. `--dangerously-bypass-approvals-
        # and-sandbox` is the autonomy analog of Claude's --dangerously-skip-
        # permissions (composer shows "permissions: YOLO mode").
        notify_script = os.path.join(PLUGIN_DIR, "hooks", "codex-notify")
        notify_cfg = "notify=" + json.dumps(["bash", notify_script])
        spawn_cmd = (
            f"codex --dangerously-bypass-approvals-and-sandbox --enable hooks "
            f"-c {shlex.quote(notify_cfg)}"
        )
    else:
        return False, f"backend {backend!r} not supported"

    env_parts = _env_exports(aid, mc_sess, tab, boss_id)
    # Env hygiene for codex: a stray AGENT_ROLE inherited from a parent shell
    # made the legacy codex hook mis-route notifications. mypeople doesn't set
    # AGENT_ROLE, so this is purely defensive (harmless no-op when unset).
    pre_exec = "unset AGENT_ROLE && " if backend == "codex" else ""
    shell_cmd = f"cd {shlex.quote(cwd)} && {' && '.join(env_parts)} && {pre_exec}exec {spawn_cmd}"

    target = f"{mc_sess}:{tab}"
    ok, err = tmux_send_text(target, shell_cmd)
    if not ok:
        return False, f"shell-cmd send failed: {err}"

    if backend == "claude":
        deadline = time.time() + 30
        while time.time() < deadline:
            r = tmux_run("capture-pane", "-t", target, "-p")
            if "bypass permissions on" in (r.stdout or ""):
                break
            time.sleep(0.5)
        else:
            return False, "claude TUI didn't show 'bypass permissions on' banner within 30s"
    elif backend == "codex":
        # Codex shows interactive gates BEFORE the composer on a fresh start: an
        # "Update available" prompt and a directory-trust prompt. Pre-seeding
        # [projects."<cwd>"].trust_level = "trusted" in ~/.codex/config.toml (the
        # CEO already does this per project) and disabling the update notifier
        # removes both; this loop ALSO dismisses them defensively so a spawn
        # never silently hangs on a gate. Ready when the startup banner OR the
        # composer footer (markers_for('codex')['region_end'], "<model> · <cwd>")
        # is on screen — the footer is the true "accepting input" signal and the
        # banner can be delayed by MCP init. Timeout is generous (60s): codex's
        # MCP startup retries on a bad/expired token, which delays the composer.
        cm = markers_for("codex")
        ready, footer = cm["ready"], cm["region_end"]
        deadline = time.time() + 60
        while time.time() < deadline:
            frame = tmux_run("capture-pane", "-t", target, "-p").stdout or ""
            low = frame.lower()
            if "do you trust" in low:                       # trust gate
                tmux_run("send-keys", "-t", target, "Enter")        # default: Yes, continue
                time.sleep(0.5); continue
            # Match the NUMBERED update prompt specifically ("1. Update now"),
            # not the persistent "Update available" info box, so we never
            # mis-fire keystrokes at the composer once it has rendered.
            if "update now" in low:                          # update gate
                tmux_run("send-keys", "-t", target, "Down")         # move off "Update now"
                time.sleep(0.1)
                tmux_run("send-keys", "-t", target, "Enter")        # choose Skip
                time.sleep(0.5); continue
            if ready in frame or footer in frame:
                break
            time.sleep(0.5)
        else:
            return False, "codex TUI didn't reach the composer (ready/footer marker) within 60s"

    # If --master, bootstrap the Boss with its doctrine: send an onboarding
    # prompt that instructs the agent to read ~/mypeople/boss-CLAUDE.md and
    # ack with a one-line summary. The spawn returns once the prompt is sent;
    # the agent's first Stop event will fire when it finishes reading + acking,
    # at which point its status.json will reflect the doctrine.
    if is_master:
        time.sleep(0.5)  # let the banner settle
        doctrine = os.path.join(INSTALL_DIR, "boss-CLAUDE.md")
        onboarding = (
            f"You are the Boss for this mypeople deployment. Your AGENT_ID is {aid}. "
            f"Read {doctrine} now — it is your full job description (plan-gate, autonomous loop, fire-and-forget). "
            f"Then reply in ONE line summarizing your role and the mp verbs you have available. "
            f"After that, await CEO instructions."
        )
        ok, err = tmux_send_text(target, onboarding)
        if not ok:
            return False, f"onboarding send failed: {err}"

    record_agent(aid, backend, boss_id, is_master)
    roster_record_spawn(aid, backend, cwd, boss_id, is_master, spawn_cmd)
    try:
        post_json("/agents/register", {"agent_id": aid, "backend": backend, "state": "alive", "boss_id": boss_id, "is_master": is_master})
    except urllib.error.URLError as e:
        return False, f"register failed: {e}"

    return True, {"agent_id": aid, "tmux_target": target, "boss_id": boss_id, "is_master": is_master}


def execute_revive(task):
    """REVIVE a retired engineer by RESUMING its actual Claude session (--resume
    <session-id>). RESUME-ONLY: there is NO fresh-spawn fallback. Every failed
    precondition returns a loud error that the HUD surfaces — we never silently
    start a brand-new session in place of the one the CEO asked to revive."""
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    with _roster_lock:
        entry = _load_roster().get(aid)
    if not entry:
        return False, f"not resumable: no roster record for {aid}"
    if entry.get("state") != "retired":
        return False, f"not revivable: {aid} is not retired (state={entry.get('state')!r})"
    backend = entry.get("backend", "claude")
    if backend != "claude":
        return False, f"not resumable: revive supports only the claude backend (got {backend!r})"
    cwd = entry.get("cwd", "")
    if not cwd or not os.path.isdir(cwd):
        return False, f"not resumable: original cwd missing on this host ({cwd!r})"
    session_id = _roster_session_id(aid)
    if not session_id:
        return False, "not resumable: no session-id captured for this engineer"
    transcript = _session_transcript(session_id)
    if not transcript:
        return False, f"not resumable: session transcript {session_id}.jsonl not found on disk"

    boss_id = entry.get("boss_id", "")
    is_master = bool(entry.get("is_master", False))
    mc_sess = f"mc-{sess}"
    has_sess = tmux_run("has-session", "-t", mc_sess).returncode == 0
    if not has_sess:
        r = tmux_run("new-session", "-d", "-s", mc_sess, "-n", tab, "-c", cwd)
        if r.returncode != 0:
            return False, f"new-session failed: {r.stderr.strip()}"
    else:
        wins = tmux_run("list-windows", "-t", mc_sess, "-F", "#{window_name}").stdout.splitlines()
        if tab in wins:
            return False, f"window {mc_sess}:{tab} already exists — kill it before reviving"
        r = tmux_run("new-window", "-t", mc_sess, "-n", tab, "-c", cwd)
        if r.returncode != 0:
            return False, f"new-window failed: {r.stderr.strip()}"

    spawn_cmd = claude_spawn_cmd(resume_sid=session_id)
    env_parts = _env_exports(aid, mc_sess, tab, boss_id)
    shell_cmd = f"cd {shlex.quote(cwd)} && {' && '.join(env_parts)} && exec {spawn_cmd}"
    target = f"{mc_sess}:{tab}"
    ok, err = tmux_send_text(target, shell_cmd)
    if not ok:
        return False, f"resume-cmd send failed: {err}"

    deadline = time.time() + 40
    while time.time() < deadline:
        r = tmux_run("capture-pane", "-t", target, "-p")
        if "bypass permissions on" in (r.stdout or ""):
            break
        time.sleep(0.5)
    else:
        return False, "claude TUI didn't show 'bypass permissions on' within 40s after --resume"

    record_agent(aid, backend, boss_id, is_master)
    roster_mark_alive(aid)
    try:
        post_json("/agents/register", {"agent_id": aid, "backend": backend, "state": "alive", "boss_id": boss_id, "is_master": is_master})
    except urllib.error.URLError as e:
        return False, f"register failed: {e}"
    return True, {"agent_id": aid, "tmux_target": target, "resumed_session_id": session_id, "transcript": transcript}


def execute_send(task):
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    target = f"mc-{sess}:{tab}"
    if tmux_run("has-session", "-t", f"mc-{sess}").returncode != 0:
        return False, f"session mc-{sess} does not exist"
    msg = task.get("payload", {}).get("message", "")
    ok, err = tmux_send_text(target, msg, _agent_backend(aid))
    if not ok:
        return False, err
    return True, {"delivered_to": target}


# Claude Code's TUI prints "esc to interrupt" in its footer ONLY while a turn is
# actively running; when the agent is idle the footer is just the bypass-perms
# hint and the composer (❯) awaits input. That token is the ground-truth busy
# signal. A raw `capture-pane` dump buries it under the composer + footer, so an
# agent that's mid-turn (e.g. installing) — especially one whose composer holds a
# freshly-queued `mp send` — reads as idle/stuck. peek must classify and surface
# the live state, not make the Boss infer it from the bottom of a text wall.
PEEK_BUSY_MARKER = "esc to interrupt"


def peek_state(pane_text, backend=DEFAULT_BACKEND):
    """Classify an agent pane as BUSY / IDLE / UNKNOWN from its live frame.

    Only the tail (the on-screen UI chrome — status line, composer, footer) is
    inspected so a stale scrollback line can't spoof the state. Use the last 15
    NON-BLANK lines: `capture-pane -S` leaves trailing blank rows on a tall pane
    (e.g. a wide ttyd-attached container is 70+ rows), which would push the
    footer/composer out of a raw last-15 slice and mis-read a healthy idle agent
    as UNKNOWN. Busy/idle markers are backend-specific (see MARKERS)."""
    m = markers_for(backend)
    idle_markers = m["idle"] if isinstance(m["idle"], tuple) else (m["idle"],)
    tail = "\n".join([l for l in pane_text.splitlines() if l.strip()][-15:])
    low = tail.lower()
    if m["busy"] in low:
        return "BUSY", "a turn is actively running (busy marker present)"
    if any((mk in tail) or (mk.lower() in low) for mk in idle_markers):
        return "IDLE", "awaiting input (no turn running)"
    return "UNKNOWN", f"no {backend} TUI footer detected (starting up, a shell, or exited)"


def execute_peek(task):
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    target = f"mc-{sess}:{tab}"
    if tmux_run("has-session", "-t", f"mc-{sess}").returncode != 0:
        return False, f"session mc-{sess} does not exist"
    # One fresh capture: visible frame (bottom = live state) + 200 lines of
    # scrollback for work context. Classify the frame, then surface the verdict
    # in a header so the Boss gets an accurate read at a glance.
    r = tmux_run("capture-pane", "-t", target, "-p", "-S", "-200")
    if r.returncode != 0:
        return False, r.stderr.strip()
    pane = r.stdout
    state, detail = peek_state(pane, _agent_backend(aid))
    header = f"[mp peek {aid}] state={state} — {detail}\n" + ("─" * 72) + "\n"
    return True, {"content": header + pane, "state": state, "activity": detail}


def execute_kill(task):
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    # The retire REASON the HUD shows: "killed" for a manual `mp kill`, or
    # "done-auto-retire" when the board's DONE→retire path kills the assignee
    # (`mp kill <id> --reason done-auto-retire`). The roster keeps the record
    # either way (retired, not deleted) so the engineer can be revived.
    reason = (task.get("payload", {}) or {}).get("reason", "killed")
    _, sess, tab = parsed
    mc_sess = f"mc-{sess}"
    target = f"{mc_sess}:{tab}"
    if tmux_run("has-session", "-t", mc_sess).returncode != 0:
        forget_agent(aid)
        roster_mark_retired(aid, reason)
        try:
            post_json("/agents/unregister", {"agent_id": aid})
        except urllib.error.URLError:
            pass
        return True, {"already_gone": True}
    wins = tmux_run("list-windows", "-t", mc_sess, "-F", "#{window_name}").stdout.splitlines()
    if len(wins) <= 1:
        r = tmux_run("kill-session", "-t", mc_sess)
    else:
        r = tmux_run("kill-window", "-t", target)
    if r.returncode != 0:
        return False, r.stderr.strip()
    forget_agent(aid)
    roster_mark_retired(aid, reason)
    try:
        post_json("/agents/unregister", {"agent_id": aid})
    except urllib.error.URLError:
        pass
    return True, {"killed": target}


def execute_answer(task):
    """Answer an AskUserQuestion form the agent is BLOCKED on, then submit it —
    so the Boss can unblock a remote question. A bare `send` only piles text into
    the composer without selecting/submitting; this drives the actual widget.

    payload.answer:
      - an integer "N"  -> select option N of the (first) question. The widget
                           opens with option 1 highlighted; Down moves the
                           highlight, Enter confirms.
      - any other text  -> type a free-form custom answer and submit it.
    """
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    mc_sess = f"mc-{sess}"
    target = f"{mc_sess}:{tab}"
    if tmux_run("has-session", "-t", mc_sess).returncode != 0:
        return False, f"session {mc_sess} does not exist"
    answer = str(task.get("payload", {}).get("answer", "")).strip()
    if not answer:
        return False, "empty answer"

    # Same copy-mode defense as tmux_send_text: a pane stuck in view-mode would
    # eat the navigation keys.
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_in_mode}")
    if r.returncode == 0 and r.stdout.strip() == "1":
        tmux_run("send-keys", "-t", target, "-X", "cancel")
        time.sleep(0.1)

    if answer.isdigit():
        n = int(answer)
        if n < 1:
            return False, "option number must be >= 1"
        # Down (N-1) times from the default top highlight, then Enter to confirm.
        for _ in range(n - 1):
            tmux_run("send-keys", "-t", target, "Down")
            time.sleep(0.08)
        time.sleep(0.12)
        r = tmux_run("send-keys", "-t", target, "Enter")
        if r.returncode != 0:
            return False, r.stderr.strip()
        return True, {"answered": target, "selected_option": n}

    # Free-form answer: type it literally and submit (custom-answer path).
    ok, err = tmux_send_text(target, answer, _agent_backend(aid))
    if not ok:
        return False, err
    return True, {"answered": target, "text": answer}


HANDLERS = {"spawn": execute_spawn, "send": execute_send, "peek": execute_peek,
            "kill": execute_kill, "answer": execute_answer, "revive": execute_revive}


def task_loop():
    while True:
        try:
            task = get_json(f"/task/poll?hostname={urllib.parse.quote(HOSTNAME)}")
        except urllib.error.URLError as e:
            print(f"{time.strftime('%H:%M:%S')} poll FAIL: {e}", file=sys.stderr, flush=True)
            time.sleep(POLL_INTERVAL)
            continue
        if not task:
            time.sleep(POLL_INTERVAL)
            continue
        tid = task.get("task_id")
        action = task.get("action", "")
        handler = HANDLERS.get(action)
        if not handler:
            try:
                post_json("/task/result", {"task_id": tid, "ok": False, "error": f"unknown action {action!r}"})
            except urllib.error.URLError:
                pass
            continue
        try:
            ok, payload = handler(task)
        except Exception as e:
            ok, payload = False, f"handler raised: {e}"
        try:
            if ok:
                post_json("/task/result", {"task_id": tid, "ok": True, "result": payload})
            else:
                post_json("/task/result", {"task_id": tid, "ok": False, "error": str(payload)})
        except urllib.error.URLError as e:
            print(f"{time.strftime('%H:%M:%S')} result POST FAIL: {e}", file=sys.stderr, flush=True)
        print(f"{time.strftime('%H:%M:%S')} task {tid[:8]} {action} → ok={ok}", flush=True)


def main():
    if not SECRET:
        print("FATAL: QUEUE_SECRET not set", file=sys.stderr)
        sys.exit(1)
    print(f"queue-client started, host={HOSTNAME}, heartbeat={HEARTBEAT}s, poll={POLL_INTERVAL}s", flush=True)
    detect_reboot_retirements()   # roster engineers whose window died (e.g. reboot) → retired, revivable
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    task_loop()


if __name__ == "__main__":
    main()
PY_EOF
chmod +x "$INSTALL_DIR/bin/queue-client.py"
```

### 6. Write the `mp` CLI

```bash
cat > "$INSTALL_DIR/bin/mp" <<'PY_EOF'
#!/usr/bin/env python3
"""mp — mypeople CLI. Verbs: status, spawn, send, peek, kill."""

import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CONFIG = Path.home() / ".config" / "mypeople" / "queue.env"
DEFAULT_TIMEOUT = 60
POLL_INTERVAL = 0.3


def load_env():
    cfg = {}
    if CONFIG.exists():
        for line in CONFIG.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg["QUEUE_URL"] = os.environ.get("QUEUE_URL", cfg.get("QUEUE_URL", "http://127.0.0.1:9900"))
    cfg["QUEUE_SECRET"] = os.environ.get("QUEUE_SECRET", cfg.get("QUEUE_SECRET", ""))
    cfg["HOST_ID"] = os.environ.get("HOST_ID", cfg.get("HOST_ID", "")) or _hostname()
    return cfg


def _hostname():
    import socket
    return socket.gethostname()


def http_get(url, secret):
    req = urllib.request.Request(url, headers={"X-Queue-Secret": secret})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        return json.loads(body) if body.strip() else {}


def http_post(url, secret, data):
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-Queue-Secret": secret},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        return json.loads(body) if body.strip() else {}


def canonicalize_agent_id(arg, host_id):
    if "/" in arg and ":" in arg:
        return arg
    if ":" in arg:
        return f"{host_id}/{arg}"
    raise ValueError(f"agent_id must be <host>/<session>:<tab> or <session>:<tab>; got {arg!r}")


def submit_and_wait(cfg, body, timeout=DEFAULT_TIMEOUT):
    url, secret = cfg["QUEUE_URL"], cfg["QUEUE_SECRET"]
    r = http_post(f"{url}/task/submit", secret, body)
    tid = r.get("task_id")
    if not tid:
        raise RuntimeError(f"submit returned no task_id: {r}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = http_get(f"{url}/task/{tid}", secret)
        if t.get("status") in ("done", "failed"):
            return t
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"task {tid} did not complete in {timeout}s")


def cmd_status(cfg, args):
    url, secret = cfg["QUEUE_URL"], cfg["QUEUE_SECRET"]
    try:
        agents = http_get(f"{url}/agents", secret)
        clients = http_get(f"{url}/clients", secret)
    except urllib.error.URLError as e:
        print(f"queue-server unreachable at {url}: {e}", file=sys.stderr)
        sys.exit(1)
    if not agents:
        print("No active agents.")
    else:
        for a in agents:
            boss = a.get("boss_id", "")
            boss_part = f" boss={boss}" if boss else ""
            print(f"  {a['agent_id']} [{a.get('state','?')}] backend={a.get('backend','?')}{boss_part}")
    print(f"\n{len(clients)} client(s) heartbeating:")
    now = time.time()
    for c in clients:
        age = int(now - c["ts"])
        print(f"  {c['hostname']} (last seen {age}s ago)")


def cmd_spawn(cfg, args):
    if len(args) < 1:
        print("Usage: mp spawn <agent_id> [--backend claude] [--cwd PATH] [--boss <agent_id>] [--master]", file=sys.stderr)
        sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    backend = "claude"
    cwd = os.path.expanduser("~")
    boss_id = ""
    is_master = False
    i = 1
    while i < len(args):
        if args[i] == "--backend" and i + 1 < len(args):
            backend = args[i + 1]; i += 2
        elif args[i] == "--cwd" and i + 1 < len(args):
            cwd = args[i + 1]; i += 2
        elif args[i] == "--boss" and i + 1 < len(args):
            boss_id = canonicalize_agent_id(args[i + 1], cfg["HOST_ID"]); i += 2
        elif args[i] == "--master":
            is_master = True; i += 1
        else:
            print(f"unknown arg: {args[i]}", file=sys.stderr); sys.exit(2)
    target_host = aid.split("/", 1)[0]
    body = {"action": "spawn", "target_host": target_host,
            "payload": {"agent_id": aid, "backend": backend, "cwd": cwd, "boss_id": boss_id, "is_master": is_master}}
    t = submit_and_wait(cfg, body, timeout=60)
    if t["status"] == "done":
        r = t.get("result") or {}
        boss_part = f" boss={r.get('boss_id','')}" if r.get("boss_id") else ""
        master_part = " [MASTER — onboarding sent]" if r.get("is_master") else ""
        print(f"Spawned {r.get('agent_id', aid)}  [tmux={r.get('tmux_target','?')}]{boss_part}{master_part}")
    else:
        print(f"Spawn FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


def cmd_send(cfg, args):
    if len(args) < 2:
        print("Usage: mp send <agent_id> <message>", file=sys.stderr); sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    msg = " ".join(args[1:])
    body = {"action": "send", "target_agent": aid, "payload": {"message": msg}}
    # 30s (was 10): tmux_send_text now patiently waits out a running turn so a queued
    # message is confirmed delivered (no false "Send FAILED" → no duplicate re-send).
    t = submit_and_wait(cfg, body, timeout=30)
    if t["status"] == "done":
        print(f"Sent to {aid}")
    else:
        print(f"Send FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


def cmd_peek(cfg, args):
    if len(args) < 1:
        print("Usage: mp peek <agent_id>", file=sys.stderr); sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    body = {"action": "peek", "target_agent": aid}
    t = submit_and_wait(cfg, body, timeout=10)
    if t["status"] == "done":
        sys.stdout.write((t.get("result") or {}).get("content", ""))
    else:
        print(f"Peek FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


def cmd_kill(cfg, args):
    if len(args) < 1:
        print("Usage: mp kill <agent_id> [--reason <killed|done-auto-retire>]", file=sys.stderr); sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    reason = "killed"
    i = 1
    while i < len(args):
        if args[i] == "--reason" and i + 1 < len(args):
            reason = args[i + 1]; i += 2
        else:
            i += 1
    # The reason is recorded on the durable roster so the HUD can show WHY an
    # engineer retired (manual kill vs DONE→auto-retire). The engineer is kept
    # (retired, not deleted) so it can be revived by resuming its session.
    body = {"action": "kill", "target_agent": aid, "payload": {"reason": reason}}
    t = submit_and_wait(cfg, body, timeout=10)
    if t["status"] == "done":
        print(f"Killed {aid}")
    else:
        print(f"Kill FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


def cmd_revive(cfg, args):
    if len(args) < 1:
        print("Usage: mp revive <agent_id>", file=sys.stderr); sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    # REVIVE = resume the engineer's ACTUAL prior Claude session by session-id.
    # Resume-only: if the session can't be resumed the server returns an error
    # (surfaced here + on the HUD) — there is NO fresh-spawn fallback.
    body = {"action": "revive", "target_agent": aid}
    t = submit_and_wait(cfg, body, timeout=60)
    if t["status"] == "done":
        r = t.get("result") or {}
        print(f"Revived {aid} — resumed session {r.get('resumed_session_id', '?')}  [tmux={r.get('tmux_target', '?')}]")
    else:
        print(f"Revive FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


def cmd_answer(cfg, args):
    # Answer an AskUserQuestion form the agent is blocked on (option number or
    # free text), actually selecting/submitting it so the agent proceeds.
    if len(args) < 2:
        print("Usage: mp answer <agent_id> <option-number | free text>", file=sys.stderr); sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    answer = " ".join(args[1:])
    body = {"action": "answer", "target_agent": aid, "payload": {"answer": answer}}
    t = submit_and_wait(cfg, body, timeout=10)
    if t["status"] == "done":
        r = t.get("result") or {}
        if "selected_option" in r:
            print(f"Answered {aid}: selected option {r['selected_option']}")
        else:
            print(f"Answered {aid}: {r.get('text','submitted')}")
    else:
        print(f"Answer FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


COMMANDS = {"status": cmd_status, "spawn": cmd_spawn, "send": cmd_send, "peek": cmd_peek, "kill": cmd_kill, "answer": cmd_answer, "revive": cmd_revive}


def main():
    if len(sys.argv) < 2:
        print("Usage: mp <command> [args]\n\nCommands: " + ", ".join(COMMANDS.keys()), file=sys.stderr); sys.exit(2)
    cfg = load_env()
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    fn = COMMANDS.get(cmd)
    if not fn:
        print(f"Unknown command: {cmd}\n\nCommands: " + ", ".join(COMMANDS.keys()), file=sys.stderr); sys.exit(2)
    return fn(cfg, rest)


if __name__ == "__main__":
    main()
PY_EOF
chmod +x "$INSTALL_DIR/bin/mp"
ln -sf "$INSTALL_DIR/bin/mp" "$HOME/.local/bin/mp"
```

### 7. Write the `tmux-boss-hooks` plugin

```bash
cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/.claude-plugin/plugin.json" <<'EOF'
{
  "name": "tmux-boss-hooks",
  "description": "Per-spawn lifecycle hooks for mypeople-managed agents.",
  "version": "1.1.0"
}
EOF

cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/hooks.json" <<EOF
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event", "timeout": 5}]}],
    "PreToolUse":   [{"matcher": "AskUserQuestion", "hooks": [{"type": "command", "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event", "timeout": 10}]}],
    "Stop":         [{"hooks": [{"type": "command", "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event", "timeout": 10}]}],
    "SessionEnd":   [{"hooks": [{"type": "command", "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event", "timeout": 5}]}]
  }
}
EOF

cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event" <<'EOF'
#!/bin/bash
# Lifecycle hook for mypeople-managed Claude agents.
#
# Triggered by Claude Code on SessionStart / Stop / SessionEnd.
# Reads the hook payload JSON from stdin. For Stop: writes a status file
# under $INSTALL_DIR/status/<session>/<agent>.json AND submits an
# "[AGENT NOTIFICATION]" send task targeting $BOSS_ID (if set).
#
# Gating: requires AGENT_ID env var. Unmanaged claude invocations are no-ops.

set -e
[ -z "${AGENT_ID:-}" ] && exit 0   # not managed by mypeople

INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/run"
LOG="$INSTALL_DIR/run/hook-events.log"

INPUT=""
IFS= read -t 5 -d '' -r INPUT || true
[ -z "$INPUT" ] && exit 0

EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // "?"' 2>/dev/null || echo "?")
SID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null || echo "")
LAST_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // ""' 2>/dev/null || echo "")
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Idempotency key for a notification: a stable digest of (event, session, agent,
# message). If the Stop hook ever fires twice for one turn-end — or a submit is
# retried — both carry the SAME key, so the queue-server dedups them inside its
# window and the Boss is notified exactly once. Portable across Debian (sha256sum)
# and macOS (shasum).
idem_key() {  # args: parts that uniquely identify this notification
  local s="$*"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$s" | sha256sum | cut -c1-32
  else
    printf '%s' "$s" | shasum -a 256 | cut -c1-32
  fi
}

# Append to local log
echo "{\"ts\":\"$TS\",\"event\":\"$EVENT\",\"agent_id\":\"$AGENT_ID\",\"session_id\":\"$SID\"}" >> "$LOG"

# Parse session+tab from AGENT_ID = host/session:tab (used by every branch).
HOST_PART="${AGENT_ID%%/*}"
REST="${AGENT_ID#*/}"
SESS_PART="${REST%%:*}"
TAB_PART="${REST#*:}"
STATUS_DIR="$INSTALL_DIR/status/mc-$SESS_PART"

# Persist the CURRENT session-id onto the durable roster so REVIVE can resume the
# actual session (this hook is authoritative for session_id; the queue-client
# merge-preserves it). Done on EVERY event so a fresh engineer's session-id is
# captured within seconds of spawn (SessionStart), not only at first Stop.
ROSTER="$INSTALL_DIR/run/roster.json"
if [ -n "$SID" ] && command -v jq >/dev/null 2>&1; then
  mkdir -p "$INSTALL_DIR/run"
  RTMP="$(mktemp)" || RTMP=""
  if [ -n "$RTMP" ]; then
    if [ -f "$ROSTER" ]; then
      jq --arg aid "$AGENT_ID" --arg sid "$SID" \
         '.[$aid] = ((.[$aid] // {}) + {session_id:$sid, agent_id:$aid})' "$ROSTER" \
         > "$RTMP" 2>/dev/null && mv "$RTMP" "$ROSTER" || rm -f "$RTMP"
    else
      jq -n --arg aid "$AGENT_ID" --arg sid "$SID" \
         '{($aid): {session_id:$sid, agent_id:$aid}}' > "$RTMP" 2>/dev/null \
         && mv "$RTMP" "$ROSTER" || rm -f "$RTMP"
    fi
  fi
fi

# SessionStart: also seed/refresh the status file with the session-id (the Stop
# branch overwrites it later with a real summary). This guarantees a durable
# session-id exists even for an engineer that has not hit a Stop yet.
if [ "$EVENT" = "SessionStart" ]; then
  mkdir -p "$STATUS_DIR"
  SF="$STATUS_DIR/$TAB_PART.json"
  if [ -f "$SF" ] && command -v jq >/dev/null 2>&1; then
    STMP="$(mktemp)" && jq --arg sid "$SID" --arg ts "$TS" \
      '.session_id=$sid | .timestamp=$ts' "$SF" > "$STMP" 2>/dev/null && mv "$STMP" "$SF" || rm -f "$STMP"
  else
    jq -n --arg agent "$TAB_PART" --arg session "mc-$SESS_PART" --arg ts "$TS" \
          --arg sid "$SID" --arg aid "$AGENT_ID" --arg boss "${BOSS_ID:-}" \
      '{agent:$agent, session:$session, status:"starting", timestamp:$ts, session_id:$sid, summary:"", agent_id:$aid, boss_id:$boss}' \
      > "$STATUS_DIR/$TAB_PART.json" 2>/dev/null || true
  fi
  exit 0
fi

# --- PreToolUse: an agent calling AskUserQuestion is about to BLOCK on an
# interactive question form. Detect it here (the tool payload carries the
# question + the exact options), notify the Boss with both, and tell the Boss
# how to answer. This closes the silent-hang gap: a question is a blocked turn,
# not a normal stop, so the Stop hook never fires for it. ---
if [ "$EVENT" = "PreToolUse" ]; then
  TOOL=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")
  [ "$TOOL" != "AskUserQuestion" ] && exit 0

  # Render each question with NUMBERED options — the numbers are exactly what
  # `mp answer <agent> <N>` selects (option N of the first/only question).
  QBLOCK=$(echo "$INPUT" | jq -r '
    [ .tool_input.questions[]?
      | "Q: " + (.question // .header // "(question)")
        + "\n   Options: "
        + ([ (.options // [])
             | to_entries[]
             | "[\(.key + 1)] " + (.value.label // (.value | tostring)) ] | join("   ")) ]
    | join("\n")' 2>/dev/null || echo "")
  [ -z "$QBLOCK" ] && QBLOCK="(could not parse question payload)"

  # Record a blocked-state status file so peek / the HUD reflect "waiting on a
  # question" instead of looking idle.
  mkdir -p "$STATUS_DIR"
  jq -n --arg agent "$TAB_PART" --arg session "mc-$SESS_PART" --arg ts "$TS" \
        --arg session_id "$SID" --arg summary "[QUESTION] $QBLOCK" \
        --arg agent_id "$AGENT_ID" --arg boss_id "${BOSS_ID:-}" \
    '{agent:$agent, session:$session, status:"blocked", timestamp:$ts, session_id:$session_id, summary:$summary, agent_id:$agent_id, boss_id:$boss_id}' \
    > "$STATUS_DIR/$TAB_PART.json" 2>/dev/null || true

  [ -z "${BOSS_ID:-}" ] && exit 0   # no boss to notify

  NOTIF="[AGENT QUESTION] $AGENT_ID is BLOCKED on a question — answer to unblock:
$QBLOCK
Reply with:  mp answer $AGENT_ID <option-number | free text>"
  BOSS_HOST="${BOSS_ID%%/*}"
  IDEM=$(idem_key "question" "$SID" "$AGENT_ID" "$QBLOCK")
  PAYLOAD=$(jq -n --arg ta "$BOSS_ID" --arg th "$BOSS_HOST" --arg msg "$NOTIF" --arg idem "$IDEM" \
    '{action:"send", target_agent:$ta, target_host:$th, idempotency_key:$idem, payload:{message:$msg}}')
  curl -fsS --max-time 3 -X POST "$QUEUE_URL/task/submit" \
    -H "Content-Type: application/json" -H "X-Queue-Secret: $QUEUE_SECRET" \
    -d "$PAYLOAD" >/dev/null 2>&1 || true
  exit 0
fi

if [ "$EVENT" != "Stop" ]; then
  # SessionStart / SessionEnd: just log, no notification.
  exit 0
fi

# --- Stop event handling ---

SUMMARY=$(echo "$LAST_MSG" | tr '\n' ' ' | cut -c1-1000)

# Write status file
mkdir -p "$STATUS_DIR"
jq -n \
  --arg agent "$TAB_PART" \
  --arg session "mc-$SESS_PART" \
  --arg ts "$TS" \
  --arg session_id "$SID" \
  --arg summary "$SUMMARY" \
  --arg agent_id "$AGENT_ID" \
  --arg boss_id "${BOSS_ID:-}" \
  '{agent: $agent, session: $session, status: "idle", timestamp: $ts, session_id: $session_id, summary: $summary, agent_id: $agent_id, boss_id: $boss_id}' \
  > "$STATUS_DIR/$TAB_PART.json"

# If no boss, we're done (status file is enough)
[ -z "${BOSS_ID:-}" ] && exit 0

# POST a send task to deliver the notification to the boss's pane
NOTIF="[AGENT NOTIFICATION] $AGENT_ID finished: $SUMMARY"
BOSS_HOST="${BOSS_ID%%/*}"
IDEM=$(idem_key "stop" "$SID" "$AGENT_ID" "$SUMMARY")
PAYLOAD=$(jq -n \
  --arg target_agent "$BOSS_ID" \
  --arg target_host "$BOSS_HOST" \
  --arg msg "$NOTIF" \
  --arg idem "$IDEM" \
  '{action: "send", target_agent: $target_agent, target_host: $target_host, idempotency_key: $idem, payload: {message: $msg}}')

curl -fsS -X POST "$QUEUE_URL/task/submit" \
  -H "Content-Type: application/json" \
  -H "X-Queue-Secret: $QUEUE_SECRET" \
  -d "$PAYLOAD" >/dev/null 2>&1 || true

exit 0
EOF
chmod +x "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event"

# --- codex-notify: Codex turn-end -> the SAME Stop-hook contract as emit-event.
# Claude agents emit turn-end via the `Stop` hook above (JSON on stdin). Codex
# CLI has NO Stop hook; instead it fires its `notify` program on turn completion
# with the payload as argv[1] and type "agent-turn-complete". The codex exec
# branch in queue-client.py points codex at THIS script via `-c notify=[...]`,
# so a codex agent's turn-end posts a byte-identical "[AGENT NOTIFICATION] ...
# finished: ..." to the Boss. No queue-server / protocol / Boss-doctrine change.
cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/codex-notify" <<'EOF'
#!/bin/bash
# codex-notify — Codex turn-end -> mypeople Stop-hook contract.
# Codex passes the notification JSON as argv[1] (NOT stdin, unlike Claude hooks)
# and the keys are HYPHENATED ("last-assistant-message", "thread-id"). This is
# the Codex-side equivalent of emit-event's Stop branch: same status file, same
# /task/submit `send` payload, same idempotency scheme -> the Boss is notified
# identically regardless of backend. Gating + identity come from the SAME env
# vars mypeople exports at spawn: AGENT_ID, BOSS_ID, QUEUE_URL, QUEUE_SECRET,
# INSTALL_DIR.

set -e
[ -z "${AGENT_ID:-}" ] && exit 0   # not managed by mypeople

INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/run"
LOG="$INSTALL_DIR/run/hook-events.log"

INPUT="${1:-}"
[ -z "$INPUT" ] && exit 0

# Only act on turn completion; ignore any other notify types.
NTYPE=$(echo "$INPUT" | jq -r '.type // ""' 2>/dev/null || echo "")
[ "$NTYPE" != "agent-turn-complete" ] && exit 0

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LAST_MSG=$(echo "$INPUT" | jq -r '.["last-assistant-message"] // ""' 2>/dev/null || echo "")
THREAD_ID=$(echo "$INPUT" | jq -r '.["thread-id"] // ""' 2>/dev/null || echo "")

# Idempotency key (same scheme as emit-event) so the queue-server dedups a
# double-fired/retried notify inside its window. thread-id is Codex's session analog.
idem_key() {
  local s="$*"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$s" | sha256sum | cut -c1-32
  else
    printf '%s' "$s" | shasum -a 256 | cut -c1-32
  fi
}

echo "{\"ts\":\"$TS\",\"event\":\"agent-turn-complete\",\"agent_id\":\"$AGENT_ID\",\"thread_id\":\"$THREAD_ID\",\"backend\":\"codex\"}" >> "$LOG"

# Parse session+tab from AGENT_ID = host/session:tab (identical to emit-event).
HOST_PART="${AGENT_ID%%/*}"
REST="${AGENT_ID#*/}"
SESS_PART="${REST%%:*}"
TAB_PART="${REST#*:}"
STATUS_DIR="$INSTALL_DIR/status/mc-$SESS_PART"

# UTF-8-safe truncation: codex replies often contain multi-byte chars; `head -c`
# can split a codepoint and corrupt the JSON, so use a codepoint-safe Python slice.
SUMMARY=$(printf '%s' "$LAST_MSG" | tr '\n' ' ' | python3 -c "import sys; print(sys.stdin.read()[:1000], end='')" 2>/dev/null || printf '%s' "$LAST_MSG" | tr '\n' ' ' | cut -c1-1000)

# Write status file — SAME shape/location the /agents HUD reads.
mkdir -p "$STATUS_DIR"
jq -n \
  --arg agent "$TAB_PART" \
  --arg session "mc-$SESS_PART" \
  --arg ts "$TS" \
  --arg session_id "$THREAD_ID" \
  --arg summary "$SUMMARY" \
  --arg agent_id "$AGENT_ID" \
  --arg boss_id "${BOSS_ID:-}" \
  '{agent: $agent, session: $session, status: "idle", timestamp: $ts, session_id: $session_id, summary: $summary, agent_id: $agent_id, boss_id: $boss_id}' \
  > "$STATUS_DIR/$TAB_PART.json"

# If no boss, the status file is enough.
[ -z "${BOSS_ID:-}" ] && exit 0

# POST the SAME send task that emit-event's Stop branch posts.
NOTIF="[AGENT NOTIFICATION] $AGENT_ID finished: $SUMMARY"
BOSS_HOST="${BOSS_ID%%/*}"
IDEM=$(idem_key "stop" "$THREAD_ID" "$AGENT_ID" "$SUMMARY")
PAYLOAD=$(jq -n \
  --arg target_agent "$BOSS_ID" \
  --arg target_host "$BOSS_HOST" \
  --arg msg "$NOTIF" \
  --arg idem "$IDEM" \
  '{action: "send", target_agent: $target_agent, target_host: $target_host, idempotency_key: $idem, payload: {message: $msg}}')

curl -fsS -X POST "$QUEUE_URL/task/submit" \
  -H "Content-Type: application/json" \
  -H "X-Queue-Secret: $QUEUE_SECRET" \
  -d "$PAYLOAD" >/dev/null 2>&1 || true

exit 0
EOF
chmod +x "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/codex-notify"
```

### 7.5. Write the HUD dashboard HTML

**Why**: queue-server's `/dashboard` route serves this file with `__INJECT_SECRET__` replaced by the live `QUEUE_SECRET`. The page then polls `/agents` + `/clients` every 3s and renders rows. Each row has a "attach" link to ttyd with the correct `mc-<sess>:<tab>` target.

```bash
# [self-contained only] — the HUD is served by the upstream queue-server in JOIN-mode.
if [ -n "${UPSTREAM_QUEUE_URL:-}" ]; then
  echo "[JOIN] skipping local HUD dashboard (served by upstream $UPSTREAM_QUEUE_URL)"
else
cat > "$INSTALL_DIR/bin/dashboard.html" <<'HTML_EOF'
<!doctype html>
<html><head><meta charset="utf-8"><title>mypeople — HUD</title>
<style>
  body { font: 14px -apple-system,system-ui; margin: 24px; background: #f4f4f4; color: #111; }
  h1 { margin: 0 0 12px; font-size: 20px; }
  .meta { color: #666; font-size: 12px; margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; }
  th, td { padding: 8px 10px; border-bottom: 1px solid #eee; text-align: left; vertical-align: top; }
  th { background: #f6f6f6; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #666; }
  tr:last-child td { border-bottom: 0; }
  .alive { color: #1e6e2c; font-weight: 600; }
  .dead, .gone { color: #a52a2a; font-weight: 600; }
  code { background: #f1f1f1; padding: 1px 5px; border-radius: 3px; font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
  a { color: #1f6feb; text-decoration: none; font-weight: 600; }
  .summary { color: #444; }
  h2 { margin: 28px 0 10px; font-size: 15px; color: #333; }
  .cmd { font-family: ui-monospace, Menlo, monospace; font-size: 11px; color: #333; white-space: pre-wrap; word-break: break-all; max-width: 360px; display: inline-block; }
  .reason { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #8a5a00; font-weight: 600; }
  button.revive { background: #1e6e2c; color: #fff; border: 0; border-radius: 4px; padding: 5px 12px; font-weight: 600; cursor: pointer; font-size: 12px; }
  button.revive:hover { background: #18581f; }
  .noresume { display: inline-block; background: #fce8e6; color: #a52a2a; border: 1px solid #f0b3ad; border-radius: 4px; padding: 4px 9px; font-size: 11px; font-weight: 600; }
  .card-link { font-size: 11px; }
</style></head>
<body>
<h1>mypeople — HUD</h1>
<div class="meta">Refreshed: <span id="ts">never</span> · <span id="clients">? clients</span></div>
<table>
  <thead><tr><th>agent_id</th><th>state</th><th>backend</th><th>boss</th><th>summary</th><th>attach</th></tr></thead>
  <tbody id="rows"></tbody>
</table>

<h2>Retired engineers — revive to resume their session</h2>
<table>
  <thead><tr><th>agent_id</th><th>spawn command</th><th>card</th><th>why retired</th><th>when</th><th>revive</th></tr></thead>
  <tbody id="retired"></tbody>
</table>

<script>
const SECRET = "__INJECT_SECRET__";
function esc(s){ return (s||'').replace(/[<>&"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c])); }
async function getJson(path) {
  const r = await fetch(path, { headers: { 'X-Queue-Secret': SECRET } });
  return r.json();
}
// Revive ONE engineer (resume its session by id). One button = one agent — there is
// deliberately NO restore-all control. The server resumes by session-id only; if it
// can't, it returns an error we show inline (never a silent fresh spawn).
async function revive(agentId, btn) {
  btn.disabled = true; btn.textContent = 'reviving…';
  try {
    const r = await fetch('/task/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Queue-Secret': SECRET },
      body: JSON.stringify({ action: 'revive', target_agent: agentId })
    });
    const sub = await r.json();
    if (!sub.task_id) throw new Error(sub.error || 'submit failed');
    // poll the task to completion so we can surface a resume error on the row
    for (let i = 0; i < 70; i++) {
      await new Promise(res => setTimeout(res, 1000));
      const t = await getJson('/task/' + sub.task_id);
      if (t.status === 'done') { btn.textContent = 'resumed ✓'; break; }
      if (t.status === 'failed') { btn.outerHTML = '<span class="noresume">revive failed: ' + esc(t.error||'') + '</span>'; break; }
    }
  } catch (e) {
    btn.outerHTML = '<span class="noresume">' + esc(e.message) + '</span>';
  }
  refresh();
}
async function refresh() {
  try {
    const [a, c] = await Promise.all([getJson('/agents'), getJson('/clients')]);
    const clientMap = {};
    (c || []).forEach(cl => { clientMap[cl.hostname] = cl; });
    const localBase = `http://${location.hostname || '127.0.0.1'}:7681`;
    const rows = a.map(x => {
      const target = x.tmux_target || '';
      // Per-host attach: a cross-host/container agent uses the ttyd base its
      // own queue-client reports (its Tailscale address). Same-host agents
      // have no reported base → fall back to localhost:7681.
      const cl = clientMap[x.host];
      const base = (cl && cl.attach_base) ? cl.attach_base : localBase;
      const url = `${base}/?arg=-t&arg=${encodeURIComponent(target)}`;
      const safeSummary = (x.summary || '').replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])).slice(0, 120);
      return `<tr>
        <td><code>${x.agent_id}</code></td>
        <td class="${x.state}">${x.state||''}</td>
        <td>${x.backend||''}</td>
        <td><code>${x.boss_id||''}</code></td>
        <td class="summary">${safeSummary}</td>
        <td><a href="${url}" target="_blank">attach</a></td>
      </tr>`;
    }).join('');
    document.getElementById('rows').innerHTML = rows || '<tr><td colspan=6 style="color:#888">No active agents.</td></tr>';
    document.getElementById('clients').textContent = c.length + ' client' + (c.length === 1 ? '' : 's') + ' heartbeating';
    document.getElementById('ts').textContent = new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById('ts').textContent = 'ERROR: ' + e.message;
  }
  // Retired engineers — each with the exact spawn command + a per-engineer revive.
  try {
    const retired = await getJson('/roster');
    const rrows = (retired || []).map(x => {
      const when = (x.retired_ts || '').replace('T', ' ').replace('Z', '');
      const card = x.card_id
        ? `<code class="card-link">${esc(x.card_id)}</code>${x.card_title ? ' ' + esc(x.card_title) : ''}`
        : '<span style="color:#aaa">—</span>';
      const action = x.resumable
        ? `<button class="revive" onclick="revive('${esc(x.agent_id)}', this)">Revive</button>`
        : `<span class="noresume" title="${esc(x.resume_error)}">Not resumable — ${esc(x.resume_error)}</span>`;
      return `<tr>
        <td><code>${esc(x.agent_id)}</code></td>
        <td><span class="cmd">${esc(x.spawn_cmd)}</span></td>
        <td>${card}</td>
        <td><span class="reason">${esc(x.retire_reason)}</span></td>
        <td style="font-size:11px;color:#666">${esc(when)}</td>
        <td>${action}</td>
      </tr>`;
    }).join('');
    document.getElementById('retired').innerHTML = rrows || '<tr><td colspan=6 style="color:#888">No retired engineers.</td></tr>';
  } catch (e) {
    document.getElementById('retired').innerHTML = '<tr><td colspan=6 style="color:#a52a2a">roster error: ' + esc(e.message) + '</td></tr>';
  }
}
refresh();
setInterval(refresh, 3000);
</script>
</body></html>
HTML_EOF
chmod 644 "$INSTALL_DIR/bin/dashboard.html"
fi
```

### 7.6. Codex backend support (optional — for `--backend codex` agents)

**Why**: `mp spawn ... --backend codex` launches an OpenAI Codex CLI agent instead of Claude. The wiring needed for this is ALREADY in the artifacts written above — nothing extra is required at install time:

- **Turn-end → Boss notification**: the queue-client's codex exec branch launches codex with `-c notify=["bash","$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/codex-notify"]`, so notify is wired **per-spawn** — no global `~/.codex/config.toml` edit, and no risk of clobbering an existing `notify` the host already uses. `codex-notify` (written in Step 7) maps Codex's `agent-turn-complete` to the same `[AGENT NOTIFICATION] … finished: …` the Claude Stop hook posts.
- **Autonomy**: codex is launched with `--dangerously-bypass-approvals-and-sandbox` (the analog of Claude's `--dangerously-skip-permissions`).
- **Startup gates**: a fresh codex shows an "Update available" prompt and a directory-trust prompt before its composer. The codex readiness probe in `execute_spawn` **auto-dismisses both** (Skip / Yes) and waits up to 60s for the composer footer — so spawns don't hang on a gate even with no pre-seeded config.
- **TUI markers**: spawn/peek/send key off the per-backend `MARKERS` table (Codex composer glyph `›` U+203A, busy `esc to interrupt`, footer `<model> · <cwd>`). The Claude path is byte-identical (`markers_for("claude")` equals the original hardcoded strings; unknown backends fall back to claude).

**The one external prerequisite (NOT installed by this seed)**: the `codex` CLI must be present on PATH **and logged in** before a `--backend codex` agent can complete a turn. This seed does not install or authenticate codex.

```bash
# Optional pre-flight: report codex availability/auth. Does NOT install or log in
# codex (that is a host-owner decision — ChatGPT re-login or an OpenAI API key).
if command -v codex >/dev/null 2>&1; then
  echo "[codex] CLI present: $(codex --version 2>/dev/null || echo '?')"
  # `login status` only checks token PRESENCE, not validity — a stale/rotated
  # ChatGPT refresh token still reports "Logged in" yet fails turns with 401
  # token_expired. Treat a real turn as the only proof of working auth.
  codex login status 2>&1 | sed 's/^/[codex] /' || true
  echo "[codex] NOTE: --backend codex needs a VALID login. If turns 401, re-auth with"
  echo "[codex]   'codex login' (ChatGPT, interactive)  OR  'printenv OPENAI_API_KEY | codex login --with-api-key'."
else
  echo "[codex] CLI not installed — --backend claude works; --backend codex unavailable until 'codex' is installed + logged in."
fi
```

> **Optional global config (only if you prefer it over per-spawn `-c notify`)**: you may instead set `notify = ["bash","$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/codex-notify"]` in `~/.codex/config.toml`. `codex-notify` is gated on `$AGENT_ID`, so it is a harmless no-op for non-mypeople codex sessions. Do this only if the host has no other `notify` consumer to avoid clobbering it. The per-spawn wiring above is the default and needs no such edit.

### 8. Write `queue.env`

```bash
QUEUE_PORT="${QUEUE_PORT:-9900}"
HOST_ID="${HOST_ID:-$(hostname -s)}"
if [ -n "${UPSTREAM_QUEUE_URL:-}" ]; then
  # [JOIN] point QUEUE_URL at the upstream; reuse the upstream secret VERBATIM
  # (never auto-generate in JOIN-mode — a secret mismatch means every request
  # is 401). The secret is written only into this 0600 file, never echoed.
  if [ -z "${UPSTREAM_QUEUE_SECRET:-}" ]; then echo "BLOCKED_REASON=upstream_secret_not_set"; exit 1; fi
  QUEUE_URL_VAL="${UPSTREAM_QUEUE_URL%/}"
  SECRET="${UPSTREAM_QUEUE_SECRET}"
  TS_LINE=""
else
  # [self-contained] local central node; reuse existing local secret or auto-gen.
  if [ -s "$HOME/.config/mypeople/queue.env" ] && grep -q '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env"; then
    SECRET=$(grep '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env" | head -1 | cut -d= -f2-)
  else
    SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
  fi
  QUEUE_URL_VAL="http://127.0.0.1:${QUEUE_PORT}"
  TS_HOSTNAME="${TS_HOSTNAME:-mypeople-$(hostname -s)}"
  TS_LINE="TS_HOSTNAME=${TS_HOSTNAME}"
fi
cat > "$HOME/.config/mypeople/queue.env" <<EOF
QUEUE_URL=${QUEUE_URL_VAL}
QUEUE_SECRET=${SECRET}
QUEUE_PORT=${QUEUE_PORT}
QUEUE_HEARTBEAT=30
QUEUE_POLL_INTERVAL=1.0
HOST_ID=${HOST_ID}
INSTALL_DIR=${INSTALL_DIR:-$HOME/mypeople}
TTYD_PORT=${TTYD_PORT:-7681}
${TS_LINE}
# UTF-8 locale is REQUIRED. Hosts that default to POSIX (many Linux
# containers, some bare-metal Linux installs) cause tmux to collapse
# multi-byte UTF-8 chars (every glyph claude TUI uses — ●, ⏺, ✻, ⏵, ⎿,
# ❯, box-drawing — gets stripped to an ASCII underscore in tmux's internal buffer
# and that's what reaches the browser via ttyd). macOS defaults to
# UTF-8 already; setting these explicitly is harmless and makes the
# behavior portable.
LANG=C.UTF-8
LC_ALL=C.UTF-8
EOF
chmod 600 "$HOME/.config/mypeople/queue.env"
```

### 8.5. Bring this host onto the tailnet

**[JOIN] first**: a JOIN node does NOT claim its own `$TS_HOSTNAME` identity — it only needs to *reach* the upstream. Test `curl -fsS "$UPSTREAM_QUEUE_URL/health"`. If it returns 200, this host is already on the right network (already on the tailnet, or the upstream is LAN-reachable) → **SKIP the rest of this Step entirely** (`TS_AUTHKEY`/`TS_HOSTNAME` not needed). If it does NOT return 200 and `TS_AUTHKEY` is set, run `tailscale up` as below (hostname `$HOST_ID` is fine) to join the tailnet, then re-test `curl "$UPSTREAM_QUEUE_URL/health"`. If still unreachable, stop with `BLOCKED_REASON=upstream_unreachable`. The rest of this Step ([self-contained]) does not apply to JOIN nodes.

**[self-contained] Intent**: this host gets its own tailnet identity (`$TS_HOSTNAME`) and a tailscale IP. After this Step, `http://<TS_HOSTNAME>.<tailnet>.ts.net:9900/dashboard` will be reachable from any other tailnet node.

The mechanism varies by host:

- **macOS**: Tailscale runs as a system app (or the standalone CLI from `brew install tailscale`). If the GUI app is installed and the user is already signed in, this Step is a no-op. Otherwise, `sudo tailscale up --authkey=$TS_AUTHKEY --hostname=$TS_HOSTNAME --ssh=false --accept-routes=false`. No daemon to start manually — the app/service handles it.

- **Linux (systemd host)**: `tailscaled` is already managed by systemd after install. Just `sudo tailscale up --authkey=$TS_AUTHKEY --hostname=$TS_HOSTNAME --ssh=false --accept-routes=false`.

- **Linux (no systemd, e.g. sandboxed container)**: start `tailscaled` manually as a userland daemon with state files under `$INSTALL_DIR/run/tailscale-state/` (it needs `/dev/net/tun` + `NET_ADMIN` — see Step 1 prereq). Then `tailscale up` with the same flags, pointing at the custom socket via `--socket=<path>`. Sample (Linux-no-systemd):
  ```bash
  TS_STATE_DIR="$INSTALL_DIR/run/tailscale-state"
  sudo mkdir -p "$TS_STATE_DIR"
  sudo nohup tailscaled \
    --state="$TS_STATE_DIR/tailscaled.state" \
    --socket="$TS_STATE_DIR/tailscaled.sock" \
    > "$INSTALL_DIR/run/tailscaled.log" 2>&1 &
  echo $! | sudo tee "$INSTALL_DIR/run/tailscaled.pid" >/dev/null
  # wait up to 15s for socket, then:
  sudo tailscale --socket="$TS_STATE_DIR/tailscaled.sock" up \
    --authkey="$TS_AUTHKEY" --hostname="$TS_HOSTNAME" \
    --ssh=false --accept-routes=false
  ```

`$TS_AUTHKEY` is required **in self-contained mode**. If unset there, stop with `BLOCKED_REASON=ts_authkey_not_set`. (In JOIN-mode it's only consulted via the **[JOIN] first** path above.)

**Verify by intent**: `tailscale status --json` reports `.Self.Online == true` and `.Self.HostName == $TS_HOSTNAME`; `tailscale ip -4` returns a `100.x.x.x` address. Stop with `BLOCKED_REASON=tailscale_no_ipv4_assigned` if not.

### 9. Start daemons

```bash
set -a; . "$HOME/.config/mypeople/queue.env"; set +a

# Determine the ttyd port and the tailnet-reachable attach URL BEFORE starting
# the queue-client, so the client advertises a WORKING attach_base in its very
# first heartbeat. The HUD builds each agent's attach link from the OWNING
# client's attach_base; without this a cross-host/JOIN node's link falls back to
# the HUD host's own localhost ttyd → dead link from any other machine.
TTYD_PORT="${TTYD_PORT:-7681}"
# A FOREIGN ttyd / web-terminal may already hold this port (common on shared
# hosts and multi-node JOIN setups). Binding a busy port makes ttyd exit
# immediately, and a port-only health check would be FOOLED by the foreign
# listener answering on it. Pick the first FREE port at/above the requested one.
port_busy() { python3 -c 'import socket,sys; s=socket.socket(); r=s.connect_ex(("127.0.0.1",int(sys.argv[1]))); s.close(); sys.exit(0 if r==0 else 1)' "$1"; }
while port_busy "$TTYD_PORT"; do
  echo "ttyd: port $TTYD_PORT already in use (foreign listener) — trying $((TTYD_PORT+1))"
  TTYD_PORT=$((TTYD_PORT+1))
done
if grep -q '^TTYD_PORT=' "$HOME/.config/mypeople/queue.env"; then
  sed -i.bak "s/^TTYD_PORT=.*/TTYD_PORT=${TTYD_PORT}/" "$HOME/.config/mypeople/queue.env" && rm -f "$HOME/.config/mypeople/queue.env.bak"
else
  echo "TTYD_PORT=${TTYD_PORT}" >> "$HOME/.config/mypeople/queue.env"
fi
# Advertise the node's TAILNET-reachable ttyd so the HUD emits an attach link
# that works from any tailnet browser (not localhost). If the node isn't on a
# tailnet, leave it empty (HUD falls back to the HUD-host localhost — fine for a
# single self-contained node).
TS_IP4="$(tailscale ip -4 2>/dev/null | head -1)"
# Prefer the tailnet IP (reachable from any tailnet browser). If this node is NOT
# on a tailnet (e.g. a JOIN node reaching the upstream over plain LAN — proven on
# a Raspberry Pi joined by LAN, no tailscale up), fall back to the node's LAN IP so
# the HUD still emits a WORKING attach link for browsers on the same LAN. Only an
# empty attach_base (the old behavior) makes the HUD fall back to the HUD-host's own
# localhost → a dead link for every agent that lives on a different host.
ATTACH_IP4="$TS_IP4"
if [ -z "$ATTACH_IP4" ]; then
  ATTACH_IP4="$( (hostname -I 2>/dev/null | awk '{print $1}') || true )"
  [ -z "$ATTACH_IP4" ] && ATTACH_IP4="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [ -n "$ATTACH_IP4" ]; then
  TTYD_PUBLIC_URL="http://${ATTACH_IP4}:${TTYD_PORT}"
  if grep -q '^TTYD_PUBLIC_URL=' "$HOME/.config/mypeople/queue.env"; then
    sed -i.bak "s#^TTYD_PUBLIC_URL=.*#TTYD_PUBLIC_URL=${TTYD_PUBLIC_URL}#" "$HOME/.config/mypeople/queue.env" && rm -f "$HOME/.config/mypeople/queue.env.bak"
  else
    echo "TTYD_PUBLIC_URL=${TTYD_PUBLIC_URL}" >> "$HOME/.config/mypeople/queue.env"
  fi
  echo "ttyd attach advertised at $TTYD_PUBLIC_URL${TS_IP4:+ (tailnet)}${TS_IP4:- (LAN fallback — no tailnet on this node)}"
fi
# Re-source so the queue-client inherits the final TTYD_PORT + TTYD_PUBLIC_URL.
set -a; . "$HOME/.config/mypeople/queue.env"; set +a

if [ -z "${UPSTREAM_QUEUE_URL:-}" ]; then
  # [self-contained] start the local queue-server and wait for its health.
  nohup python3 -u "$INSTALL_DIR/bin/queue-server.py" > "$INSTALL_DIR/run/queue-server.log" 2>&1 &
  echo $! > "$INSTALL_DIR/run/queue-server.pid"
  for i in $(seq 1 25); do
    curl -fsS "http://127.0.0.1:${QUEUE_PORT}/health" >/dev/null 2>&1 && break
    sleep 0.2
  done
else
  # [JOIN] no local queue-server — confirm the UPSTREAM is reachable AND accepts
  # our secret BEFORE starting the client (fail fast with a clear reason).
  curl -fsS "${QUEUE_URL}/health" | grep -q '"status"' || { echo "BLOCKED_REASON=upstream_unreachable"; exit 1; }
  curl -fsS -H "X-Queue-Secret: ${QUEUE_SECRET}" "${QUEUE_URL}/clients" >/dev/null 2>&1 || { echo "BLOCKED_REASON=upstream_secret_rejected"; exit 1; }
fi
# Both modes: queue-client heartbeats to QUEUE_URL (local in self-contained,
# upstream in JOIN), registering this host as a client.
nohup python3 -u "$INSTALL_DIR/bin/queue-client.py" > "$INSTALL_DIR/run/queue-client.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/queue-client.pid"

# ttyd: per-tab browser-attach (port already chosen + advertised above).
#   -W = writable so the browser user can type.
#   -a = allow URL args (?arg=-t&arg=mc-X:Y) — MANDATORY for per-tab attach;
#        without it the link is ignored and the user lands in a default session.
#   -t fontFamily/fontSize = xterm.js glyph support (❯ ● ✻ …).
#   -t disableLeaveAlert=true = kill the browser tab-close prompt (the tmux
#        session persists across detach, so dropping the ttyd client loses no work).
nohup ttyd -W -a -p "$TTYD_PORT" \
  -t 'fontFamily=Menlo, Monaco, "Cascadia Mono", "Fira Code", "Courier New", monospace' \
  -t 'fontSize=13' \
  -t 'disableLeaveAlert=true' \
  tmux attach > "$INSTALL_DIR/run/ttyd.log" 2>&1 &
TTYD_PID=$!
echo "$TTYD_PID" > "$INSTALL_DIR/run/ttyd.pid"
for i in $(seq 1 25); do
  curl -fsS -o /dev/null "http://127.0.0.1:${TTYD_PORT}/" && break
  sleep 0.2
done
# Assert OUR ttyd actually bound (the PID we launched is still alive) — not a
# foreign listener masquerading on the port. Catches the silent bind failure.
sleep 0.3
ps -p "$TTYD_PID" >/dev/null 2>&1 || { echo "BLOCKED_REASON=ttyd_failed_to_bind (port ${TTYD_PORT}); check $INSTALL_DIR/run/ttyd.log"; exit 1; }
```

### 9.5. Install + start the TODO app (Priorities board) [self-contained]

The CEO's done-condition: a one-shot install brings up a COMPLETE self-contained
mypeople = comms + HUD + **TODO app**. The board (todo-server.py + todos.html) is
inlined here byte-exact (base64, identical bytes to `todo.seed.md`). It LISTENS on
its own port **9933** (the `todo-server.py` listen port env is the confusingly-named
`QUEUE_PORT`; do NOT give it 9900 or it collides with the queue-server) and TALKS to
the queue at `QUEUE_URL` (9900) using the same `QUEUE_SECRET`, so card comments route
to the Boss via `mp send` and `/todo/attach` resolves ttyd `attach_base`. The
WhatsApp/tailscale-serve digest (slice e) is intentionally NOT started here — it
needs a Hermes last-hop and must never break the clean one-shot; it is opt-in.

```bash
set -a; . "$HOME/.config/mypeople/queue.env"; set +a   # QUEUE_SECRET, QUEUE_PORT(9900), INSTALL_DIR
export INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
export TODO_DIR="$INSTALL_DIR/todos"
mkdir -p "$INSTALL_DIR/bin" "$TODO_DIR/proofs"
command -v python3 >/dev/null || { echo "BLOCKED_REASON=todo_needs_python3"; exit 1; }

# --- byte-exact app files (VERBATIM from todo.seed.md Step 1: base64 writes) ---
echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJ0b2RvIHNlcnZlciDigJQgdGhlIENFTydzIHByaW9yaXR5IGJvYXJkIGFzIHRoZSBCb3NzJ3Mgc291cmNlIG9mIHRydXRoLgoKU2xpY2U6IEFQSSArIHNoYXJlZCBzdG9yZSArIFBJTkcgU1RBVEUgTUFDSElORS4gRGVzaWduZWQgdG8gYmUgaW5saW5lZCAoaGVyZWRvYykKaW50byBzZWVkcy90b2RvLnNlZWQubWQgYW5kIHRvIHJ1biBlaXRoZXI6CiAgLSBzdGFuZGFsb25lIGluIGEgY2xlYW4gY29udGFpbmVyIChib3NzIHBpbmdzIGdvIHRvIGEgZmlsZSBzaW5rOyBUT0RPX1RFU1RfU0lOSz0xKSwgb3IKICAtIG9uIHRvcCBvZiBhIGxpdmUgbXlwZW9wbGUgcnVudGltZSAoYm9zcyBwaW5ncyBnbyB0aHJvdWdoIGBtcCBzZW5kIG1haW46Qm9zc2ApLgoKU3RvcmUgOiAkVE9ET19ESVIvYm9hcmQudjIuanNvbiAgIHByb29mczogJFRPRE9fRElSL3Byb29mcy88dGFza19pZD4vCkVudiAgIDogUVVFVUVfUE9SVCg5OTAwKSBRVUVVRV9TRUNSRVQoJycpIFRPRE9fRElSKH4vbXlwZW9wbGUvdG9kb3MpCiAgICAgICAgUElOR19DUk9OX1NFQyg2MCkgSURMRV9HUkFDRV9TRUMoNjApIFRPRE9fSFRNTCg8ZGlyPi90b2Rvcy5odG1sKQogICAgICAgIFRPRE9fVEVTVF9TSU5LKDApICBCT1NTX0FHRU5UKG1haW46Qm9zcykgIFFVRVVFX1VSTChodHRwOi8vMTI3LjAuMC4xOjk5MDApCiAgICAgICAgKFFVRVVFX1VSTCA9IHRoZSBteXBlb3BsZSBxdWV1ZS1zZXJ2ZXIsIHF1ZXJpZWQgZm9yIHR0eWQgYXR0YWNoX2Jhc2UgaW4gL3RvZG8vYXR0YWNoKQogICAgICAgIFdoYXRzQXBwIGRyYWluIChzbGljZSBlKTogV0FfRFJBSU4oMSkgV0FfQ0hBVF9KSUQoQ0VPIEpJRCkgV0FfU0VORF9DTUQoSGVybWVzIGxhc3QgaG9wLAogICAgICAgIHJlYWRzIHtjaGF0SWQsbWVzc2FnZX0gb24gc3RkaW4pIFdBX0JPQVJEX1VSTCgnJykgV0FfV0FUQ0hET0dfU0VDKDE4MCkgV0FfRFJBSU5fU0VDKDEwKSBXQV9SRVBJTkdfU0VDKDkwMCkKIiIiCmltcG9ydCBodHRwLnNlcnZlciwganNvbiwgb3MsIHRocmVhZGluZywgdGltZSwgdXVpZCwgYmFzZTY0LCBzdWJwcm9jZXNzLCBzaHV0aWwsIGRhdGV0aW1lLCB1cmxsaWIucmVxdWVzdApmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKZnJvbSB1cmxsaWIucGFyc2UgaW1wb3J0IHVybHBhcnNlLCBwYXJzZV9xcwoKUE9SVCAgICAgICAgPSBpbnQob3MuZW52aXJvbi5nZXQoIlFVRVVFX1BPUlQiLCAiOTkwMCIpKQpTRUNSRVQgICAgICA9IG9zLmVudmlyb24uZ2V0KCJRVUVVRV9TRUNSRVQiLCAiIikKVE9ET19ESVIgICAgPSBQYXRoKG9zLmVudmlyb24uZ2V0KCJUT0RPX0RJUiIsIHN0cihQYXRoKF9fZmlsZV9fKS5yZXNvbHZlKCkucGFyZW50IC8gImRhdGEiKSkpICAjIGR1cmFibGUsIGJlc2lkZSB0aGUgc2VydmVyIChOT1QgL3RtcCkKUFJPT0ZfRElSICAgPSBUT0RPX0RJUiAvICJwcm9vZnMiCkJPQVJEX1BBVEggID0gVE9ET19ESVIgLyAiYm9hcmQudjIuanNvbiIKSU5CT1hfTE9HICAgPSBUT0RPX0RJUiAvICJib3NzLWluYm94LmxvZyIKUElOR19DUk9OICAgPSBmbG9hdChvcy5lbnZpcm9uLmdldCgiUElOR19DUk9OX1NFQyIsICIxMjAiKSkgICAjIHVuYXNzaWduZWQtY2FyZCBjcm9uIChDRU86IDIgbWluKQpJRExFX0dSQUNFICA9IGZsb2F0KG9zLmVudmlyb24uZ2V0KCJJRExFX0dSQUNFX1NFQyIsICI2MCIpKSAgICAjIGFzc2lnbmVkIGlkbGUtcG9zdC1zdG9wLWhvb2sgKDEgbWluKQpJRExFX1NUQUxMICA9IGZsb2F0KG9zLmVudmlyb24uZ2V0KCJJRExFX1NUQUxMX1NFQyIsICIxODAiKSkgICAjIGFzc2lnbmVkLWJ1dC1pZGxlIFdBVENIRE9HIHRocmVzaG9sZCAoMyBtaW4pClNUQUxMX1JFUElORz0gZmxvYXQob3MuZW52aXJvbi5nZXQoIlNUQUxMX1JFUElOR19TRUMiLCAiMzAwIikpICMgcmUtcGluZyB0aHJvdHRsZSBwZXIgc3RhbGxlZCBjYXJkCldBVENIRE9HICAgID0gZmxvYXQob3MuZW52aXJvbi5nZXQoIldBVENIRE9HX1NFQyIsICI2MCIpKSAgICAgICMgd2F0Y2hkb2cgc2NhbiBpbnRlcnZhbApTVEFUVVNfRElSICA9IFBhdGgob3MuZW52aXJvbi5nZXQoIlNUQVRVU19ESVIiLCBzdHIoUGF0aC5ob21lKCkgLyAibXlwZW9wbGUiIC8gInN0YXR1cyIpKSkKUFJPSkVDVFNfRElSPSBQYXRoKG9zLmVudmlyb24uZ2V0KCJQUk9KRUNUU19ESVIiLCBzdHIoUGF0aC5ob21lKCkgLyAiLmNsYXVkZSIgLyAicHJvamVjdHMiKSkpCkJVU1lfQ1BVICAgID0gZmxvYXQob3MuZW52aXJvbi5nZXQoIkJVU1lfQ1BVX1BDVCIsICIyMCIpKSAgICAgICMgd2F0Y2hkb2c6IHByb2Nlc3MtdHJlZSBDUFUlIGFib3ZlIHRoaXMgPT0gYnVzeSAobG9uZyBqb2IpCkJVU1lfTkFNRVMgID0gc2V0KG4uc3RyaXAoKSBmb3IgbiBpbiBvcy5lbnZpcm9uLmdldCgiQlVTWV9OQU1FUyIsCiAgICAiZmZtcGVnLGRvY2tlcixidWlsZGtpdGQsY29udGFpbmVyZCxyc3luYyxzY3Asc3NoLHNmdHAsd2dldCxjdXJsLGdpdCxtYWtlLGNtYWtlLG5pbmphLGNhcmdvLHJ1c3RjLCIKICAgICJnY2MsY2MsY2xhbmcsbGQsY29sbGVjdDIsdHNjLHdlYnBhY2ssdml0ZSxlc2J1aWxkLHJvbGx1cCxuZXh0LHZlcmNlbCxidW4sc294LHdoaXNwZXIiKS5zcGxpdCgiLCIpIGlmIG4uc3RyaXAoKSkKVEVTVF9TSU5LICAgPSBvcy5lbnZpcm9uLmdldCgiVE9ET19URVNUX1NJTksiLCAiMCIpID09ICIxIgpCT1NTX0FHRU5UICA9IG9zLmVudmlyb24uZ2V0KCJCT1NTX0FHRU5UIiwgIm1haW46Qm9zcyIpCkhUTUxfUEFUSCAgID0gUGF0aChvcy5lbnZpcm9uLmdldCgiVE9ET19IVE1MIiwgc3RyKFBhdGgoX19maWxlX18pLnJlc29sdmUoKS5wYXJlbnQgLyAidG9kb3MuaHRtbCIpKSkKUVVFVUVfVVJMICAgPSBvcy5lbnZpcm9uLmdldCgiUVVFVUVfVVJMIiwgImh0dHA6Ly8xMjcuMC4wLjE6OTkwMCIpLnJzdHJpcCgiLyIpICAjIHRoZSBteXBlb3BsZSBxdWV1ZS1zZXJ2ZXIgKGZvciAvY2xpZW50cyBhdHRhY2hfYmFzZTsgc2xpY2UgYykKIyDilIDilIAgV2hhdHNBcHAgbGFzdC1ob3AgZHJhaW4gKyBDRU8td2F0Y2hkb2cgKHNsaWNlIGUpIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAojIEEgJ3doYXRzYXBwJyBxdWV1ZSBwYXJ0aWNpcGFudC4gVGhlIENFTy13YXRjaGRvZyAoZXZlcnkgV0FfV0FUQ0hET0dfU0VDID0gNSBtaW4pIHNlbmRzIHRoZSBDRU8KIyBPTkUgY29uc29saWRhdGVkIERJR0VTVCBsaXN0aW5nIGV2ZXJ5IGNhcmQgYmxvY2tlZCBvbiBoaW0g4oCUIGdyb3VwZWQgcmV2aWV3LXBlbmRpbmcgLwojIGJyYWluc3Rvcm0tcGVuZGluZywgZWFjaCBsaW5lID0gY2FyZCB0aXRsZSArIGEgdGFwcGFibGUgZGVlcC1saW5rIHN0cmFpZ2h0IHRvIHRoYXQgY2FyZCDigJQgdmlhIHRoZQojIExBU1QgSE9QIChjb250YWluZXJpemVkIEhlcm1lcyAvc2VuZCB0byBoaXMgcGVyc29uYWwgSklEKS4gSXQgZmlyZXMgb25seSB3aGlsZSDiiaUxIGNhcmQgaXMgYmxvY2tlZCwKIyByZXBlYXRzIGV2ZXJ5IDUgbWluLCB1cGRhdGVzIGFzIGNhcmRzIGNsZWFyLCBhbmQgc3RvcHMgd2hlbiBub25lIHJlbWFpbi4gVGhlIHNlbmQgY29tbWFuZCBpcwojIGNvbmZpZ3VyYWJsZSBzbyB0aGUgc2VlZCB3b3JrcyB3aGVyZXZlciBIZXJtZXMgaXMgcmVhY2hhYmxlOyBXQV9EUkFJTj0wIGRpc2FibGVzIHRoZSBsYXN0IGhvcC4KV0FfT1VUQk9YICAgPSBUT0RPX0RJUiAvICJ3YS1vdXRib3guanNvbiIKV0FfQ0hBVF9KSUQgPSBvcy5lbnZpcm9uLmdldCgiV0FfQ0hBVF9KSUQiLCAiIikuc3RyaXAoKSAgICMgQ0VPIFdoYXRzQXBwIEpJRCDigJQgUkVRVUlSRUQgZm9yIHRoZSBkcmFpbjsgc2V0IHZpYSBlbnYvcGxpc3QuIE5FVkVSIGhhcmRjb2RlIGEgcGVyc29uYWwgbnVtYmVyIGluIHRoZSBwdWJsaXNoZWQgc2VlZCAocHJpdmFjeSkuIGUuZy4gPGRpZ2l0cz5Acy53aGF0c2FwcC5uZXQKV0FfRFJBSU5fT04gPSAob3MuZW52aXJvbi5nZXQoIldBX0RSQUlOIiwgIjEiKSA9PSAiMSIpIGFuZCBib29sKFdBX0NIQVRfSklEKSAgICMgbm8gdGFyZ2V0IEpJRCAtPiBkcmFpbiBzdGF5cyBvZmYKV0FfU0VORF9DTUQgPSBvcy5lbnZpcm9uLmdldCgiV0FfU0VORF9DTUQiLCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyByZWFkcyB7Y2hhdElkLG1lc3NhZ2V9IEpTT04gb24gc3RkaW4KICAgICdkb2NrZXIgZXhlYyAtaSBoZXJtZXMtd2EgY3VybCAtcyAtSCAiSG9zdDogMTI3LjAuMC4xIiAtSCAiQ29udGVudC1UeXBlOiBhcHBsaWNhdGlvbi9qc29uIiAnCiAgICAnLVggUE9TVCBodHRwOi8vMTI3LjAuMC4xOjMwMDAvc2VuZCAtZCBALScpCldBX0JPQVJEX1VSTD0gb3MuZW52aXJvbi5nZXQoIldBX0JPQVJEX1VSTCIsICIiKSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBib2FyZCBwYWdlIFVSTDsgZWFjaCBjYXJkIGxpbmUgbGlua3MgdG8gPFdBX0JPQVJEX1VSTD4jY2FyZC88aWQ+CldBX1dBVENIRE9HID0gZmxvYXQob3MuZW52aXJvbi5nZXQoIldBX1dBVENIRE9HX1NFQyIsICIzMDAiKSkgICAgICAgICAgICAgICAgIyBDRU8td2F0Y2hkb2c6IHNlbmQgdGhlIGRpZ2VzdCBldmVyeSA1IG1pbiB3aGlsZSDiiaUxIGNhcmQgaXMgYmxvY2tlZApXQV9EUkFJTl9TRUM9IGZsb2F0KG9zLmVudmlyb24uZ2V0KCJXQV9EUkFJTl9TRUMiLCAiMTAiKSkgICAgICAgICAgICAgICAgICAgICMgZHJhaW4gdGljawpXQV9SRVBJTkcgICA9IGZsb2F0KG9zLmVudmlyb24uZ2V0KCJXQV9SRVBJTkdfU0VDIiwgIjI3MCIpKSAgICAgICAgICAgICAgICAgIyBtaW4gaW50ZXJ2YWwgKHMpIGJldHdlZW4gZGlnZXN0cyDigJQganVzdCB1bmRlciB0aGUgNS1taW4gdGljayBzbyBlYWNoIHRpY2sgc2VuZHMsIGJ1dCBhIG11dGF0aW9uIG1pZC1pbnRlcnZhbCBjYW4ndCBhZGQgYW4gZXh0cmEgZGlnZXN0Cl93YV9sb2NrID0gdGhyZWFkaW5nLlJMb2NrKCkKClZBTElEX1NUQVRFUyA9IHsibmVlZHNfYnJhaW5zdG9ybSIsICJ3b3JraW5nIiwgInJldmlldyIsICJibG9ja2VkIiwgImRvbmUiLCAiY2FuY2VsbGVkIn0gICAjIENFTyBtb2RlbDogaW4tcHJvZ3Jlc3MgaXMgJ3dvcmtpbmcnOyAncmV2aWV3JyA9IGVuZ2luZWVyIGRvbmUgKyBCb3NzLXZlcmlmaWVkLCBhd2FpdGluZyBDRU8gc2lnbi1vZmYgKFJ1bGUgMjE6IG9ubHkgdGhlIENFTyBtYXJrcyBkb25lKTsgJ2NhbmNlbGxlZCcgPSB0ZXJtaW5hbCBzaWRlLWV4aXQgKENFTyBhYmFuZG9ucyB0aGUgdGFzayDigJQgYWxvbmdzaWRlICdkb25lJywgbmV2ZXIgd29ya2VkL3BpbmdlZCBhZ2FpbikKVEVSTUlOQUxfU1RBVEVTID0geyJkb25lIiwgImNhbmNlbGxlZCJ9ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyB0ZXJtaW5hbDogbm90IEFDVElWRSwgbmV2ZXIgZGlzcGF0Y2hlZC9waW5nZWQvaW4gdGhlIFdoYXRzQXBwIGRpZ2VzdApBQ1RJVkUgPSBsYW1iZGEgdDogdC5nZXQoIndvcmtUb0RvbmUiKSBhbmQgdC5nZXQoInN0YXRlIikgbm90IGluIFRFUk1JTkFMX1NUQVRFUwpfbG9jayA9IHRocmVhZGluZy5STG9jaygpCiMgcGVyLWFnZW50IGxhc3Qgc3RvcC1ob29rIHN0YXRlOiBhZ2VudF9pZCAtPiAiaWRsZSIgfCAid29ya2luZyIKX2hvb2tfc3RhdGUgPSB7fQoKZGVmIG5vdygpOiByZXR1cm4gaW50KHRpbWUudGltZSgpICogMTAwMCkKZGVmIHVpZCgpOiByZXR1cm4gdXVpZC51dWlkNCgpLmhleFs6MTJdCmRlZiBfYnVpbGRfc3RhbXAoKToKICAgICIiIkEgc3RhYmxlIGJ1aWxkIGlkID0gbXRpbWUgb2YgdGhlIHNlcnZlZCBIVE1MLiBDaGFuZ2VzIGV4YWN0bHkgb25jZSBwZXIgZGVwbG95LCBzbyBhbiBvcGVuCiAgICBib2FyZCByZWxvYWRzIGl0c2VsZiB3aGVuIGEgbmV3IHRvZG9zLmh0bWwgc2hpcHMgKG5vIG1hbnVhbCBoYXJkLXJlZnJlc2ggLyBzdGFsZS1KUyBidWdzKS4iIiIKICAgIHRyeTogcmV0dXJuIHN0cihpbnQoSFRNTF9QQVRILnN0YXQoKS5zdF9tdGltZSkpCiAgICBleGNlcHQgRXhjZXB0aW9uOiByZXR1cm4gIjAiCgpkZWYgX2RlZmF1bHRfYm9hcmQoKTogcmV0dXJuIHsidmVyc2lvbiI6ICJ2MiIsICJvcmRlciI6IFtdLCAidGFza3MiOiB7fX0KCmRlZiBsb2FkKCk6CiAgICB0cnk6CiAgICAgICAgYiA9IGpzb24ubG9hZHMoQk9BUkRfUEFUSC5yZWFkX3RleHQoKSkKICAgICAgICBpZiBub3QgaXNpbnN0YW5jZShiLCBkaWN0KSBvciBiLmdldCgidmVyc2lvbiIpICE9ICJ2MiI6IHJldHVybiBfZGVmYXVsdF9ib2FyZCgpCiAgICAgICAgYi5zZXRkZWZhdWx0KCJvcmRlciIsIFtdKTsgYi5zZXRkZWZhdWx0KCJ0YXNrcyIsIHt9KQogICAgICAgIGZvciB0IGluIGJbInRhc2tzIl0udmFsdWVzKCk6CiAgICAgICAgICAgIHQuc2V0ZGVmYXVsdCgiY29tbWVudHMiLCBbXSkgICAgICAgICAgICAgICAgICMgaXNzdWUtc3R5bGUgdGhyZWFkIChzbGljZSBiKQogICAgICAgICAgICB0LnNldGRlZmF1bHQoInF1ZXN0aW9ucyIsIFtdKSAgICAgICAgICAgICAgICAjIGJyYWluc3Rvcm0gZ2F0ZSAoc2xpY2UgZCkKICAgICAgICAgICAgdC5zZXRkZWZhdWx0KCJicmFpbnN0b3JtQXNrZWQiLCBGYWxzZSkKICAgICAgICByZXR1cm4gYgogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICByZXR1cm4gX2RlZmF1bHRfYm9hcmQoKQoKZGVmIHNhdmUoYik6CiAgICBUT0RPX0RJUi5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICB0bXAgPSBCT0FSRF9QQVRILndpdGhfc3VmZml4KCIudG1wIikKICAgIHRtcC53cml0ZV90ZXh0KGpzb24uZHVtcHMoYiwgaW5kZW50PTIpKTsgdG1wLnJlcGxhY2UoQk9BUkRfUEFUSCkKCmRlZiBfaW5nZXN0X2ZpbGUodGlkLCBwaWQsIHB0eXBlLCBzcmNwYXRoKToKICAgICIiIkNvcHkgYSByZWZlcmVuY2VkIGxvY2FsIGltYWdlL3ZpZGVvIGludG8gdGhlIHNlcnZlZCBwcm9vZiBzdG9yZTsgcmV0dXJuIGl0cyBVUkwgb3IgTm9uZS4iIiIKICAgIHNyYyA9IHNyY3BhdGhbNzpdIGlmIHNyY3BhdGguc3RhcnRzd2l0aCgiZmlsZTovLyIpIGVsc2Ugc3JjcGF0aAogICAgaWYgbm90IG9zLnBhdGguaXNmaWxlKHNyYyk6IHJldHVybiBOb25lCiAgICBiYXNlID0gb3MucGF0aC5iYXNlbmFtZShzcmMpCiAgICBleHQgPSBiYXNlLnJzcGxpdCgiLiIsIDEpWy0xXS5sb3dlcigpIGlmICIuIiBpbiBiYXNlIGVsc2UgKCJwbmciIGlmIHB0eXBlID09ICJpbWFnZSIgZWxzZSAibXA0IikKICAgIFBEID0gUFJPT0ZfRElSIC8gdGlkOyBQRC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICBkc3QgPSBQRCAvIGYie3BpZH0ue2V4dH0iCiAgICB0cnk6CiAgICAgICAgaWYgbm90IGRzdC5leGlzdHMoKTogc2h1dGlsLmNvcHlmaWxlKHNyYywgZHN0KQogICAgICAgIHJldHVybiBmIi90b2RvL3Byb29mL3t0aWR9L3twaWR9LntleHR9IgogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICByZXR1cm4gTm9uZQoKZGVmIG1pZ3JhdGVfcHJvb2ZzKGIpOgogICAgIiIiSW1hZ2UvdmlkZW8gcHJvb2ZzIHN0b3JlZCBhcyBhIGxvY2FsIHBhdGgvZmlsZTovLyAtPiBjb3B5IGludG8gdGhlIHN0b3JlICsgcmV3cml0ZSB0byBhIHNlcnZlZCBVUkwuIiIiCiAgICBjaGFuZ2VkID0gRmFsc2UKICAgIGZvciB0aWQsIHQgaW4gYi5nZXQoInRhc2tzIiwge30pLml0ZW1zKCk6CiAgICAgICAgZm9yIHByIGluIHQuZ2V0KCJwcm9vZnMiLCBbXSk6CiAgICAgICAgICAgIGlmIG5vdCBpc2luc3RhbmNlKHByLCBkaWN0KTogY29udGludWUgICAjIHRvbGVyYXRlIGxlZ2FjeS9tYWxmb3JtZWQgcHJvb2YgZW50cmllcyAoZS5nLiBhIGJhcmUgcGF0aCBzdHJpbmcpIOKAlCBuZXZlciBsZXQgb25lIGNyYXNoIHRoZSB3aG9sZSBib2FyZCBHRVQKICAgICAgICAgICAgaWYgcHIuZ2V0KCJ0eXBlIikgaW4gKCJpbWFnZSIsICJ2aWRlbyIpOgogICAgICAgICAgICAgICAgcmVmID0gcHIuZ2V0KCJyZWYiLCAiIikKICAgICAgICAgICAgICAgIGlmIHJlZiBhbmQgbm90IHJlZi5zdGFydHN3aXRoKCIvdG9kby9wcm9vZi8iKToKICAgICAgICAgICAgICAgICAgICB1cmwgPSBfaW5nZXN0X2ZpbGUodGlkLCBwclsiaWQiXSwgcHJbInR5cGUiXSwgcmVmKQogICAgICAgICAgICAgICAgICAgIGlmIHVybDogcHJbInJlZiJdID0gdXJsOyBjaGFuZ2VkID0gVHJ1ZQogICAgaWYgY2hhbmdlZDogc2F2ZShiKQogICAgcmV0dXJuIGIKCmRlZiBuZXdfdGFzayh0ZXh0KToKICAgIHJldHVybiB7ImlkIjogdWlkKCksICJ0ZXh0IjogdGV4dCBvciAiIiwgImRvbmVDb25kaXRpb24iOiAiIiwgImJyYWluc3Rvcm0iOiAiIiwKICAgICAgICAgICAgIndvcmtUb0RvbmUiOiBGYWxzZSwgImFzc2lnbmVlIjogTm9uZSwgInN0YXRlIjogIm5lZWRzX2JyYWluc3Rvcm0iLAogICAgICAgICAgICAidmVyaWZpZWQiOiBGYWxzZSwgImxhc3RTdGF0dXMiOiAiIiwgInByb29mcyI6IFtdLCAic3VicyI6IFtdLCAiY29tbWVudHMiOiBbXSwKICAgICAgICAgICAgInF1ZXN0aW9ucyI6IFtdLCAiYnJhaW5zdG9ybUFza2VkIjogRmFsc2UsICJ0ZXN0IjogRmFsc2UsCiAgICAgICAgICAgICJwYXJlbnQiOiBOb25lLCAiZGVwZW5kc09uIjogW10sICJoYXJkR2F0ZSI6IEZhbHNlLCAgICMgaXNzdWUgIzM6IHBhcmVudC9jaGlsZCBoaWVyYXJjaHkgKyAnYmxvY2tlZCBieScgZGVwcyArIG9wdGlvbmFsIHBlci1jYXJkIGhhcmQgZ2F0ZSAoT0ZGIGJ5IGRlZmF1bHQpCiAgICAgICAgICAgICJwaW5nc1RvQm9zcyI6IDAsICJhc3NpZ25lZEF0IjogTm9uZSwgImxhc3RTdG9wVHMiOiBOb25lLAogICAgICAgICAgICAiY3JlYXRlZCI6IG5vdygpLCAidXBkYXRlZCI6IG5vdygpfQoKIyDilIDilIAgc3VidGFza3MgKyBkZXBlbmRlbmNpZXMgKGlzc3VlICMzKSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKZGVmIF9jaGlsZHJlbihiLCB0aWQpOiAgICAgICAgICAgICAgICAgICAgICAjIHJlYWwgY2hpbGQgY2FyZHMgKHBhcmVudCA9PSB0aWQpCiAgICByZXR1cm4gW3ggZm9yIHggaW4gYlsidGFza3MiXS52YWx1ZXMoKSBpZiB4LmdldCgicGFyZW50IikgPT0gdGlkXQpkZWYgX2luY29tcGxldGVfY2hpbGRyZW4oYiwgdGlkKToKICAgIHJldHVybiBbYyBmb3IgYyBpbiBfY2hpbGRyZW4oYiwgdGlkKSBpZiBjLmdldCgic3RhdGUiKSBub3QgaW4gVEVSTUlOQUxfU1RBVEVTXQpkZWYgX3VubWV0X2RlcHMoYiwgdCk6ICAgICAgICAgICAgICAgICAgICAgICAjICdibG9ja2VkIGJ5JyBjYXJkcyBub3QgeWV0IGRvbmUvY2FuY2VsbGVkCiAgICBvdXQgPSBbXQogICAgZm9yIGRlcCBpbiAodC5nZXQoImRlcGVuZHNPbiIpIG9yIFtdKToKICAgICAgICBkMiA9IGJbInRhc2tzIl0uZ2V0KGRlcCkKICAgICAgICBpZiBkMiBhbmQgZDIuZ2V0KCJzdGF0ZSIpIG5vdCBpbiBURVJNSU5BTF9TVEFURVM6IG91dC5hcHBlbmQoZGVwKQogICAgcmV0dXJuIG91dApkZWYgX2NyZWF0ZXNfY3ljbGUoYiwgdGlkLCBwYXJlbnRfaWQpOiAgICAgICAjIHdvdWxkIHNldHRpbmcgdGlkLnBhcmVudD1wYXJlbnRfaWQgY3JlYXRlIGEgbG9vcD8KICAgIHNlZW4sIGN1ciA9IHNldCgpLCBwYXJlbnRfaWQKICAgIHdoaWxlIGN1cjoKICAgICAgICBpZiBjdXIgPT0gdGlkOiByZXR1cm4gVHJ1ZQogICAgICAgIGlmIGN1ciBpbiBzZWVuOiBicmVhawogICAgICAgIHNlZW4uYWRkKGN1cik7IGN1ciA9IChiWyJ0YXNrcyJdLmdldChjdXIpIG9yIHt9KS5nZXQoInBhcmVudCIpCiAgICByZXR1cm4gRmFsc2UKZGVmIHN0YXRlX2dhdGUoYiwgdCwgbmV3c3RhdGUpOgogICAgIiIiSXNzdWUgIzMgZ2F0ZXMuIFJldHVybnMgYW4gZXJyb3Igc3RyaW5nIHRvIGJsb2NrIHRoZSB0cmFuc2l0aW9uLCBvciBOb25lIHRvIGFsbG93LgogICAgLSBET05FIGlzIGJsb2NrZWQgd2hpbGUgYW55IHN1YnRhc2svZGVwZW5kZW5jeSBpcyBzdGlsbCBpbmNvbXBsZXRlIChDRU8ncyByZXF1ZXN0ZWQgZ3VhcmRyYWlsKS4KICAgIC0gV09SS0lORyBpcyBibG9ja2VkIG9ubHkgd2hlbiB0aGlzIGNhcmQncyBwZXItY2FyZCBoYXJkIGdhdGUgaXMgT04gYW5kIGEgcHJlcmVxIGlzIHVubWV0IChPRkYgYnkgZGVmYXVsdCkuIiIiCiAgICBpZiBuZXdzdGF0ZSA9PSAiZG9uZSI6CiAgICAgICAgaW5jLCB1biA9IF9pbmNvbXBsZXRlX2NoaWxkcmVuKGIsIHRbImlkIl0pLCBfdW5tZXRfZGVwcyhiLCB0KQogICAgICAgIGlmIGluYyBvciB1bjoKICAgICAgICAgICAgcGFydHMgPSBbXQogICAgICAgICAgICBpZiBpbmM6IHBhcnRzLmFwcGVuZChmIntsZW4oaW5jKX0gc3VidGFzayhzKSBub3QgZG9uZS9jYW5jZWxsZWQiKQogICAgICAgICAgICBpZiB1bjogIHBhcnRzLmFwcGVuZChmIntsZW4odW4pfSBkZXBlbmRlbmN5KGllcykgbm90IGRvbmUvY2FuY2VsbGVkIikKICAgICAgICAgICAgcmV0dXJuICJjYW5ub3QgbWFyayBET05FIOKAlCAiICsgIiBhbmQgIi5qb2luKHBhcnRzKSArICIgKGZpbmlzaCBvciBjYW5jZWwgdGhlbSBmaXJzdCkiCiAgICBpZiBuZXdzdGF0ZSA9PSAid29ya2luZyIgYW5kIHQuZ2V0KCJoYXJkR2F0ZSIpOgogICAgICAgIHVuID0gX3VubWV0X2RlcHMoYiwgdCkKICAgICAgICBpZiB1bjogcmV0dXJuIGYiaGFyZCBnYXRlIE9OIOKAlCBibG9ja2VkIGJ5IHtsZW4odW4pfSB1bmZpbmlzaGVkIHByZXJlcXVpc2l0ZShzKTsgZmluaXNoL2NhbmNlbCB0aGVtIG9yIHR1cm4gdGhlIGhhcmQgZ2F0ZSBvZmYiCiAgICByZXR1cm4gTm9uZQoKIyDilIDilIAgdGVzdC9kZW1vL3Byb29mIGNhcmQgRVhFTVBUSU9OIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAojIEFuIGVuZ2luZWVyJ3MgdGhyb3dhd2F5IGZpeHR1cmUgbXVzdCBOT1QgbnVkZ2UgdGhlIEJvc3MvQ0VPOiBhIGNhcmQgZmxhZ2dlZCB0ZXN0OnRydWUgT1Igd2hvc2UgdGl0bGUKIyBzdGFydHMgd2l0aCBbZGVtb10vW3Byb29mXS9bdGVzdF0gZmlyZXMgTk8gY3JlYXRlLXBpbmcsIGlzIHNraXBwZWQgYnkgdGhlIGNyb24gKyBicmFpbnN0b3JtLXRyaWFnZSArCiMgdGhlIGFzc2lnbmVkLWlkbGUgd2F0Y2hkb2csIGFuZCBuZXZlciBhcHBlYXJzIGluIHRoZSBDRU8gV2hhdHNBcHAgZGlnZXN0LiAoUmVhbCB3b3JrIGlzIG5ldmVyIHByZWZpeGVkCiMgdGhhdCB3YXksIHNvIHRoaXMgY2FuJ3Qgc2lsZW5jZSBhIGdlbnVpbmUgdGFzay4pCl9URVNUX1BSRUZJWEVTID0gKCJbZGVtb10iLCAiW3Byb29mXSIsICJbdGVzdF0iLCAiW2RlbW8gIiwgIltwcm9vZiAiLCAiW3Rlc3QgIikKZGVmIF9pc190ZXN0KHQpOgogICAgaWYgdC5nZXQoInRlc3QiKSBpcyBUcnVlOiByZXR1cm4gVHJ1ZQogICAgcmV0dXJuICh0LmdldCgidGV4dCIpIG9yICIiKS5sc3RyaXAoKS5sb3dlcigpLnN0YXJ0c3dpdGgoX1RFU1RfUFJFRklYRVMpCgojIOKUgOKUgCBCUkFJTlNUT1JNIEdBVEUgKHNsaWNlIGQpIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAojIEFuIHVuZGVyLXNwZWNpZmllZCBuZXcgdGFzayBjYW4ndCBiZSB3b3JrZWQgdW50aWwgaXQncyBiZWVuIGJyYWluc3Rvcm1lZDogdGhlIGJyYWluc3Rvcm0KIyB3b3JrZXIgKGJpbi90b2RvLWJyYWluc3Rvcm0pIGdlbmVyYXRlcyBjbGFyaWZ5aW5nIFFVRVNUSU9OUyAob2ZmaWNlLWhvdXJzIG1ldGhvZCwgdmlhIGhlYWRsZXNzCiMgY2xhdWRlKSBhbmQgcG9zdHMgdGhlbSBoZXJlOyB0aGV5IHN1cmZhY2UgaW4gdGhlIGNhcmQgQVMgcXVlc3Rpb25zIHRvIHRoZSBDRU87IHRoZSB0YXNrIHN0YXlzCiMgbmVlZHNfYnJhaW5zdG9ybSBhbmQgbm9uLXdvcmthYmxlIHVudGlsIGV2ZXJ5IHF1ZXN0aW9uIGlzIGFuc3dlcmVkOyB0aGUgcmVzb2x2ZWQgUSZBIGlzIGZvbGRlZAojIGludG8gdGhlIGR1cmFibGUgYnJhaW5zdG9ybSBhcnRpZmFjdC4gQSB0YXNrIHRoZSBnZW5lcmF0b3IganVkZ2VzIGFscmVhZHktY2xlYXIgZ2V0cyBaRVJPCiMgcXVlc3Rpb25zICsgYSBvbmUtbGluZSBicmFpbnN0b3JtIOKGkiBpbW1lZGlhdGVseSBwcm9tb3RhYmxlLiAoU2lsZW50LW5vLW9wIHN1cmZhY2luZyBhbHJlYWR5IHNoaXBzLikKZGVmIF91bmFuc3dlcmVkKHQpOgogICAgcmV0dXJuIFtxIGZvciBxIGluIHQuZ2V0KCJxdWVzdGlvbnMiLCBbXSkgaWYgbm90IChxLmdldCgiYW5zd2VyIikgb3IgIiIpLnN0cmlwKCldCgpkZWYgYnJhaW5zdG9ybV9yZWFkeSh0KToKICAgICIiIlRydWUgaWZmIHRoZSB0YXNrIGhhcyBjbGVhcmVkIHRoZSBnYXRlIGFuZCBtYXkgYmUgcHJvbW90ZWQgdG8gd29ya2luZy4iIiIKICAgIGlmIF91bmFuc3dlcmVkKHQpOiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIG9wZW4gcXVlc3Rpb25zIGJsb2NrIHRoZSBnYXRlCiAgICAgICAgcmV0dXJuIEZhbHNlCiAgICByZXR1cm4gYm9vbCgodC5nZXQoImJyYWluc3Rvcm0iKSBvciAiIikuc3RyaXAoKSkgb3IgYm9vbCh0LmdldCgicXVlc3Rpb25zIikpCgpkZWYgX2Fzc2VtYmxlX2FydGlmYWN0KHQpOgogICAgIiIiRm9sZCB0aGUgYW5zd2VyZWQgUSZBIGludG8gdGhlIGR1cmFibGUgYnJhaW5zdG9ybSBhcnRpZmFjdCAoaWRlbXBvdGVudC1pc2gpLiIiIgogICAgcXMgPSB0LmdldCgicXVlc3Rpb25zIiwgW10pCiAgICBpZiBub3QgcXM6IHJldHVybgogICAgbGluZXMgPSBbIiIsICLilIDilIAgY2xhcmlmaWNhdGlvbnMgKENFTykg4pSA4pSAIl0KICAgIGZvciBxIGluIHFzOgogICAgICAgIGxpbmVzLmFwcGVuZChmIlE6IHtxLmdldCgncScsJycpLnN0cmlwKCl9IikKICAgICAgICBsaW5lcy5hcHBlbmQoZiJBOiB7KHEuZ2V0KCdhbnN3ZXInKSBvciAnJykuc3RyaXAoKX0iKQogICAgYmxvY2sgPSAiXG4iLmpvaW4obGluZXMpCiAgICBiYXNlID0gKHQuZ2V0KCJicmFpbnN0b3JtIikgb3IgIiIpLnN0cmlwKCkKICAgIGlmICLilIDilIAgY2xhcmlmaWNhdGlvbnMgKENFTykg4pSA4pSAIiBpbiBiYXNlOiAgICAgICAgICAgICAjIHJlZnJlc2ggdGhlIGJsb2NrIHJhdGhlciB0aGFuIHN0YWNrIGNvcGllcwogICAgICAgIGJhc2UgPSBiYXNlLnNwbGl0KCLilIDilIAgY2xhcmlmaWNhdGlvbnMgKENFTykg4pSA4pSAIilbMF0ucnN0cmlwKCkKICAgICAgICBibG9jayA9ICJcbiIgKyBibG9jawogICAgdFsiYnJhaW5zdG9ybSJdID0gKGJhc2UgKyAiXG4iICsgYmxvY2spLnN0cmlwKCkgaWYgYmFzZSBlbHNlIGJsb2NrLnN0cmlwKCkKCiMg4pSA4pSAIGlzc3VlLXN0eWxlIHRocmVhZCAoc2xpY2UgYik6IGEgZHVyYWJsZSBwZXItdGFzayBjb21tZW50L2V2ZW50IHRpbWVsaW5lLiDilIDilIAKIyBFdmVyeSBtZWFuaW5nZnVsIHNpZ25hbCAoZW5naW5lZXIgc3RhdHVzLCBzdGF0ZSB0cmFuc2l0aW9uLCBicmFpbnN0b3JtIHNhdmUsIENFTy9BSSBjb21tZW50KQojIGlzIGFwcGVuZGVkIGFzIGFuIGltbXV0YWJsZSBldmVudCBzbyB0aGUgY2FyZCBzaG93cyB0aGUgRlVMTCBoaXN0b3J5LCBHaXRIdWItaXNzdWUgc3R5bGUg4oCUCiMgdW5saWtlIGxhc3RTdGF0dXMsIHdoaWNoIGlzIG92ZXJ3cml0dGVuLiBUaGUgY2FyZCBVSSBtZXJnZXMgdGhlc2Ugd2l0aCBwcm9vZnNbXSBieSB0cy4KIyAgIGtpbmQ6ICdjb21tZW50JyAoQ0VPL2VuZ2luZWVyIGZyZWUgdGV4dCkgfCAnc3RhdHVzJyAoZW5naW5lZXIgbGFzdFN0YXR1cykgfAojICAgICAgICAgJ3N0YXRlJyAoc3RhdGUgdHJhbnNpdGlvbikgfCAnYnJhaW5zdG9ybScgKGFydGlmYWN0IHNhdmVkL3VwZGF0ZWQpCmRlZiBhZGRfY29tbWVudCh0LCBib2R5LCBieSwga2luZD0iY29tbWVudCIpOgogICAgYm9keSA9IChib2R5IG9yICIiKS5zdHJpcCgpCiAgICBpZiBub3QgYm9keTogcmV0dXJuIE5vbmUKICAgIGMgPSB7ImlkIjogdWlkKCksICJraW5kIjoga2luZCwgImJvZHkiOiBib2R5LCAiYnkiOiBieSBvciAic3lzdGVtIiwgInRzIjogbm93KCl9CiAgICB0LnNldGRlZmF1bHQoImNvbW1lbnRzIiwgW10pLmFwcGVuZChjKQogICAgcmV0dXJuIGMKCiMg4pSA4pSAIEJvc3MgcGluZzogdGhlIE9OTFkgdGhpbmcgdGhlIHBpbmcgbWFjaGluZSBkb2VzLiBBbHdheXMgdGFyZ2V0cyB0aGUgQm9zcy4g4pSA4pSACmRlZiBib3NzX3BpbmcodGFza19pZCwgcmVhc29uKToKICAgIHdpdGggX2xvY2s6CiAgICAgICAgYiA9IGxvYWQoKQogICAgICAgIHQgPSBiWyJ0YXNrcyJdLmdldCh0YXNrX2lkKQogICAgICAgIGlmIG5vdCB0OiByZXR1cm4KICAgICAgICB0WyJwaW5nc1RvQm9zcyJdID0gdC5nZXQoInBpbmdzVG9Cb3NzIiwgMCkgKyAxCiAgICAgICAgdFsidXBkYXRlZCJdID0gbm93KCkKICAgICAgICBzYXZlKGIpCiAgICAgICAgIyBDT01QQUNUIGVudmVsb3BlICjiiaR+MjIwIGNoYXJzKS4gRW1iZWRkaW5nIHRoZSBGVUxMIGNhcmQgdGV4dCBoZXJlICh+MTUwMCBjaGFycykgbWFkZSB0aGUKICAgICAgICAjIGJyYWNrZXRlZC1wYXN0ZSBsYW5kIGFzIGEgbGFyZ2Ugc3R1Y2sgZHJhZnQgaW4gdGhlIEJvc3MncyBjb21wb3Nlcjogd2hlbiB0aGUgQm9zcyB3YXMgbWlkLXR1cm4KICAgICAgICAjIHRoZSBkZWxheWVkLUVudGVyIHdhcyBhYnNvcmJlZCBhbmQgdG11eF9zZW5kX3RleHQncyA4LXJldHJ5IHJlY292ZXJ5IGNvdWxkIG5vdCBzdWJtaXQgaXQsIHNvCiAgICAgICAgIyB0aGUgcGluZyB3YXMgYSBSRUFMIG5vbi1kZWxpdmVyeSAocmM9MSAiY29tcG9zZXIgc3RpbGwgaGVsZCBhIGRyYWZ0IikuIEEgc2hvcnQgbWVzc2FnZSBzdWJtaXRzLwogICAgICAgICMgcXVldWVzIGNsZWFubHkuIFRoZSBjYXJkIGlkIGlzIHRoZSBsb29rdXAga2V5OyB0aGUgdGl0bGUncyBmaXJzdCBsaW5lIGlzIGVub3VnaCBjb250ZXh0LgogICAgICAgIHRpdGxlID0gKHQuZ2V0KCJ0ZXh0IiwgIiIpLnNwbGl0bGluZXMoKVswXSBpZiB0LmdldCgidGV4dCIpIGVsc2UgIiIpWzo4MF0KICAgICAgICBtc2cgPSBmIlt0b2RvXSB0YXNrIHt0YXNrX2lkfSBcInt0aXRsZX1cIjoge3JlYXNvbn0uIHN0YXRlPXt0WydzdGF0ZSddfSBhc3NpZ25lZT17dFsnYXNzaWduZWUnXX0iCiAgICB0cnk6CiAgICAgICAgSU5CT1hfTE9HLnBhcmVudC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICAgICAgd2l0aCBJTkJPWF9MT0cub3BlbigiYSIpIGFzIGY6IGYud3JpdGUoZiJ7bm93KCl9IHttc2d9XG4iKQogICAgZXhjZXB0IEV4Y2VwdGlvbjogcGFzcwogICAgaWYgbm90IFRFU1RfU0lOSyBhbmQgc2h1dGlsLndoaWNoKCJtcCIpOgogICAgICAgIHRyeToKICAgICAgICAgICAgciA9IHN1YnByb2Nlc3MucnVuKFsibXAiLCAic2VuZCIsIEJPU1NfQUdFTlQsIG1zZ10sIGNhcHR1cmVfb3V0cHV0PVRydWUsIHRleHQ9VHJ1ZSwgdGltZW91dD0zMCkKICAgICAgICAgICAgd2l0aCBJTkJPWF9MT0cub3BlbigiYSIpIGFzIGY6CiAgICAgICAgICAgICAgICBmLndyaXRlKGYie25vdygpfSBNUF9TRU5EIC0+IHtCT1NTX0FHRU5UfSByYz17ci5yZXR1cm5jb2RlfSA6OiB7KHIuc3Rkb3V0IG9yIHIuc3RkZXJyKS5zdHJpcCgpWzoxNDBdfVxuIikKICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgICAgIHdpdGggSU5CT1hfTE9HLm9wZW4oImEiKSBhcyBmOiBmLndyaXRlKGYie25vdygpfSBNUF9TRU5EIEVSUk9SIHtlfVxuIikKCiMg4pSA4pSAIHBpbmcgbWFjaGluZSAoYSk6IGNyb24g4oCUIGFjdGl2ZSArIFVOQVNTSUdORUQgdGFza3MgcGluZyB0aGUgQm9zcyBldmVyeSBQSU5HX0NST04g4pSA4pSACmRlZiBjcm9uX2xvb3AoKToKICAgIHdoaWxlIFRydWU6CiAgICAgICAgdGltZS5zbGVlcChQSU5HX0NST04pCiAgICAgICAgZm9yIHRpZCBpbiBsaXN0KGxvYWQoKVsidGFza3MiXS5rZXlzKCkpOgogICAgICAgICAgICB0ID0gbG9hZCgpWyJ0YXNrcyJdLmdldCh0aWQpCiAgICAgICAgICAgIGlmIG5vdCB0IG9yIF9pc190ZXN0KHQpOiBjb250aW51ZSAgICAgICAgICAjIHRlc3QvZGVtby9wcm9vZiBmaXh0dXJlcyBuZXZlciBudWRnZSB0aGUgQm9zcwogICAgICAgICAgICAjIFRoZSBCb3NzIGNyb24gb25seSBjaGFzZXMgQUNUSVZFICh3b3JrLXRvLWRvbmUpICsgdW5hc3NpZ25lZCBXT1JLIHRvIGFzc2lnbitkaXNwYXRjaC4KICAgICAgICAgICAgIyBCcmFpbnN0b3JtLXRyaWFnZSBpcyBOT1QgYSByZXBlYXRlZCBCb3NzIG51ZGdlOiBhIGNhcmQgYmxvY2tlZCBvbiB0aGUgQ0VPIChyZXZpZXcgLyBibG9ja2VkIC8KICAgICAgICAgICAgIyBuZWVkc19icmFpbnN0b3JtLXdpdGgtcXVlc3Rpb25zKSBpcyBwaW5nZWQgdG8gdGhlIENFTydzIFdoYXRzQXBwIGJ5IHRoZSBDRU8td2F0Y2hkb2cgKHNsaWNlIGUpLAogICAgICAgICAgICAjIGFuZCBhIGZyZXNobHktY3JlYXRlZCBjYXJkIGdldHMgT05FIGNyZWF0ZS1waW5nLiBTbyB0aGVyZSdzIG5vIHJlcGVhdGVkIGluLWFwcCBicmFpbnN0b3JtIGNyb24uCiAgICAgICAgICAgIGlmIEFDVElWRSh0KSBhbmQgbm90IHQuZ2V0KCJhc3NpZ25lZSIpIGFuZCB0WyJzdGF0ZSJdIG5vdCBpbiAoImJsb2NrZWQiLCAicmV2aWV3Iik6CiAgICAgICAgICAgICAgICByZWFzb24gPSAibmVlZHMgYnJhaW5zdG9ybSIgaWYgdFsic3RhdGUiXSA9PSAibmVlZHNfYnJhaW5zdG9ybSIgZWxzZSAid29ya2luZyAmIHVuYXNzaWduZWQg4oCUIGFzc2lnbitkaXNwYXRjaCIKICAgICAgICAgICAgICAgIGJvc3NfcGluZyh0aWQsIGYiY3Jvbih1bmFzc2lnbmVkKToge3JlYXNvbn0iKQoKIyDilIDilIAgcGluZyBtYWNoaW5lIChiKTogaWRsZS1kcml2ZW4g4oCUIGZpcmVkIGJ5IHRoZSBBU1NJR05FRCBlbmdpbmVlcidzIHN0b3AgaG9vayDilIDilIAKZGVmIG9uX3N0b3BfaG9vayhhZ2VudF9pZCwgaG9va19zdGF0ZSk6CiAgICBfaG9va19zdGF0ZVthZ2VudF9pZF0gPSBob29rX3N0YXRlICAgICAgICAgICAjIGxhdGVzdCBzdGF0ZSB3aW5zCiAgICB0X2F0X2ZpcmUgPSBob29rX3N0YXRlCiAgICBkZWYgY2hlY2soKToKICAgICAgICBpZiBfaG9va19zdGF0ZS5nZXQoYWdlbnRfaWQpICE9ICJpZGxlIjogICMgcGlja2VkIHVwIHdvcmsgd2l0aGluIHRoZSBncmFjZSB3aW5kb3cKICAgICAgICAgICAgcmV0dXJuCiAgICAgICAgZm9yIHRpZCBpbiBsaXN0KGxvYWQoKVsidGFza3MiXS5rZXlzKCkpOgogICAgICAgICAgICB0ID0gbG9hZCgpWyJ0YXNrcyJdLmdldCh0aWQpCiAgICAgICAgICAgIGlmIHQgYW5kIEFDVElWRSh0KSBhbmQgdC5nZXQoImFzc2lnbmVlIikgPT0gYWdlbnRfaWQ6CiAgICAgICAgICAgICAgICBib3NzX3BpbmcodGlkLCBmImlkbGUge0lETEVfR1JBQ0V9cyBhZnRlciB7YWdlbnRfaWR9IHN0b3AtaG9vayDigJQgbm90IGRvbmUiKQogICAgd2l0aCBfbG9jazoKICAgICAgICBiID0gbG9hZCgpCiAgICAgICAgZm9yIHQgaW4gYlsidGFza3MiXS52YWx1ZXMoKToKICAgICAgICAgICAgaWYgdC5nZXQoImFzc2lnbmVlIikgPT0gYWdlbnRfaWQ6IHRbImxhc3RTdG9wVHMiXSA9IG5vdygpCiAgICAgICAgc2F2ZShiKQogICAgaWYgaG9va19zdGF0ZSA9PSAiaWRsZSI6CiAgICAgICAgdGhyZWFkaW5nLlRpbWVyKElETEVfR1JBQ0UsIGNoZWNrKS5zdGFydCgpCgojIOKUgOKUgCBwaW5nIG1hY2hpbmUgKGMpOiBBU1NJR05FRC1CVVQtSURMRSBXQVRDSERPRyDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKIyBSZWFsIGVuZ2luZWVycyBkb24ndCBQT1NUIC9ob29rL3N0b3AsIHNvIG1hY2hpbmUgKGIpIG9mdGVuIG5ldmVyIGZpcmVzLiBUaGlzCiMgd2F0Y2hkb2cgYWN0aXZlbHkgZGV0ZWN0cyBhbiBhc3NpZ25lZCBlbmdpbmVlciB0aGF0IGhhcyBnb25lIGlkbGUvc3RhbGxlZCBhdAojIGl0cyBwcm9tcHQgYW5kIHBpbmdzIHRoZSBCb3NzLiBTaWduYWwgKG15cGVvcGxlLW5hdGl2ZSk6CiMgICAqIHRoZSBhZ2VudCdzIHN0YXR1cy5qc29uIChzdGF0dXM9J2lkbGUnICsgJ3RpbWVzdGFtcCcgPSB3aGVuIGl0IGxhc3QgU1RPUFBFRCkKIyAgICogaXRzIENsYXVkZSBzZXNzaW9uIHRyYW5zY3JpcHQgbXRpbWUgKHN0aWxsIGJlaW5nIHdyaXR0ZW4gPT0gYnVzeSBpbiBhIHR1cm4pCiMgU3RhbGxlZCAgOj0gc3RvcHBlZCA+IElETEVfU1RBTEwgYWdvICBBTkQgIHRyYW5zY3JpcHQgbm90IHdyaXR0ZW4gaW4gSURMRV9TVEFMTAojICAgICAgICAgICAgIChzbyBhIGxvbmcgc2lsZW50IHJlbmRlciByZWFkcyBhcyBidXN5LCBub3QgaWRsZSDigJQgbm8gZmFsc2Ugc3RhbGwpLgojIFVua25vd24gYWdlbnQgKG5vIHN0YXR1cyBmaWxlKSAtPiB0cmVhdCBhcyBzdGFsbGVkIChlcnIgdG93YXJkIHBpbmdpbmcsIHBlciBDRU8pLgpkZWYgX2lzb19lcG9jaCh0cyk6CiAgICB0cnk6IHJldHVybiBkYXRldGltZS5kYXRldGltZS5mcm9taXNvZm9ybWF0KHRzLnJlcGxhY2UoIloiLCAiKzAwOjAwIikpLnRpbWVzdGFtcCgpCiAgICBleGNlcHQgRXhjZXB0aW9uOiByZXR1cm4gTm9uZQoKZGVmIF9zdGF0dXNfZm9yKGFnZW50X2lkKToKICAgIHRyeToKICAgICAgICBmb3IgcCBpbiBTVEFUVVNfRElSLmdsb2IoIiovKi5qc29uIik6CiAgICAgICAgICAgIHRyeTogZCA9IGpzb24ubG9hZHMocC5yZWFkX3RleHQoKSkKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogY29udGludWUKICAgICAgICAgICAgaWYgZC5nZXQoImFnZW50X2lkIikgPT0gYWdlbnRfaWQ6IHJldHVybiBkCiAgICBleGNlcHQgRXhjZXB0aW9uOiBwYXNzCiAgICByZXR1cm4gTm9uZQoKZGVmIF9zZXNzaW9uX2FjdGl2ZV93aXRoaW4oc2Vzc2lvbl9pZCwgd2luZG93KToKICAgIGlmIG5vdCBzZXNzaW9uX2lkOiByZXR1cm4gRmFsc2UKICAgIG5vd3QgPSB0aW1lLnRpbWUoKQogICAgdHJ5OgogICAgICAgIGZvciBwIGluIFBST0pFQ1RTX0RJUi5nbG9iKGYiKi97c2Vzc2lvbl9pZH0uanNvbmwiKToKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgaWYgbm93dCAtIHAuc3RhdCgpLnN0X210aW1lIDwgd2luZG93OiByZXR1cm4gVHJ1ZQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiBjb250aW51ZQogICAgZXhjZXB0IEV4Y2VwdGlvbjogcGFzcwogICAgcmV0dXJuIEZhbHNlCgojIFByb2Nlc3MtbGV2ZWwgImlzIHRoZSBlbmdpbmVlciBhY3R1YWxseSBydW5uaW5nIGEgbG9uZyBqb2I/IiDigJQgY292ZXJzIHRoZSBjYXNlIHdoZXJlIGEgbG9uZwojIGJhc2gvdG9vbCBjYWxsIChmZm1wZWcgcmVuZGVyLCBkb2NrZXIgYnVpbGQsIG5wbSBidWlsZCkgbWFrZXMgdGhlIHRyYW5zY3JpcHQgZ28gcXVpZXQgZm9yIG1pbnV0ZXMuCmRlZiBfcHJvY190YWJsZSgpOgogICAgIyBwaWQgLT4gKHBwaWQsIHBjcHUsIGNvbW0pCiAgICB0cnk6CiAgICAgICAgb3V0ID0gc3VicHJvY2Vzcy5ydW4oWyJwcyIsICItYXhvIiwgInBpZD0scHBpZD0scGNwdT0sY29tbT0iXSwgY2FwdHVyZV9vdXRwdXQ9VHJ1ZSwgdGV4dD1UcnVlLCB0aW1lb3V0PTUpLnN0ZG91dAogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICByZXR1cm4ge30KICAgIHRhYiA9IHt9CiAgICBmb3IgbG4gaW4gb3V0LnNwbGl0bGluZXMoKToKICAgICAgICBwID0gbG4uc3BsaXQoTm9uZSwgMykKICAgICAgICBpZiBsZW4ocCkgPCA0OiBjb250aW51ZQogICAgICAgIHRyeTogdGFiW2ludChwWzBdKV0gPSAoaW50KHBbMV0pLCBmbG9hdChwWzJdKSwgb3MucGF0aC5iYXNlbmFtZShwWzNdLnN0cmlwKCkpKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IGNvbnRpbnVlCiAgICByZXR1cm4gdGFiCgpkZWYgX2V0aW1lX3NlY3MocGlkKToKICAgICMgcG9ydGFibGUgKG1hY09TICsgTGludXgpOiBlbGFwc2VkIHNlY29uZHMgc2luY2UgYHBpZGAgc3RhcnRlZCwgZnJvbSBwcyBldGltZSAoW1tERC1dSEg6XU1NOlNTKQogICAgdHJ5OgogICAgICAgIG91dCA9IHN1YnByb2Nlc3MucnVuKFsicHMiLCAiLW8iLCAiZXRpbWU9IiwgIi1wIiwgc3RyKHBpZCldLCBjYXB0dXJlX291dHB1dD1UcnVlLCB0ZXh0PVRydWUsIHRpbWVvdXQ9NSkuc3Rkb3V0LnN0cmlwKCkKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcmV0dXJuIE5vbmUKICAgIGlmIG5vdCBvdXQ6IHJldHVybiBOb25lCiAgICBkYXlzID0gMAogICAgaWYgIi0iIGluIG91dDoKICAgICAgICBkLCBvdXQgPSBvdXQuc3BsaXQoIi0iLCAxKQogICAgICAgIHRyeTogZGF5cyA9IGludChkKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IHJldHVybiBOb25lCiAgICB0cnk6IHBhcnRzID0gW2ludCh4KSBmb3IgeCBpbiBvdXQuc3BsaXQoIjoiKV0KICAgIGV4Y2VwdCBFeGNlcHRpb246IHJldHVybiBOb25lCiAgICBpZiBsZW4ocGFydHMpID09IDM6ICAgaCwgbSwgcyA9IHBhcnRzCiAgICBlbGlmIGxlbihwYXJ0cykgPT0gMjogaCwgbSwgcyA9IDAsIHBhcnRzWzBdLCBwYXJ0c1sxXQogICAgZWxzZTogcmV0dXJuIE5vbmUKICAgIHJldHVybiBkYXlzICogODY0MDAgKyBoICogMzYwMCArIG0gKiA2MCArIHMKCmRlZiBfZGVzY2VuZGFudHMocHAsIHRhYik6CiAgICBraWRzID0ge30KICAgIGZvciBwaWQsIHYgaW4gdGFiLml0ZW1zKCk6IGtpZHMuc2V0ZGVmYXVsdCh2WzBdLCBbXSkuYXBwZW5kKHBpZCkKICAgIHNlZW4sIHN0YWNrID0gc2V0KCksIFtwcF0KICAgIHdoaWxlIHN0YWNrOgogICAgICAgIHggPSBzdGFjay5wb3AoKQogICAgICAgIGZvciBjIGluIGtpZHMuZ2V0KHgsIFtdKToKICAgICAgICAgICAgaWYgYyBub3QgaW4gc2Vlbjogc2Vlbi5hZGQoYyk7IHN0YWNrLmFwcGVuZChjKQogICAgcmV0dXJuIFtwIGZvciBwIGluIChzZWVuIHwge3BwfSkgaWYgcCBpbiB0YWJdCgpkZWYgX3Nlc3Npb25fYWdlKGFnZW50X2lkKToKICAgICIiIlNlY29uZHMgc2luY2UgdGhlIGFnZW50J3MgQ1VSUkVOVCBsaXZlIHNlc3Npb24gc3RhcnRlZCAoaXRzIGNsYXVkZSBwcm9jZXNzIGFnZSksIHNvIGEKICAgIHJlc3Bhd25lZCBhZ2VudCByZXVzaW5nIGEgbmFtZSBpc24ndCBqdWRnZWQgYnkgdGhlIGRlYWQgc2Vzc2lvbidzIHN0YWxlIHN0b3AtdGltZXN0YW1wLiIiIgogICAgcHAgPSBfcGFuZV9waWQoYWdlbnRfaWQpCiAgICBpZiBub3QgcHA6IHJldHVybiBOb25lCiAgICB0YWIgPSBfcHJvY190YWJsZSgpCiAgICBjbGF1ZGVfcGlkcyA9IFtwIGZvciBwIGluIF9kZXNjZW5kYW50cyhwcCwgdGFiKSBpZiB0YWIuZ2V0KHAsICgwLCAwLCAiIikpWzJdID09ICJjbGF1ZGUiXSBpZiBwcCBpbiB0YWIgZWxzZSBbXQogICAgYWdlcyA9IFthIGZvciBhIGluIChfZXRpbWVfc2VjcyhwKSBmb3IgcCBpbiAoY2xhdWRlX3BpZHMgb3IgW3BwXSkpIGlmIGEgaXMgbm90IE5vbmVdCiAgICByZXR1cm4gbWluKGFnZXMpIGlmIGFnZXMgZWxzZSBOb25lICAgICAgICAgICAgICAjIHlvdW5nZXN0IGNsYXVkZSA9IGN1cnJlbnQgc2Vzc2lvbjsgZWxzZSBwYW5lIHNoZWxsIGFnZQoKZGVmIF9wYW5lX3BpZChhZ2VudF9pZCk6CiAgICAiIiJ0bXV4IHBhbmUgcGlkIGZvciBhZ2VudCBob3N0L3Nlc3Npb246dGFiIC0+IHRtdXggc2Vzc2lvbiAnbWMtPHNlc3Npb24+Jywgd2luZG93ICc8dGFiPicuIiIiCiAgICB0cnk6IHNlc3MsIHRhYiA9IGFnZW50X2lkLnNwbGl0KCIvIiwgMSlbMV0uc3BsaXQoIjoiLCAxKQogICAgZXhjZXB0IEV4Y2VwdGlvbjogcmV0dXJuIE5vbmUKICAgIHRyeToKICAgICAgICByID0gc3VicHJvY2Vzcy5ydW4oWyJ0bXV4IiwgImxpc3QtcGFuZXMiLCAiLXMiLCAiLXQiLCAibWMtIiArIHNlc3MsICItRiIsICIje3dpbmRvd19uYW1lfVx0I3twYW5lX3BpZH0iXSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgY2FwdHVyZV9vdXRwdXQ9VHJ1ZSwgdGV4dD1UcnVlLCB0aW1lb3V0PTUpCiAgICAgICAgaWYgci5yZXR1cm5jb2RlICE9IDA6IHJldHVybiBOb25lCiAgICAgICAgZm9yIGxuIGluIHIuc3Rkb3V0LnNwbGl0bGluZXMoKToKICAgICAgICAgICAgdywgXywgcHAgPSBsbi5wYXJ0aXRpb24oIlx0IikKICAgICAgICAgICAgaWYgdyA9PSB0YWI6CiAgICAgICAgICAgICAgICB0cnk6IHJldHVybiBpbnQocHApCiAgICAgICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiByZXR1cm4gTm9uZQogICAgZXhjZXB0IEV4Y2VwdGlvbjogcmV0dXJuIE5vbmUKICAgIHJldHVybiBOb25lCgpkZWYgX2lnbm9yZWRfZm9yX2NwdShjb21tKToKICAgICMgdGhlIHBlcnNpc3RlbnQgTUNQL2Jyb3dzZXIgc3RhY2sgYnVybnMgQ1BVIHJlZ2FyZGxlc3Mgb2Ygd2hldGhlciB0aGUgYWdlbnQgaXMgd29ya2luZzsKICAgICMgaXQgbXVzdCBOT1QgY291bnQgYXMgImJ1c3kiLCBvciBhIHBhcmtlZCBhZ2VudCB3aXRoIGFuIG9wZW4gYnJvd3NlciB3b3VsZCBuZXZlciBiZSBmbGFnZ2VkLgogICAgYyA9IGNvbW0ubG93ZXIoKQogICAgcmV0dXJuIGFueShrIGluIGMgZm9yIGsgaW4gKCJjaHJvbWUiLCAibm9kZSIsICJjYWZmZWluYXRlIiwgIm1jcCIsICI5MjIyIiwgImdvb2dsZSIpKQoKZGVmIGFnZW50X2J1c3koYWdlbnRfaWQpOgogICAgIiIiVHJ1ZSBpZiB0aGUgYXNzaWduZWQgZW5naW5lZXIgaGFzIGFuIEFDVElWRSBsb25nLXJ1bm5pbmcgam9iIGluIGl0cyBwcm9jZXNzIHRyZWUuCiAgICBUd28gc2lnbmFsczogKDEpIGEgaGVhdnkgY29tbWFuZCBieSBOQU1FIChmZm1wZWcvZG9ja2VyL2J1aWxkIHRvb2xzIOKAlCB0aGUgZG9ja2VyL2ZmbXBlZyBDTEkKICAgIGNsaWVudCBzdGF5cyBhIHBhbmUgY2hpbGQgZm9yIHRoZSB3aG9sZSBqb2IsIE1DUC1pbW11bmUpOyAoMikgQ1BVIGJ1cm4gRVhDTFVESU5HIHRoZSBwZXJzaXN0ZW50CiAgICBNQ1AvYnJvd3NlciBzdGFjay4gUmV0dXJucyBGYWxzZSBpZiB0aGUgcGFuZSBjYW4ndCBiZSBsb2NhdGVkIChubyB0bXV4KSAtPiB0cmFuc2NyaXB0L3RpbWVzdGFtcCBkZWNpZGUuIiIiCiAgICBwcCA9IF9wYW5lX3BpZChhZ2VudF9pZCkKICAgIGlmIG5vdCBwcDogcmV0dXJuIEZhbHNlCiAgICB0YWIgPSBfcHJvY190YWJsZSgpCiAgICBub2RlcyA9IF9kZXNjZW5kYW50cyhwcCwgdGFiKQogICAgYnlfbmFtZSA9IGFueSh0YWJbcF1bMl0gaW4gQlVTWV9OQU1FUyBmb3IgcCBpbiBub2RlcykKICAgIGNwdSA9IHN1bSh0YWJbcF1bMV0gZm9yIHAgaW4gbm9kZXMgaWYgbm90IF9pZ25vcmVkX2Zvcl9jcHUodGFiW3BdWzJdKSkKICAgIGJ1c3kgPSBieV9uYW1lIG9yIGNwdSA+PSBCVVNZX0NQVQogICAgaWYgb3MuZW52aXJvbi5nZXQoIkRFQlVHX0JVU1kiKSA9PSAiMSI6CiAgICAgICAgbmFtZXMgPSBzb3J0ZWQoe3RhYltwXVsyXSBmb3IgcCBpbiBub2Rlc30pCiAgICAgICAgcHJpbnQoZiJbYnVzeV0ge2FnZW50X2lkfSBwYW5lPXtwcH0gY3B1KGV4Y2wtbWNwKT17Y3B1Oi4xZn0gYnlfbmFtZT17YnlfbmFtZX0gLT4ge2J1c3l9IDo6IHtuYW1lc30iLCBmbHVzaD1UcnVlKQogICAgcmV0dXJuIGJ1c3kKCiMgR3JvdW5kLXRydXRoIEJVU1kgc2lnbmFsIOKAlCB0aGUgU0FNRSBtYXJrZXIgYG1wIHBlZWtgIHVzZXMuIENsYXVkZSBDb2RlIEFORCBDb2RleCBwcmludAojICJlc2MgdG8gaW50ZXJydXB0IiBpbiB0aGUgVFVJIGZvb3RlciBPTkxZIHdoaWxlIGEgdHVybiBpcyBhY3RpdmVseSBydW5uaW5nIChDb2RleCB3cmFwcyBpdAojIGFzICIqIFdvcmtpbmcgKE5zICogZXNjIHRvIGludGVycnVwdCkiKS4gQSBkZWVwLXRoaW5raW5nIC8gbG9uZy10dXJuIGFnZW50IGJ1cm5zIH5ubyBDUFUgYW5kCiMgd3JpdGVzIH5ubyB0cmFuc2NyaXB0IG1pZC10dXJuLCBzbyB0aGUgQ1BVL3RyYW5zY3JpcHQgc2lnbmFscyBtaXNzIGl0IGFuZCB0aGUgd2F0Y2hkb2cgd291bGQKIyBmYWxzZWx5IG51ZGdlIGl0LiBUaGlzIHBhbmUgcmVhZCBpcyB0aGUgYXV0aG9yaXRhdGl2ZSAiaXMgYSB0dXJuIHJ1bm5pbmcgUklHSFQgTk9XPyIgY2hlY2suClBFRUtfQlVTWV9NQVJLRVIgPSAiZXNjIHRvIGludGVycnVwdCIKCmRlZiBhZ2VudF9wYW5lX2J1c3koYWdlbnRfaWQpOgogICAgIiIiVHJ1ZSBpZiB0aGUgYWdlbnQncyBsaXZlIHRtdXggcGFuZSBzaG93cyB0aGUgYnVzeSBtYXJrZXIgKGEgdHVybiBpcyBhY3RpdmVseSBydW5uaW5nKSwKICAgIGNsYXNzaWZpZWQgZXhhY3RseSBsaWtlIGBtcCBwZWVrYC9wZWVrX3N0YXRlOiBsYXN0IDE1IE5PTi1CTEFOSyBsaW5lcyBvZiB0aGUgZnJhbWUgY29udGFpbgogICAgJ2VzYyB0byBpbnRlcnJ1cHQnLiBSZXR1cm5zIEZhbHNlIGlmIHRoZSBwYW5lIGNhbid0IGJlIHJlYWQgKG5vIHRtdXgpIC0+IG90aGVyIHNpZ25hbHMgZGVjaWRlLiIiIgogICAgdHJ5OgogICAgICAgIHNlc3MsIHRhYiA9IGFnZW50X2lkLnNwbGl0KCIvIiwgMSlbMV0uc3BsaXQoIjoiLCAxKQogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICByZXR1cm4gRmFsc2UKICAgIHRyeToKICAgICAgICByID0gc3VicHJvY2Vzcy5ydW4oWyJ0bXV4IiwgImNhcHR1cmUtcGFuZSIsICItdCIsIGYibWMte3Nlc3N9Ont0YWJ9IiwgIi1wIiwgIi1TIiwgIi0yMDAiXSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgY2FwdHVyZV9vdXRwdXQ9VHJ1ZSwgdGV4dD1UcnVlLCB0aW1lb3V0PTUpCiAgICAgICAgaWYgci5yZXR1cm5jb2RlICE9IDA6IHJldHVybiBGYWxzZQogICAgICAgIHRhaWwgPSAiXG4iLmpvaW4oW2wgZm9yIGwgaW4gci5zdGRvdXQuc3BsaXRsaW5lcygpIGlmIGwuc3RyaXAoKV1bLTE1Ol0pLmxvd2VyKCkKICAgICAgICBidXN5ID0gUEVFS19CVVNZX01BUktFUiBpbiB0YWlsCiAgICAgICAgaWYgb3MuZW52aXJvbi5nZXQoIkRFQlVHX0JVU1kiKSA9PSAiMSI6CiAgICAgICAgICAgIHByaW50KGYiW3BhbmUtYnVzeV0ge2FnZW50X2lkfSBtYy17c2Vzc306e3RhYn0gbWFya2VyPXtidXN5fSIsIGZsdXNoPVRydWUpCiAgICAgICAgcmV0dXJuIGJ1c3kKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcmV0dXJuIEZhbHNlCgpkZWYgYXNzaWduZWVfaWRsZV9zZWNzKGFnZW50X2lkKToKICAgICIiIklkbGUgc2Vjb25kcyBpZiB0aGUgYXNzaWduZWQgYWdlbnQgbG9va3MgcGFya2VkL3N0YWxsZWQsIGVsc2UgTm9uZSAoYWN0aXZlL2dyYWNlL2J1c3ktam9iKS4KCiAgICBUaGUgbnVkZ2UgaXMgZ2F0ZWQgb24gdGhlIGFnZW50J3MgQUNUVUFMIHN0YXRlLCBuZXZlciBqdXN0IGVsYXBzZWQtdGltZTogYSB0dXJuIHJ1bm5pbmcgUklHSFQKICAgIE5PVyAoVFVJIGJ1c3kgbWFya2VyLCB0aGUgbXAtcGVlayBncm91bmQgdHJ1dGgpIGlzIEJVU1kgYW5kIGlzIG5ldmVyIG51ZGdlZCwgZXZlbiBpZiB0aGUKICAgIHN0b3AtaG9vayB0aW1lc3RhbXAgaXMgc3RhbGUgYW5kIHRoZSB0cmFuc2NyaXB0IGlzIHF1aWV0IChkZWVwLXRoaW5raW5nIGxvbmcgdHVybikuIE9ubHkgYQogICAgZ2VudWluZWx5IElETEUtYXQtcHJvbXB0IGFnZW50IHBhc3QgdGhlIHRocmVzaG9sZCBpcyByZXBvcnRlZCBhcyBzdGFsbGVkLiIiIgogICAgaWYgYWdlbnRfcGFuZV9idXN5KGFnZW50X2lkKTogcmV0dXJuIE5vbmUgICAgICAgICAgICAgICMgYSB0dXJuIGlzIGFjdGl2ZWx5IHJ1bm5pbmcgTk9XIC0+IEJVU1kgLT4gbmV2ZXIgYSBmYWxzZSBudWRnZQogICAgZCA9IF9zdGF0dXNfZm9yKGFnZW50X2lkKQogICAgaWYgbm90IGQ6IHJldHVybiBJRExFX1NUQUxMICsgMSAgICAgICAgICAgICAgICAgICAgICAgICAjIG5vIHN0YXR1cyAtPiBjYW4ndCBjb25maXJtIGFjdGl2ZSAtPiBzdGFsbGVkCiAgICBpZiBkLmdldCgic3RhdHVzIikgIT0gImlkbGUiOiByZXR1cm4gTm9uZSAgICAgICAgICAgICAgIyBleHBsaWNpdGx5IGJ1c3kKICAgIHQgPSBfaXNvX2Vwb2NoKGQuZ2V0KCJ0aW1lc3RhbXAiLCAiIikpCiAgICBpZGxlX2ZvciA9ICh0aW1lLnRpbWUoKSAtIHQpIGlmIHQgZWxzZSBJRExFX1NUQUxMICsgMQogICAgYWdlID0gX3Nlc3Npb25fYWdlKGFnZW50X2lkKSAgICAgICAgICAgICAgICAgICAgICAgICAgICMgcmVzcGF3bi1hd2FyZTogYSBmcmVzaGx5IHJlLXNwYXduZWQgYWdlbnQKICAgIGlmIGFnZSBpcyBub3QgTm9uZTogaWRsZV9mb3IgPSBtaW4oaWRsZV9mb3IsIGFnZSkgICAgICAjIGNhbid0IGhhdmUgYmVlbiBpZGxlIGxvbmdlciB0aGFuIGl0cyBsaXZlIHNlc3Npb24gZXhpc3RzCiAgICBpZiBpZGxlX2ZvciA8IElETEVfU1RBTEw6IHJldHVybiBOb25lICAgICAgICAgICAgICAgICAgIyByZWNlbnRseSBzdG9wcGVkL3Jlc3Bhd25lZCAtPiBncmFjZQogICAgaWYgX3Nlc3Npb25fYWN0aXZlX3dpdGhpbihkLmdldCgic2Vzc2lvbl9pZCIpLCBJRExFX1NUQUxMKTogcmV0dXJuIE5vbmUgICMgdHJhbnNjcmlwdCBtb3ZpbmcgLT4gYnVzeSB0dXJuCiAgICBpZiBhZ2VudF9idXN5KGFnZW50X2lkKTogcmV0dXJuIE5vbmUgICAgICAgICAgICAgICAgICAgIyBsb25nLXJ1bm5pbmcgam9iIGluIGl0cyBwcm9jZXNzIHRyZWUgLT4gYnVzeQogICAgcmV0dXJuIGlkbGVfZm9yCgpkZWYgd2F0Y2hkb2dfbG9vcCgpOgogICAgd2hpbGUgVHJ1ZToKICAgICAgICB0aW1lLnNsZWVwKFdBVENIRE9HKQogICAgICAgIGZvciB0aWQgaW4gbGlzdChsb2FkKCkuZ2V0KCJ0YXNrcyIsIHt9KS5rZXlzKCkpOgogICAgICAgICAgICBwaW5nID0gTm9uZQogICAgICAgICAgICAjICgxKSBGQVNUIHNuYXBzaG90IHVuZGVyIHRoZSBsb2NrOiByZWFkIE9OTFkgdGhlIGZldyBmaWVsZHMgd2UgbmVlZCwgdGhlbiBSRUxFQVNFIGl0LgogICAgICAgICAgICB3aXRoIF9sb2NrOgogICAgICAgICAgICAgICAgYiA9IGxvYWQoKTsgdCA9IGJbInRhc2tzIl0uZ2V0KHRpZCkKICAgICAgICAgICAgICAgIGlmIG5vdCB0IG9yIF9pc190ZXN0KHQpIG9yIG5vdCAodC5nZXQoIndvcmtUb0RvbmUiKSBhbmQgdC5nZXQoInN0YXRlIikgPT0gIndvcmtpbmciIGFuZCB0LmdldCgiYXNzaWduZWUiKSk6CiAgICAgICAgICAgICAgICAgICAgY29udGludWUgICAgICAgICAgIyB0ZXN0L2RlbW8gZml4dHVyZXMgbmV2ZXIgdHJpZ2dlciB0aGUgc3RhbGwgd2F0Y2hkb2cKICAgICAgICAgICAgICAgIGFzc2lnbmVlID0gdFsiYXNzaWduZWUiXQogICAgICAgICAgICAjICgyKSBTTE9XIGNoZWNrIE9VVFNJREUgdGhlIGxvY2suIGFzc2lnbmVlX2lkbGVfc2VjcygpIHJ1bnMgdG11eCBjYXB0dXJlLXBhbmUgLyBwcyAvIG1wCiAgICAgICAgICAgICMgICAgIHN1YnByb2Nlc3NlcyBwZXIgYWdlbnQg4oCUIGhvbGRpbmcgX2xvY2sgYWNyb3NzIHRoZW0gc2VyaWFsaXplcyBFVkVSWSAvdG9kby9ib2FyZCByZWFkCiAgICAgICAgICAgICMgICAgIGJlaGluZCB0aGUgd2F0Y2hkb2cgYW5kIGVtcHRpZXMgdGhlIGJvYXJkIChQMCBkZWFkbG9jaykuIE5FVkVSIGhvbGQgX2xvY2sgZHVyaW5nIGEKICAgICAgICAgICAgIyAgICAgc3VicHJvY2Vzcy5ydW4uIFRoZSBsb2NrIGlzIHJlYWNxdWlyZWQgYmVsb3cgb25seSB0byB3cml0ZSBzdGFsbFBpbmdUcyArIHNhdmUuCiAgICAgICAgICAgIGlkbGUgPSBhc3NpZ25lZV9pZGxlX3NlY3MoYXNzaWduZWUpCiAgICAgICAgICAgICMgKDMpIHJlYWNxdWlyZSB0aGUgbG9jayBPTkxZIHRvIHJlY29yZCB0aGUgcmVzdWx0IChmYXN0OiBpbi1tZW1vcnkgKyBzYXZlKS4KICAgICAgICAgICAgd2l0aCBfbG9jazoKICAgICAgICAgICAgICAgIGIgPSBsb2FkKCk7IHQgPSBiWyJ0YXNrcyJdLmdldCh0aWQpCiAgICAgICAgICAgICAgICAjIHJlLXZhbGlkYXRlIGFnYWluc3QgdGhlIGxpdmUgc3RvcmUgKHRoZSBjYXJkIG1heSBoYXZlIGNoYW5nZWQgd2hpbGUgdGhlIGxvY2sgd2FzIGZyZWUpCiAgICAgICAgICAgICAgICBpZiBub3QgdCBvciBfaXNfdGVzdCh0KSBvciBub3QgKHQuZ2V0KCJ3b3JrVG9Eb25lIikgYW5kIHQuZ2V0KCJzdGF0ZSIpID09ICJ3b3JraW5nIiBhbmQgdC5nZXQoImFzc2lnbmVlIikgPT0gYXNzaWduZWUpOgogICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICAgICBpZiBpZGxlIGlzIE5vbmU6CiAgICAgICAgICAgICAgICAgICAgaWYgdC5nZXQoInN0YWxsUGluZ1RzIik6ICAgICAgICAgICAgICAgICMgYWdlbnQgcmVjb3ZlcmVkIC0+IHJlc2V0IHNvIG5leHQgc3RhbGwgcmUtcGluZ3MKICAgICAgICAgICAgICAgICAgICAgICAgdFsic3RhbGxQaW5nVHMiXSA9IDA7IHNhdmUoYikKICAgICAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICAgICAgaWYgKHRpbWUudGltZSgpIC0gKHQuZ2V0KCJzdGFsbFBpbmdUcyIpIG9yIDApKSA+PSBTVEFMTF9SRVBJTkc6CiAgICAgICAgICAgICAgICAgICAgdFsic3RhbGxQaW5nVHMiXSA9IHRpbWUudGltZSgpOyBzYXZlKGIpCiAgICAgICAgICAgICAgICAgICAgcGluZyA9IChhc3NpZ25lZSwgaW50KGlkbGUgLy8gNjApKQogICAgICAgICAgICBpZiBwaW5nOgogICAgICAgICAgICAgICAgYm9zc19waW5nKHRpZCwgZiJXQVRDSERPRzogYXNzaWduZWUge3BpbmdbMF19IElETEUvc3RhbGxlZCB+e3BpbmdbMV19bSBhdCBwcm9tcHQgIgogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgZiIobm8gYWN0aXZpdHkpIOKAlCByZS1lbmdhZ2Ugb3IgcmVhc3NpZ24iKQoKIyDilIDilIAgbXV0YXRpb25zIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgApkZWYgYXBwbHlfdXBkYXRlKGQpOgogICAgb3AgPSBkLmdldCgib3AiKQogICAgcmV0aXJlID0gTm9uZSAgICAgICAgICAgICAgICAgICAgICAgIyAocHJldl9zdGF0ZSwgdGFza19zbmFwc2hvdCkgc2V0IG9uIGEgZ2VudWluZSDihpJkb25lIHRyYW5zaXRpb247IHJ1biBhZnRlciB0aGUgbG9jawogICAgd2l0aCBfbG9jazoKICAgICAgICBiID0gbG9hZCgpCiAgICAgICAgaWYgb3AgPT0gImFkZCI6CiAgICAgICAgICAgIHQgPSBuZXdfdGFzayhkLmdldCgidGV4dCIsICIiKSk7IHRbInRlc3QiXSA9IGJvb2woZC5nZXQoInRlc3QiKSkgb3IgX2lzX3Rlc3QodCkKICAgICAgICAgICAgaWYgZC5nZXQoInBhcmVudCIpIGFuZCBkWyJwYXJlbnQiXSBpbiBiWyJ0YXNrcyJdOiAgICMgaXNzdWUgIzM6IGNyZWF0ZSBkaXJlY3RseSBhcyBhIHN1YnRhc2sgb2YgYW4gZXhpc3RpbmcgY2FyZAogICAgICAgICAgICAgICAgdFsicGFyZW50Il0gPSBkWyJwYXJlbnQiXQogICAgICAgICAgICBiWyJ0YXNrcyJdW3RbImlkIl1dID0gdDsgYlsib3JkZXIiXS5pbnNlcnQoMCwgdFsiaWQiXSkKICAgICAgICAgICAgc2F2ZShiKQogICAgICAgICAgICAjIGEgY3JlYXRlZCB0YXNrIG11c3QgTkVWRVIgc2lsZW50bHkgZGllOiBwaW5nIHRoZSBCb3NzIG9uIGNyZWF0ZSBzbyBpdCdzIHRyaWFnZWQvYnJhaW5zdG9ybWVkCiAgICAgICAgICAgICMg4oCUIFVOTEVTUyBpdCdzIGEgdGVzdC9kZW1vL3Byb29mIGZpeHR1cmUgKGV4ZW1wdDogbm8gQm9zcyBudWRnZSkuCiAgICAgICAgICAgIGlmIG5vdCBfaXNfdGVzdCh0KToKICAgICAgICAgICAgICAgIGJvc3NfcGluZyh0WyJpZCJdLCAibmV3IHRhc2sgY3JlYXRlZCDigJQgYnJhaW5zdG9ybSArIHRyaWFnZSBpdCAobm8gd29yay10by1kb25lIHRvZ2dsZSBuZWVkZWQgZm9yIGl0IHRvIGJlIHNlZW4pIikKICAgICAgICAgICAgcmV0dXJuIHsib2siOiBUcnVlLCAiaWQiOiB0WyJpZCJdfQogICAgICAgIHRpZCA9IGQuZ2V0KCJpZCIpOyB0ID0gYlsidGFza3MiXS5nZXQodGlkKQogICAgICAgIGlmIG5vdCB0OiByZXR1cm4geyJlcnJvciI6ICJubyBzdWNoIHRhc2sifQogICAgICAgIGlmIG9wID09ICJkZWwiOgogICAgICAgICAgICBiWyJ0YXNrcyJdLnBvcCh0aWQsIE5vbmUpOyBiWyJvcmRlciJdID0gW3ggZm9yIHggaW4gYlsib3JkZXIiXSBpZiB4ICE9IHRpZF0KICAgICAgICAgICAgc2F2ZShiKTsgcmV0dXJuIHsib2siOiBUcnVlfQogICAgICAgIGlmIG9wID09ICJyZW9yZGVyIjoKICAgICAgICAgICAgYlsib3JkZXIiXSA9IFt4IGZvciB4IGluIGQuZ2V0KCJvcmRlciIsIFtdKSBpZiB4IGluIGJbInRhc2tzIl1dCiAgICAgICAgICAgIHNhdmUoYik7IHJldHVybiB7Im9rIjogVHJ1ZX0KICAgICAgICBpZiBvcCA9PSAiYWRkc3ViIjoKICAgICAgICAgICAgdFsic3VicyJdLmFwcGVuZCh7ImlkIjogdWlkKCksICJ0ZXh0IjogZC5nZXQoInRleHQiLCAiIiksICJkb25lIjogRmFsc2UsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICJkb25lQ29uZGl0aW9uIjogZC5nZXQoImRvbmVDb25kaXRpb24iLCAiIiksICJjcmVhdGVkIjogbm93KCl9KQogICAgICAgICAgICB0WyJ1cGRhdGVkIl0gPSBub3coKTsgc2F2ZShiKTsgcmV0dXJuIHsib2siOiBUcnVlfQogICAgICAgIGlmIG9wID09ICJzZXQiOgogICAgICAgICAgICBib3NzX2VucXVldWVkID0gRmFsc2UKICAgICAgICAgICAgaWYgImRvbmVDb25kaXRpb24iIGluIGQ6IHRbImRvbmVDb25kaXRpb24iXSA9IGRbImRvbmVDb25kaXRpb24iXQogICAgICAgICAgICBpZiAidGV4dCIgaW4gZDogdFsidGV4dCJdID0gZFsidGV4dCJdCiAgICAgICAgICAgIGlmICJhc3NpZ25lZSIgaW4gZDoKICAgICAgICAgICAgICAgIHRbImFzc2lnbmVlIl0gPSBkWyJhc3NpZ25lZSJdOyB0WyJhc3NpZ25lZEF0Il0gPSBub3coKSBpZiBkWyJhc3NpZ25lZSJdIGVsc2UgTm9uZQogICAgICAgICAgICBpZiAicGFyZW50IiBpbiBkOiAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIGlzc3VlICMzOiBwYXJlbnQvY2hpbGQgaGllcmFyY2h5CiAgICAgICAgICAgICAgICBwaWQgPSBkWyJwYXJlbnQiXSBvciBOb25lCiAgICAgICAgICAgICAgICBpZiBwaWQgYW5kIChwaWQgbm90IGluIGJbInRhc2tzIl0gb3IgcGlkID09IHRpZCBvciBfY3JlYXRlc19jeWNsZShiLCB0aWQsIHBpZCkpOgogICAgICAgICAgICAgICAgICAgIHJldHVybiB7ImVycm9yIjogImludmFsaWQgcGFyZW50IChtaXNzaW5nLCBzZWxmLCBvciB3b3VsZCBjcmVhdGUgYSBjeWNsZSkifQogICAgICAgICAgICAgICAgdFsicGFyZW50Il0gPSBwaWQKICAgICAgICAgICAgaWYgImRlcGVuZHNPbiIgaW4gZDogICAgICAgICAgICAgICAgICAgICAgICAgIyBpc3N1ZSAjMzogJ2Jsb2NrZWQgYnknIGxpbmtzIChleGlzdGluZyBjYXJkcywgbmV2ZXIgc2VsZikKICAgICAgICAgICAgICAgIHRbImRlcGVuZHNPbiJdID0gW3ggZm9yIHggaW4gKGRbImRlcGVuZHNPbiJdIG9yIFtdKSBpZiB4IGluIGJbInRhc2tzIl0gYW5kIHggIT0gdGlkXQogICAgICAgICAgICBpZiAiaGFyZEdhdGUiIGluIGQ6ICAgICAgICAgICAgICAgICAgICAgICAgICAjIGlzc3VlICMzOiBwZXItY2FyZCBoYXJkIGdhdGUgKE9GRiBieSBkZWZhdWx0KQogICAgICAgICAgICAgICAgdFsiaGFyZEdhdGUiXSA9IGJvb2woZFsiaGFyZEdhdGUiXSkKICAgICAgICAgICAgaWYgZC5nZXQoIndvcmtUb0RvbmUiKSBpcyBUcnVlOgogICAgICAgICAgICAgICAgaWYgbm90ICh0LmdldCgiZG9uZUNvbmRpdGlvbiIpIG9yICIiKS5zdHJpcCgpOgogICAgICAgICAgICAgICAgICAgIHJldHVybiB7ImVycm9yIjogImRvbmVDb25kaXRpb24gcmVxdWlyZWQgYmVmb3JlIHdvcmtUb0RvbmUifQogICAgICAgICAgICAgICAgd2FzX29uID0gYm9vbCh0LmdldCgid29ya1RvRG9uZSIpKSAgICAgICAgICMgb25seSBwaW5nIG9uIGEgcmVhbCBPRkYtPk9OIHRyYW5zaXRpb24gKGlkZW1wb3RlbnQgT04gPSBubyBkdXBsaWNhdGUgcGluZzsgY29tcGxlbWVudHMgdGhlIGNsaWVudCA1MDBtcyBkZWJvdW5jZSkKICAgICAgICAgICAgICAgIHRbIndvcmtUb0RvbmUiXSA9IFRydWUKICAgICAgICAgICAgICAgICMgU0lMRU5ULU5PLU9QIEZJWCAoc2xpY2UgZCk6IHRoZSBkaXNwYXRjaGVyIG9ubHkgYWN0cyBvbiBzdGF0ZT09J3dvcmtpbmcnLiBBCiAgICAgICAgICAgICAgICAjIG5lZWRzX2JyYWluc3Rvcm0gY2FyZCB3aXRoIHdvcmstdG8tZG9uZSBPTiB3b3VsZCBvdGhlcndpc2Ugc2l0IHNpbGVudC4gU3VyZmFjZSBpdAogICAgICAgICAgICAgICAgIyAodmlzaWJsZSBsYXN0U3RhdHVzICsgYSBkaXN0aW5jdCBCb3NzIHBpbmcpIGluc3RlYWQgb2YgZG9pbmcgbm90aGluZy4KICAgICAgICAgICAgICAgIGlmIHRbInN0YXRlIl0gPT0gIm5lZWRzX2JyYWluc3Rvcm0iOgogICAgICAgICAgICAgICAgICAgIHRbImxhc3RTdGF0dXMiXSA9ICJuZWVkcyBicmFpbnN0b3JtIGZpcnN0IOKAlCB3b3JrLXRvLWRvbmUgaXMgT04gYnV0IHRoaXMgdGFzayB3b24ndCBiZSB3b3JrZWQgdW50aWwgaXQncyBicmFpbnN0b3JtZWQvYW5zd2VyZWQgYW5kIHByb21vdGVkIHRvIHdvcmtpbmciCiAgICAgICAgICAgICAgICAgICAgdFsidXBkYXRlZCJdID0gbm93KCk7IHNhdmUoYikKICAgICAgICAgICAgICAgICAgICBpZiBub3Qgd2FzX29uOiBib3NzX3BpbmcodGlkLCAid29yay10by1kb25lIE9OIGJ1dCB0YXNrIE5FRURTIEJSQUlOU1RPUk0g4oCUIG5vdCB3b3JrYWJsZSB5ZXQ7IHN1cmZhY2UgcXVlc3Rpb25zIHRvIHRoZSBDRU8iKTsgYm9zc19lbnF1ZXVlZCA9IG5vdCB3YXNfb24KICAgICAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICAgICAgdFsidXBkYXRlZCJdID0gbm93KCk7IHNhdmUoYikKICAgICAgICAgICAgICAgICAgICBpZiBub3Qgd2FzX29uOiBib3NzX3BpbmcodGlkLCAid29yay10by1kb25lIHRvZ2dsZWQgT04g4oCUIGRyaXZlIHRvIGRvbmUiKTsgYm9zc19lbnF1ZXVlZCA9IG5vdCB3YXNfb24KICAgICAgICAgICAgICAgIGIgPSBsb2FkKCk7IHQgPSBiWyJ0YXNrcyJdW3RpZF0KICAgICAgICAgICAgZWxpZiBkLmdldCgid29ya1RvRG9uZSIpIGlzIEZhbHNlOgogICAgICAgICAgICAgICAgdFsid29ya1RvRG9uZSJdID0gRmFsc2UKICAgICAgICAgICAgaWYgInN0YXRlIiBpbiBkOgogICAgICAgICAgICAgICAgaWYgZFsic3RhdGUiXSBub3QgaW4gVkFMSURfU1RBVEVTOgogICAgICAgICAgICAgICAgICAgIHJldHVybiB7ImVycm9yIjogZiJpbnZhbGlkIHN0YXRlIHtkWydzdGF0ZSddIXJ9IChhbGxvd2VkOiB7c29ydGVkKFZBTElEX1NUQVRFUyl9KSJ9CiAgICAgICAgICAgICAgICBpZiBkWyJzdGF0ZSJdID09ICJkb25lIjogICAgICAgICAgICAgICAgICMgUnVsZSAyMTogb25seSB0aGUgQ0VPIG1hcmtzIGRvbmUgKG9uZSBjbGljaywgYW55IHN0YXRlKTsgQUkgLT4gcmV2aWV3IG1heAogICAgICAgICAgICAgICAgICAgIGlmIHN0cihkLmdldCgiYnkiLCAiIikpLnN0cmlwKCkudXBwZXIoKSA9PSAiQ0VPIjoKICAgICAgICAgICAgICAgICAgICAgICAgdFsidmVyaWZpZWQiXSA9IFRydWUKICAgICAgICAgICAgICAgICAgICBlbHNlOgogICAgICAgICAgICAgICAgICAgICAgICByZXR1cm4geyJlcnJvciI6ICJvbmx5IHRoZSBDRU8gbWFya3MgZG9uZSAoQUkvZW5naW5lZXIgY2FuIG1vdmUgdXAgdG8gJ3JldmlldycsIG5ldmVyICdkb25lJykifQogICAgICAgICAgICAgICAgaWYgZFsic3RhdGUiXSA9PSAid29ya2luZyIgYW5kIHRbInN0YXRlIl0gPT0gIm5lZWRzX2JyYWluc3Rvcm0iOgogICAgICAgICAgICAgICAgICAgIHJldHVybiB7ImVycm9yIjogIm5vdCB3b3JrYWJsZSBiZWZvcmUgYnJhaW5zdG9ybSAoYnJhaW5zdG9ybSBnYXRlKSJ9CiAgICAgICAgICAgICAgICBfZyA9IHN0YXRlX2dhdGUoYiwgdCwgZFsic3RhdGUiXSkgICAgICAgICMgaXNzdWUgIzM6IHN1YnRhc2svZGVwZW5kZW5jeSArIGhhcmQtZ2F0ZSBndWFyZHJhaWxzCiAgICAgICAgICAgICAgICBpZiBfZzogcmV0dXJuIHsiZXJyb3IiOiBfZ30KICAgICAgICAgICAgICAgIGlmIGRbInN0YXRlIl0gIT0gdFsic3RhdGUiXToKICAgICAgICAgICAgICAgICAgICBhZGRfY29tbWVudCh0LCBmInN0YXRlOiB7dFsnc3RhdGUnXX0g4oaSIHtkWydzdGF0ZSddfSIsIGQuZ2V0KCJieSIpIG9yICJzeXN0ZW0iLCAic3RhdGUiKQogICAgICAgICAgICAgICAgX3ByZXZfc3RhdGUgPSB0WyJzdGF0ZSJdCiAgICAgICAgICAgICAgICB0WyJzdGF0ZSJdID0gZFsic3RhdGUiXQogICAgICAgICAgICAgICAgaWYgZFsic3RhdGUiXSA9PSAiZG9uZSIgYW5kIF9wcmV2X3N0YXRlICE9ICJkb25lIjogICAjIGdlbnVpbmUgQ0VPIOKGkmRvbmUgdHJhbnNpdGlvbiDihpIgcmV0aXJlIHRoZSBhc3NpZ25lZSBhZnRlciB0aGUgbG9jawogICAgICAgICAgICAgICAgICAgIHJldGlyZSA9IChfcHJldl9zdGF0ZSwgZGljdCh0KSkKICAgICAgICAgICAgdFsidXBkYXRlZCJdID0gbm93KCk7IHNhdmUoYikKICAgICAgICAgICAgcmVzID0geyJvayI6IFRydWUsICJib3NzRW5xdWV1ZWQiOiBib3NzX2VucXVldWVkfQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHJldHVybiB7ImVycm9yIjogZiJ1bmtub3duIG9wIHtvcCFyfSJ9CiAgICBpZiByZXRpcmU6IHJldGlyZV9vbl9kb25lKHJldGlyZVswXSwgcmV0aXJlWzFdKSAgICMgT1VUU0lERSBfbG9jazogcnVucyBgbXAga2lsbGAsIGV2ZW50cyB0aGUgQm9zcywgdGhyZWFkcyB0aGUgY2FyZAogICAgcmV0dXJuIHJlcwoKZGVmIF9tcF9zZW5kKGFnZW50LCBtc2cpOgogICAgIiIiUmVsYXkgYSBtZXNzYWdlIHRvIGFuIGFnZW50IHZpYSBgbXAgc2VuZGAgKGNoYWluIG9mIGNvbW1hbmQpLiBBbHdheXMgYXVkaXQtbG9ncyB0byB0aGUgYm9zcwogICAgaW5ib3g7IGRvZXMgdGhlIHJlYWwgc2VuZCB3aGVuIGxpdmUgKG5vdCBURVNUX1NJTksgKyBtcCBvbiBQQVRIKS4gUmV0dXJucyBUcnVlIGlmIHNlbnQgbGl2ZS4iIiIKICAgIHRyeToKICAgICAgICBJTkJPWF9MT0cucGFyZW50Lm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkKICAgICAgICB3aXRoIElOQk9YX0xPRy5vcGVuKCJhIikgYXMgZjogZi53cml0ZShmIntub3coKX0gTVBfU0VORCAtPiB7YWdlbnR9IDo6IHttc2dbOjIwMF19XG4iKQogICAgZXhjZXB0IEV4Y2VwdGlvbjogcGFzcwogICAgaWYgbm90IFRFU1RfU0lOSyBhbmQgc2h1dGlsLndoaWNoKCJtcCIpOgogICAgICAgIHRyeToKICAgICAgICAgICAgciA9IHN1YnByb2Nlc3MucnVuKFsibXAiLCAic2VuZCIsIGFnZW50LCBtc2ddLCBjYXB0dXJlX291dHB1dD1UcnVlLCB0ZXh0PVRydWUsIHRpbWVvdXQ9MzApCiAgICAgICAgICAgIHJldHVybiByLnJldHVybmNvZGUgPT0gMAogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IHJldHVybiBGYWxzZQogICAgcmV0dXJuIEZhbHNlCgojIOKUgOKUgCBBVVRPLVJFVElSRSAoY2FyZCA2OTM0ZTUyMGI3OTEpOiB3aGVuIHRoZSBDRU8gbWFya3MgYSB0YXNrIERPTkUsIHRoZSBlbmdpbmVlciB0aGF0IHdhcwojIGFzc2lnbmVkIHRvIGl0IGhhcyBmaW5pc2hlZCBpdHMgam9iIOKAlCByZXRpcmUgaXQgKG1wIGtpbGwpIHNvIGl0IHN0b3BzIGNodXJuaW5nLiBUaGlzIGlzIHRoZQojIHJldGlyZW1lbnQgVFJJR0dFUiwgZmlyZWQgT05MWSBvbiBhIGdlbnVpbmUgdHJhbnNpdGlvbiBJTlRPICdkb25lJyAoUnVsZSAyMTogQ0VPLW9ubHkpLgojIFNlcnZlci1kaXJlY3Qga2lsbCAoZGV0ZXJtaW5pc3RpYyArIGRpcmVjdGx5IHZlcmlmaWFibGUsIHNhbWUgbWVjaGFuaXNtIGFzIGJvc3NfcGluZy9fbXBfc2VuZCksCiMgUExVUyBhIHN0cnVjdHVyZWQgZXZlbnQgdG8gdGhlIEJvc3Mgc28gdGhlIEJvc3Mga25vd3MgdGhlIHRhc2sgZmluaXNoZWQgKyB3aG8gd2FzIHJldGlyZWQuCiMgRWRnZSBjYXNlczogb25seSBvbiDihpJkb25lIChjYWxsZXIgcGFzc2VzIHByZXZfc3RhdGUpOyBubyBhc3NpZ25lZSDihpIgbm8tb3A7IG5ldmVyIHRhcmdldHMgYQojIG5vbi1hc3NpZ25lZSAod2Ugb25seSBldmVyIHBhc3MgdFsnYXNzaWduZWUnXSk7IGFscmVhZHktZGVhZCBlbmdpbmVlciDihpIgbXAga2lsbCBmYWlscy90aW1lb3V0cywKIyB3ZSBjYXRjaCArIGxvZyAiYWxyZWFkeSByZXRpcmVkIChuby1vcCkiIGFuZCBORVZFUiBmYWlsIHRoZSBET05FIHdyaXRlLgpkZWYgcmV0aXJlX29uX2RvbmUocHJldl9zdGF0ZSwgdCk6CiAgICAjIE11c3QgYmUgY2FsbGVkIE9VVFNJREUgX2xvY2sgKGl0IHJ1bnMgc2xvdyBgbXBgIHN1YnByb2Nlc3NlcyBhbmQgcmVsb2Fkcy9zYXZlcyBvbiBpdHMgb3duKS4KICAgIGlmIHByZXZfc3RhdGUgPT0gImRvbmUiOiAgICAgICAgICAgICMgbm90IGEgcmVhbCB0cmFuc2l0aW9uIChyZS1zYXZlIG9mIGFuIGFscmVhZHktZG9uZSBjYXJkKQogICAgICAgIHJldHVybgogICAgYXNzaWduZWUgPSAodC5nZXQoImFzc2lnbmVlIikgb3IgIiIpLnN0cmlwKCkKICAgIHRpZCA9IHQuZ2V0KCJpZCIsICI/IikKICAgIGRlZiBfbG9nKGxpbmUpOgogICAgICAgIHRyeToKICAgICAgICAgICAgSU5CT1hfTE9HLnBhcmVudC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICAgICAgICAgIHdpdGggSU5CT1hfTE9HLm9wZW4oImEiKSBhcyBmOiBmLndyaXRlKGYie25vdygpfSB7bGluZX1cbiIpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogcGFzcwogICAgaWYgbm90IGFzc2lnbmVlOiAgICAgICAgICAgICAgICAgICAgIyBub3RoaW5nIGFzc2lnbmVkIOKGkiBub3RoaW5nIHRvIHJldGlyZSAoY2xlYW4gbm8tb3ApCiAgICAgICAgX2xvZyhmIlJFVElSRSB0YXNrIHt0aWR9IG1hcmtlZCBET05FIGJ1dCBoYWQgbm8gYXNzaWduZWUg4oCUIG5vLW9wIikKICAgICAgICByZXR1cm4KICAgIGtpbGxlZCA9IEZhbHNlOyBkZXRhaWwgPSAiIgogICAgaWYgbm90IFRFU1RfU0lOSyBhbmQgc2h1dGlsLndoaWNoKCJtcCIpOgogICAgICAgIHRyeToKICAgICAgICAgICAgciA9IHN1YnByb2Nlc3MucnVuKFsibXAiLCAia2lsbCIsIGFzc2lnbmVlXSwgY2FwdHVyZV9vdXRwdXQ9VHJ1ZSwgdGV4dD1UcnVlLCB0aW1lb3V0PTE1KQogICAgICAgICAgICBraWxsZWQgPSAoci5yZXR1cm5jb2RlID09IDApCiAgICAgICAgICAgIGRldGFpbCA9IChyLnN0ZG91dCBvciByLnN0ZGVyciBvciAiIikuc3RyaXAoKVs6MTYwXQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICAgICAgZGV0YWlsID0gZiJleGNlcHRpb24ge2V9IiAgICAgICAgICAjIGFscmVhZHktZGVhZCBob3N0L2FnZW50IOKGkiB0aW1lb3V0L2VycjogY2xlYW4gbm8tb3AKICAgIGVsc2U6CiAgICAgICAgZGV0YWlsID0gIlRFU1RfU0lOSy9uby1tcCDigJQga2lsbCBza2lwcGVkIChhdWRpdCBvbmx5KSIKICAgIG5vdGUgPSAicmV0aXJlZCIgaWYga2lsbGVkIGVsc2UgImtpbGwgbm8tb3AgKGFscmVhZHkgZGVhZCAvIHVucmVhY2hhYmxlKSIKICAgIF9sb2coZiJSRVRJUkUgdGFzayB7dGlkfSBET05FIC0+IG1wIGtpbGwge2Fzc2lnbmVlfSA6OiB7bm90ZX0gOjoge2RldGFpbH0iKQogICAgIyB0ZWxsIHRoZSBCb3NzIHRoZSB0YXNrIGZpbmlzaGVkICsgd2hvIHdhcyByZXRpcmVkICh0aGUgQ0VPJ3MgInNlbmQgYW4gZXZlbnQgdG8gdGhlIGJvc3MiIGludGVudCkKICAgIF9tcF9zZW5kKEJPU1NfQUdFTlQsIGYiW3RvZG9dIHRhc2sge3RpZH0gbWFya2VkIERPTkUgYnkgQ0VPIOKAlCBhdXRvLXJldGlyZWQgYXNzaWduZWUge2Fzc2lnbmVlfSAoe25vdGV9KS4iKQogICAgIyB0aHJlYWQgdGhlIHJldGlyZW1lbnQgaW50byB0aGUgY2FyZCdzIGR1cmFibGUgaGlzdG9yeSBmb3IgdGhlIENFTydzIHZpc2liaWxpdHkgKG93biBzaG9ydCBsb2NrKQogICAgd2l0aCBfbG9jazoKICAgICAgICBiID0gbG9hZCgpOyBjdCA9IGJbInRhc2tzIl0uZ2V0KHRpZCkKICAgICAgICBpZiBjdDoKICAgICAgICAgICAgYWRkX2NvbW1lbnQoY3QsIGYiYXV0by1yZXRpcmU6IGVuZ2luZWVyIHthc3NpZ25lZX0ge25vdGV9ICh0YXNrIG1hcmtlZCBET05FKSIsICJzeXN0ZW0iLCAic3RhdHVzIikKICAgICAgICAgICAgY3RbInVwZGF0ZWQiXSA9IG5vdygpOyBzYXZlKGIpCgpkZWYgYXBwbHlfY29tbWVudChkKToKICAgICIiIkFwcGVuZCBhIGNvbW1lbnQgdG8gYSB0YXNrJ3MgdGhyZWFkIChzbGljZSBiKSBBTkQgbWFrZSBpdCBhIHR3by13YXkgY2hhbm5lbC4KICAgIENIQUlOIE9GIENPTU1BTkQ6IGEgQ0VPIGNvbW1lbnQgaXMgcmVsYXllZCB0byB0aGUgQk9TUyAod2hvIHJlZGlyZWN0cyB0byB0aGUgcmlnaHQgZW5naW5lZXIpIOKAlAogICAgbmV2ZXIgQ0VP4oaSZW5naW5lZXIgZGlyZWN0bHkuIEVuZ2luZWVyL0FJIHJlcGxpZXMgKGJ5PTxhZ2VudCBpZD4pIHRocmVhZCBiYWNrIGludG8gdGhlIGNhcmQgZm9yCiAgICB0aGUgQ0VPJ3MgdmlzaWJpbGl0eSAoYSByZWFsIHR3by13YXkgR2l0SHViLWlzc3VlIGNvbnZlcnNhdGlvbikgQU5EIG5vdyBBTFNPIHBpbmcgdGhlIEJvc3MsIHNvCiAgICB0aGUgQm9zcyBzZWVzIGNhcmQgYWN0aXZpdHkgaW4gcmVhbCB0aW1lIGluc3RlYWQgb2Ygc3VwZXJ2aXNpbmcgYmxpbmQgb2ZmIG1wIHJlcG9ydHMuIEd1YXJkZWQKICAgIGFnYWluc3Qgbm9pc2U6IHRoZSBCb3NzJ3MgT1dOIGNvbW1lbnRzIGFyZSBOT1QgcmVsYXllZCBiYWNrIHRvIGl0c2VsZiAobm8gbG9vcCksIGFuZCAnc3lzdGVtJwogICAgYXV0by1wb3N0cyBkb24ndCBwaW5nLiBDRU8gY29tbWVudHMga2VlcCB0aGVpciBleGlzdGluZyBjaGFpbi1vZi1jb21tYW5kIHJlbGF5IChubyBkb3VibGUtcGluZykuIiIiCiAgICB3aXRoIF9sb2NrOgogICAgICAgIGIgPSBsb2FkKCk7IHQgPSBiWyJ0YXNrcyJdLmdldChkLmdldCgidGFza19pZCIpIG9yIGQuZ2V0KCJpZCIpKQogICAgICAgIGlmIG5vdCB0OiByZXR1cm4geyJlcnJvciI6ICJubyBzdWNoIHRhc2sifQogICAgICAgIGJ5ID0gZC5nZXQoImJ5IiwgIkNFTyIpOyBpc19jZW8gPSBzdHIoYnkpLnVwcGVyKCkgPT0gIkNFTyIKICAgICAgICBjID0gYWRkX2NvbW1lbnQodCwgZC5nZXQoImJvZHkiLCAiIiksIGJ5LCAiY29tbWVudCIpCiAgICAgICAgaWYgbm90IGM6IHJldHVybiB7ImVycm9yIjogImVtcHR5IGNvbW1lbnQifQogICAgICAgICMgQ09NTUVOVC1PTi1SRVZJRVcgPSBNT1JFIFdPUks6IGEgQ0VPIGNvbW1lbnQgb24gYSAncmV2aWV3JyBjYXJkIG1lYW5zIHdvcmsgcmVtYWlucywgc28gaXQKICAgICAgICAjIGF1dG8ta2lja3MgYmFjayByZXZpZXcgLT4gd29ya2luZy4gRWRnZS1jYXNlIHBvbGljeToKICAgICAgICAjICAoYSkgT05MWSAncmV2aWV3JyBhdXRvLWtpY2tzLiB3b3JraW5nIHN0YXlzIHdvcmtpbmcgLyBuZWVkc19icmFpbnN0b3JtIHN0YXlzIGdhdGVkIC8KICAgICAgICAjICAgICAgYmxvY2tlZCBzdGF5cyBibG9ja2VkIC8gZG9uZSBzdGF5cyBkb25lIOKAlCBidXQgdGhlIGNvbW1lbnQgU1RJTEwgcmVsYXlzIHRvIHRoZSBCb3NzIGluCiAgICAgICAgIyAgICAgIGV2ZXJ5IGNhc2UgKHdlIG5ldmVyIGxvc2UgdGhlIHJlbGF5KS4gTm9uLXJldmlldyBzdGF0ZXMgYXJlbid0IGZvcmNlLW1vdmVkIChhdm9pZAogICAgICAgICMgICAgICBieXBhc3NpbmcgdGhlIGJyYWluc3Rvcm0gZ2F0ZSBvciBzaWxlbnRseSByZW9wZW5pbmcgYSBkb25lIGNhcmQ7IHVzZSB0aGUgc3RhdHVzIGNvbnRyb2wpLgogICAgICAgICMgIChiKSBPTkxZIHRoZSBDRU8ncyBjb21tZW50IGtpY2tzIOKAlCBhbiBlbmdpbmVlci9BSSBzdGF0dXMgcG9zdCAoYnkgIT0gQ0VPKSBuZXZlciBjaGFuZ2VzIHN0YXRlLgogICAgICAgICMgIChjKSB0aGUgcmVsYXkgdG8gdGhlIEJvc3MgaGFwcGVucyB3aGV0aGVyIG9yIG5vdCBpdCBraWNrZWQgKHNlZSBiZWxvdykuCiAgICAgICAgIyAgKGQpIG5vIHRocmFzaDogb25jZSBraWNrZWQgaXQncyAnd29ya2luZycgKG5vdCAncmV2aWV3JyksIHNvIGZ1cnRoZXIgY29tbWVudHMgZG9uJ3QgcmUta2ljay4KICAgICAgICBraWNrZWQgPSBpc19jZW8gYW5kIHQuZ2V0KCJzdGF0ZSIpID09ICJyZXZpZXciCiAgICAgICAgaWYga2lja2VkOgogICAgICAgICAgICBhZGRfY29tbWVudCh0LCAic3RhdGU6IHJldmlldyDihpIgd29ya2luZyIsIGJ5LCAic3RhdGUiKQogICAgICAgICAgICB0WyJzdGF0ZSJdID0gIndvcmtpbmciCiAgICAgICAgdFsidXBkYXRlZCJdID0gbm93KCk7IHNhdmUoYikKICAgICAgICB0aWQgPSB0WyJpZCJdOyB0aXRsZSA9ICh0LmdldCgidGV4dCIpIG9yICIiKVs6NzBdOyBhc3NpZ25lZSA9IHQuZ2V0KCJhc3NpZ25lZSIpOyBib2R5ID0gY1siYm9keSJdCiAgICByb3V0ZWQgPSBOb25lCiAgICB3aGVyZSA9IGYiYXNzaWduZWQ6IHthc3NpZ25lZX0iIGlmIGFzc2lnbmVlIGVsc2UgIlVOQVNTSUdORUQg4oCUIGFzc2lnbiArIHJlbGF5IgogICAgaWYgaXNfY2VvOiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIHJlbGF5IHRvIHRoZSBCb3NzIChvdXRzaWRlIHRoZSBsb2NrKQogICAgICAgIGtpY2sgPSAiIFtjYXJkIGtpY2tlZCByZXZpZXfihpJ3b3JraW5nIOKAlCBtb3JlIHdvcmsgbmVlZGVkXSIgaWYga2lja2VkIGVsc2UgIiIKICAgICAgICBzZW50ID0gX21wX3NlbmQoQk9TU19BR0VOVCwgZiJbQ0VPIGNvbW1lbnQgb24gY2FyZCB7dGlkfSDigJx7dGl0bGV94oCdICh7d2hlcmV9KV17a2lja306IHtib2R5fVxuIgogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBmIuKGkiBjaGFpbiBvZiBjb21tYW5kOiByZWxheSB0byB0aGUgcmlnaHQgZW5naW5lZXIgKGRvIG5vdCBleHBlY3QgdGhlIENFTyB0byBwaW5nIHRoZW0gZGlyZWN0bHkpLiIpCiAgICAgICAgcm91dGVkID0gZiJib3NzOnsnc2VudCcgaWYgc2VudCBlbHNlICdsb2dnZWQnfSIKICAgIGVsc2U6CiAgICAgICAgIyBFbmdpbmVlci9BSSBjYXJkLWNvbW1lbnQg4oaSIHBpbmcgdGhlIEJvc3MgZm9yIHJlYWwtdGltZSB2aXNpYmlsaXR5LiBTa2lwIHRoZSBCb3NzJ3MgT1dOCiAgICAgICAgIyBjb21tZW50cyAodGhlIGF1dGhvcidzIHRhYiBpcyAnQm9zcycsIG9yIGl0IGVxdWFscyBCT1NTX0FHRU5ULCBvciB0aGUgYm9keSBpcyBhIFtCT1NTXSBub3RlKQogICAgICAgICMgc28gd2UgbmV2ZXIgbG9vcCBhIEJvc3MgcG9zdCBiYWNrIHRvIGl0c2VsZjsgc2tpcCAnc3lzdGVtJyBhdXRvLXBvc3RzIChhdXRvLXJldGlyZSwgZXRjLikuCiAgICAgICAgX2J5ID0gc3RyKGJ5KQogICAgICAgIGF1dGhvcl9pc19ib3NzID0gKF9ieSA9PSBCT1NTX0FHRU5UKSBvciAoX2J5LnJzcGxpdCgiOiIsIDEpWy0xXSA9PSAiQm9zcyIpIG9yIGJvZHkubHN0cmlwKCkudXBwZXIoKS5zdGFydHN3aXRoKCJbQk9TU10iKQogICAgICAgIGlmIChub3QgYXV0aG9yX2lzX2Jvc3MpIGFuZCBfYnkubG93ZXIoKSAhPSAic3lzdGVtIjoKICAgICAgICAgICAgc25pcHBldCA9IGJvZHkgaWYgbGVuKGJvZHkpIDw9IDMwMCBlbHNlIGJvZHlbOjI5OV0gKyAi4oCmIgogICAgICAgICAgICBzZW50ID0gX21wX3NlbmQoQk9TU19BR0VOVCwgZiJbY2FyZCB1cGRhdGUgb24ge3RpZH0g4oCce3RpdGxlfeKAnSBieSB7X2J5fSAoe3doZXJlfSldOiB7c25pcHBldH1cbiIKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGYi4oaSIGVuZ2luZWVyL0FJIHBvc3RlZCB0aGlzIG9uIHRoZSBjYXJkIChDRU8gY2FuIHNlZSBpdCkuIFN1cGVydmlzZSDigJQgZm9sbG93IHVwIGlmIGl0IG5lZWRzIGFjdGlvbi4iKQogICAgICAgICAgICByb3V0ZWQgPSBmImJvc3M6eydzZW50JyBpZiBzZW50IGVsc2UgJ2xvZ2dlZCd9IgogICAgd2FfcmVjb25jaWxlKCkgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIGlmIGl0IGxlZnQgJ3JldmlldycsIGRyb3AgaXQgZnJvbSB0aGUgQ0VPIFdoYXRzQXBwIGRpZ2VzdCAoc2xpY2UgZSkKICAgIHJldHVybiB7Im9rIjogVHJ1ZSwgImNvbW1lbnRfaWQiOiBjWyJpZCJdLCAicm91dGVkIjogcm91dGVkLCAia2lja2VkIjoga2lja2VkfQoKIyDilIDilIAgQ0xJQ0stVEhFLUxJTktFRC1FTkdJTkVFUiDihpIgQVRUQUNIIChzbGljZSBjKSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKIyBNaXJyb3IgdGhlIEhVRCdzIGF0dGFjaCBleGFjdGx5OiB0aGUgbGl2ZSB0bXV4IHNlc3Npb24gaXMgYG1jLTxzZXNzaW9uPmAgd2luZG93IGA8dGFiPmAsIGFuZAojIHRoZSBicm93c2VyIHJlYWNoZXMgaXQgdmlhIHR0eWQgYXQgYDxhdHRhY2hfYmFzZT4vP2FyZz0tdCZhcmc9bWMtPHNlc3Npb24+Ojx0YWI+YC4gVGhlIHBlci1ob3N0CiMgdHR5ZCBgYXR0YWNoX2Jhc2VgIGlzIGFkdmVydGlzZWQgYnkgZWFjaCBxdWV1ZS1jbGllbnQgYW5kIGV4cG9zZWQgb24gdGhlIHF1ZXVlLXNlcnZlcidzIC9jbGllbnRzCiMgKGEgcmVtb3RlL0pPSU4gaG9zdCBhZHZlcnRpc2VzIGl0cyBvd24gdGFpbG5ldCB0dHlkOyB0aGUgbG9jYWwgSFVEIGhvc3QgaGFzIG5vbmUg4oaSIHRoZSBjbGllbnQKIyBmYWxscyBiYWNrIHRvIGl0cyBvd24gYDxsb2NhdGlvbi5ob3N0bmFtZT46NzY4MWApLiBXZSByZXNvbHZlIHRoZSBiYXNlIGhlcmUgKHNlcnZlci1zaWRlLCBzbyB0aGUKIyBxdWV1ZSBzZWNyZXQgbmV2ZXIgcmVhY2hlcyB0aGUgYnJvd3NlciBhbmQgdGhlcmUncyBubyBjcm9zcy1vcmlnaW4gZmV0Y2gpIGFuZCBoYW5kIHRoZSBjbGllbnQgdGhlCiMgdG11eCB0YXJnZXQgKyBiYXNlOyB0aGUgY2xpZW50IGFzc2VtYmxlcyB0aGUgZmluYWwgVVJMIHdpdGggdGhlIFNBTUUgbG9jYWxob3N0IGZhbGxiYWNrIHRoZSBIVUQgdXNlcy4KX2NsaWVudHNfY2FjaGUgPSB7InRzIjogMC4wLCAiZGF0YSI6IFtdfQpkZWYgX3F1ZXVlX2NsaWVudHMoKToKICAgIG5vd3QgPSB0aW1lLnRpbWUoKQogICAgaWYgbm93dCAtIF9jbGllbnRzX2NhY2hlWyJ0cyJdIDwgNSBhbmQgX2NsaWVudHNfY2FjaGVbImRhdGEiXToKICAgICAgICByZXR1cm4gX2NsaWVudHNfY2FjaGVbImRhdGEiXQogICAgdHJ5OgogICAgICAgIHJlcSA9IHVybGxpYi5yZXF1ZXN0LlJlcXVlc3QoUVVFVUVfVVJMICsgIi9jbGllbnRzIiwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGhlYWRlcnM9eyJYLVF1ZXVlLVNlY3JldCI6IFNFQ1JFVH0gaWYgU0VDUkVUIGVsc2Uge30pCiAgICAgICAgd2l0aCB1cmxsaWIucmVxdWVzdC51cmxvcGVuKHJlcSwgdGltZW91dD0zKSBhcyByOgogICAgICAgICAgICBkYXRhID0ganNvbi5sb2FkcyhyLnJlYWQoKSBvciBiIltdIikKICAgICAgICBpZiBpc2luc3RhbmNlKGRhdGEsIGxpc3QpOgogICAgICAgICAgICBfY2xpZW50c19jYWNoZVsidHMiXSA9IG5vd3Q7IF9jbGllbnRzX2NhY2hlWyJkYXRhIl0gPSBkYXRhCiAgICAgICAgICAgIHJldHVybiBkYXRhCiAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgIHBhc3MKICAgIHJldHVybiBfY2xpZW50c19jYWNoZVsiZGF0YSJdIG9yIFtdCgpkZWYgcmVzb2x2ZV9hdHRhY2goYWdlbnRfaWQpOgogICAgIiIiUmVzb2x2ZSBhbiBhc3NpZ25lZSAoYGhvc3Qvc2Vzc2lvbjp0YWJgIG9yIGBzZXNzaW9uOnRhYmApIHRvIHt0YXJnZXQsIGJhc2V9IGZvciB0dHlkIGF0dGFjaC4iIiIKICAgIGFnZW50X2lkID0gKGFnZW50X2lkIG9yICIiKS5zdHJpcCgpCiAgICBob3N0LCByZXN0ID0gKGFnZW50X2lkLnNwbGl0KCIvIiwgMSkgKyBbIiJdKVs6Ml0gaWYgIi8iIGluIGFnZW50X2lkIGVsc2UgKE5vbmUsIGFnZW50X2lkKQogICAgaWYgbm90IHJlc3Qgb3IgIjoiIG5vdCBpbiByZXN0OgogICAgICAgIHJldHVybiB7Im9rIjogRmFsc2UsICJlcnJvciI6IGYie2FnZW50X2lkIXJ9IGlzIG5vdCBhbiBhdHRhY2hhYmxlIGFnZW50IChuZWVkIGhvc3Qvc2Vzc2lvbjp0YWIpIn0KICAgIHNlc3Npb24sIHRhYiA9IHJlc3Quc3BsaXQoIjoiLCAxKQogICAgaWYgbm90IHNlc3Npb24uc3RyaXAoKSBvciBub3QgdGFiLnN0cmlwKCk6CiAgICAgICAgcmV0dXJuIHsib2siOiBGYWxzZSwgImVycm9yIjogZiJ7YWdlbnRfaWQhcn0gaXMgbm90IGFuIGF0dGFjaGFibGUgYWdlbnQgKG5lZWQgaG9zdC9zZXNzaW9uOnRhYikifQogICAgYmFzZSA9ICIiCiAgICBpZiBob3N0OgogICAgICAgIGZvciBjIGluIF9xdWV1ZV9jbGllbnRzKCk6CiAgICAgICAgICAgIGlmIGMuZ2V0KCJob3N0bmFtZSIpID09IGhvc3Q6CiAgICAgICAgICAgICAgICBiYXNlID0gKGMuZ2V0KCJhdHRhY2hfYmFzZSIpIG9yICIiKS5zdHJpcCgpOyBicmVhawogICAgcmV0dXJuIHsib2siOiBUcnVlLCAiYWdlbnQiOiBhZ2VudF9pZCwgImhvc3QiOiBob3N0LCAidGFyZ2V0IjogZiJtYy17c2Vzc2lvbn06e3RhYn0iLCAiYmFzZSI6IGJhc2V9CgojIOKUgOKUgCBXaGF0c0FwcCBsYXN0LWhvcCBkcmFpbiAoc2xpY2UgZSk6IG91dGJveCArIHJlY29uY2lsZSArIGRyYWluIHBhcnRpY2lwYW50IOKUgOKUgApkZWYgd2FfbG9hZCgpOgogICAgdHJ5OgogICAgICAgIGQgPSBqc29uLmxvYWRzKFdBX09VVEJPWC5yZWFkX3RleHQoKSkKICAgICAgICBpZiBpc2luc3RhbmNlKGQsIGRpY3QpOiBkLnNldGRlZmF1bHQoInF1ZXVlIiwgW10pOyByZXR1cm4gZAogICAgZXhjZXB0IEV4Y2VwdGlvbjogcGFzcwogICAgcmV0dXJuIHsicXVldWUiOiBbXX0KCmRlZiB3YV9zYXZlKGQpOgogICAgVE9ET19ESVIubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgdG1wID0gV0FfT1VUQk9YLndpdGhfc3VmZml4KCIudG1wIik7IHRtcC53cml0ZV90ZXh0KGpzb24uZHVtcHMoZCwgaW5kZW50PTIpKTsgdG1wLnJlcGxhY2UoV0FfT1VUQk9YKQoKZGVmIF9ibG9ja2VkX2l0ZW1zKGIpOgogICAgIiIiQ2FyZHMgYmxvY2tlZCBPTiBUSEUgQ0VPIOKGkiBbKHRpZCwga2luZCwgdGl0bGUsIGRldGFpbCldLiBCbG9ja2VkLW9uLUNFTyAoYWxsIOKGkiBXaGF0c0FwcCBwaW5nKToKICAgIHN0YXRlPT1yZXZpZXcgKGF3YWl0aW5nIGhpcyBET05FKSBPUiBzdGF0ZT09YmxvY2tlZCAoY2VvR2F0ZWQg4oCUIGF3YWl0aW5nIGEgQ0VPIGRlY2lzaW9uL2Fuc3dlcnMpIE9SCiAgICBhIG5lZWRzX2JyYWluc3Rvcm0gY2FyZCB3aXRoIHVuYW5zd2VyZWQgcXVlc3Rpb25zIChhd2FpdGluZyB0aGUgQ0VPJ3MgYW5zd2VycykuIiIiCiAgICBvdXQgPSBbXQogICAgZm9yIHRpZCBpbiBiLmdldCgib3JkZXIiLCBsaXN0KGJbInRhc2tzIl0ua2V5cygpKSk6CiAgICAgICAgdCA9IGJbInRhc2tzIl0uZ2V0KHRpZCkKICAgICAgICBpZiBub3QgdCBvciBfaXNfdGVzdCh0KTogY29udGludWUgICAgICAgICAgICAgICMgdGVzdC9kZW1vIGZpeHR1cmVzIG5ldmVyIGVudGVyIHRoZSBDRU8gV2hhdHNBcHAgZGlnZXN0CiAgICAgICAgdGl0bGUgPSAodC5nZXQoInRleHQiKSBvciAiIikuc3RyaXAoKVs6ODBdIG9yICIodW50aXRsZWQpIgogICAgICAgIHN0ID0gdC5nZXQoInN0YXRlIikKICAgICAgICB1YSA9IFsocS5nZXQoInEiKSBvciAiIikuc3RyaXAoKSBmb3IgcSBpbiB0LmdldCgicXVlc3Rpb25zIiwgW10pIGlmIG5vdCAocS5nZXQoImFuc3dlciIpIG9yICIiKS5zdHJpcCgpXQogICAgICAgIGlmIHN0ID09ICJyZXZpZXciOgogICAgICAgICAgICBvdXQuYXBwZW5kKCh0aWQsICJyZXZpZXciLCB0aXRsZSwgIiIpKQogICAgICAgIGVsaWYgc3QgPT0gIm5lZWRzX2JyYWluc3Rvcm0iIGFuZCB1YToKICAgICAgICAgICAgb3V0LmFwcGVuZCgodGlkLCAiYnJhaW5zdG9ybSIsIHRpdGxlLCAiXG4iLmpvaW4oZiIgICB7aSsxfSkge3F9IiBmb3IgaSwgcSBpbiBlbnVtZXJhdGUodWEpKSkpCiAgICAgICAgZWxpZiBzdCA9PSAiYmxvY2tlZCI6ICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBjZW9HYXRlZCAtPiBhd2FpdGluZyB0aGUgQ0VPIChlLmcuIGJyYWluc3Rvcm0gYW5zd2VycyAvIGEgZGVjaXNpb24pCiAgICAgICAgICAgIG91dC5hcHBlbmQoKHRpZCwgImJsb2NrZWQiLCB0aXRsZSwgKHQuZ2V0KCJsYXN0U3RhdHVzIikgb3IgIiIpLnN0cmlwKClbOjI0MF0pKQogICAgcmV0dXJuIG91dAoKZGVmIF9kZWVwbGluayh0aWQpOgogICAgcmV0dXJuIGYie1dBX0JPQVJEX1VSTH0jY2FyZC97dGlkfSIgaWYgV0FfQk9BUkRfVVJMIGVsc2UgZiIoY2FyZCB7dGlkfSkiCgpkZWYgX2J1aWxkX2RpZ2VzdChpdGVtcyk6CiAgICAiIiJPTkUgY29uc29saWRhdGVkIG1lc3NhZ2UgbGlzdGluZyBldmVyeSBibG9ja2VkLW9uLUNFTyBjYXJkLCBncm91cGVkLCBlYWNoIHdpdGggaXRzIGRlZXAtbGluay4KICAgIEJyYWluc3Rvcm0gY2FyZHMgbGlzdCB0aGVpciBvcGVuIHF1ZXN0aW9ucyBpbmxpbmUgc28gdGhlIENFTyBjYW4gYW5zd2VyIHN0cmFpZ2h0IGZyb20gdGhlIHBpbmcuIiIiCiAgICByZXYgPSBbeCBmb3IgeCBpbiBpdGVtcyBpZiB4WzFdID09ICJyZXZpZXciXTsgYnMgPSBbeCBmb3IgeCBpbiBpdGVtcyBpZiB4WzFdID09ICJicmFpbnN0b3JtIl07IGJsID0gW3ggZm9yIHggaW4gaXRlbXMgaWYgeFsxXSA9PSAiYmxvY2tlZCJdCiAgICBuID0gbGVuKGl0ZW1zKQogICAgbGluZXMgPSBbZiLwn5SUIHtufSBpdGVteydzJyBpZiBuICE9IDEgZWxzZSAnJ30gbmVlZCB5b3U6Il0KICAgIGlmIHJldjoKICAgICAgICBsaW5lcy5hcHBlbmQoIlxuUmV2aWV3IOKAlCBuZWVkcyB5b3VyIERPTkU6IikKICAgICAgICBmb3IgdGlkLCBfLCB0aXRsZSwgX2QgaW4gcmV2OiBsaW5lcy5hcHBlbmQoZiLigKIge3RpdGxlfVxuICB7X2RlZXBsaW5rKHRpZCl9IikKICAgIGlmIGJzOgogICAgICAgIGxpbmVzLmFwcGVuZCgiXG5CcmFpbnN0b3JtIOKAlCBuZWVkcyB5b3VyIGFuc3dlcnM6IikKICAgICAgICBmb3IgdGlkLCBfLCB0aXRsZSwgZGV0YWlsIGluIGJzOiBsaW5lcy5hcHBlbmQoZiLigKIge3RpdGxlfVxue2RldGFpbH1cbiAge19kZWVwbGluayh0aWQpfSIpCiAgICBpZiBibDoKICAgICAgICBsaW5lcy5hcHBlbmQoIlxuQmxvY2tlZCBvbiB5b3U6IikKICAgICAgICBmb3IgdGlkLCBfLCB0aXRsZSwgZGV0YWlsIGluIGJsOiBsaW5lcy5hcHBlbmQoZiLigKIge3RpdGxlfSIgKyAoZiIg4oCUIHtkZXRhaWx9IiBpZiBkZXRhaWwgZWxzZSAiIikgKyBmIlxuICB7X2RlZXBsaW5rKHRpZCl9IikKICAgIHJldHVybiAiXG4iLmpvaW4obGluZXMpCgpkZWYgd2FfcmVjb25jaWxlKCk6CiAgICAiIiJDRU8td2F0Y2hkb2cgcGFzczogaWYg4omlMSBjYXJkIGlzIGJsb2NrZWQgb24gdGhlIENFTywgZW5xdWV1ZSBPTkUgY29uc29saWRhdGVkIGRpZ2VzdCAodGhyb3R0bGVkCiAgICB0byB+b25lIHBlciBXQV9XQVRDSERPRyB0aWNrKTsgaWYgbm9uZSBhcmUgYmxvY2tlZCwgY2FuY2VsIGFueSBwZW5kaW5nIGRpZ2VzdC4gSWRlbXBvdGVudC4iIiIKICAgIGlmIG5vdCBXQV9EUkFJTl9PTjogcmV0dXJuCiAgICBpdGVtcyA9IF9ibG9ja2VkX2l0ZW1zKGxvYWQoKSk7IG5vd3QgPSBub3coKQogICAgd2l0aCBfd2FfbG9jazoKICAgICAgICBvID0gd2FfbG9hZCgpOyBxID0gb1sicXVldWUiXQogICAgICAgIGlmIG5vdCBpdGVtczogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgbm90aGluZyBibG9ja2VkIC0+IGNhbmNlbCBhbnkgdW5zZW50IGRpZ2VzdCwgc3RvcAogICAgICAgICAgICBjaCA9IEZhbHNlCiAgICAgICAgICAgIGZvciBlIGluIHE6CiAgICAgICAgICAgICAgICBpZiBlLmdldCgic2VudEF0IikgaXMgTm9uZSBhbmQgbm90IGUuZ2V0KCJjYW5jZWxlZCIpOiBlWyJjYW5jZWxlZCJdID0gVHJ1ZTsgY2ggPSBUcnVlCiAgICAgICAgICAgIGlmIGNoOiB3YV9zYXZlKG8pCiAgICAgICAgICAgIHJldHVybgogICAgICAgIGlmIGFueShlLmdldCgic2VudEF0IikgaXMgTm9uZSBhbmQgbm90IGUuZ2V0KCJjYW5jZWxlZCIpIGZvciBlIGluIHEpOgogICAgICAgICAgICByZXR1cm4gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgYSBkaWdlc3QgaXMgYWxyZWFkeSBwZW5kaW5nIChkb24ndCBwaWxlIHVwKQogICAgICAgIGxhc3QgPSBtYXgoW2UuZ2V0KCJzZW50QXQiKSBvciAwIGZvciBlIGluIHFdIG9yIFswXSkKICAgICAgICBpZiBsYXN0IGFuZCAobm93dCAtIGxhc3QpIDwgV0FfUkVQSU5HICogMTAwMDogICAgICAjIHNlbnQgb25lIHJlY2VudGx5IC0+IG5leHQgdGljawogICAgICAgICAgICByZXR1cm4KICAgICAgICBxLmFwcGVuZCh7ImlkIjogdWlkKCksICJraW5kIjogImRpZ2VzdCIsICJkZWR1cEtleSI6ICJkaWdlc3QiLCAidGV4dCI6IF9idWlsZF9kaWdlc3QoaXRlbXMpLAogICAgICAgICAgICAgICAgICAiY291bnQiOiBsZW4oaXRlbXMpLCAiY3JlYXRlZCI6IG5vd3QsICJzZW50QXQiOiBOb25lLCAiYXR0ZW1wdHMiOiAwLCAibGFzdEVycm9yIjogIiIsICJjYW5jZWxlZCI6IEZhbHNlfSkKICAgICAgICBvWyJxdWV1ZSJdID0gcVstNTAwOl07IHdhX3NhdmUobykKCmRlZiB3YV9zZW5kKHRleHQpOgogICAgIiIiVEhFIExBU1QgSE9QIOKAlCBoYW5kIHRoZSBtZXNzYWdlIHRvIHRoZSBjb250YWluZXJpemVkIEhlcm1lcyBicmlkZ2Ug4oaSIENFTyBXaGF0c0FwcC4KICAgIEJ1aWxkcyB7Y2hhdElkLCBtZXNzYWdlfSBKU09OIGFuZCBwaXBlcyBpdCB0byBXQV9TRU5EX0NNRCBvbiBzdGRpbi4gUmV0dXJucyAob2ssIGluZm8pLiIiIgogICAgcGF5bG9hZCA9IGpzb24uZHVtcHMoeyJjaGF0SWQiOiBXQV9DSEFUX0pJRCwgIm1lc3NhZ2UiOiB0ZXh0fSkKICAgIHRyeToKICAgICAgICByID0gc3VicHJvY2Vzcy5ydW4oV0FfU0VORF9DTUQsIHNoZWxsPVRydWUsIGlucHV0PXBheWxvYWQsIGNhcHR1cmVfb3V0cHV0PVRydWUsIHRleHQ9VHJ1ZSwgdGltZW91dD0zMCkKICAgICAgICBvdXQgPSAoKHIuc3Rkb3V0IG9yICIiKSArIChyLnN0ZGVyciBvciAiIikpLnN0cmlwKCkKICAgICAgICBvayA9ICcic3VjY2VzcyI6dHJ1ZScgaW4gb3V0LnJlcGxhY2UoIiAiLCAiIikgb3IgJyJtZXNzYWdlaWQiJyBpbiBvdXQubG93ZXIoKQogICAgICAgIHJldHVybiBvaywgb3V0WzoyMDBdCiAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgcmV0dXJuIEZhbHNlLCBzdHIoZSlbOjIwMF0KCmRlZiB3YV9kcmFpbl9vbmNlKCk6CiAgICB3aXRoIF93YV9sb2NrOgogICAgICAgIHBlbmQgPSBbZGljdChlKSBmb3IgZSBpbiB3YV9sb2FkKClbInF1ZXVlIl0gaWYgZS5nZXQoInNlbnRBdCIpIGlzIE5vbmUgYW5kIG5vdCBlLmdldCgiY2FuY2VsZWQiKV0KICAgIGZvciBlIGluIHBlbmQ6CiAgICAgICAgd2l0aCBfd2FfbG9jazogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyByZS1jaGVjazogYSByZWNvbmNpbGUgbWF5IGhhdmUgY2FuY2VsZWQgaXQgKGJsb2NrIGNsZWFyZWQpIHNpbmNlIHRoZSBzbmFwc2hvdAogICAgICAgICAgICBjdXIgPSBuZXh0KCh4IGZvciB4IGluIHdhX2xvYWQoKVsicXVldWUiXSBpZiB4WyJpZCJdID09IGVbImlkIl0pLCBOb25lKQogICAgICAgICAgICBpZiBub3QgY3VyIG9yIGN1ci5nZXQoInNlbnRBdCIpIG9yIGN1ci5nZXQoImNhbmNlbGVkIik6IGNvbnRpbnVlCiAgICAgICAgb2ssIGluZm8gPSB3YV9zZW5kKGVbInRleHQiXSkKICAgICAgICB3aXRoIF93YV9sb2NrOgogICAgICAgICAgICBvID0gd2FfbG9hZCgpOyBjdXIgPSBuZXh0KCh4IGZvciB4IGluIG9bInF1ZXVlIl0gaWYgeFsiaWQiXSA9PSBlWyJpZCJdKSwgTm9uZSkKICAgICAgICAgICAgaWYgbm90IGN1ciBvciBjdXIuZ2V0KCJjYW5jZWxlZCIpOiBjb250aW51ZSAgICAjIGNhbmNlbGVkIG1pZC1zZW5kIC0+IGRvbid0IHJlY29yZCBhcyBzZW50CiAgICAgICAgICAgIGN1clsiYXR0ZW1wdHMiXSA9IGN1ci5nZXQoImF0dGVtcHRzIiwgMCkgKyAxCiAgICAgICAgICAgIGlmIG9rOiBjdXJbInNlbnRBdCJdID0gbm93KCk7IGN1clsiaW5mbyJdID0gaW5mbwogICAgICAgICAgICBlbHNlOiAgY3VyWyJsYXN0RXJyb3IiXSA9IGluZm8KICAgICAgICAgICAgd2Ffc2F2ZShvKQoKZGVmIHdhX2RyYWluX2xvb3AoKToKICAgIHdoaWxlIFRydWU6CiAgICAgICAgdGltZS5zbGVlcChXQV9EUkFJTl9TRUMpCiAgICAgICAgaWYgV0FfRFJBSU5fT046CiAgICAgICAgICAgIHRyeTogd2FfZHJhaW5fb25jZSgpCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IHBhc3MKCmRlZiB3YV93YXRjaGRvZ19sb29wKCk6CiAgICB3aGlsZSBUcnVlOgogICAgICAgIHRpbWUuc2xlZXAoV0FfV0FUQ0hET0cpCiAgICAgICAgdHJ5OiB3YV9yZWNvbmNpbGUoKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IHBhc3MKCmRlZiBhcHBseV9icmFpbnN0b3JtKGQpOgogICAgd2l0aCBfbG9jazoKICAgICAgICBiID0gbG9hZCgpOyB0ID0gYlsidGFza3MiXS5nZXQoZC5nZXQoImlkIikpCiAgICAgICAgaWYgbm90IHQ6IHJldHVybiB7ImVycm9yIjogIm5vIHN1Y2ggdGFzayJ9CiAgICAgICAgcHJldl9icywgcHJldl9zdGF0ZSA9IHQuZ2V0KCJicmFpbnN0b3JtIiwgIiIpLCB0WyJzdGF0ZSJdCiAgICAgICAgd2hvID0gZC5nZXQoImJ5Iikgb3IgImJyYWluc3Rvcm0iCiAgICAgICAgIyB0aGUgd29ya2VyIHBvc3RzIGdlbmVyYXRlZCBjbGFyaWZ5aW5nIHF1ZXN0aW9ucyAoc3RhdGUgc3RheXMgbmVlZHNfYnJhaW5zdG9ybSkKICAgICAgICBpZiAicXVlc3Rpb25zIiBpbiBkIGFuZCBpc2luc3RhbmNlKGRbInF1ZXN0aW9ucyJdLCBsaXN0KToKICAgICAgICAgICAgdFsicXVlc3Rpb25zIl0gPSBbeyJpZCI6IHVpZCgpLCAicSI6IHN0cihxKS5zdHJpcCgpLCAiYW5zd2VyIjogIiIsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAiYXNrZWRBdCI6IG5vdygpLCAiYW5zd2VyZWRBdCI6IE5vbmV9CiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGZvciBxIGluIGRbInF1ZXN0aW9ucyJdIGlmIHN0cihxKS5zdHJpcCgpXQogICAgICAgICAgICB0WyJicmFpbnN0b3JtQXNrZWQiXSA9IFRydWUKICAgICAgICAgICAgbiA9IGxlbih0WyJxdWVzdGlvbnMiXSkKICAgICAgICAgICAgYWRkX2NvbW1lbnQodCwgKGYiYnJhaW5zdG9ybSBnZW5lcmF0ZWQge259IGNsYXJpZnlpbmcgcXVlc3Rpb24ocykg4oCUIGFuc3dlciB0aGVtIGluIHRoZSBjYXJkIHRvIHVuYmxvY2sgdGhpcyB0YXNrLiIKICAgICAgICAgICAgICAgICAgICAgICAgICAgIGlmIG4gZWxzZSAiYnJhaW5zdG9ybTogdGFzayBpcyBjbGVhciBlbm91Z2ggdG8gd29yayDigJQgbm8gb3BlbiBxdWVzdGlvbnMuIiksIHdobywgImJyYWluc3Rvcm0iKQogICAgICAgICAgICBpZiBuOgogICAgICAgICAgICAgICAgdFsibGFzdFN0YXR1cyJdID0gZiJuZWVkcyBicmFpbnN0b3JtIOKAlCB7bn0gcXVlc3Rpb24ocykgYXdhaXRpbmcgdGhlIENFTyIKICAgICAgICBpZiAiYnJhaW5zdG9ybSIgaW4gZDoKICAgICAgICAgICAgdFsiYnJhaW5zdG9ybSJdID0gZC5nZXQoImJyYWluc3Rvcm0iLCB0LmdldCgiYnJhaW5zdG9ybSIsICIiKSkKICAgICAgICAgICAgaWYgdFsiYnJhaW5zdG9ybSJdLnN0cmlwKCkgYW5kIHRbImJyYWluc3Rvcm0iXSAhPSBwcmV2X2JzOgogICAgICAgICAgICAgICAgYWRkX2NvbW1lbnQodCwgdFsiYnJhaW5zdG9ybSJdLCB3aG8sICJicmFpbnN0b3JtIikKICAgICAgICBpZiBkLmdldCgicHJvbW90ZSIpIGFuZCB0WyJzdGF0ZSJdID09ICJuZWVkc19icmFpbnN0b3JtIjoKICAgICAgICAgICAgaWYgbm90IGJyYWluc3Rvcm1fcmVhZHkodCk6CiAgICAgICAgICAgICAgICB1YSA9IGxlbihfdW5hbnN3ZXJlZCh0KSkKICAgICAgICAgICAgICAgIHJldHVybiB7ImVycm9yIjogZiJicmFpbnN0b3JtIGdhdGU6IHt1YX0gdW5hbnN3ZXJlZCBxdWVzdGlvbihzKSDigJQgYW5zd2VyIHRoZW0gYmVmb3JlIHByb21vdGluZyIKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgaWYgdWEgZWxzZSAiYnJhaW5zdG9ybSBnYXRlOiBubyBicmFpbnN0b3JtIGFydGlmYWN0IHlldCJ9CiAgICAgICAgICAgIF9nID0gc3RhdGVfZ2F0ZShiLCB0LCAid29ya2luZyIpICAgICAgICAgICAgICMgaXNzdWUgIzM6IHJlc3BlY3QgdGhlIGhhcmQgZ2F0ZSBvbiBwcm9tb3Rl4oaSd29ya2luZwogICAgICAgICAgICBpZiBfZzogcmV0dXJuIHsiZXJyb3IiOiBfZ30KICAgICAgICAgICAgX2Fzc2VtYmxlX2FydGlmYWN0KHQpCiAgICAgICAgICAgIHRbInN0YXRlIl0gPSAid29ya2luZyI7IHRbImxhc3RTdGF0dXMiXSA9ICIiCiAgICAgICAgaWYgdFsic3RhdGUiXSAhPSBwcmV2X3N0YXRlOgogICAgICAgICAgICBhZGRfY29tbWVudCh0LCBmInN0YXRlOiB7cHJldl9zdGF0ZX0g4oaSIHt0WydzdGF0ZSddfSIsIHdobywgInN0YXRlIikKICAgICAgICB0WyJ1cGRhdGVkIl0gPSBub3coKTsgc2F2ZShiKQogICAgICAgIHJlcyA9IHsib2siOiBUcnVlLCAic3RhdGUiOiB0WyJzdGF0ZSJdLCAicmVhZHkiOiBicmFpbnN0b3JtX3JlYWR5KHQpLCAidW5hbnN3ZXJlZCI6IGxlbihfdW5hbnN3ZXJlZCh0KSl9CiAgICB3YV9yZWNvbmNpbGUoKSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBxdWVzdGlvbnMgcG9zdGVkIChicmFpbnN0b3JtLXBlbmRpbmcpIC0+IGVucXVldWUgV2hhdHNBcHAgKHNsaWNlIGUpCiAgICByZXR1cm4gcmVzCgpkZWYgYXBwbHlfYW5zd2VyKGQpOgogICAgIiIiQ0VPIGFuc3dlcnMgYSBnZW5lcmF0ZWQgYnJhaW5zdG9ybSBxdWVzdGlvbiBpbiB0aGUgY2FyZC4gV2hlbiB0aGUgbGFzdCBvbmUgaXMgYW5zd2VyZWQsCiAgICB0aGUgYXJ0aWZhY3QgaXMgYXNzZW1ibGVkIGFuZCB0aGUgdGFzayBiZWNvbWVzIHByb21vdGFibGUgKHN0aWxsIG5lZWRzX2JyYWluc3Rvcm0gdW50aWwgcHJvbW90ZWQpLiIiIgogICAgd2l0aCBfbG9jazoKICAgICAgICBiID0gbG9hZCgpOyB0ID0gYlsidGFza3MiXS5nZXQoZC5nZXQoInRhc2tfaWQiKSBvciBkLmdldCgiaWQiKSkKICAgICAgICBpZiBub3QgdDogcmV0dXJuIHsiZXJyb3IiOiAibm8gc3VjaCB0YXNrIn0KICAgICAgICBxaWQsIGFucyA9IGQuZ2V0KCJxaWQiKSwgKGQuZ2V0KCJhbnN3ZXIiKSBvciAiIikuc3RyaXAoKQogICAgICAgIHEgPSBuZXh0KCh4IGZvciB4IGluIHQuZ2V0KCJxdWVzdGlvbnMiLCBbXSkgaWYgeC5nZXQoImlkIikgPT0gcWlkKSwgTm9uZSkKICAgICAgICBpZiBub3QgcTogcmV0dXJuIHsiZXJyb3IiOiAibm8gc3VjaCBxdWVzdGlvbiJ9CiAgICAgICAgaWYgbm90IGFuczogcmV0dXJuIHsiZXJyb3IiOiAiZW1wdHkgYW5zd2VyIn0KICAgICAgICBxWyJhbnN3ZXIiXSA9IGFuczsgcVsiYW5zd2VyZWRBdCJdID0gbm93KCkKICAgICAgICBhZGRfY29tbWVudCh0LCBmIlE6IHtxLmdldCgncScsJycpLnN0cmlwKCl9XG5BOiB7YW5zfSIsIGQuZ2V0KCJieSIsICJDRU8iKSwgImNvbW1lbnQiKQogICAgICAgIHVhID0gbGVuKF91bmFuc3dlcmVkKHQpKQogICAgICAgIGlmIHVhID09IDA6CiAgICAgICAgICAgIF9hc3NlbWJsZV9hcnRpZmFjdCh0KQogICAgICAgICAgICB0WyJsYXN0U3RhdHVzIl0gPSAiYnJhaW5zdG9ybSBhbnN3ZXJlZCDigJQgcmVhZHkgdG8gcHJvbW90ZSB0byB3b3JraW5nIgogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHRbImxhc3RTdGF0dXMiXSA9IGYibmVlZHMgYnJhaW5zdG9ybSDigJQge3VhfSBxdWVzdGlvbihzKSBzdGlsbCBhd2FpdGluZyB0aGUgQ0VPIgogICAgICAgIHRbInVwZGF0ZWQiXSA9IG5vdygpOyBzYXZlKGIpICAgICAgICAgICAgICAgIyBwZXJzaXN0IHRoZSBhbnN3ZXIgQkVGT1JFIHBpbmdpbmcgKGJvc3NfcGluZyByZWxvYWRzIGZyb20gZGlzaykKICAgIHdhX3JlY29uY2lsZSgpICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIGFuIGFuc3dlciBtYXkgY2xlYXIgdGhlIGJyYWluc3Rvcm0gYmxvY2sgLT4gY2FuY2VsIGl0cyBXaGF0c0FwcCBwaW5nIChzbGljZSBlKQogICAgaWYgdWEgPT0gMDogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgcGluZyBvdXRzaWRlIHRoZSBsb2NrOyBpdCByZWxvYWRzIHRoZSBqdXN0LXNhdmVkIHN0YXRlCiAgICAgICAgYm9zc19waW5nKGQuZ2V0KCJ0YXNrX2lkIikgb3IgZC5nZXQoImlkIiksICJicmFpbnN0b3JtIGdhdGUgY2xlYXJlZCDigJQgYWxsIHF1ZXN0aW9ucyBhbnN3ZXJlZDsgcHJvbW90ZSB0byB3b3JraW5nIikKICAgIHJldHVybiB7Im9rIjogVHJ1ZSwgInVuYW5zd2VyZWQiOiB1YSwgInJlYWR5IjogVHJ1ZSBpZiB1YSA9PSAwIGVsc2UgRmFsc2V9CgpkZWYgYXBwbHlfc3RhdHVzKGQpOgogICAgd2l0aCBfbG9jazoKICAgICAgICBiID0gbG9hZCgpOyB0ID0gYlsidGFza3MiXS5nZXQoZC5nZXQoImlkIikpCiAgICAgICAgaWYgbm90IHQ6IHJldHVybiB7ImVycm9yIjogIm5vIHN1Y2ggdGFzayJ9CiAgICAgICAgd2hvID0gZC5nZXQoImJ5Iikgb3IgdC5nZXQoImFzc2lnbmVlIikgb3IgImVuZ2luZWVyIgogICAgICAgIHByZXZfc3RhdGUgPSB0WyJzdGF0ZSJdCiAgICAgICAgaWYgImxhc3RTdGF0dXMiIGluIGQ6CiAgICAgICAgICAgIHRbImxhc3RTdGF0dXMiXSA9IGRbImxhc3RTdGF0dXMiXQogICAgICAgICAgICBhZGRfY29tbWVudCh0LCBkWyJsYXN0U3RhdHVzIl0sIHdobywgInN0YXR1cyIpICAgIyBlbmdpbmVlcidzIHZvaWNlIC0+IGR1cmFibGUgdGhyZWFkIGV2ZW50CiAgICAgICAgaWYgInZlcmlmaWVkIiBpbiBkOiB0WyJ2ZXJpZmllZCJdID0gYm9vbChkWyJ2ZXJpZmllZCJdKQogICAgICAgIGlmICJzdGF0ZSIgaW4gZDoKICAgICAgICAgICAgaWYgZFsic3RhdGUiXSBub3QgaW4gVkFMSURfU1RBVEVTOgogICAgICAgICAgICAgICAgcmV0dXJuIHsiZXJyb3IiOiBmImludmFsaWQgc3RhdGUge2RbJ3N0YXRlJ10hcn0gKGFsbG93ZWQ6IHtzb3J0ZWQoVkFMSURfU1RBVEVTKX0pIn0KICAgICAgICAgICAgaWYgZFsic3RhdGUiXSA9PSAiZG9uZSI6CiAgICAgICAgICAgICAgICAjIFJ1bGUgMjE6IE9OTFkgdGhlIENFTyBtYXJrcyBkb25lIOKAlCBoaXMgYWN0aW9uIElTIHRoZSBzaWduLW9mZiArIHZlcmlmaWNhdGlvbiwgaW4gT05FCiAgICAgICAgICAgICAgICAjIHN0ZXAgZnJvbSBBTlkgc3RhdGUgKHdvcmtpbmcgLyBuZWVkc19icmFpbnN0b3JtIC8gYmxvY2tlZCAvIHJldmlldykuIFRoZSBBSS9lbmdpbmVlcgogICAgICAgICAgICAgICAgIyBjYW4gbW92ZSBhIGNhcmQgVVAgVE8gJ3JldmlldycgZm9yIENFTyBzaWduLW9mZiBidXQgY2FuIE5FVkVSIHNldCAnZG9uZScgKHRoZSBnYXRlCiAgICAgICAgICAgICAgICAjIGV4aXN0cyBzb2xlbHkgdG8gc3RvcCB0aGUgQUkgYXV0by1jbG9zaW5nIHVucmVhZHkgd29yayDigJQgaXQgbXVzdCBub3QgZ2F0ZSB0aGUgQ0VPKS4KICAgICAgICAgICAgICAgIGlmIHN0cihkLmdldCgiYnkiLCAiIikpLnN0cmlwKCkudXBwZXIoKSA9PSAiQ0VPIjoKICAgICAgICAgICAgICAgICAgICB0WyJ2ZXJpZmllZCJdID0gVHJ1ZQogICAgICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgICAgICByZXR1cm4geyJlcnJvciI6ICJvbmx5IHRoZSBDRU8gbWFya3MgZG9uZSDigJQgQUkvZW5naW5lZXIgY2FuIG1vdmUgYSBjYXJkIHVwIHRvICdyZXZpZXcnIGZvciBDRU8gc2lnbi1vZmYsIG5ldmVyIHRvICdkb25lJyJ9CiAgICAgICAgICAgIF9nID0gc3RhdGVfZ2F0ZShiLCB0LCBkWyJzdGF0ZSJdKSAgICAgICAgICAgICMgaXNzdWUgIzM6IHN1YnRhc2svZGVwZW5kZW5jeSArIGhhcmQtZ2F0ZSBndWFyZHJhaWxzCiAgICAgICAgICAgIGlmIF9nOiByZXR1cm4geyJlcnJvciI6IF9nfQogICAgICAgICAgICB0WyJzdGF0ZSJdID0gZFsic3RhdGUiXQogICAgICAgIGlmIGQuZ2V0KCJjZW9HYXRlZCIpOiAgICAgICAgICAgIyBlbmdpbmVlciBzaWduYWxzIGRvbmUtcGVuZGluZy1DRU8gLT4gYmxvY2tlZCAoQ0VPIHdpbmRvdy9kZWNpc2lvbiBnYXRlcyBpdCkKICAgICAgICAgICAgdFsic3RhdGUiXSA9ICJibG9ja2VkIiAgICAgICMgdGhlIHdhdGNoZG9nICsgdW5hc3NpZ25lZCBjcm9uIHNraXAgJ2Jsb2NrZWQnIC0+IG5vIGZhbHNlIHN0YWxsLW5hZwogICAgICAgIGlmIHRbInN0YXRlIl0gIT0gcHJldl9zdGF0ZToKICAgICAgICAgICAgYWRkX2NvbW1lbnQodCwgZiJzdGF0ZToge3ByZXZfc3RhdGV9IOKGkiB7dFsnc3RhdGUnXX0iLCB3aG8sICJzdGF0ZSIpCiAgICAgICAgdFsidXBkYXRlZCJdID0gbm93KCk7IHNhdmUoYikKICAgICAgICByZXRpcmUgPSAocHJldl9zdGF0ZSwgZGljdCh0KSkgaWYgKHRbInN0YXRlIl0gPT0gImRvbmUiIGFuZCBwcmV2X3N0YXRlICE9ICJkb25lIikgZWxzZSBOb25lCiAgICB3YV9yZWNvbmNpbGUoKSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBDRU8tYmxvY2tlZD8gKHJldmlldy9ibG9ja2VkKSAtPiBlbnF1ZXVlIFdoYXRzQXBwIChzbGljZSBlKQogICAgaWYgcmV0aXJlOiByZXRpcmVfb25fZG9uZShyZXRpcmVbMF0sIHJldGlyZVsxXSkgICMgT1VUU0lERSBfbG9jazogQ0VPIOKGkmRvbmUg4oaSIHJldGlyZSB0aGUgYXNzaWduZWUgKG1wIGtpbGwpICsgZXZlbnQgdGhlIEJvc3MKICAgIHJldHVybiB7Im9rIjogVHJ1ZSwgInN0YXRlIjogdFsic3RhdGUiXX0KCmRlZiBhcHBseV9wcm9vZihkKToKICAgIHdpdGggX2xvY2s6CiAgICAgICAgYiA9IGxvYWQoKTsgdGlkID0gZC5nZXQoInRhc2tfaWQiKTsgdCA9IGJbInRhc2tzIl0uZ2V0KHRpZCkKICAgICAgICBpZiBub3QgdDogcmV0dXJuIHsiZXJyb3IiOiAibm8gc3VjaCB0YXNrIn0KICAgICAgICBwdHlwZSA9IGQuZ2V0KCJ0eXBlIiwgInRleHQiKTsgcmVmID0gZC5nZXQoInJlZiIsICIiKTsgcGlkID0gdWlkKCkKICAgICAgICBpZiBwdHlwZSBpbiAoImltYWdlIiwgInZpZGVvIikgYW5kIGQuZ2V0KCJkYXRhX2I2NCIpOgogICAgICAgICAgICBQRCA9IFBST09GX0RJUiAvIHRpZDsgUEQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgICAgICAgICBleHQgPSAoZC5nZXQoImV4dCIpIG9yICgicG5nIiBpZiBwdHlwZSA9PSAiaW1hZ2UiIGVsc2UgIm1wNCIpKS5sc3RyaXAoIi4iKQogICAgICAgICAgICByYXcgPSBkWyJkYXRhX2I2NCJdCiAgICAgICAgICAgIGlmIHJhdy5zdGFydHN3aXRoKCJkYXRhOiIpOiByYXcgPSByYXcuc3BsaXQoIiwiLCAxKVsxXSAgICMgc3RyaXAgZGF0YS1VUkwgcHJlZml4CiAgICAgICAgICAgIGZwID0gUEQgLyBmIntwaWR9LntleHR9IjsgZnAud3JpdGVfYnl0ZXMoYmFzZTY0LmI2NGRlY29kZShyYXcpKQogICAgICAgICAgICByZWYgPSBmIi90b2RvL3Byb29mL3t0aWR9L3twaWR9LntleHR9IiAgICMgYSBTRVJWRUQgdXJsLCBub3QgYSBmaWxlc3lzdGVtIHBhdGgKICAgICAgICBlbGlmIHB0eXBlIGluICgiaW1hZ2UiLCAidmlkZW8iKSBhbmQgcmVmIGFuZCBub3QgcmVmLnN0YXJ0c3dpdGgoIi90b2RvL3Byb29mLyIpOgogICAgICAgICAgICB1cmwgPSBfaW5nZXN0X2ZpbGUodGlkLCBwaWQsIHB0eXBlLCByZWYpICAgIyBhdHRhY2hlZCBieSBwYXRoL2ZpbGU6Ly8gLT4gY29weSBpbiArIHNlcnZlCiAgICAgICAgICAgIGlmIHVybDogcmVmID0gdXJsCiAgICAgICAgcHJvb2YgPSB7ImlkIjogcGlkLCAidHlwZSI6IHB0eXBlLCAicmVmIjogcmVmLCAiY2FwdGlvbiI6IGQuZ2V0KCJjYXB0aW9uIiwgIiIpLAogICAgICAgICAgICAgICAgICJieSI6IGQuZ2V0KCJieSIsICJlbmdpbmVlciIpLCAidHMiOiBub3coKX0KICAgICAgICB0WyJwcm9vZnMiXS5hcHBlbmQocHJvb2YpOyB0WyJ1cGRhdGVkIl0gPSBub3coKTsgc2F2ZShiKQogICAgICAgIHJldHVybiB7Im9rIjogVHJ1ZSwgInByb29mX2lkIjogcGlkfQoKIyDilIDilIAgSFRUUCDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKY2xhc3MgSChodHRwLnNlcnZlci5CYXNlSFRUUFJlcXVlc3RIYW5kbGVyKToKICAgIGRlZiBsb2dfbWVzc2FnZShzZWxmLCAqYSk6IHBhc3MKICAgIGRlZiBfc2VuZChzZWxmLCBjb2RlLCBib2R5LCBjdHlwZT0iYXBwbGljYXRpb24vanNvbiIpOgogICAgICAgIGlmIGlzaW5zdGFuY2UoYm9keSwgKGRpY3QsIGxpc3QpKTogYm9keSA9IGpzb24uZHVtcHMoYm9keSkuZW5jb2RlKCkKICAgICAgICBlbGlmIGlzaW5zdGFuY2UoYm9keSwgc3RyKTogYm9keSA9IGJvZHkuZW5jb2RlKCkKICAgICAgICBzZWxmLnNlbmRfcmVzcG9uc2UoY29kZSk7IHNlbGYuc2VuZF9oZWFkZXIoIkNvbnRlbnQtVHlwZSIsIGN0eXBlKQogICAgICAgIHNlbGYuc2VuZF9oZWFkZXIoIkNvbnRlbnQtTGVuZ3RoIiwgc3RyKGxlbihib2R5KSkpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQ2FjaGUtQ29udHJvbCIsICJuby1jYWNoZSwgbm8tc3RvcmUsIG11c3QtcmV2YWxpZGF0ZSIpICAjIG5ldmVyIGNhY2hlIHRoZSBib2FyZCBIVE1ML0pTT04g4oCUIHRoZSBDRU8gbXVzdCBhbHdheXMgZ2V0IHRoZSBsYXRlc3QgYm9hcmQgSlMgKHN0YWxlIEpTID0gdGhlIG1vZGFsIGJ1ZyBoZSBrZXB0IGhpdHRpbmcpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQWNjZXNzLUNvbnRyb2wtQWxsb3ctT3JpZ2luIiwgIioiKQogICAgICAgIHNlbGYuc2VuZF9oZWFkZXIoIkFjY2Vzcy1Db250cm9sLUFsbG93LUhlYWRlcnMiLCAiQ29udGVudC1UeXBlLFgtUXVldWUtU2VjcmV0IikKICAgICAgICBzZWxmLmVuZF9oZWFkZXJzKCk7IHNlbGYud2ZpbGUud3JpdGUoYm9keSkKICAgIGRlZiBfc2VydmVfYnl0ZXMoc2VsZiwgZGF0YSwgY3R5cGUpOgogICAgICAgICIiIlNlcnZlIGEgYmluYXJ5IHdpdGggSFRUUCBSYW5nZSBzdXBwb3J0IHNvIDx2aWRlbz4gY2FuIHNlZWsgKENFTzogd2F0Y2ggcHJvb2Ygb24gdGhlIGJvYXJkKS4iIiIKICAgICAgICB0b3RhbCA9IGxlbihkYXRhKTsgcm5nID0gc2VsZi5oZWFkZXJzLmdldCgiUmFuZ2UiLCAiIik7IHBhcnRpYWwgPSBGYWxzZTsgc3RhcnQsIGVuZCA9IDAsIHRvdGFsIC0gMQogICAgICAgIGlmIHJuZy5zdGFydHN3aXRoKCJieXRlcz0iKToKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgcywgXywgZSA9IHJuZ1s2Ol0ucGFydGl0aW9uKCItIikKICAgICAgICAgICAgICAgIHN0YXJ0ID0gaW50KHMpIGlmIHMgZWxzZSAwCiAgICAgICAgICAgICAgICBlbmQgPSBpbnQoZSkgaWYgZSBlbHNlIHRvdGFsIC0gMQogICAgICAgICAgICAgICAgaWYgMCA8PSBzdGFydCA8PSBlbmQgPCB0b3RhbDogcGFydGlhbCA9IFRydWUKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogcGFydGlhbCA9IEZhbHNlCiAgICAgICAgY2h1bmsgPSBkYXRhW3N0YXJ0OmVuZCArIDFdIGlmIHBhcnRpYWwgZWxzZSBkYXRhCiAgICAgICAgc2VsZi5zZW5kX3Jlc3BvbnNlKDIwNiBpZiBwYXJ0aWFsIGVsc2UgMjAwKQogICAgICAgIHNlbGYuc2VuZF9oZWFkZXIoIkNvbnRlbnQtVHlwZSIsIGN0eXBlKQogICAgICAgIHNlbGYuc2VuZF9oZWFkZXIoIkFjY2VwdC1SYW5nZXMiLCAiYnl0ZXMiKQogICAgICAgIGlmIHBhcnRpYWw6IHNlbGYuc2VuZF9oZWFkZXIoIkNvbnRlbnQtUmFuZ2UiLCBmImJ5dGVzIHtzdGFydH0te2VuZH0ve3RvdGFsfSIpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1MZW5ndGgiLCBzdHIobGVuKGNodW5rKSkpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQWNjZXNzLUNvbnRyb2wtQWxsb3ctT3JpZ2luIiwgIioiKQogICAgICAgIHNlbGYuZW5kX2hlYWRlcnMoKQogICAgICAgIHRyeTogc2VsZi53ZmlsZS53cml0ZShjaHVuaykKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiBwYXNzCiAgICBkZWYgX2F1dGgoc2VsZik6CiAgICAgICAgcmV0dXJuIChub3QgU0VDUkVUKSBvciBzZWxmLmhlYWRlcnMuZ2V0KCJYLVF1ZXVlLVNlY3JldCIsICIiKSA9PSBTRUNSRVQKICAgIGRlZiBfYm9keShzZWxmKToKICAgICAgICBuID0gaW50KHNlbGYuaGVhZGVycy5nZXQoIkNvbnRlbnQtTGVuZ3RoIiwgIjAiKSBvciAwKQogICAgICAgIHRyeTogcmV0dXJuIGpzb24ubG9hZHMoc2VsZi5yZmlsZS5yZWFkKG4pIG9yIGIie30iKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IHJldHVybiB7fQogICAgZGVmIGRvX09QVElPTlMoc2VsZik6IHNlbGYuX3NlbmQoMjA0LCBiIiIsICJ0ZXh0L3BsYWluIikKICAgIGRlZiBkb19HRVQoc2VsZik6CiAgICAgICAgcCA9IHNlbGYucGF0aC5zcGxpdCgiPyIsIDEpWzBdCiAgICAgICAgaWYgcCA9PSAiL2hlYWx0aCI6IHJldHVybiBzZWxmLl9zZW5kKDIwMCwgeyJzdGF0dXMiOiAib2siLCAic2VydmljZSI6ICJ0b2RvIiwgImJ1aWxkIjogX2J1aWxkX3N0YW1wKCl9KQogICAgICAgIGlmIHAgaW4gKCIvdG9kb3MiLCAiL3RvZG9zLyIsICIvIik6CiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIGh0bWwgPSBIVE1MX1BBVEgucmVhZF90ZXh0KCkucmVwbGFjZSgiX19RVUVVRV9TRUNSRVRfXyIsIFNFQ1JFVCkucmVwbGFjZSgiX19CVUlMRF9fIiwgX2J1aWxkX3N0YW1wKCkpCiAgICAgICAgICAgICAgICByZXR1cm4gc2VsZi5fc2VuZCgyMDAsIGh0bWwsICJ0ZXh0L2h0bWw7IGNoYXJzZXQ9dXRmLTgiKQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6IHJldHVybiBzZWxmLl9zZW5kKDUwMCwgeyJlcnJvciI6IGYiaHRtbDoge2V9In0pCiAgICAgICAgaWYgcC5zdGFydHN3aXRoKCIvdG9kby9wcm9vZi8iKTogICAgICMgc2VydmUgcHJvb2YgYmluYXJpZXMgKHB1YmxpYywgc28gPGltZyBzcmM+IHdvcmtzKQogICAgICAgICAgICBzZWcgPSBwW2xlbigiL3RvZG8vcHJvb2YvIik6XS5zdHJpcCgiLyIpLnNwbGl0KCIvIikKICAgICAgICAgICAgaWYgbGVuKHNlZykgPT0gMiBhbmQgc2VnWzFdIGFuZCAiLi4iIG5vdCBpbiBzZWdbMF0gYW5kICIuLiIgbm90IGluIHNlZ1sxXToKICAgICAgICAgICAgICAgIGZwID0gUFJPT0ZfRElSIC8gc2VnWzBdIC8gc2VnWzFdCiAgICAgICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICAgICAgZGF0YSA9IGZwLnJlYWRfYnl0ZXMoKQogICAgICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogcmV0dXJuIHNlbGYuX3NlbmQoNDA0LCB7ImVycm9yIjogIm5vIHN1Y2ggcHJvb2YifSkKICAgICAgICAgICAgICAgIGV4dCA9IGZwLnN1ZmZpeC5sb3dlcigpLmxzdHJpcCgiLiIpCiAgICAgICAgICAgICAgICBjdHlwZSA9IHsicG5nIjoiaW1hZ2UvcG5nIiwianBnIjoiaW1hZ2UvanBlZyIsImpwZWciOiJpbWFnZS9qcGVnIiwiZ2lmIjoiaW1hZ2UvZ2lmIiwKICAgICAgICAgICAgICAgICAgICAgICAgICJ3ZWJwIjoiaW1hZ2Uvd2VicCIsInN2ZyI6ImltYWdlL3N2Zyt4bWwiLCJtcDQiOiJ2aWRlby9tcDQiLCJ3ZWJtIjoidmlkZW8vd2VibSIsCiAgICAgICAgICAgICAgICAgICAgICAgICAibW92IjoidmlkZW8vcXVpY2t0aW1lIn0uZ2V0KGV4dCwgImFwcGxpY2F0aW9uL29jdGV0LXN0cmVhbSIpCiAgICAgICAgICAgICAgICByZXR1cm4gc2VsZi5fc2VydmVfYnl0ZXMoZGF0YSwgY3R5cGUpICAgIyBSYW5nZS1hd2FyZSAtPiBpbmxpbmUgdmlkZW8gcGxheWJhY2sgKyBzZWVraW5nCiAgICAgICAgICAgIHJldHVybiBzZWxmLl9zZW5kKDQwNCwgeyJlcnJvciI6ICJiYWQgcHJvb2YgcGF0aCJ9KQogICAgICAgIGlmIHAgPT0gIi90b2RvL2JvYXJkIjoKICAgICAgICAgICAgaWYgbm90IHNlbGYuX2F1dGgoKTogcmV0dXJuIHNlbGYuX3NlbmQoNDAzLCB7ImVycm9yIjogInVuYXV0aG9yaXplZCJ9KQogICAgICAgICAgICB3aXRoIF9sb2NrOiBiID0gbWlncmF0ZV9wcm9vZnMobG9hZCgpKQogICAgICAgICAgICBiID0gZGljdChiKTsgYlsiYnVpbGQiXSA9IF9idWlsZF9zdGFtcCgpICAgICAgIyBjbGllbnQgYXV0by1yZWxvYWRzIGlmIHRoZSBzZXJ2ZWQgSFRNTCBidWlsZCBjaGFuZ2VkIChraWxscyBzdGFsZS1KUyBidWdzKQogICAgICAgICAgICByZXR1cm4gc2VsZi5fc2VuZCgyMDAsIGIpCiAgICAgICAgaWYgcCA9PSAiL3RvZG8vYXR0YWNoIjogICAgICAgICAgICAgICAjIHJlc29sdmUgYW4gYXNzaWduZWUgLT4gdHR5ZCBhdHRhY2ggdGFyZ2V0IChzbGljZSBjKQogICAgICAgICAgICBpZiBub3Qgc2VsZi5fYXV0aCgpOiByZXR1cm4gc2VsZi5fc2VuZCg0MDMsIHsiZXJyb3IiOiAidW5hdXRob3JpemVkIn0pCiAgICAgICAgICAgIGFnZW50ID0gKHBhcnNlX3FzKHVybHBhcnNlKHNlbGYucGF0aCkucXVlcnkpLmdldCgiYWdlbnQiKSBvciBbIiJdKVswXQogICAgICAgICAgICByZXR1cm4gc2VsZi5fc2VuZCgyMDAsIHJlc29sdmVfYXR0YWNoKGFnZW50KSkKICAgICAgICBpZiBwID09ICIvdG9kby93YSI6ICAgICAgICAgICAgICAgICAgICMgaW5zcGVjdCB0aGUgV2hhdHNBcHAgb3V0Ym94IChzbGljZSBlKQogICAgICAgICAgICBpZiBub3Qgc2VsZi5fYXV0aCgpOiByZXR1cm4gc2VsZi5fc2VuZCg0MDMsIHsiZXJyb3IiOiAidW5hdXRob3JpemVkIn0pCiAgICAgICAgICAgIHdpdGggX3dhX2xvY2s6IG8gPSB3YV9sb2FkKCkKICAgICAgICAgICAgcGVuZCA9IFtlIGZvciBlIGluIG9bInF1ZXVlIl0gaWYgZS5nZXQoInNlbnRBdCIpIGlzIE5vbmUgYW5kIG5vdCBlLmdldCgiY2FuY2VsZWQiKV0KICAgICAgICAgICAgcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCB7ImppZCI6IFdBX0NIQVRfSklELCAiZHJhaW4iOiBXQV9EUkFJTl9PTiwgInBlbmRpbmciOiBsZW4ocGVuZCksCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICJxdWV1ZSI6IG9bInF1ZXVlIl1bLTUwOl19KQogICAgICAgIHJldHVybiBzZWxmLl9zZW5kKDQwNCwgeyJlcnJvciI6ICJub3QgZm91bmQifSkKICAgIGRlZiBkb19QT1NUKHNlbGYpOgogICAgICAgIHAgPSBzZWxmLnBhdGguc3BsaXQoIj8iLCAxKVswXQogICAgICAgIGlmIHAgPT0gIi9ob29rL3N0b3AiOiAgICAgICAgICAgICMgdXNlZCBieSB0aGUgc3RvcC1ob29rIGJyaWRnZSAvIHNpbS1zdG9wLWhvb2sKICAgICAgICAgICAgZCA9IHNlbGYuX2JvZHkoKTsgb25fc3RvcF9ob29rKGQuZ2V0KCJhZ2VudCIsICIiKSwgZC5nZXQoInN0YXRlIiwgImlkbGUiKSkKICAgICAgICAgICAgcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCB7Im9rIjogVHJ1ZX0pCiAgICAgICAgaWYgbm90IHNlbGYuX2F1dGgoKTogcmV0dXJuIHNlbGYuX3NlbmQoNDAzLCB7ImVycm9yIjogImZvcmJpZGRlbiJ9KQogICAgICAgIGQgPSBzZWxmLl9ib2R5KCkKICAgICAgICBpZiBwID09ICIvdG9kby91cGRhdGUiOiAgICAgcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCBhcHBseV91cGRhdGUoZCkpCiAgICAgICAgaWYgcCA9PSAiL3RvZG8vYnJhaW5zdG9ybSI6IHJldHVybiBzZWxmLl9zZW5kKDIwMCwgYXBwbHlfYnJhaW5zdG9ybShkKSkKICAgICAgICBpZiBwID09ICIvdG9kby9zdGF0dXMiOiAgICAgcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCBhcHBseV9zdGF0dXMoZCkpCiAgICAgICAgaWYgcCA9PSAiL3RvZG8vcHJvb2YiOiAgICAgIHJldHVybiBzZWxmLl9zZW5kKDIwMCwgYXBwbHlfcHJvb2YoZCkpCiAgICAgICAgaWYgcCA9PSAiL3RvZG8vY29tbWVudCI6ICAgIHJldHVybiBzZWxmLl9zZW5kKDIwMCwgYXBwbHlfY29tbWVudChkKSkKICAgICAgICBpZiBwID09ICIvdG9kby9hbnN3ZXIiOiAgICAgcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCBhcHBseV9hbnN3ZXIoZCkpCiAgICAgICAgaWYgcCA9PSAiL3RvZG8vd2EvdGVzdCI6ICAgICMgZW5xdWV1ZSBhIG9uZS1vZmYgbWVzc2FnZSAocHJvb2YgLyBzbW9rZSkgLT4gZHJhaW5lZCB0byBDRU8gV2hhdHNBcHAKICAgICAgICAgICAgdHh0ID0gKGQuZ2V0KCJ0ZXh0Iikgb3IgIkJvYXJkIHRlc3QgcGluZy4iKS5zdHJpcCgpCiAgICAgICAgICAgIHdpdGggX3dhX2xvY2s6CiAgICAgICAgICAgICAgICBvID0gd2FfbG9hZCgpOyBvWyJxdWV1ZSJdLmFwcGVuZCh7ImlkIjogdWlkKCksICJ0YXNrX2lkIjogTm9uZSwgImtpbmQiOiAidGVzdCIsCiAgICAgICAgICAgICAgICAgICAgImRlZHVwS2V5IjogZiJ0ZXN0Ont1aWQoKX0iLCAidGV4dCI6IHR4dCwgImNyZWF0ZWQiOiBub3coKSwgInNlbnRBdCI6IE5vbmUsCiAgICAgICAgICAgICAgICAgICAgImF0dGVtcHRzIjogMCwgImxhc3RFcnJvciI6ICIiLCAiY2FuY2VsZWQiOiBGYWxzZX0pOyB3YV9zYXZlKG8pCiAgICAgICAgICAgIHJldHVybiBzZWxmLl9zZW5kKDIwMCwgeyJvayI6IFRydWUsICJlbnF1ZXVlZCI6IHR4dH0pCiAgICAgICAgaWYgcCA9PSAiL3RvZG8vd2EvZHJhaW4iOiAgIHRocmVhZGluZy5UaHJlYWQodGFyZ2V0PXdhX2RyYWluX29uY2UsIGRhZW1vbj1UcnVlKS5zdGFydCgpOyByZXR1cm4gc2VsZi5fc2VuZCgyMDAsIHsib2siOiBUcnVlfSkKICAgICAgICByZXR1cm4gc2VsZi5fc2VuZCg0MDQsIHsiZXJyb3IiOiAibm90IGZvdW5kIn0pCgpjbGFzcyBTZXJ2ZXIoaHR0cC5zZXJ2ZXIuVGhyZWFkaW5nSFRUUFNlcnZlcik6CiAgICBkYWVtb25fdGhyZWFkcyA9IFRydWU7IGFsbG93X3JldXNlX2FkZHJlc3MgPSBUcnVlCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgVE9ET19ESVIubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgaWYgbm90IEJPQVJEX1BBVEguZXhpc3RzKCk6IHNhdmUoX2RlZmF1bHRfYm9hcmQoKSkKICAgIHRocmVhZGluZy5UaHJlYWQodGFyZ2V0PWNyb25fbG9vcCwgZGFlbW9uPVRydWUpLnN0YXJ0KCkKICAgIHRocmVhZGluZy5UaHJlYWQodGFyZ2V0PXdhdGNoZG9nX2xvb3AsIGRhZW1vbj1UcnVlKS5zdGFydCgpCiAgICBpZiBXQV9EUkFJTl9PTjogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBzbGljZSBlOiBDRU8tYmxvY2tlZCB3YXRjaGRvZyArIFdoYXRzQXBwIGRyYWluIHBhcnRpY2lwYW50CiAgICAgICAgdGhyZWFkaW5nLlRocmVhZCh0YXJnZXQ9d2Ffd2F0Y2hkb2dfbG9vcCwgZGFlbW9uPVRydWUpLnN0YXJ0KCkKICAgICAgICB0aHJlYWRpbmcuVGhyZWFkKHRhcmdldD13YV9kcmFpbl9sb29wLCBkYWVtb249VHJ1ZSkuc3RhcnQoKQogICAgcHJpbnQoZiJ0b2RvIDp7UE9SVH0gIHN0b3JlPXtCT0FSRF9QQVRIfSAgY3Jvbj17UElOR19DUk9OfXMgZ3JhY2U9e0lETEVfR1JBQ0V9cyAiCiAgICAgICAgICBmInN0YWxsPXtJRExFX1NUQUxMfXMvc2NhbntXQVRDSERPR31zIHNpbms9eydmaWxlJyBpZiBURVNUX1NJTksgZWxzZSAnbXAnfSAiCiAgICAgICAgICBmIndhPXsnb27ihpInK1dBX0NIQVRfSklEIGlmIFdBX0RSQUlOX09OIGVsc2UgJ29mZid9IiwgZmx1c2g9VHJ1ZSkKICAgIFNlcnZlcigoIjAuMC4wLjAiLCBQT1JUKSwgSCkuc2VydmVfZm9yZXZlcigpCg== | base64 -d > "$INSTALL_DIR/bin/todo-server.py"
echo PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAiPgo8dGl0bGU+UGxvdyDigJQgUHJpb3JpdGllcyAoVE9ETyk8L3RpdGxlPgo8bGluayBocmVmPSJodHRwczovL2ZvbnRzLmdvb2dsZWFwaXMuY29tL2NzczI/ZmFtaWx5PURNK01vbm86d2dodEA0MDA7NTAwOzcwMCZmYW1pbHk9RE0rU2FuczppdGFsLHdnaHRAMCwzMDA7MCw0MDA7MCw1MDA7MCw2MDA7MCw3MDA7MSw0MDAmZmFtaWx5PUluc3RydW1lbnQrU2VyaWY6aXRhbEAwOzEmZGlzcGxheT1zd2FwIiByZWw9InN0eWxlc2hlZXQiPgo8c3R5bGU+Cjpyb290ewogIC0tbWlkbmlnaHQ6IzAxMDAwQTsgLS12b2x0OiNENUVGOEE7IC0tZ3JvdmU6IzVlN2E1ZTsgLS1pcmlzOiNDNEJGRkY7CiAgLS1kYXJrLWJnOiMxMTExMTA7IC0tZGFyay1ib3JkZXI6cmdiYSgyNTUsMjU1LDI1NSwwLjA5KTsKICAtLXRleHQtZGFyazojRjBGMEU4OyAtLW11dGVkLWRhcms6cmdiYSgyNDAsMjQwLDIzMiwwLjQ1KTsKICAtLXN1Y2Nlc3M6IzM0Yzc1OTsgLS1kYW5nZXI6I2ZmM2IzMDsgLS13YXJuaW5nOiNmZWJjMmU7IC0taW5mbzojNWFjOGZhOwogIC0tdm9sdC1kaW06cmdiYSgyMTMsMjM5LDEzOCwwLjE1KTsgLS12b2x0LWdsb3c6cmdiYSgyMTMsMjM5LDEzOCwwLjI1KTsKICAtLXN1cmZhY2U6cmdiYSgyNTUsMjU1LDI1NSwwLjA1KTsgLS1zdXJmYWNlMjpyZ2JhKDI1NSwyNTUsMjU1LDAuMDgpOyAtLWJvcmRlcjI6cmdiYSgyNTUsMjU1LDI1NSwwLjE1KTsKICAtLXNlcmlmOidJbnN0cnVtZW50IFNlcmlmJyxHZW9yZ2lhLHNlcmlmOyAtLXNhbnM6J0RNIFNhbnMnLHN5c3RlbS11aSxzYW5zLXNlcmlmOyAtLW1vbm86J0RNIE1vbm8nLCdTRiBNb25vJyxtb25vc3BhY2U7Cn0KKnttYXJnaW46MDtwYWRkaW5nOjA7Ym94LXNpemluZzpib3JkZXItYm94fQpodG1sLGJvZHl7aGVpZ2h0OjEwMCV9CmJvZHl7YmFja2dyb3VuZDp2YXIoLS1kYXJrLWJnKTtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtd2VpZ2h0OjMwMDttaW4taGVpZ2h0OjEwMHZoO292ZXJmbG93LXg6aGlkZGVuOy13ZWJraXQtZm9udC1zbW9vdGhpbmc6YW50aWFsaWFzZWR9CmJvZHk6OmFmdGVye2NvbnRlbnQ6Jyc7cG9zaXRpb246Zml4ZWQ7aW5zZXQ6MDtiYWNrZ3JvdW5kLWltYWdlOnVybCgiZGF0YTppbWFnZS9zdmcreG1sLCUzQ3N2ZyB2aWV3Qm94PScwIDAgMjAwIDIwMCcgeG1sbnM9J2h0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnJyUzRSUzQ2ZpbHRlciBpZD0nbiclM0UlM0NmZVR1cmJ1bGVuY2UgdHlwZT0nZnJhY3RhbE5vaXNlJyBiYXNlRnJlcXVlbmN5PScwLjc1JyBudW1PY3RhdmVzPSc0JyBzdGl0Y2hUaWxlcz0nc3RpdGNoJy8lM0UlM0MvZmlsdGVyJTNFJTNDcmVjdCB3aWR0aD0nMTAwJTI1JyBoZWlnaHQ9JzEwMCUyNScgZmlsdGVyPSd1cmwoJTIzbiknLyUzRSUzQy9zdmclM0UiKTtvcGFjaXR5OjAuMDQ7cG9pbnRlci1ldmVudHM6bm9uZTt6LWluZGV4Ojk5OTl9Ci53cmFwe21heC13aWR0aDoxMjAwcHg7bWFyZ2luOjAgYXV0bztwYWRkaW5nOjQ4cHggNTZweCA4MHB4O3Bvc2l0aW9uOnJlbGF0aXZlO3otaW5kZXg6MX0KaGVhZGVye2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjMycHg7cGFkZGluZy1ib3R0b206MjhweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7ZmxleC13cmFwOndyYXB9Ci5icmFuZHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxOHB4fQoubWFya3t3aWR0aDo1NnB4O2hlaWdodDo1NnB4O2JvcmRlci1yYWRpdXM6MTNweDtiYWNrZ3JvdW5kOnZhcigtLXZvbHQpO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcjtmbGV4LXNocmluazowO2JveC1zaGFkb3c6MCA0cHggMjRweCByZ2JhKDAsMCwwLC40KX0KLm1hcmsgc3Bhbntmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC1zaXplOjM4cHg7Y29sb3I6dmFyKC0tZ3JvdmUpO2xpbmUtaGVpZ2h0OjF9Cmgxe2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo0MDA7Zm9udC1zaXplOmNsYW1wKDM0cHgsNHZ3LDU0cHgpO2xldHRlci1zcGFjaW5nOi0uMDJlbTtsaW5lLWhlaWdodDoxfQpoMSBlbXtmb250LXN0eWxlOml0YWxpYztjb2xvcjpyZ2JhKDI0MCwyNDAsMjMyLC41NSl9Ci5zdWJ0e2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2xldHRlci1zcGFjaW5nOi4xMmVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKTttYXJnaW4tdG9wOjZweH0KLmxpdmUtcGlsbHtkaXNwbGF5OmlubGluZS1mbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4O2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMWVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS12b2x0KTtiYWNrZ3JvdW5kOnJnYmEoMjEzLDIzOSwxMzgsLjEwKTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjEzLDIzOSwxMzgsLjQ1KTtwYWRkaW5nOjVweCAxM3B4O2JvcmRlci1yYWRpdXM6MTAwcHg7dGV4dC1zaGFkb3c6MCAwIDEwcHggcmdiYSgyMTMsMjM5LDEzOCwuMjgpfQoubGl2ZS1kb3R7d2lkdGg6OHB4O2hlaWdodDo4cHg7Ym9yZGVyLXJhZGl1czo1MCU7YmFja2dyb3VuZDp2YXIoLS12b2x0KTtib3gtc2hhZG93OjAgMCA4cHggdmFyKC0tdm9sdCk7YW5pbWF0aW9uOnB1bHNlIDEuNnMgZWFzZS1pbi1vdXQgaW5maW5pdGV9CiNjbG9ja3tjb2xvcjp2YXIoLS10ZXh0LWRhcmspO29wYWNpdHk6Ljg0fQpAa2V5ZnJhbWVzIHB1bHNlezAlLDEwMCV7b3BhY2l0eToxO3RyYW5zZm9ybTpzY2FsZSgxKX01MCV7b3BhY2l0eTouMzU7dHJhbnNmb3JtOnNjYWxlKC43KX19Ci5jb3VudHN7ZGlzcGxheTpmbGV4O2dhcDoxMHB4O21hcmdpbi10b3A6MTBweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJweDtmbGV4LXdyYXA6d3JhcH0KLmNvdW50cyBzcGFue3BhZGRpbmc6NHB4IDEycHg7Ym9yZGVyLXJhZGl1czoxMDBweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWRhcmstYm9yZGVyKTtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmFkZGJhcntkaXNwbGF5OmZsZXg7Z2FwOjEycHg7bWFyZ2luOjM0cHggMCAxNHB4O2ZsZXgtd3JhcDp3cmFwfQouYWRkYmFyIGlucHV0e2ZsZXg6MTttaW4td2lkdGg6MjgwcHg7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjIwcHg7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UpO2JvcmRlcjoxLjVweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7Ym9yZGVyLXJhZGl1czoxNHB4O3BhZGRpbmc6MTZweCAyMHB4O291dGxpbmU6bm9uZX0KLmFkZGJhciBpbnB1dDpmb2N1c3tib3JkZXItY29sb3I6dmFyKC0tZ3JvdmUpO2JveC1zaGFkb3c6MCAwIDAgM3B4IHJnYmEoOTQsMTIyLDk0LC4yNSl9Ci5idG4tdm9sdHtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjE3cHg7Y29sb3I6dmFyKC0tbWlkbmlnaHQpO2JhY2tncm91bmQ6dmFyKC0tdm9sdCk7Ym9yZGVyOm5vbmU7Ym9yZGVyLXJhZGl1czoxNHB4O3BhZGRpbmc6MCAzMnB4O2N1cnNvcjpwb2ludGVyO3doaXRlLXNwYWNlOm5vd3JhcH0KLmJ0bi12b2x0OmhvdmVye2ZpbHRlcjpicmlnaHRuZXNzKDEuMDYpO2JveC1zaGFkb3c6MCA0cHggMjBweCB2YXIoLS12b2x0LWdsb3cpfQouY250LWhpZGRlbntjb2xvcjp2YXIoLS1pcmlzKSFpbXBvcnRhbnQ7Ym9yZGVyLWNvbG9yOnJnYmEoMTk2LDE5MSwyNTUsLjM1KSFpbXBvcnRhbnR9Ci52aWV3YmFye2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjE4cHggMjhweDtmbGV4LXdyYXA6d3JhcDttYXJnaW46MThweCAwIDRweDtwYWRkaW5nOjE0cHggMDtib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpfQoudmItZ3JvdXB7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4O2ZsZXgtd3JhcDp3cmFwfQoudmItbGFiZWx7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjEzZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkLWRhcmspO21hcmdpbi1yaWdodDozcHh9Ci5jaGlwe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMDRlbTtib3JkZXItcmFkaXVzOjEwMHB4O3BhZGRpbmc6NHB4IDExcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2N1cnNvcjpwb2ludGVyO2JvcmRlcjoxcHggc29saWQgdHJhbnNwYXJlbnQ7dXNlci1zZWxlY3Q6bm9uZTt0cmFuc2l0aW9uOmZpbHRlciAuMTVzLG9wYWNpdHkgLjE1c30KLmNoaXA6aG92ZXJ7ZmlsdGVyOmJyaWdodG5lc3MoMS4xMil9Ci5jaGlwLm9mZntiYWNrZ3JvdW5kOnRyYW5zcGFyZW50IWltcG9ydGFudDtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKSFpbXBvcnRhbnQ7Ym9yZGVyLWNvbG9yOnZhcigtLWRhcmstYm9yZGVyKSFpbXBvcnRhbnQ7dGV4dC1kZWNvcmF0aW9uOmxpbmUtdGhyb3VnaDtvcGFjaXR5Oi41NX0KLnZiLXNlcHt3aWR0aDoxcHg7aGVpZ2h0OjIycHg7YmFja2dyb3VuZDp2YXIoLS1kYXJrLWJvcmRlcik7bWFyZ2luOjAgM3B4fQoudmJ0bntmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMDRlbTtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6NXB4IDEycHg7Y3Vyc29yOnBvaW50ZXI7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO3RyYW5zaXRpb246LjE1c30KLnZidG46aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLXZvbHQpO2NvbG9yOnZhcigtLXZvbHQpfQoudmJ0bi5vbntiYWNrZ3JvdW5kOnZhcigtLXZvbHQtZGltKTtib3JkZXItY29sb3I6dmFyKC0tdm9sdCk7Y29sb3I6dmFyKC0tdm9sdCl9CnVse2xpc3Qtc3R5bGU6bm9uZX0KLnRhc2t7YmFja2dyb3VuZDp2YXIoLS1zdXJmYWNlKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWRhcmstYm9yZGVyKTtib3JkZXItcmFkaXVzOjE4cHg7cGFkZGluZzoyMHB4IDIycHg7bWFyZ2luLXRvcDoxNHB4fQoudGFzay5mcmVzaHthbmltYXRpb246ZmFkZVVwIC4ycyBlYXNlLW91dH0KQGtleWZyYW1lcyBmYWRlVXB7ZnJvbXtvcGFjaXR5OjA7dHJhbnNmb3JtOnRyYW5zbGF0ZVkoMTZweCl9dG97b3BhY2l0eToxO3RyYW5zZm9ybTpub25lfX0KLnRhc2suZG9uZXtvcGFjaXR5Oi42fQoudGFzay5jYW5jZWxsZWR7b3BhY2l0eTouNX0KLnRhc2stdG9we2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpmbGV4LXN0YXJ0O2dhcDoxNnB4fQouY2hlY2t7d2lkdGg6MzhweDtoZWlnaHQ6MzhweDtmbGV4LXNocmluazowO2JvcmRlci1yYWRpdXM6MTFweDtjdXJzb3I6cG9pbnRlcjtib3JkZXI6MnB4IHNvbGlkIHZhcigtLWJvcmRlcjIpO2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO3RyYW5zaXRpb246LjJzO2NvbG9yOiNmZmY7Zm9udC13ZWlnaHQ6NzAwfQouY2hlY2s6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLXZvbHQpfQouY2hlY2sub257YmFja2dyb3VuZDp2YXIoLS1zdWNjZXNzKTtib3JkZXItY29sb3I6dmFyKC0tc3VjY2Vzcyl9Ci5jaGVjay5kaXNhYmxlZHtvcGFjaXR5Oi4zO2N1cnNvcjpub3QtYWxsb3dlZH0KLnRhc2stbWFpbntmbGV4OjE7bWluLXdpZHRoOjB9Ci50YXNrLXRleHR7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtc2l6ZTpjbGFtcCgyMnB4LDIuMnZ3LDMwcHgpO2xpbmUtaGVpZ2h0OjEuMTU7bGV0dGVyLXNwYWNpbmc6LS4wMWVtO3dvcmQtYnJlYWs6YnJlYWstd29yZDtjdXJzb3I6dGV4dDtvdXRsaW5lOm5vbmV9Ci50YXNrLXRleHQ6Zm9jdXN7Ym94LXNoYWRvdzowIDJweCAwIHZhcigtLWdyb3ZlKX0KLnRhc2suZG9uZSAudGFzay10ZXh0e3RleHQtZGVjb3JhdGlvbjpsaW5lLXRocm91Z2g7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayl9Ci50YXNrLmNhbmNlbGxlZCAudGFzay10ZXh0e3RleHQtZGVjb3JhdGlvbjpsaW5lLXRocm91Z2g7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayl9Ci5tZXRhe2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjhweDttYXJnaW4tdG9wOjhweDtmbGV4LXdyYXA6d3JhcH0KLmJhZGdle2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMDRlbTtib3JkZXItcmFkaXVzOjEwMHB4O3BhZGRpbmc6M3B4IDEwcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlfQouc3QtbmVlZHNfYnJhaW5zdG9ybXtiYWNrZ3JvdW5kOnJnYmEoMTk2LDE5MSwyNTUsLjE4KTtjb2xvcjp2YXIoLS1pcmlzKX0KLnN0LXdvcmtpbmd7YmFja2dyb3VuZDpyZ2JhKDI1NCwxODgsNDYsLjE4KTtjb2xvcjp2YXIoLS13YXJuaW5nKX0KLnN0LXJldmlld3tiYWNrZ3JvdW5kOnJnYmEoOTAsMjAwLDI1MCwuMTYpO2NvbG9yOnZhcigtLWluZm8pfQouc3QtYmxvY2tlZHtiYWNrZ3JvdW5kOnJnYmEoMjU1LDU5LDQ4LC4xNik7Y29sb3I6dmFyKC0tZGFuZ2VyKX0KLnN0LWRvbmV7YmFja2dyb3VuZDpyZ2JhKDUyLDE5OSw4OSwuMTYpO2NvbG9yOiM1MmQ4NzN9Ci5zdC1jYW5jZWxsZWR7YmFja2dyb3VuZDpyZ2JhKDE0MiwxNDIsMTQ3LC4xOCk7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayl9Ci51bnJlYWQtYmFkZ2V7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMC41cHg7bGV0dGVyLXNwYWNpbmc6LjA2ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW1pZG5pZ2h0KTtiYWNrZ3JvdW5kOnZhcigtLXZvbHQpO2JvcmRlcjoxcHggc29saWQgcmdiYSgyMTMsMjM5LDEzOCwuNyk7Ym9yZGVyLXJhZGl1czoxMDBweDtwYWRkaW5nOjNweCA5cHg7Ym94LXNoYWRvdzowIDAgMTZweCByZ2JhKDIxMywyMzksMTM4LC4yNCl9Ci50YWd7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7Ym9yZGVyLXJhZGl1czoxMDBweDtwYWRkaW5nOjNweCAxMHB4fQovKiBjbGljay10aGUtbGlua2VkLWVuZ2luZWVyIOKGkiBhdHRhY2ggdG8gaXRzIHRlcm1pbmFsIChzbGljZSBjKSAqLwoudGFnLmF0dGFjaHtjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1pbmZvKTtib3JkZXItY29sb3I6cmdiYSg5MCwyMDAsMjUwLC40KX0KLnRhZy5hdHRhY2g6OmJlZm9yZXtjb250ZW50Oifip4kgJztvcGFjaXR5Oi44NX0KLnRhZy5hdHRhY2g6aG92ZXJ7Y29sb3I6dmFyKC0tdm9sdCk7Ym9yZGVyLWNvbG9yOnZhcigtLXZvbHQpO2JhY2tncm91bmQ6dmFyKC0tdm9sdC1kaW0pfQoucm93e2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjEwcHg7bWFyZ2luLXRvcDoxMnB4O2ZsZXgtd3JhcDp3cmFwfQouZmllbGR7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjE0cHg7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6MTBweDtwYWRkaW5nOjlweCAxMnB4O291dGxpbmU6bm9uZTtmbGV4OjE7bWluLXdpZHRoOjIyMHB4fQouZmllbGQ6Zm9jdXN7Ym9yZGVyLWNvbG9yOnZhcigtLWdyb3ZlKTtib3gtc2hhZG93OjAgMCAwIDJweCByZ2JhKDk0LDEyMiw5NCwuMil9Ci5sYWJlbHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMDZlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7bWluLXdpZHRoOjEyMHB4fQoubGFiZWwucmVxOjphZnRlcntjb250ZW50OicgKic7Y29sb3I6dmFyKC0tZGFuZ2VyKX0KLnRvZ2dsZXtkaXNwbGF5OmlubGluZS1mbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OXB4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkLWRhcmspO3VzZXItc2VsZWN0Om5vbmV9Ci50b2dnbGUuZGlzYWJsZWR7b3BhY2l0eTouNDtjdXJzb3I6bm90LWFsbG93ZWR9Ci5zd3t3aWR0aDo0MnB4O2hlaWdodDoyNHB4O2JvcmRlci1yYWRpdXM6MTAwcHg7YmFja2dyb3VuZDp2YXIoLS1zdXJmYWNlMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIyKTtwb3NpdGlvbjpyZWxhdGl2ZTt0cmFuc2l0aW9uOi4yc30KLnN3OjphZnRlcntjb250ZW50OicnO3Bvc2l0aW9uOmFic29sdXRlO3RvcDoycHg7bGVmdDoycHg7d2lkdGg6MThweDtoZWlnaHQ6MThweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZhcigtLW11dGVkLWRhcmspO3RyYW5zaXRpb246LjJzfQoudG9nZ2xlLm9uIC5zd3tiYWNrZ3JvdW5kOnZhcigtLXZvbHQtZGltKTtib3JkZXItY29sb3I6dmFyKC0tdm9sdCl9Ci50b2dnbGUub24gLnN3OjphZnRlcntsZWZ0OjIxcHg7YmFja2dyb3VuZDp2YXIoLS12b2x0KX0KLmJyYWluc3Rvcm17bWFyZ2luLXRvcDoxMHB4O2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtc2l6ZToxNHB4O2xpbmUtaGVpZ2h0OjEuNTtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2JhY2tncm91bmQ6cmdiYSgxOTYsMTkxLDI1NSwuMDcpO2JvcmRlci1sZWZ0OjJweCBzb2xpZCB2YXIoLS1pcmlzKTtib3JkZXItcmFkaXVzOjAgOHB4IDhweCAwO3BhZGRpbmc6MTBweCAxNHB4fQouYnJhaW5zdG9ybSAuaHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzouMWVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1pcmlzKTtkaXNwbGF5OmJsb2NrO21hcmdpbi1ib3R0b206NHB4fQouc3RhdHVze21hcmdpbi10b3A6MTBweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTIuNXB4O2NvbG9yOnZhcigtLXdhcm5pbmcpO2JhY2tncm91bmQ6cmdiYSgyNTQsMTg4LDQ2LC4wOCk7Ym9yZGVyLXJhZGl1czo4cHg7cGFkZGluZzo4cHggMTJweH0KLm5lZWRicmFpbnttYXJnaW4tdG9wOjEwcHg7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEyLjVweDtjb2xvcjp2YXIoLS1pcmlzKTtiYWNrZ3JvdW5kOnJnYmEoMTk2LDE5MSwyNTUsLjEpO2JvcmRlcjoxcHggc29saWQgcmdiYSgxOTYsMTkxLDI1NSwuMzUpO2JvcmRlci1yYWRpdXM6OHB4O3BhZGRpbmc6OXB4IDEzcHg7Zm9udC13ZWlnaHQ6NTAwfQoucHJvb2Zze2Rpc3BsYXk6ZmxleDtnYXA6OHB4O2ZsZXgtd3JhcDp3cmFwO21hcmdpbi10b3A6MTBweDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5wcm9vZi1saXN0e2Rpc3BsYXk6Y29udGVudHN9Ci5wcm9vZntmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2JhY2tncm91bmQ6dmFyKC0tc3VyZmFjZTIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OHB4O3BhZGRpbmc6NnB4IDEwcHg7bWF4LXdpZHRoOjI0MHB4O292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcDt0ZXh0LWRlY29yYXRpb246bm9uZTtkaXNwbGF5OmlubGluZS1ibG9ja30KLnByb29mLmltZ3twYWRkaW5nOjNweH0KLnByb29mLmltZyBpbWd7bWF4LXdpZHRoOjIwMHB4O21heC1oZWlnaHQ6MTQwcHg7Ym9yZGVyLXJhZGl1czo2cHg7ZGlzcGxheTpibG9ja30KLnByb29mLnZpZHtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2dhcDo1cHg7cGFkZGluZzowO21heC13aWR0aDpub25lO292ZXJmbG93OnZpc2libGU7d2hpdGUtc3BhY2U6bm9ybWFsO2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7Ym9yZGVyOm5vbmV9Ci5wcm9vZi52aWQgdmlkZW97d2lkdGg6MzgwcHg7bWF4LXdpZHRoOjc4dnc7Ym9yZGVyLXJhZGl1czoxMHB4O2JhY2tncm91bmQ6IzAwMDtkaXNwbGF5OmJsb2NrO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpfQoucHJvb2YudmlkIC52Y2Fwe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLXZvbHQpO3RleHQtZGVjb3JhdGlvbjpub25lfQoucHJvb2YudmlkIC52Y2FwOmhvdmVye3RleHQtZGVjb3JhdGlvbjp1bmRlcmxpbmV9Ci5wcm9vZi5tb3Jle2N1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLXZvbHQpO2JvcmRlci1jb2xvcjpyZ2JhKDIxMywyMzksMTM4LC40NSk7YmFja2dyb3VuZDpyZ2JhKDIxMywyMzksMTM4LC4xMCk7Zm9udC13ZWlnaHQ6NzAwfQoucHJvb2YubW9yZTpob3Zlcntib3JkZXItY29sb3I6dmFyKC0tdm9sdCk7YmFja2dyb3VuZDp2YXIoLS12b2x0LWRpbSl9Ci5jdHJsc3tkaXNwbGF5OmZsZXg7Z2FwOjZweDtmbGV4LXNocmluazowfQouaWN0cmx7bWluLXdpZHRoOjM0cHg7aGVpZ2h0OjM0cHg7cGFkZGluZzowIDhweDtib3JkZXItcmFkaXVzOjlweDtjdXJzb3I6cG9pbnRlcjtiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2NvbG9yOnZhcigtLW11dGVkLWRhcmspO2ZvbnQtc2l6ZToxNHB4O2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcn0KLmljdHJsOmhvdmVye2JvcmRlci1jb2xvcjp2YXIoLS12b2x0KTtjb2xvcjp2YXIoLS12b2x0KX0KLmljdHJsLmRlbDpob3Zlcntib3JkZXItY29sb3I6dmFyKC0tZGFuZ2VyKTtjb2xvcjp2YXIoLS1kYW5nZXIpfQouZW1wdHl7dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzo3MHB4IDIwcHg7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtc3R5bGU6aXRhbGljO2ZvbnQtc2l6ZToyOHB4O2NvbG9yOnZhcigtLW11dGVkLWRhcmspfQoucGluZ3tmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLnRhc2stb3BlbnttYXJnaW4tbGVmdDphdXRvO2N1cnNvcjpwb2ludGVyfQovKiDilIDilIAgaXNzdWUtc3R5bGUgY2FyZCB2aWV3IChzbGljZSBiKSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAgKi8KLm1vZGFse3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7ei1pbmRleDoxMDAwO2Rpc3BsYXk6bm9uZTtiYWNrZ3JvdW5kOnJnYmEoMSwwLDEwLC43Mik7YmFja2Ryb3AtZmlsdGVyOmJsdXIoNHB4KTtvdmVyZmxvdy15OmF1dG87cGFkZGluZzo0MHB4IDIwcHh9Ci5tb2RhbC5zaG93e2Rpc3BsYXk6YmxvY2t9Ci5jYXJke21heC13aWR0aDo4MjBweDttYXJnaW46MCBhdXRvO2JhY2tncm91bmQ6dmFyKC0tZGFyay1iZyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIyKTtib3JkZXItcmFkaXVzOjIwcHg7Ym94LXNoYWRvdzowIDMwcHggOTBweCByZ2JhKDAsMCwwLC42KTtvdmVyZmxvdzpoaWRkZW59Ci5jYXJkLWhke3BhZGRpbmc6MjZweCAzMHB4IDIycHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO3Bvc2l0aW9uOnJlbGF0aXZlfQouY2FyZC1jbG9zZXtwb3NpdGlvbjphYnNvbHV0ZTt0b3A6MThweDtyaWdodDoyMHB4O3dpZHRoOjM2cHg7aGVpZ2h0OjM2cHg7Ym9yZGVyLXJhZGl1czoxMHB4O2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7Zm9udC1zaXplOjIwcHg7Y3Vyc29yOnBvaW50ZXI7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyfQouY2FyZC1jbG9zZTpob3Zlcntib3JkZXItY29sb3I6dmFyKC0tZGFuZ2VyKTtjb2xvcjp2YXIoLS1kYW5nZXIpfQouY2FyZC10aXRsZXtmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC1zaXplOmNsYW1wKDI2cHgsM3Z3LDM4cHgpO2xpbmUtaGVpZ2h0OjEuMTtsZXR0ZXItc3BhY2luZzotLjAxZW07cGFkZGluZy1yaWdodDo0OHB4O3dvcmQtYnJlYWs6YnJlYWstd29yZH0KLmNhcmQtc3Vie2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjlweDttYXJnaW4tdG9wOjEzcHg7ZmxleC13cmFwOndyYXB9Ci5jYXJkLWlke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkLWRhcmspfQouY2FyZC1zdGF0dXNyb3d7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OXB4O21hcmdpbi10b3A6MTRweH0KLmNhcmQtc3RhdHVzbGJse2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMHB4O2xldHRlci1zcGFjaW5nOi4xMWVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmNhcmQtc3RhdGV7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcjIpO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6NnB4IDEycHg7Y3Vyc29yOnBvaW50ZXI7b3V0bGluZTpub25lfQouY2FyZC1zdGF0ZTpob3Zlcntib3JkZXItY29sb3I6dmFyKC0tdm9sdCl9Ci5jYXJkLXN0YXRlOmZvY3Vze2JvcmRlci1jb2xvcjp2YXIoLS1ncm92ZSk7Ym94LXNoYWRvdzowIDAgMCAycHggcmdiYSg5NCwxMjIsOTQsLjIpfQouY2FyZC1jb25ke21hcmdpbi10b3A6MTZweDtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXNpemU6MTVweDtsaW5lLWhlaWdodDoxLjU7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6MTJweDtwYWRkaW5nOjEzcHggMTZweH0KLmNhcmQtY29uZCAuaCwuY2FyZC1hcnQgLmh7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjExZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkLWRhcmspO2Rpc3BsYXk6YmxvY2s7bWFyZ2luLWJvdHRvbTo2cHh9Ci5jYXJkLWFydHttYXJnaW46MTRweCAzMHB4IDA7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjE0LjVweDtsaW5lLWhlaWdodDoxLjU1O2NvbG9yOnZhcigtLXRleHQtZGFyayk7YmFja2dyb3VuZDpyZ2JhKDE5NiwxOTEsMjU1LC4wOCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDE5NiwxOTEsMjU1LC4zKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0taXJpcyk7Ym9yZGVyLXJhZGl1czowIDEycHggMTJweCAwO3BhZGRpbmc6MTRweCAxOHB4O3doaXRlLXNwYWNlOnByZS13cmFwO3dvcmQtYnJlYWs6YnJlYWstd29yZH0KLyogcmVsYXRpb25zOiBibG9ja2VkLWJ5IGRlcHMgKyBzdWJ0YXNrIHByb2dyZXNzIChpc3N1ZSAjMykg4oCUIGJvYXJkIGNhcmQgY2hpcHMgKi8KLnJlbHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzouMDNlbTtib3JkZXItcmFkaXVzOjEwMHB4O3BhZGRpbmc6MnB4IDhweDtkaXNwbGF5OmlubGluZS1ibG9ja30KLnJlbC5ibG9ja2Vke2JhY2tncm91bmQ6cmdiYSgyNTUsNTksNDgsLjE2KTtjb2xvcjp2YXIoLS1kYW5nZXIpfQoucmVsLnN1YnN7YmFja2dyb3VuZDpyZ2JhKDkwLDIwMCwyNTAsLjE0KTtjb2xvcjp2YXIoLS1pbmZvKX0KLnJlbC5jaGlsZHtiYWNrZ3JvdW5kOnJnYmEoMTk2LDE5MSwyNTUsLjE0KTtjb2xvcjp2YXIoLS1pcmlzKX0KLyogcmVsYXRpb25zIHBhbmVsIGluc2lkZSB0aGUgb3BlbmVkIGNhcmQgKGlzc3VlICMzKSAqLwouY2FyZC1yZWx7bWFyZ2luOjE0cHggMzBweCAwO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6MTRweDtwYWRkaW5nOjE0cHggMTZweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2dhcDoxNHB4fQoucmVsLXNlYyAuaHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzouMTFlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7ZGlzcGxheTpibG9jazttYXJnaW4tYm90dG9tOjhweH0KLnJlbC1yb3d7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OXB4O3BhZGRpbmc6NXB4IDB9Ci5yZWwtbGlua3tmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2N1cnNvcjpwb2ludGVyO2ZsZXg6MTttaW4td2lkdGg6MDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXA7dGV4dC1kZWNvcmF0aW9uOm5vbmV9Ci5yZWwtbGluazpob3Zlcntjb2xvcjp2YXIoLS12b2x0KX0KLnJlbC1kZWx7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7YmFja2dyb3VuZDp0cmFuc3BhcmVudDtib3JkZXItcmFkaXVzOjdweDt3aWR0aDoyNHB4O2hlaWdodDoyNHB4O2N1cnNvcjpwb2ludGVyO2ZsZXgtc2hyaW5rOjB9Ci5yZWwtZGVsOmhvdmVye2JvcmRlci1jb2xvcjp2YXIoLS1kYW5nZXIpO2NvbG9yOnZhcigtLWRhbmdlcil9Ci5yZWwtYWRke2Rpc3BsYXk6ZmxleDtnYXA6OHB4O21hcmdpbi10b3A6OHB4fQoucmVsLWFkZCBpbnB1dCwucmVsLWFkZCBzZWxlY3R7ZmxleDoxO21pbi13aWR0aDowO2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLXRleHQtZGFyayk7YmFja2dyb3VuZDp2YXIoLS1kYXJrLWJnKTtib3JkZXI6MS41cHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6OHB4IDExcHg7b3V0bGluZTpub25lfQoucmVsLWFkZCBpbnB1dDpmb2N1cywucmVsLWFkZCBzZWxlY3Q6Zm9jdXN7Ym9yZGVyLWNvbG9yOnZhcigtLWlyaXMpfQoucmVsLWFkZCBidXR0b257Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC13ZWlnaHQ6NjAwO2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLW1pZG5pZ2h0KTtiYWNrZ3JvdW5kOnZhcigtLWlyaXMpO2JvcmRlcjpub25lO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6MCAxNHB4O2N1cnNvcjpwb2ludGVyO3doaXRlLXNwYWNlOm5vd3JhcH0KLnJlbC1hZGQgYnV0dG9uOmhvdmVye2ZpbHRlcjpicmlnaHRuZXNzKDEuMDcpfQoucmVsLWdhdGV7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS10ZXh0LWRhcmspfQoucmVsLWdhdGUgLmdhdGUtaGludHtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKTtmb250LXNpemU6MTFweH0KLnJlbC1lbXB0eXtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXN0eWxlOml0YWxpYztmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmNhcmQtYXJ0IC5oe2NvbG9yOnZhcigtLWlyaXMpfQovKiBicmFpbnN0b3JtIGdhdGUg4oCUIGludGVyYWN0aXZlIFEmQSAoc2xpY2UgZCkgKi8KLmNhcmQtcWF7bWFyZ2luOjE0cHggMzBweCAwO2JvcmRlcjoxcHggc29saWQgcmdiYSgxOTYsMTkxLDI1NSwuMzIpO2JvcmRlci1yYWRpdXM6MTRweDtvdmVyZmxvdzpoaWRkZW59Ci5xYS1iYW5uZXJ7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEycHg7bGV0dGVyLXNwYWNpbmc6LjAyZW07cGFkZGluZzoxMXB4IDE2cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OXB4fQoucWEtYmFubmVyLmJsb2NrZWR7YmFja2dyb3VuZDpyZ2JhKDE5NiwxOTEsMjU1LC4xMik7Y29sb3I6dmFyKC0taXJpcyl9Ci5xYS1iYW5uZXIucmVhZHl7YmFja2dyb3VuZDpyZ2JhKDUyLDE5OSw4OSwuMTIpO2NvbG9yOiM1MmQ4NzN9Ci5xYS1saXN0e3BhZGRpbmc6NnB4IDE2cHggMTRweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2dhcDoxNHB4fQoucWEtaXRlbSAucXtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXNpemU6MTVweDtsaW5lLWhlaWdodDoxLjQ1O2NvbG9yOnZhcigtLXRleHQtZGFyayk7bWFyZ2luLWJvdHRvbTo3cHh9Ci5xYS1pdGVtIC5xOjpiZWZvcmV7Y29udGVudDonUSc7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWlyaXMpO2JhY2tncm91bmQ6cmdiYSgxOTYsMTkxLDI1NSwuMTgpO2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MnB4IDdweDttYXJnaW4tcmlnaHQ6OXB4fQoucWEtYW5zLXJvd3tkaXNwbGF5OmZsZXg7Z2FwOjhweDthbGlnbi1pdGVtczpmbGV4LXN0YXJ0fQoucWEtYW5zLXJvdyB0ZXh0YXJlYXtmbGV4OjE7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjE0cHg7bGluZS1oZWlnaHQ6MS40NTtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2JhY2tncm91bmQ6dmFyKC0tZGFyay1iZyk7Ym9yZGVyOjEuNXB4IHNvbGlkIHZhcigtLWRhcmstYm9yZGVyKTtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzo5cHggMTJweDtvdXRsaW5lOm5vbmU7cmVzaXplOnZlcnRpY2FsO21pbi1oZWlnaHQ6NDJweH0KLnFhLWFucy1yb3cgdGV4dGFyZWE6Zm9jdXN7Ym9yZGVyLWNvbG9yOnZhcigtLWlyaXMpO2JveC1zaGFkb3c6MCAwIDAgMnB4IHJnYmEoMTk2LDE5MSwyNTUsLjIyKX0KLnFhLWFucy1idG57Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC13ZWlnaHQ6NjAwO2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLW1pZG5pZ2h0KTtiYWNrZ3JvdW5kOnZhcigtLWlyaXMpO2JvcmRlcjpub25lO2JvcmRlci1yYWRpdXM6MTBweDtwYWRkaW5nOjAgMTVweDtjdXJzb3I6cG9pbnRlcjthbGlnbi1zZWxmOnN0cmV0Y2g7d2hpdGUtc3BhY2U6bm93cmFwfQoucWEtYW5zLWJ0bjpob3ZlcntmaWx0ZXI6YnJpZ2h0bmVzcygxLjA3KX0KLnFhLWl0ZW0uYW5zd2VyZWQgLnFhLWFuc3tmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXNpemU6MTRweDtsaW5lLWhlaWdodDoxLjQ1O2NvbG9yOnZhcigtLXRleHQtZGFyayk7YmFja2dyb3VuZDpyZ2JhKDUyLDE5OSw4OSwuMDgpO2JvcmRlci1sZWZ0OjJweCBzb2xpZCB2YXIoLS1zdWNjZXNzKTtib3JkZXItcmFkaXVzOjAgOHB4IDhweCAwO3BhZGRpbmc6OHB4IDEycHh9Ci5xYS1pdGVtLmFuc3dlcmVkIC5xYS1hbnM6OmJlZm9yZXtjb250ZW50OifinJMgJztjb2xvcjp2YXIoLS1zdWNjZXNzKTtmb250LXdlaWdodDo3MDB9Ci5xYS1wcm9tb3Rle2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1taWRuaWdodCk7YmFja2dyb3VuZDp2YXIoLS12b2x0KTtib3JkZXI6bm9uZTtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzoxMHB4IDE4cHg7Y3Vyc29yOnBvaW50ZXI7bWFyZ2luOjAgMTZweCAxNHB4fQoucWEtcHJvbW90ZTpob3ZlcntmaWx0ZXI6YnJpZ2h0bmVzcygxLjA2KX0KLnRocmVhZHtwYWRkaW5nOjhweCAzMHB4IDIycHh9Ci50bC1lbXB0eXtmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC1zdHlsZTppdGFsaWM7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzoyOHB4IDEwcHh9Ci5ldntkaXNwbGF5OmZsZXg7Z2FwOjEzcHg7cGFkZGluZzoxNXB4IDA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpfQouZXY6bGFzdC1jaGlsZHtib3JkZXItYm90dG9tOm5vbmV9Ci5hdnt3aWR0aDozNHB4O2hlaWdodDozNHB4O2ZsZXgtc2hyaW5rOjA7Ym9yZGVyLXJhZGl1czo1MCU7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTNweDtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UyKTtjb2xvcjp2YXIoLS10ZXh0LWRhcmspfQouYXYuY2Vve2JhY2tncm91bmQ6dmFyKC0tdm9sdCk7Y29sb3I6dmFyKC0tZ3JvdmUpfQouYXYuYWdlbnR7YmFja2dyb3VuZDpyZ2JhKDkwLDIwMCwyNTAsLjIpO2NvbG9yOnZhcigtLWluZm8pfQouYXYuYnJhaW57YmFja2dyb3VuZDpyZ2JhKDE5NiwxOTEsMjU1LC4yMik7Y29sb3I6dmFyKC0taXJpcyl9Ci5ldi1ib2R5e2ZsZXg6MTttaW4td2lkdGg6MH0KLmV2LWhke2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpiYXNlbGluZTtnYXA6OHB4O2ZsZXgtd3JhcDp3cmFwO21hcmdpbi1ib3R0b206NXB4fQouZXYtYnl7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToxMi41cHg7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKX0KLmV2LWtpbmR7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjA2ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkLWRhcmspO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6MTAwcHg7cGFkZGluZzoxcHggOHB4fQouZXYtdGltZXtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmV2LXRleHR7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjE0LjVweDtsaW5lLWhlaWdodDoxLjU1O2NvbG9yOnZhcigtLXRleHQtZGFyayk7d2hpdGUtc3BhY2U6cHJlLXdyYXA7d29yZC1icmVhazpicmVhay13b3JkfQovKiByZW5kZXJlZCBtYXJrZG93biBpbiBhIGNvbW1lbnQvc3RhdHVzIGJvZHk6IHJlc2V0IHByZS13cmFwIChibG9jayB0YWdzIGNhcnJ5IHRoZSBsYXlvdXQgbm93KSAqLwouZXYtdGV4dC5tZHt3aGl0ZS1zcGFjZTpub3JtYWx9Ci5ldi10ZXh0Lm1kPjpmaXJzdC1jaGlsZHttYXJnaW4tdG9wOjB9LmV2LXRleHQubWQ+Omxhc3QtY2hpbGR7bWFyZ2luLWJvdHRvbTowfQouZXYtdGV4dC5tZCBwe21hcmdpbjowIDAgOHB4fQouZXYtdGV4dC5tZCBoMSwuZXYtdGV4dC5tZCBoMiwuZXYtdGV4dC5tZCBoMywuZXYtdGV4dC5tZCBoNCwuZXYtdGV4dC5tZCBoNSwuZXYtdGV4dC5tZCBoNntmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXdlaWdodDo2MDA7bGluZS1oZWlnaHQ6MS4zO21hcmdpbjoxMnB4IDAgNnB4fQouZXYtdGV4dC5tZCBoMXtmb250LXNpemU6MTlweH0uZXYtdGV4dC5tZCBoMntmb250LXNpemU6MTdweH0uZXYtdGV4dC5tZCBoM3tmb250LXNpemU6MTUuNXB4fQouZXYtdGV4dC5tZCBoNCwuZXYtdGV4dC5tZCBoNSwuZXYtdGV4dC5tZCBoNntmb250LXNpemU6MTQuNXB4fQouZXYtdGV4dC5tZCB1bCwuZXYtdGV4dC5tZCBvbHttYXJnaW46NHB4IDAgOHB4O3BhZGRpbmctbGVmdDoyMnB4fQouZXYtdGV4dC5tZCBsaXttYXJnaW46MnB4IDB9Ci5ldi10ZXh0Lm1kIHN0cm9uZ3tmb250LXdlaWdodDo2MDB9LmV2LXRleHQubWQgZW17Zm9udC1zdHlsZTppdGFsaWN9Ci5ldi10ZXh0Lm1kIGF7Y29sb3I6dmFyKC0taW5mbyk7dGV4dC1kZWNvcmF0aW9uOnVuZGVybGluZX0KLmV2LXRleHQubWQgY29kZXtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTIuNXB4O2JhY2tncm91bmQ6dmFyKC0tc3VyZmFjZTIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6NXB4O3BhZGRpbmc6MXB4IDVweH0KLmV2LXRleHQubWQgcHJle2JhY2tncm91bmQ6dmFyKC0tc3VyZmFjZTIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OHB4O3BhZGRpbmc6MTFweCAxM3B4O21hcmdpbjo2cHggMCA5cHg7b3ZlcmZsb3cteDphdXRvfQouZXYtdGV4dC5tZCBwcmUgY29kZXtmb250LXNpemU6MTIuNXB4O2JhY2tncm91bmQ6bm9uZTtib3JkZXI6bm9uZTtib3JkZXItcmFkaXVzOjA7cGFkZGluZzowO3doaXRlLXNwYWNlOnByZTtkaXNwbGF5OmJsb2NrfQouZXYtdGV4dC5tZCBibG9ja3F1b3Rle21hcmdpbjo2cHggMDtwYWRkaW5nOjJweCAwIDJweCAxMnB4O2JvcmRlci1sZWZ0OjNweCBzb2xpZCB2YXIoLS1ib3JkZXIyKTtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmV2LmJyYWluc3Rvcm0gLmV2LXRleHR7YmFja2dyb3VuZDpyZ2JhKDE5NiwxOTEsMjU1LC4wNyk7Ym9yZGVyLXJhZGl1czo4cHg7cGFkZGluZzoxMHB4IDEzcHh9Ci8qIHN0YXRlLXRyYW5zaXRpb246IGNvbXBhY3QgY2VudGVyZWQgdGltZWxpbmUgbWFya2VyLCBubyBhdmF0YXIgKi8KLmV2LnN0YXRle3BhZGRpbmc6OXB4IDA7Ym9yZGVyLWJvdHRvbTpub25lO2p1c3RpZnktY29udGVudDpjZW50ZXI7Z2FwOjhweDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5ldi5zdGF0ZSAuZXYtdGV4dHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTEuNXB4O2NvbG9yOnZhcigtLW11dGVkLWRhcmspO2JhY2tncm91bmQ6dmFyKC0tc3VyZmFjZSk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7Ym9yZGVyLXJhZGl1czoxMDBweDtwYWRkaW5nOjRweCAxM3B4O3doaXRlLXNwYWNlOm5vd3JhcH0KLmV2LXByb29mc3tkaXNwbGF5OmZsZXg7Z2FwOjhweDtmbGV4LXdyYXA6d3JhcDttYXJnaW4tdG9wOjhweDthbGlnbi1pdGVtczpmbGV4LXN0YXJ0fQovKiBvcGVuZWQtY2FyZCBhdHRhY2htZW50cyByZW5kZXIgRlVMTC1XSURUSCAmIHVuY3JvcHBlZCDigJQgdGhlIDIwMMOXMTQwIGNhcCBpcyBvbmx5IGZvciB0aGUgc21hbGwKICAgYm9hcmQtY2FyZCB0aHVtYm5haWxzICgucHJvb2ZzKSwgbmV2ZXIgdGhlIG9wZW5lZCBpc3N1ZSBjYXJkLiBFYWNoIG1lZGlhIHRha2VzIGl0cyBvd24gcm93LiAqLwouZXYtcHJvb2ZzIC5wcm9vZi5pbWd7ZmxleDoxIDEgMTAwJTttYXgtd2lkdGg6MTAwJTtwYWRkaW5nOjA7YmFja2dyb3VuZDp0cmFuc3BhcmVudDtib3JkZXI6bm9uZTtvdmVyZmxvdzp2aXNpYmxlO3doaXRlLXNwYWNlOm5vcm1hbDtkaXNwbGF5OmJsb2NrfQouZXYtcHJvb2ZzIC5wcm9vZi5pbWcgaW1ne21heC13aWR0aDoxMDAlO3dpZHRoOmF1dG87bWF4LWhlaWdodDo3OHZoO2hlaWdodDphdXRvO29iamVjdC1maXQ6Y29udGFpbjtib3JkZXItcmFkaXVzOjEwcHg7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcil9Ci5ldi1wcm9vZnMgLnByb29mLnZpZHtmbGV4OjEgMSAxMDAlO21heC13aWR0aDoxMDAlfQouZXYtcHJvb2ZzIC5wcm9vZi52aWQgdmlkZW97d2lkdGg6MTAwJTttYXgtd2lkdGg6MTAwJX0KLmV2LXByb29mcyAucHJvb2Z7bWF4LXdpZHRoOjEwMCV9Ci5jb21wb3NlcntkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2dhcDoxMHB4O3BhZGRpbmc6MThweCAzMHB4IDI2cHg7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JhY2tncm91bmQ6dmFyKC0tc3VyZmFjZSl9Ci5jb21wb3NlciB0ZXh0YXJlYXtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXNpemU6MTVweDtsaW5lLWhlaWdodDoxLjU7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLWRhcmstYmcpO2JvcmRlcjoxLjVweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7Ym9yZGVyLXJhZGl1czoxMnB4O3BhZGRpbmc6MTNweCAxNXB4O291dGxpbmU6bm9uZTtyZXNpemU6dmVydGljYWw7bWluLWhlaWdodDo3OHB4fQouY29tcG9zZXIgdGV4dGFyZWE6Zm9jdXN7Ym9yZGVyLWNvbG9yOnZhcigtLWdyb3ZlKTtib3gtc2hhZG93OjAgMCAwIDNweCByZ2JhKDk0LDEyMiw5NCwuMjIpfQouY29tcG9zZXIgLmNyb3d7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjtnYXA6MTJweDtmbGV4LXdyYXA6d3JhcH0KLmNvbXBvc2VyIC5jaGludHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmNvbXBvc2VyIC5jYnRuc3tkaXNwbGF5OmZsZXg7Z2FwOjlweH0KLmNidG57Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC13ZWlnaHQ6NjAwO2ZvbnQtc2l6ZToxNHB4O2JvcmRlci1yYWRpdXM6MTFweDtwYWRkaW5nOjlweCAxOHB4O2N1cnNvcjpwb2ludGVyO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JhY2tncm91bmQ6dmFyKC0tc3VyZmFjZTIpO2NvbG9yOnZhcigtLXRleHQtZGFyayl9Ci5jYnRuLnByaW1hcnl7YmFja2dyb3VuZDp2YXIoLS12b2x0KTtjb2xvcjp2YXIoLS1taWRuaWdodCk7Ym9yZGVyOm5vbmU7Zm9udC13ZWlnaHQ6NzAwfQouY2J0bi5wcmltYXJ5OmhvdmVye2ZpbHRlcjpicmlnaHRuZXNzKDEuMDYpfQpAbWVkaWEobWF4LXdpZHRoOjc2MHB4KXsud3JhcHtwYWRkaW5nOjMwcHggMThweCA2MHB4fWhlYWRlcntmbGV4LWRpcmVjdGlvbjpjb2x1bW47YWxpZ24taXRlbXM6ZmxleC1zdGFydH0ubW9kYWx7cGFkZGluZzowfS5jYXJke2JvcmRlci1yYWRpdXM6MDttaW4taGVpZ2h0OjEwMHZofS5jYXJkLWFydHttYXJnaW4tbGVmdDoxOHB4O21hcmdpbi1yaWdodDoxOHB4fS50aHJlYWQsLmNvbXBvc2VyLC5jYXJkLWhke3BhZGRpbmctbGVmdDoxOHB4O3BhZGRpbmctcmlnaHQ6MThweH19Cjwvc3R5bGU+CjwvaGVhZD4KPGJvZHk+CjxkaXYgY2xhc3M9IndyYXAiPgogIDxoZWFkZXI+CiAgICA8ZGl2PgogICAgICA8ZGl2IGNsYXNzPSJicmFuZCI+CiAgICAgICAgPGRpdiBjbGFzcz0ibWFyayI+PHNwYW4+UDwvc3Bhbj48L2Rpdj4KICAgICAgICA8ZGl2PjxoMT5Qcmlvcml0aWVzPC9oMT48ZGl2IGNsYXNzPSJzdWJ0Ij5Cb3NzIHNvdXJjZS1vZi10cnV0aCDCtyBNeVBlb3BsZTwvZGl2PjwvZGl2PgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iY291bnRzIiBpZD0iY291bnRzIj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBzdHlsZT0idGV4dC1hbGlnbjpyaWdodCI+CiAgICAgIDxzcGFuIGNsYXNzPSJsaXZlLXBpbGwiPjxzcGFuIGNsYXNzPSJsaXZlLWRvdCI+PC9zcGFuPjxzcGFuIGlkPSJjb25uIj5saXZlPC9zcGFuPjwvc3Bhbj4KICAgICAgPGRpdiBjbGFzcz0ic3VidCIgaWQ9ImNsb2NrIiBzdHlsZT0ibWFyZ2luLXRvcDo4cHgiPuKAlDwvZGl2PgogICAgPC9kaXY+CiAgPC9oZWFkZXI+CiAgPGRpdiBjbGFzcz0iYWRkYmFyIj4KICAgIDxpbnB1dCBpZD0ibmV3SXRlbSIgdHlwZT0idGV4dCIgcGxhY2Vob2xkZXI9IkFkZCBhIHByaW9yaXR5IGFuZCBoaXQgRW50ZXLigKYiIGF1dG9jb21wbGV0ZT0ib2ZmIj4KICAgIDxidXR0b24gY2xhc3M9ImJ0bi12b2x0IiBpZD0iYWRkQnRuIj5BZGQ8L2J1dHRvbj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ2aWV3YmFyIj4KICAgIDxkaXYgY2xhc3M9InZiLWdyb3VwIj4KICAgICAgPHNwYW4gY2xhc3M9InZiLWxhYmVsIj5zaG93PC9zcGFuPgogICAgICA8c3BhbiBpZD0ic2hvd0NoaXBzIiBzdHlsZT0iZGlzcGxheTpjb250ZW50cyI+PC9zcGFuPgogICAgICA8c3BhbiBjbGFzcz0idmItc2VwIj48L3NwYW4+CiAgICAgIDxidXR0b24gY2xhc3M9InZidG4iIGRhdGEtcHJlc2V0PSJhbGwiPmFsbDwvYnV0dG9uPgogICAgICA8YnV0dG9uIGNsYXNzPSJ2YnRuIiBkYXRhLXByZXNldD0iaGlkZS1kb25lIj5oaWRlIGRvbmU8L2J1dHRvbj4KICAgICAgPGJ1dHRvbiBjbGFzcz0idmJ0biIgZGF0YS1wcmVzZXQ9Im9ubHktZG9uZSI+b25seSBkb25lPC9idXR0b24+CiAgICAgIDxzcGFuIGNsYXNzPSJ2Yi1zZXAiPjwvc3Bhbj4KICAgICAgPGJ1dHRvbiBjbGFzcz0idmJ0biIgZGF0YS10b2dnbGU9InVucmVhZCIgdGl0bGU9InNob3cgb25seSBjYXJkcyB3aXRoIGEgbmV3LCB1bnJlYWQgdXBkYXRlIOKAlCBvcGVuaW5nIG9uZSBjbGVhcnMgaXQiPnVucmVhZCBvbmx5PC9idXR0b24+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8dWwgaWQ9Imxpc3QiPjwvdWw+CjwvZGl2PgoKPCEtLSBpc3N1ZS1zdHlsZSBjYXJkIHZpZXcgKHNsaWNlIGIpOiBmdWxsIG1lc3NhZ2UgaGlzdG9yeSArIHByb29mcyArIGJyYWluc3Rvcm0gYXJ0aWZhY3QgLS0+CjxkaXYgY2xhc3M9Im1vZGFsIiBpZD0iY2FyZE1vZGFsIj4KICA8ZGl2IGNsYXNzPSJjYXJkIiBpZD0iY2FyZElubmVyIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQtaGQiPgogICAgICA8YnV0dG9uIGNsYXNzPSJjYXJkLWNsb3NlIiBpZD0iY2FyZENsb3NlIiB0aXRsZT0iY2xvc2UgKEVzYykiPsOXPC9idXR0b24+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdGl0bGUiIGlkPSJjYXJkVGl0bGUiPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjYXJkLXN1YiIgaWQ9ImNhcmRTdWIiPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjYXJkLXN0YXR1c3JvdyI+PHNwYW4gY2xhc3M9ImNhcmQtc3RhdHVzbGJsIj5tb3ZlIHRvPC9zcGFuPjxzZWxlY3QgY2xhc3M9ImNhcmQtc3RhdGUiIGlkPSJjYXJkU3RhdGUiPjwvc2VsZWN0PjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjYXJkLWNvbmQiIGlkPSJjYXJkQ29uZCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+PHNwYW4gY2xhc3M9ImgiPmRvbmUtY29uZGl0aW9uPC9zcGFuPjxzcGFuIGlkPSJjYXJkQ29uZEJvZHkiPjwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZC1xYSIgaWQ9ImNhcmRRYSIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkLWFydCIgaWQ9ImNhcmRBcnQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPjxzcGFuIGNsYXNzPSJoIj5icmFpbnN0b3JtIGFydGlmYWN0PC9zcGFuPjxzcGFuIGlkPSJjYXJkQXJ0Qm9keSI+PC9zcGFuPjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZC1yZWwiIGlkPSJjYXJkUmVsIiBzdHlsZT0iZGlzcGxheTpub25lIj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InRocmVhZCIgaWQ9ImNhcmRUaHJlYWQiPjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY29tcG9zZXIiPgogICAgICA8dGV4dGFyZWEgaWQ9ImNhcmRDb21wb3NlIiBwbGFjZWhvbGRlcj0iTGVhdmUgYSBjb21tZW50IGFzIENFT+KApiI+PC90ZXh0YXJlYT4KICAgICAgPGRpdiBjbGFzcz0iY3JvdyI+CiAgICAgICAgPHNwYW4gY2xhc3M9ImNoaW50Ij7ijJgvQ3RybCArIEVudGVyIHRvIGNvbW1lbnQ8L3NwYW4+CiAgICAgICAgPGRpdiBjbGFzcz0iY2J0bnMiPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iY2J0biBwcmltYXJ5IiBpZD0iY2FyZENvbW1lbnRCdG4iPkNvbW1lbnQ8L2J1dHRvbj4KICAgICAgICA8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8c2NyaXB0Pgpjb25zdCBTRUNSRVQ9Il9fUVVFVUVfU0VDUkVUX18iOwpjb25zdCBCVUlMRD0iX19CVUlMRF9fIjsgICAvLyBzZXJ2ZXIgc3RhbXBzIHRoZSBIVE1MIG10aW1lOyBpZiBhIG5ld2VyIGJvYXJkIHNoaXBzLCB0aGUgb3BlbiBwYWdlIGF1dG8tcmVsb2FkcyAobm8gc3RhbGUtSlMgYnVncykKY29uc3QgbGlzdEVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsaXN0JyksIGlucHV0PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCduZXdJdGVtJyk7CmxldCBib2FyZD17dmVyc2lvbjoidjIiLG9yZGVyOltdLHRhc2tzOnt9fTsKY29uc3QgZWxzPXt9OyAgICAgICAgICAgICAgICAgICAgICAgICAvLyB0YXNrIGlkIC0+IDxsaT4gKHdpdGggbGkuX3IgY2FjaGVkIGNoaWxkIHJlZnMpCmNvbnN0IEhPTUVfTUVESUFfUFJFVklFV19MSU1JVD0zOwpjb25zdCBSRUFEX0tFWT0ndG9kb0Nlb1JlYWQudjEnLCBSRUFEX1NFRURFRF9LRVk9J3RvZG9DZW9SZWFkU2VlZGVkLnYxJzsKbGV0IHJlYWRTdGF0ZT17fTsKdHJ5eyByZWFkU3RhdGU9SlNPTi5wYXJzZShsb2NhbFN0b3JhZ2UuZ2V0SXRlbShSRUFEX0tFWSl8fCd7fScpfHx7fTsgfWNhdGNoKGUpeyByZWFkU3RhdGU9e307IH0KbGV0IHJlYWRTZWVkZWQ9bG9jYWxTdG9yYWdlLmdldEl0ZW0oUkVBRF9TRUVERURfS0VZKT09PScxJzsKCmNvbnN0IEg9KCk9Pih7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nLC4uLihTRUNSRVQ/eydYLVF1ZXVlLVNlY3JldCc6U0VDUkVUfTp7fSl9KTsKYXN5bmMgZnVuY3Rpb24gYXBpKHBhdGgsYm9keSl7Y29uc3Qgcj1hd2FpdCBmZXRjaChwYXRoLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6SCgpLGJvZHk6SlNPTi5zdHJpbmdpZnkoYm9keSl9KTtyZXR1cm4gci5qc29uKCk7fQpjb25zdCB1cGQ9Yj0+YXBpKCcvdG9kby91cGRhdGUnLGIpLCBzdGF0dXNBcGk9Yj0+YXBpKCcvdG9kby9zdGF0dXMnLGIpLCBicmFpbnN0b3JtQXBpPWI9PmFwaSgnL3RvZG8vYnJhaW5zdG9ybScsYiksIHByb29mQXBpPWI9PmFwaSgnL3RvZG8vcHJvb2YnLGIpLCBjb21tZW50QXBpPWI9PmFwaSgnL3RvZG8vY29tbWVudCcsYiksIGFuc3dlckFwaT1iPT5hcGkoJy90b2RvL2Fuc3dlcicsYik7CmNvbnN0IFNUTEFCRUw9e25lZWRzX2JyYWluc3Rvcm06J25lZWRzIGJyYWluc3Rvcm0nLHdvcmtpbmc6J3dvcmtpbmcnLHJldmlldzoncmV2aWV3IChDRU8pJyxibG9ja2VkOidibG9ja2VkJyxkb25lOidkb25lJyxjYW5jZWxsZWQ6J2NhbmNlbGxlZCd9OwoKLy8g4pSA4pSAIENMSUNLLVRIRS1MSU5LRUQtRU5HSU5FRVIg4oaSIEFUVEFDSCAoc2xpY2UgYykg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACi8vIE9wZW4gdGhlIGFzc2lnbmVlJ3MgbGl2ZSB0ZXJtaW5hbCBpbiBhIG5ldyB0YWIgdmlhIHR0eWQg4oCUIHRoZSBTQU1FIGVmZmVjdCBhcyB0aGUgSFVECi8vIGF0dGFjaC4gVGhlIHNlcnZlciByZXNvbHZlcyB0aGUgdG11eCB0YXJnZXQgKG1jLTxzZXNzaW9uPjo8dGFiPikgKyB0aGUgaG9zdCdzIHR0eWQgYmFzZQovLyBmcm9tIHRoZSBxdWV1ZSAvY2xpZW50czsgd2UgYXNzZW1ibGUgdGhlIFVSTCB3aXRoIHRoZSBTQU1FIGA8bG9jYXRpb24uaG9zdG5hbWU+Ojc2ODFgCi8vIGZhbGxiYWNrIHRoZSBIVUQgdXNlcyB3aGVuIGEgaG9zdCBhZHZlcnRpc2VzIG5vIGF0dGFjaF9iYXNlICh0aGUgbG9jYWwgbm9kZSkuCmFzeW5jIGZ1bmN0aW9uIGF0dGFjaFRvRW5naW5lZXIoYWdlbnQpewogIGlmKCFhZ2VudCkgcmV0dXJuOwogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goJy90b2RvL2F0dGFjaD9hZ2VudD0nK2VuY29kZVVSSUNvbXBvbmVudChhZ2VudCkse2hlYWRlcnM6SCgpfSk7CiAgICBjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgaWYoIWQub2speyBhbGVydChkLmVycm9yfHwnY2Fubm90IGF0dGFjaCB0byB0aGlzIGFzc2lnbmVlJyk7IHJldHVybjsgfQogICAgY29uc3QgYmFzZT1kLmJhc2UgfHwgKCdodHRwOi8vJysobG9jYXRpb24uaG9zdG5hbWV8fCcxMjcuMC4wLjEnKSsnOjc2ODEnKTsKICAgIHdpbmRvdy5vcGVuKGJhc2UrJy8/YXJnPS10JmFyZz0nK2VuY29kZVVSSUNvbXBvbmVudChkLnRhcmdldCksJ19ibGFuaycsJ25vb3BlbmVyJyk7CiAgfWNhdGNoKGUpeyBhbGVydCgnYXR0YWNoIGZhaWxlZDogJytlKTsgfQp9Ci8vIGFuIGFzc2lnbmVlIGlzIGF0dGFjaGFibGUgaWZmIGl0IGNhcnJpZXMgYSB0bXV4IHNlc3Npb246dGFiIChob3N0L3Nlc3Npb246dGFiIG9yIHNlc3Npb246dGFiKQpmdW5jdGlvbiBpc0F0dGFjaGFibGUoYXNnKXsgcmV0dXJuICEhYXNnICYmIC86W146L10rJC8udGVzdChhc2cpICYmIC8oXnxcLylbXi86XSs6W14vOl0rJC8udGVzdChhc2cpOyB9CmZ1bmN0aW9uIGVzYyhzKXtyZXR1cm4gKHN8fCcnKS5yZXBsYWNlKC8mL2csJyZhbXA7JykucmVwbGFjZSgvPC9nLCcmbHQ7JykucmVwbGFjZSgvPi9nLCcmZ3Q7JykucmVwbGFjZSgvIi9nLCcmcXVvdDsnKTt9CgovLyDilIDilIAgTWluaW1hbCwgWFNTLVNBRkUgbWFya2Rvd24gcmVuZGVyZXIgZm9yIGNvbW1lbnQgLyBzdGF0dXMgYm9kaWVzIOKUgOKUgAovLyBTdHJhdGVneTogaHRtbC1lc2NhcGUgdGhlIEVOVElSRSBpbnB1dCBGSVJTVCAoc28gbm8gcmF3IHRhZyB0aGUgdXNlciB0eXBlcyBjYW4gZXZlcgovLyBzdXJ2aXZlKSwgVEhFTiBhcHBseSBtYXJrZG93biB0cmFuc2Zvcm1zIHRoYXQgb25seSBFTUlUIGEgZml4ZWQsIGtub3duLXNhZmUgc2V0IG9mIHRhZ3MKLy8gKGgxLTYsIHAsIGJyLCBzdHJvbmcsIGVtLCBjb2RlLCBwcmUsIHVsL29sL2xpLCBibG9ja3F1b3RlLCBhKS4gQmVjYXVzZSB0aGUgc291cmNlIGlzIGZ1bGx5Ci8vIGVzY2FwZWQgdXAgZnJvbnQsIHVzZXIgdGV4dCBjYW4gbmV2ZXIgaW5qZWN0IG1hcmt1cCBvciBzY3JpcHRzIOKAlCB3ZSBvbmx5IGFkZCBvdXIgb3duIHRhZ3MuCi8vIExpbmtzIGFyZSBocmVmLXNhbml0aXplZCB0byBodHRwKHMpL21haWx0by9yZWxhdGl2ZS9hbmNob3Igb25seSAobm8gamF2YXNjcmlwdDovZGF0YTogVVJJcykuCmZ1bmN0aW9uIG1kU2FmZVVybCh1KXsgdT0odXx8JycpLnRyaW0oKTsgcmV0dXJuIC9eKGh0dHBzPzpcL1wvfG1haWx0bzp8XC98IykvaS50ZXN0KHUpID8gdSA6ICcjJzsgfQpmdW5jdGlvbiBtZElubGluZShzKXsgICAgICAgICAgIC8vIHMgaXMgYWxyZWFkeSBodG1sLWVzY2FwZWQ7IGFkZCBpbmxpbmUgc3BhbnMgb25seQogIHJldHVybiBzCiAgICAucmVwbGFjZSgvYChbXmBdKylgL2csIChtLGMpPT4nPGNvZGU+JytjKyc8L2NvZGU+JykgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAvLyBgaW5saW5lIGNvZGVgCiAgICAucmVwbGFjZSgvXFsoW15cXV0rKVxdXCgoW14pXHNdKylcKS9nLCAobSx0LHUpPT4nPGEgaHJlZj0iJytlc2MobWRTYWZlVXJsKHUpKSsnIiB0YXJnZXQ9Il9ibGFuayIgcmVsPSJub29wZW5lciBub3JlZmVycmVyIj4nK3QrJzwvYT4nKSAgLy8gW3RleHRdKHVybCkKICAgIC5yZXBsYWNlKC9cKlwqKFteKl0rKVwqXCovZywgJzxzdHJvbmc+JDE8L3N0cm9uZz4nKSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC8vICoqYm9sZCoqCiAgICAucmVwbGFjZSgvX18oW15fXSspX18vZywgJzxzdHJvbmc+JDE8L3N0cm9uZz4nKSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAvLyBfX2JvbGRfXwogICAgLnJlcGxhY2UoLyhefFteKl0pXCooW14qXG5dKylcKi9nLCAnJDE8ZW0+JDI8L2VtPicpICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgLy8gKml0YWxpYyoKICAgIC5yZXBsYWNlKC8oXnxbXl9cd10pXyhbXl9cbl0rKV8oPyFbXHddKS9nLCAnJDE8ZW0+JDI8L2VtPicpOyAgICAgICAgICAgICAgICAgICAgICAvLyBfaXRhbGljXwp9CmZ1bmN0aW9uIG1kVG9IdG1sKHNyYyl7CiAgc3JjID0gZXNjKFN0cmluZyhzcmM9PW51bGw/Jyc6c3JjKSk7CiAgY29uc3QgZmVuY2VzPVtdOyAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAvLyBwdWxsIGZlbmNlZCBgYGAgYmxvY2tzIG91dCBiZWZvcmUgbGluZSBwYXJzaW5nCiAgc3JjID0gc3JjLnJlcGxhY2UoL2BgYFteXG5dKlxuPyhbXHNcU10qPylgYGAvZywgKG0sY29kZSk9PnsgZmVuY2VzLnB1c2goY29kZS5yZXBsYWNlKC9cbiskLywnJykpOyByZXR1cm4gJwBGJysoZmVuY2VzLmxlbmd0aC0xKSsnACc7IH0pOwogIGNvbnN0IGxpbmVzPXNyYy5zcGxpdCgnXG4nKSwgb3V0PVtdOyBsZXQgbGlzdD1udWxsLCBwYXJhPVtdOwogIGNvbnN0IGZsdXNoUGFyYT0oKT0+eyBpZihwYXJhLmxlbmd0aCl7IG91dC5wdXNoKCc8cD4nK3BhcmEubWFwKG1kSW5saW5lKS5qb2luKCc8YnI+JykrJzwvcD4nKTsgcGFyYT1bXTsgfSB9OwogIGNvbnN0IGNsb3NlTGlzdD0oKT0+eyBpZihsaXN0KXsgb3V0LnB1c2goJzwvJytsaXN0Kyc+Jyk7IGxpc3Q9bnVsbDsgfSB9OwogIGZvcihjb25zdCBsaW5lIG9mIGxpbmVzKXsKICAgIGxldCBtOwogICAgaWYoKG09bGluZS5tYXRjaCgvXgBGKFxkKykAJC8pKSl7IGZsdXNoUGFyYSgpOyBjbG9zZUxpc3QoKTsgb3V0LnB1c2goJzxwcmU+PGNvZGU+JytmZW5jZXNbK21bMV1dKyc8L2NvZGU+PC9wcmU+Jyk7IGNvbnRpbnVlOyB9CiAgICBpZigvXlxzKiQvLnRlc3QobGluZSkpeyBmbHVzaFBhcmEoKTsgY2xvc2VMaXN0KCk7IGNvbnRpbnVlOyB9CiAgICBpZigobT1saW5lLm1hdGNoKC9eXHN7MCwzfSgjezEsNn0pXHMrKC4qKSQvKSkpeyBmbHVzaFBhcmEoKTsgY2xvc2VMaXN0KCk7IGNvbnN0IGx2bD1tWzFdLmxlbmd0aDsgb3V0LnB1c2goJzxoJytsdmwrJz4nK21kSW5saW5lKG1bMl0udHJpbSgpKSsnPC9oJytsdmwrJz4nKTsgY29udGludWU7IH0KICAgIGlmKChtPWxpbmUubWF0Y2goL15cc3swLDN9Jmd0O1xzPyguKikkLykpKXsgZmx1c2hQYXJhKCk7IGNsb3NlTGlzdCgpOyBvdXQucHVzaCgnPGJsb2NrcXVvdGU+JyttZElubGluZShtWzFdKSsnPC9ibG9ja3F1b3RlPicpOyBjb250aW51ZTsgfSAgLy8gJz4nIGlzIGFscmVhZHkgZXNjYXBlZCB0byAmZ3Q7IGJ5IHRoZSB1cC1mcm9udCBlc2MoKQogICAgaWYoKG09bGluZS5tYXRjaCgvXlxzezAsM31bLSorXVxzKyguKikkLykpKXsgZmx1c2hQYXJhKCk7IGlmKGxpc3QhPT0ndWwnKXsgY2xvc2VMaXN0KCk7IG91dC5wdXNoKCc8dWw+Jyk7IGxpc3Q9J3VsJzsgfSBvdXQucHVzaCgnPGxpPicrbWRJbmxpbmUobVsxXSkrJzwvbGk+Jyk7IGNvbnRpbnVlOyB9CiAgICBpZigobT1saW5lLm1hdGNoKC9eXHN7MCwzfVxkK1wuXHMrKC4qKSQvKSkpeyBmbHVzaFBhcmEoKTsgaWYobGlzdCE9PSdvbCcpeyBjbG9zZUxpc3QoKTsgb3V0LnB1c2goJzxvbD4nKTsgbGlzdD0nb2wnOyB9IG91dC5wdXNoKCc8bGk+JyttZElubGluZShtWzFdKSsnPC9saT4nKTsgY29udGludWU7IH0KICAgIGNsb3NlTGlzdCgpOyBwYXJhLnB1c2gobGluZS50cmltKCkpOwogIH0KICBmbHVzaFBhcmEoKTsgY2xvc2VMaXN0KCk7CiAgcmV0dXJuIG91dC5qb2luKCcnKTsKfQoKLy8g4pSA4pSAIFZJRVcgTEFZRVI6IGZpbHRlciBieSBzdGF0dXMgKGNsaWVudC1vbmx5OyBORVZFUiBtdXRhdGVzIGJvYXJkLm9yZGVyKSDilIDilIAKLy8gUHVyZSBwcmVzZW50YXRpb24uIFRoZSBkdXJhYmxlIHN0b3JlLCBtYW51YWwgb3JkZXIsIGNyb24gJiB3YXRjaGRvZyBhcmUgdW50b3VjaGVkIOKAlAovLyB0aGlzIG9ubHkgZGVjaWRlcyB3aGljaCBjYXJkcyBzaG93LiBDYXJkcyBhbHdheXMgcmVuZGVyIGluIHRoZSBDRU8ncyBtYW51YWwgYm9hcmQgb3JkZXIuCi8vIFBlcnNpc3RlZCBpbiBsb2NhbFN0b3JhZ2UuCmNvbnN0IFNUQVRFUz1bJ25lZWRzX2JyYWluc3Rvcm0nLCd3b3JraW5nJywncmV2aWV3JywnYmxvY2tlZCcsJ2RvbmUnLCdjYW5jZWxsZWQnXTsKbGV0IHZpZXc9e2hpZGRlbjpuZXcgU2V0KCksdW5yZWFkT25seTpmYWxzZX07ICAgLy8gaGlkZGVuOiBzdGF0ZXMgdG8gaGlkZTsgdW5yZWFkT25seTogc2hvdyBvbmx5IGNhcmRzIHdpdGggYSBuZXcgKHVucmVhZCkgdXBkYXRlCnRyeXsgY29uc3Qgdj1KU09OLnBhcnNlKGxvY2FsU3RvcmFnZS5nZXRJdGVtKCd0b2RvVmlldycpfHwne30nKTsKICAgICBpZihBcnJheS5pc0FycmF5KHYuaGlkZGVuKSkgdmlldy5oaWRkZW49bmV3IFNldCh2LmhpZGRlbi5maWx0ZXIocz0+U1RBVEVTLmluY2x1ZGVzKHMpKSk7CiAgICAgaWYodHlwZW9mIHYudW5yZWFkT25seT09PSdib29sZWFuJykgdmlldy51bnJlYWRPbmx5PXYudW5yZWFkT25seTsgfWNhdGNoKGUpe30KZnVuY3Rpb24gc2F2ZVZpZXcoKXsgdHJ5e2xvY2FsU3RvcmFnZS5zZXRJdGVtKCd0b2RvVmlldycsSlNPTi5zdHJpbmdpZnkoe2hpZGRlbjpbLi4udmlldy5oaWRkZW5dLHVucmVhZE9ubHk6dmlldy51bnJlYWRPbmx5fSkpO31jYXRjaChlKXt9IH0KCi8vIGFwcGx5IGN1cnJlbnQgZmlsdGVyIHRvIGFuIG9yZGVyZWQgaWQgbGlzdCAtPiB2aXNpYmxlIGlkcyBpbiBtYW51YWwgYm9hcmQgb3JkZXIuCmZ1bmN0aW9uIGFwcGx5VmlldyhpZHMpewogIGxldCB2PWlkcy5maWx0ZXIoaWQ9PiF2aWV3LmhpZGRlbi5oYXMoYm9hcmQudGFza3NbaWRdLnN0YXRlKSk7CiAgaWYodmlldy51bnJlYWRPbmx5KSB2PXYuZmlsdGVyKGlkPT51bnJlYWRDb3VudChib2FyZC50YXNrc1tpZF0pPjApOyAgIC8vIHJldXNlIHRoZSBTQU1FIHVucmVhZCBkZWZpbml0aW9uIGFzIHRoZSAnTiBuZXcnIGJhZGdlIOKAlCBubyBzZXBhcmF0ZSBub3Rpb24gb2YgdW5yZWFkCiAgcmV0dXJuIHY7Cn0KCi8vIGJ1aWxkIHRoZSBwZXItc3RhdHVzIHRvZ2dsZSBjaGlwcyBvbmNlLCB3aXJlIHVwIGFsbCB2aWV3IGNvbnRyb2xzCmZ1bmN0aW9uIGluaXRWaWV3YmFyKCl7CiAgY29uc3Qgd3JhcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2hvd0NoaXBzJyk7CiAgd3JhcC5pbm5lckhUTUw9U1RBVEVTLm1hcChzPT5gPHNwYW4gY2xhc3M9ImNoaXAgc3QtJHtzfSIgZGF0YS1zdD0iJHtzfSI+JHtlc2MoU1RMQUJFTFtzXXx8cyl9PC9zcGFuPmApLmpvaW4oJycpOwogIHdyYXAucXVlcnlTZWxlY3RvckFsbCgnLmNoaXAnKS5mb3JFYWNoKGM9PnsKICAgIGMub25jbGljaz0oKT0+eyBjb25zdCBzPWMuZGF0YXNldC5zdDsgdmlldy5oaWRkZW4uaGFzKHMpP3ZpZXcuaGlkZGVuLmRlbGV0ZShzKTp2aWV3LmhpZGRlbi5hZGQocyk7IHNhdmVWaWV3KCk7IHJlbmRlclZpZXdiYXIoKTsgcmVjb25jaWxlKCk7IH07CiAgfSk7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnZpZXdiYXIgW2RhdGEtcHJlc2V0XScpLmZvckVhY2goYj0+ewogICAgYi5vbmNsaWNrPSgpPT57IGNvbnN0IHA9Yi5kYXRhc2V0LnByZXNldDsKICAgICAgaWYocD09PSdhbGwnKSB2aWV3LmhpZGRlbj1uZXcgU2V0KCk7CiAgICAgIGVsc2UgaWYocD09PSdoaWRlLWRvbmUnKSB2aWV3LmhpZGRlbj1uZXcgU2V0KFsnZG9uZSddKTsKICAgICAgZWxzZSBpZihwPT09J29ubHktZG9uZScpIHZpZXcuaGlkZGVuPW5ldyBTZXQoU1RBVEVTLmZpbHRlcihzPT5zIT09J2RvbmUnKSk7CiAgICAgIHNhdmVWaWV3KCk7IHJlbmRlclZpZXdiYXIoKTsgcmVjb25jaWxlKCk7IH07CiAgfSk7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnZpZXdiYXIgW2RhdGEtdG9nZ2xlPSJ1bnJlYWQiXScpLmZvckVhY2goYj0+ewogICAgYi5vbmNsaWNrPSgpPT57IHZpZXcudW5yZWFkT25seT0hdmlldy51bnJlYWRPbmx5OyBzYXZlVmlldygpOyByZW5kZXJWaWV3YmFyKCk7IHJlY29uY2lsZSgpOyB9OwogIH0pOwp9CmZ1bmN0aW9uIHJlbmRlclZpZXdiYXIoKXsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcjc2hvd0NoaXBzIC5jaGlwJykuZm9yRWFjaChjPT5jLmNsYXNzTGlzdC50b2dnbGUoJ29mZicsIHZpZXcuaGlkZGVuLmhhcyhjLmRhdGFzZXQuc3QpKSk7CiAgY29uc3QgdW5iPWRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoJy52aWV3YmFyIFtkYXRhLXRvZ2dsZT0idW5yZWFkIl0nKTsgICAvLyBsaXZlIGNvdW50IHNvIHRoZSBDRU8gY2FuIGp1bXAgc3RyYWlnaHQgdG8gdW5yZWFkIGNhcmRzCiAgaWYodW5iKXsgdW5iLmNsYXNzTGlzdC50b2dnbGUoJ29uJywgdmlldy51bnJlYWRPbmx5KTsKICAgIGxldCBuPTA7IGNvbnN0IG9yZD0oYm9hcmQmJmJvYXJkLm9yZGVyKXx8W107CiAgICBvcmQuZm9yRWFjaChpZD0+eyBjb25zdCB0PWJvYXJkLnRhc2tzW2lkXTsgaWYodCYmdW5yZWFkQ291bnQodCk+MCkgbisrOyB9KTsKICAgIGNvbnN0IGxibCA9IG4gPyBgdW5yZWFkIG9ubHkgwrcgJHtufWAgOiAndW5yZWFkIG9ubHknOwogICAgaWYodW5iLnRleHRDb250ZW50IT09bGJsKSB1bmIudGV4dENvbnRlbnQ9bGJsOwogIH0KfQoKLy8g4pSA4pSAIERJUlRZIEZJRUxEUyBBUkUgU0FDUkVEIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAovLyBBIGZpZWxkIGlzIHNhY3JlZCBpZiBpdCdzIGZvY3VzZWQgT1IgaGFzIHVuc2F2ZWQgbG9jYWwgZWRpdHMgKGRhdGEtZGlydHk9MSkuCi8vIFRoZSBwb2xsIG5ldmVyIG92ZXJ3cml0ZXMgYSBzYWNyZWQgZmllbGQ7IGxvY2FsIHR5cGluZyB3aW5zIHVudGlsIGNvbW1pdHRlZC4KZnVuY3Rpb24gaXNEaXJ0eShlbCl7IHJldHVybiAhIWVsICYmIChlbD09PWRvY3VtZW50LmFjdGl2ZUVsZW1lbnQgfHwgZWwuZGF0YXNldC5kaXJ0eT09PScxJyk7IH0KZnVuY3Rpb24gd2F0Y2hEaXJ0eShlbCl7IGVsLmFkZEV2ZW50TGlzdGVuZXIoJ2lucHV0JywoKT0+e2VsLmRhdGFzZXQuZGlydHk9JzEnO30pOyB9CmZ1bmN0aW9uIGNsZWFyRGlydHkoZWwpeyBlbC5kYXRhc2V0LmRpcnR5PScnOyB9CmZ1bmN0aW9uIHNldENsZWFuKGVsLHZhbCl7IGlmKGlzRGlydHkoZWwpKXJldHVybjsgaWYoZWwudmFsdWUhPT12YWwpIGVsLnZhbHVlPXZhbDsgfSAgICAgICAgICAgICAgLy8gPGlucHV0PgpmdW5jdGlvbiBzZXRDbGVhblRleHQoZWwsdmFsKXsgaWYoaXNEaXJ0eShlbCkpcmV0dXJuOyBpZihlbC50ZXh0Q29udGVudCE9PXZhbCkgZWwudGV4dENvbnRlbnQ9dmFsOyB9IC8vIGNvbnRlbnRlZGl0YWJsZQpmdW5jdGlvbiBzaG93KGVsLG9uKXsgZWwuc3R5bGUuZGlzcGxheSA9IG9uPycnOidub25lJzsgfQpmdW5jdGlvbiBzYXZlUmVhZFN0YXRlKCl7IHRyeXtsb2NhbFN0b3JhZ2Uuc2V0SXRlbShSRUFEX0tFWSxKU09OLnN0cmluZ2lmeShyZWFkU3RhdGUpKTt9Y2F0Y2goZSl7fSB9CmZ1bmN0aW9uIGlzQ2VvQWN0b3IoYnkpeyByZXR1cm4gKGJ5fHwnJykudHJpbSgpLnRvTG93ZXJDYXNlKCk9PT0nY2VvJzsgfQovLyDilIDilIAgcmVsYXRpb25zIChpc3N1ZSAjMyk6IHBhcmVudC9jaGlsZCArICdibG9ja2VkIGJ5JyBkZXBlbmRlbmNpZXMg4pSA4pSACmNvbnN0IGlzVGVybWluYWw9cz0+cz09PSdkb25lJ3x8cz09PSdjYW5jZWxsZWQnOwpmdW5jdGlvbiBjaGlsZHJlbk9mKGlkKXsgcmV0dXJuIGJvYXJkLm9yZGVyLm1hcCh4PT5ib2FyZC50YXNrc1t4XSkuZmlsdGVyKHQ9PnQmJnQucGFyZW50PT09aWQpOyB9CmZ1bmN0aW9uIHVubWV0RGVwcyh0KXsgcmV0dXJuICh0LmRlcGVuZHNPbnx8W10pLmZpbHRlcihpZD0+e2NvbnN0IHg9Ym9hcmQudGFza3NbaWRdOyByZXR1cm4geCAmJiAhaXNUZXJtaW5hbCh4LnN0YXRlKTt9KTsgfQpmdW5jdGlvbiB0YXNrVGl0bGUodCl7IHJldHVybiAodCYmKHQudGV4dHx8JycpLnRyaW0oKSl8fCcodW50aXRsZWQpJzsgfQpmdW5jdGlvbiBzaG9ydFRpdGxlKHQpeyBjb25zdCBzPXRhc2tUaXRsZSh0KTsgcmV0dXJuIHMubGVuZ3RoPjYwP3Muc2xpY2UoMCw1NykrJ+KApic6czsgfQpmdW5jdGlvbiB0YXNrVXBkYXRlRXZlbnRzKHQpewogIGNvbnN0IGl0ZW1zPVtdOwogICh0LmNvbW1lbnRzfHxbXSkuZm9yRWFjaChjPT57IGlmKCFpc0Nlb0FjdG9yKGMuYnkpKSBpdGVtcy5wdXNoKHt0czpjLnRzfHwwfSk7IH0pOwogICh0LnByb29mc3x8W10pLmZvckVhY2gocD0+eyBpZighaXNDZW9BY3RvcihwLmJ5KSkgaXRlbXMucHVzaCh7dHM6cC50c3x8MH0pOyB9KTsKICByZXR1cm4gaXRlbXM7Cn0KZnVuY3Rpb24gbGF0ZXN0VXBkYXRlVHModCl7IHJldHVybiBNYXRoLm1heCgwLC4uLnRhc2tVcGRhdGVFdmVudHModCkubWFwKGU9PmUudHN8fDApKTsgfQpmdW5jdGlvbiB1bnJlYWRDb3VudCh0KXsKICBjb25zdCBsYXN0PU51bWJlcihyZWFkU3RhdGVbdC5pZF18fDApOwogIHJldHVybiB0YXNrVXBkYXRlRXZlbnRzKHQpLmZpbHRlcihlPT4oZS50c3x8MCk+bGFzdCkubGVuZ3RoOwp9CmZ1bmN0aW9uIG1hcmtUYXNrUmVhZChpZCl7CiAgY29uc3QgdD1ib2FyZC50YXNrc1tpZF07IGlmKCF0KXJldHVybjsKICBjb25zdCBsYXRlc3Q9bGF0ZXN0VXBkYXRlVHModCk7CiAgaWYobGF0ZXN0PihOdW1iZXIocmVhZFN0YXRlW2lkXXx8MCkpKXsKICAgIHJlYWRTdGF0ZVtpZF09bGF0ZXN0OyBzYXZlUmVhZFN0YXRlKCk7CiAgICBpZihlbHNbaWRdKSBzeW5jVGFzayhlbHNbaWRdLHQpOwogIH0KfQpmdW5jdGlvbiBzZWVkUmVhZEJhc2VsaW5lcyhpZHMpewogIGlmKHJlYWRTZWVkZWQpIHJldHVybjsKICBpZHMuZm9yRWFjaChpZD0+eyBjb25zdCB0PWJvYXJkLnRhc2tzW2lkXTsgaWYodCAmJiByZWFkU3RhdGVbaWRdPT09dW5kZWZpbmVkKSByZWFkU3RhdGVbaWRdPWxhdGVzdFVwZGF0ZVRzKHQpOyB9KTsKICByZWFkU2VlZGVkPXRydWU7IHNhdmVSZWFkU3RhdGUoKTsKICB0cnl7IGxvY2FsU3RvcmFnZS5zZXRJdGVtKFJFQURfU0VFREVEX0tFWSwnMScpOyB9Y2F0Y2goZSl7fQp9CgovLyDilIDilIAgbGl2ZSBwb2xsOiBmZXRjaCBib2FyZCwgcmVjb25jaWxlIG9ubHkgdGhlIGRlbHRhLiBOTyBwYWdlIHJlbG9hZC4g4pSA4pSA4pSA4pSA4pSA4pSACmFzeW5jIGZ1bmN0aW9uIHB1bGwoKXsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKCcvdG9kby9ib2FyZCcse2hlYWRlcnM6SCgpfSk7CiAgICBpZighci5vayl7IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjb25uJykudGV4dENvbnRlbnQ9KHIuc3RhdHVzPT09NDAzPydhdXRoJzonb2ZmbGluZScpOyByZXR1cm47IH0KICAgIGNvbnN0IG5iPWF3YWl0IHIuanNvbigpOwogICAgaWYobmIuYnVpbGQgJiYgQlVJTEQhPT0nX19CVUlMRF9fJyAmJiBuYi5idWlsZCE9PUJVSUxEKXsgbG9jYXRpb24ucmVsb2FkKCk7IHJldHVybjsgfSAgIC8vIGEgbmV3ZXIgYm9hcmQgc2hpcHBlZCAtPiByZWxvYWQgdG8gdGhlIGxhdGVzdCBKUwogICAgYm9hcmQ9bmI7IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjb25uJykudGV4dENvbnRlbnQ9J2xpdmUnOyByZWNvbmNpbGUoKTsKICAgIGlmKCFfaGFzaENoZWNrZWQpeyBfaGFzaENoZWNrZWQ9dHJ1ZTsgY2hlY2tIYXNoKCk7IH0gICAvLyBkZWVwIGxpbmsgcHJlc2VudCBhdCBsb2FkIC0+IG9wZW4gdGhhdCBjYXJkIChoYXNoY2hhbmdlIGRvZXNuJ3QgZmlyZSBvbiBpbml0aWFsIGxvYWQpCiAgfWNhdGNoKGUpeyBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29ubicpLnRleHRDb250ZW50PSdvZmZsaW5lJzsgfQp9CgpmdW5jdGlvbiByZWNvbmNpbGUoKXsKICBjb25zdCBpZHM9Ym9hcmQub3JkZXIuZmlsdGVyKGlkPT5ib2FyZC50YXNrc1tpZF0pOyAgICAgICAgLy8gZXZlcnkgcmVhbCBjYXJkLCBpbiBtYW51YWwgb3JkZXIKICBzZWVkUmVhZEJhc2VsaW5lcyhpZHMpOwogIGxldCBkb25lPTA7IGlkcy5mb3JFYWNoKGlkPT57aWYoYm9hcmQudGFza3NbaWRdLnN0YXRlPT09J2RvbmUnKWRvbmUrKzt9KTsKICBjb25zdCB2aWV3SWRzPWFwcGx5VmlldyhpZHMpOyAgICAgICAgICAgICAgICAgICAgICAgICAgICAgLy8gZmlsdGVyZWQgKyBzb3J0ZWQgdmlldyAoY2xpZW50LW9ubHkpCiAgY29uc3QgaGlkZGVuPWlkcy5sZW5ndGgtdmlld0lkcy5sZW5ndGg7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NvdW50cycpLmlubmVySFRNTD0KICAgIGA8c3Bhbj4ke2RvbmV9IGRvbmU8L3NwYW4+PHNwYW4+JHtpZHMubGVuZ3RoLWRvbmV9IG9wZW48L3NwYW4+PHNwYW4+JHtpZHMubGVuZ3RofSB0b3RhbDwvc3Bhbj5gKwogICAgKGhpZGRlbj9gPHNwYW4gY2xhc3M9ImNudC1oaWRkZW4iPiR7aGlkZGVufSBoaWRkZW48L3NwYW4+YDonJyk7ICAgLy8gc3VidGxlIGNvdW50IGNoaXA7IHRoZSAnYWxsJyBwcmVzZXQgY2xlYXJzIGZpbHRlcnMKICByZW5kZXJWaWV3YmFyKCk7CiAgaWYoIWlkcy5sZW5ndGgpeyBpZighbGlzdEVsLnF1ZXJ5U2VsZWN0b3IoJy5lbXB0eScpKSBsaXN0RWwuaW5uZXJIVE1MPSc8bGkgY2xhc3M9ImVtcHR5Ij5OYWRhIGFpbmRhLiBBZGljaW9uYSBhIHByaW1laXJhIHByaW9yaWRhZGUgYWNpbWEuPC9saT4nOyBmb3IoY29uc3QgayBpbiBlbHMpIGRlbGV0ZSBlbHNba107IHJldHVybjsgfQogIGNvbnN0IGJhc2VFbXB0eT1saXN0RWwucXVlcnlTZWxlY3RvcignLmVtcHR5Om5vdCguZmlsdGVyZWQpJyk7IGlmKGJhc2VFbXB0eSkgYmFzZUVtcHR5LnJlbW92ZSgpOwogIGNvbnN0IHN5PXdpbmRvdy5zY3JvbGxZLCBhY3RpdmU9ZG9jdW1lbnQuYWN0aXZlRWxlbWVudDsKICAvLyBjcmVhdGUgKyB1cGRhdGUgaW4gcGxhY2UgKGV2ZXJ5IGNhcmQgaXMga2VwdCBzeW5jZWQsIGV2ZW4gaWYgZmlsdGVyZWQgb3V0KQogIGlkcy5mb3JFYWNoKGlkPT57IHRyeXsgbGV0IGxpPWVsc1tpZF07IGlmKCFsaSl7IGxpPWNyZWF0ZVRhc2soaWQpOyBlbHNbaWRdPWxpOyBsaXN0RWwuYXBwZW5kQ2hpbGQobGkpOyBsaS5jbGFzc0xpc3QuYWRkKCdmcmVzaCcpOyB9IHN5bmNUYXNrKGxpLCBib2FyZC50YXNrc1tpZF0pOyB9CiAgICBjYXRjaChlKXsgY29uc29sZS5lcnJvcigncmVuZGVyIGVycm9yIG9uIGNhcmQnLGlkLGUpOyB9IH0pOyAgIC8vIG9uZSBiYWQgY2FyZCBtdXN0IE5FVkVSIGJsYW5rIHRoZSB3aG9sZSBib2FyZAogIC8vIHJlbW92ZSBnb25lCiAgZm9yKGNvbnN0IGlkIGluIGVscyl7IGlmKCFib2FyZC50YXNrc1tpZF0peyBlbHNbaWRdLnJlbW92ZSgpOyBkZWxldGUgZWxzW2lkXTsgfSB9CiAgLy8gZmlsdGVyOiBzaG93IG9ubHkgY2FyZHMgaW4gdGhlIHZpZXc7IGhpZGRlbiBjYXJkcyBzdGF5IGluIHRoZSBET00gYnV0IGRpc3BsYXk6bm9uZQogIGNvbnN0IHZpc2libGU9bmV3IFNldCh2aWV3SWRzKTsKICBpZHMuZm9yRWFjaChpZD0+eyBlbHNbaWRdLnN0eWxlLmRpc3BsYXkgPSB2aXNpYmxlLmhhcyhpZCk/Jyc6J25vbmUnOyB9KTsKICAvLyAibm90aGluZyBtYXRjaGVzIiBtZXNzYWdlIHdoZW4gdGhlIGZpbHRlciBoaWRlcyBldmVyeXRoaW5nCiAgbGV0IGZlPWxpc3RFbC5xdWVyeVNlbGVjdG9yKCcuZW1wdHkuZmlsdGVyZWQnKTsKICBpZighdmlld0lkcy5sZW5ndGgpeyBpZighZmUpeyBmZT1kb2N1bWVudC5jcmVhdGVFbGVtZW50KCdsaScpOyBmZS5jbGFzc05hbWU9J2VtcHR5IGZpbHRlcmVkJzsgZmUudGV4dENvbnRlbnQ9J05vIGNhcmRzIG1hdGNoIHRoaXMgZmlsdGVyLic7IGxpc3RFbC5hcHBlbmRDaGlsZChmZSk7IH0gfQogIGVsc2UgaWYoZmUpeyBmZS5yZW1vdmUoKTsgZmU9bnVsbDsgfQogIC8vIHJlb3JkZXIgRE9NIG9ubHkgaWYgaXQgYWN0dWFsbHkgY2hhbmdlZDogdmlzaWJsZSAoc29ydGVkKSBmaXJzdCwgdGhlbiBoaWRkZW4gY2FyZHMKICBjb25zdCB0YXJnZXQ9Wy4uLnZpZXdJZHMsIC4uLmlkcy5maWx0ZXIoaWQ9PiF2aXNpYmxlLmhhcyhpZCkpXTsKICBjb25zdCBjdXI9Wy4uLmxpc3RFbC5jaGlsZHJlbl0ubWFwKG49Pm4uZGF0YXNldC5pZCkuZmlsdGVyKEJvb2xlYW4pOwogIGlmKGN1ci5qb2luKCcsJykhPT10YXJnZXQuam9pbignLCcpKSB0YXJnZXQuZm9yRWFjaChpZD0+bGlzdEVsLmFwcGVuZENoaWxkKGVsc1tpZF0pKTsKICBpZihmZSkgbGlzdEVsLmFwcGVuZENoaWxkKGZlKTsgICAgICAgICAgICAgICAgICAgICAgICAgICAgLy8ga2VlcCB0aGUgZmlsdGVyLWVtcHR5IG5vdGljZSBsYXN0CiAgLy8gcHJlc2VydmUgZm9jdXMgKyBzY3JvbGwgYWNyb3NzIHRoZSB0aWNrCiAgaWYoYWN0aXZlICYmIGRvY3VtZW50LmNvbnRhaW5zKGFjdGl2ZSkgJiYgZG9jdW1lbnQuYWN0aXZlRWxlbWVudCE9PWFjdGl2ZSl7IHRyeXthY3RpdmUuZm9jdXMoe3ByZXZlbnRTY3JvbGw6dHJ1ZX0pO31jYXRjaChlKXt9IH0KICBpZih3aW5kb3cuc2Nyb2xsWSE9PXN5KSB3aW5kb3cuc2Nyb2xsVG8oMCxzeSk7CiAgaWYoY2FyZE9wZW5JZCkgcmVuZGVyQ2FyZCgpOyAgICAvLyBzdHJlYW0gbmV3IGFjdGl2aXR5IGludG8gdGhlIG9wZW4gY2FyZCAoY29tcG9zZXIgdW50b3VjaGVkKQp9CgpmdW5jdGlvbiBjcmVhdGVUYXNrKGlkKXsKICBjb25zdCBsaT1kb2N1bWVudC5jcmVhdGVFbGVtZW50KCdsaScpOyBsaS5jbGFzc05hbWU9J3Rhc2snOyBsaS5kYXRhc2V0LmlkPWlkOwogIGxpLmlubmVySFRNTD1gCiAgICA8ZGl2IGNsYXNzPSJ0YXNrLXRvcCI+CiAgICAgIDxkaXYgY2xhc3M9ImNoZWNrIiB0aXRsZT0iIj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0idGFzay1tYWluIj4KICAgICAgICA8ZGl2IGNsYXNzPSJ0YXNrLXRleHQiIGNvbnRlbnRlZGl0YWJsZT0idHJ1ZSIgc3BlbGxjaGVjaz0iZmFsc2UiPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9Im1ldGEiPjxzcGFuIGNsYXNzPSJiYWRnZSI+PC9zcGFuPjxzcGFuIGNsYXNzPSJ1bnJlYWQtYmFkZ2UiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPjwvc3Bhbj48c3BhbiBjbGFzcz0idGFnIGFzZy10YWciPjwvc3Bhbj48c3BhbiBjbGFzcz0iYmFkZ2Ugc3QtZG9uZSB2ZXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPnZlcmlmaWVkPC9zcGFuPjxzcGFuIGNsYXNzPSJyZWxzIj48L3NwYW4+PHNwYW4gY2xhc3M9InBpbmciPjwvc3Bhbj48L2Rpdj4KICAgICAgPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImN0cmxzIj48YnV0dG9uIGNsYXNzPSJpY3RybCBvcGVuIiB0aXRsZT0ib3BlbiBjYXJkIOKAlCBmdWxsIGhpc3RvcnkiPuKkojwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImljdHJsIHVwIj7ihpE8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJpY3RybCBkb3duIj7ihpM8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJpY3RybCBkZWwiPsOXPC9idXR0b24+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InJvdyI+PHNwYW4gY2xhc3M9ImxhYmVsIHJlcSI+ZG9uZS1jb25kaXRpb248L3NwYW4+PGlucHV0IGNsYXNzPSJmaWVsZCBjb25kIiBwbGFjZWhvbGRlcj0iaG93IGRvIHdlIHZlcmlmeSB0aGlzIGlzIERPTkU/Ij48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InJvdyI+PGxhYmVsIGNsYXNzPSJ0b2dnbGUiPjxzcGFuIGNsYXNzPSJzdyI+PC9zcGFuPndvcmsgdG8gZG9uZTwvbGFiZWw+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJuZWVkYnJhaW4iIHN0eWxlPSJkaXNwbGF5Om5vbmUiPuKaoCBOZWVkcyBicmFpbnN0b3JtIOKAlCBub3Qgd29ya2FibGUgdW50aWwgcHJvbW90ZWQuIEFuc3dlciB0aGUgb3BlbiBxdWVzdGlvbihzKSwgdGhlbiBpdCBtb3ZlcyB0byB3b3JraW5nLjwvZGl2PgogICAgPGRpdiBjbGFzcz0iYnJhaW5zdG9ybSIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+PHNwYW4gY2xhc3M9ImgiPmJyYWluc3Rvcm08L3NwYW4+PHNwYW4gY2xhc3M9ImJzLWJvZHkiPjwvc3Bhbj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InN0YXR1cyIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwcm9vZnMiPjxzcGFuIGNsYXNzPSJwcm9vZi1saXN0Ij48L3NwYW4+PC9kaXY+YDsKICBjb25zdCByPXsgY2hlY2s6bGkucXVlcnlTZWxlY3RvcignLmNoZWNrJyksIHRleHQ6bGkucXVlcnlTZWxlY3RvcignLnRhc2stdGV4dCcpLCBiYWRnZTpsaS5xdWVyeVNlbGVjdG9yKCcuYmFkZ2UnKSwKICAgIHVucmVhZDpsaS5xdWVyeVNlbGVjdG9yKCcudW5yZWFkLWJhZGdlJyksIGFzZ1RhZzpsaS5xdWVyeVNlbGVjdG9yKCcuYXNnLXRhZycpLCB2ZXI6bGkucXVlcnlTZWxlY3RvcignLnZlcicpLCBwaW5nOmxpLnF1ZXJ5U2VsZWN0b3IoJy5waW5nJyksIHJlbHM6bGkucXVlcnlTZWxlY3RvcignLnJlbHMnKSwKICAgIGNvbmQ6bGkucXVlcnlTZWxlY3RvcignLmNvbmQnKSwgdG9nZ2xlOmxpLnF1ZXJ5U2VsZWN0b3IoJy50b2dnbGUnKSwKICAgIGJyYWluOmxpLnF1ZXJ5U2VsZWN0b3IoJy5icmFpbnN0b3JtJyksIGJzQm9keTpsaS5xdWVyeVNlbGVjdG9yKCcuYnMtYm9keScpLCBzdGF0dXM6bGkucXVlcnlTZWxlY3RvcignLnN0YXR1cycpLCBuZWVkYnJhaW46bGkucXVlcnlTZWxlY3RvcignLm5lZWRicmFpbicpLAogICAgcHJvb2ZMaXN0OmxpLnF1ZXJ5U2VsZWN0b3IoJy5wcm9vZi1saXN0JyksIHVwOmxpLnF1ZXJ5U2VsZWN0b3IoJy51cCcpLCBkb3duOmxpLnF1ZXJ5U2VsZWN0b3IoJy5kb3duJyksIGRlbDpsaS5xdWVyeVNlbGVjdG9yKCcuZGVsJyksCiAgICBvcGVuOmxpLnF1ZXJ5U2VsZWN0b3IoJy5vcGVuJyksIHBzaWc6bnVsbCB9OwogIGxpLl9yPXI7CiAgY29uc3QgVD0oKT0+Ym9hcmQudGFza3NbaWRdOwogIC8vIHRleHQgKGNvbnRlbnRlZGl0YWJsZSkKICB3YXRjaERpcnR5KHIudGV4dCk7CiAgci50ZXh0Lm9uYmx1cj0oKT0+eyBjb25zdCB2PXIudGV4dC50ZXh0Q29udGVudC50cmltKCk7IGNsZWFyRGlydHkoci50ZXh0KTsgY29uc3QgdD1UKCk7IGlmKHQmJnYmJnYhPT10LnRleHQpIHVwZCh7b3A6J3NldCcsaWQsdGV4dDp2fSkudGhlbihwdWxsKTsgfTsKICByLnRleHQub25rZXlkb3duPWU9PnsgaWYoZS5rZXk9PT0nRW50ZXInKXtlLnByZXZlbnREZWZhdWx0KCk7IHIudGV4dC5ibHVyKCk7fSB9OwogIC8vIGNoZWNrIHRvZ2dsZSBkb25lL3VuZG9uZQogIHIuY2hlY2sub25jbGljaz1lPT57IGUuc3RvcFByb3BhZ2F0aW9uKCk7ICAgICAgICAgICAgICAvLyBDRU8gbWFyay1kb25lIOKAlCBtdXN0IE5PVCBidWJibGUgdG8gdGhlIGNhcmQtb3BlbiBoYW5kbGVyCiAgICBjb25zdCB0PVQoKTsgaWYoIXQpcmV0dXJuOwogICAgLy8gUnVsZSAyMTogdGhlIENFTyBtYXJrcyBkb25lIGluIE9ORSBjbGljayBmcm9tIEFOWSBzdGF0ZSAodGhlIHZlcmlmeS9yZXZpZXcgZ2F0ZSBpcyBvbmx5IGZvciB0aGUgQUkpLgogICAgaWYodC5zdGF0ZT09PSdkb25lJykgc3RhdHVzQXBpKHtpZCxzdGF0ZTond29ya2luZycsdmVyaWZpZWQ6ZmFsc2UsYnk6J0NFTyd9KS50aGVuKHB1bGwpOyAgIC8vIHVuLWRvbmUKICAgIGVsc2Ugc3RhdHVzQXBpKHtpZCxzdGF0ZTonZG9uZScsdmVyaWZpZWQ6dHJ1ZSxieTonQ0VPJ30pLnRoZW4ocHVsbCk7IH07ICAgICAgICAgICAgICAgICAgICAgLy8gLT4gZG9uZSwgb25lIGNsaWNrLCBhbnkgc3RhdGUKICAvLyBkb25lLWNvbmRpdGlvbgogIHdhdGNoRGlydHkoci5jb25kKTsKICByLmNvbmQub25ibHVyPSgpPT57IGNvbnN0IHQ9VCgpOyBjbGVhckRpcnR5KHIuY29uZCk7IGlmKHQmJnIuY29uZC52YWx1ZSE9PXQuZG9uZUNvbmRpdGlvbikgdXBkKHtvcDonc2V0JyxpZCxkb25lQ29uZGl0aW9uOnIuY29uZC52YWx1ZX0pLnRoZW4ocHVsbCk7IH07CiAgci5jb25kLm9ua2V5ZG93bj1lPT57IGlmKGUua2V5PT09J0VudGVyJykgci5jb25kLmJsdXIoKTsgfTsKICAvLyB3b3JrLXRvLWRvbmUgdG9nZ2xlCiAgLy8gd29yay10by1kb25lOiBERUJPVU5DRUQgNTAwbXMg4oCUIHJhcGlkIG9uL29mZiBzZXR0bGVzIHRvIE9ORSBmaW5hbCBQT1NUOyBpZiBpdCBuZXRzIGJhY2sgdG8gdGhlCiAgLy8gY3VycmVudCBzZXJ2ZXIgc3RhdGUsIG5vdGhpbmcgaXMgc2VudCAobm8gZHVwbGljYXRlIEJvc3Mgbm90aWZpY2F0aW9uKS4KICByLnRvZ2dsZS5vbmNsaWNrPSgpPT57IGNvbnN0IHQ9VCgpOyBpZighdHx8ISh0LmRvbmVDb25kaXRpb258fCcnKS50cmltKCkpcmV0dXJuOwogICAgaWYoci5fcGVuZFd0ZD09PXVuZGVmaW5lZCkgci5fcGVuZFd0ZD0hIXQud29ya1RvRG9uZTsKICAgIHIuX3BlbmRXdGQ9IXIuX3BlbmRXdGQ7CiAgICByLnRvZ2dsZS5jbGFzc0xpc3QudG9nZ2xlKCdvbicsIHIuX3BlbmRXdGQpOyAgICAgICAgICAgIC8vIGltbWVkaWF0ZSB2aXN1YWwgZmVlZGJhY2sKICAgIGNsZWFyVGltZW91dChyLl93dGRUaW1lcik7CiAgICByLl93dGRUaW1lcj1zZXRUaW1lb3V0KCgpPT57IGNvbnN0IGN1cj1UKCksIHdhbnQ9ci5fcGVuZFd0ZDsgci5fcGVuZFd0ZD11bmRlZmluZWQ7CiAgICAgIGlmKGN1ciAmJiB3YW50IT09ISFjdXIud29ya1RvRG9uZSkgdXBkKHtvcDonc2V0JyxpZCx3b3JrVG9Eb25lOndhbnR9KS50aGVuKHB1bGwpOyAgIC8vIG9ubHkgdGhlIG5ldCBjaGFuZ2UgZmlyZXMKICAgICAgZWxzZSBwdWxsKCk7ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgLy8gbm8gbmV0IGNoYW5nZSAtPiByZXN5bmMsIHNlbmQgbm90aGluZwogICAgfSwgNTAwKTsKICB9OwogIC8vIGNsaWNrIHRoZSBsaW5rZWQtZW5naW5lZXIgY2hpcCAtPiBhdHRhY2ggdG8gaXRzIHRlcm1pbmFsIChkb24ndCBhbHNvIG9wZW4gdGhlIGNhcmQpCiAgci5hc2dUYWcub25jbGljaz1lPT57IGNvbnN0IHQ9VCgpOyBpZih0JiZpc0F0dGFjaGFibGUodC5hc3NpZ25lZSkpeyBlLnN0b3BQcm9wYWdhdGlvbigpOyBhdHRhY2hUb0VuZ2luZWVyKHQuYXNzaWduZWUpOyB9IH07CiAgLy8gcmVvcmRlciAvIGRlbGV0ZQogIHIudXAub25jbGljaz0oKT0+bW92ZShpZCwtMSk7IHIuZG93bi5vbmNsaWNrPSgpPT5tb3ZlKGlkLDEpOwogIHIuZGVsLm9uY2xpY2s9KCk9PnsgaWYoY29uZmlybSgnRGVsZXRlIHRoaXMgcHJpb3JpdHk/JykpIHVwZCh7b3A6J2RlbCcsaWR9KS50aGVuKHB1bGwpOyB9OwogIC8vIG9wZW4gdGhlIGlzc3VlLXN0eWxlIGNhcmQgKGV4cGxpY2l0IOKkoiwgb3IgY2xpY2sgdGhlIGNhcmQgYm9keSBhd2F5IGZyb20gYW55IGNvbnRyb2wpCiAgci5vcGVuLm9uY2xpY2s9ZT0+eyBlLnN0b3BQcm9wYWdhdGlvbigpOyBvcGVuQ2FyZChpZCk7IH07CiAgbGkuYWRkRXZlbnRMaXN0ZW5lcignY2xpY2snLGU9PnsgaWYoZS50YXJnZXQuY2xvc2VzdCgnaW5wdXQsdGV4dGFyZWEsYnV0dG9uLGEsbGFiZWwsdmlkZW8sW2NvbnRlbnRlZGl0YWJsZV0sLmNoZWNrLC5jdHJscywucHJvb2ZzLC50b2dnbGUnKSkgcmV0dXJuOyBvcGVuQ2FyZChpZCk7IH0pOwogIHJldHVybiBsaTsKfQoKZnVuY3Rpb24gcHJvb2ZDaGlwKHApewogIGlmKHAudHlwZT09PSdpbWFnZScpIHJldHVybiBgPGEgY2xhc3M9InByb29mIGltZyIgaHJlZj0iJHtlc2MocC5yZWYpfSIgdGFyZ2V0PSJfYmxhbmsiIHRpdGxlPSIke2VzYyhwLmNhcHRpb258fCdpbWFnZScpfSI+PGltZyBzcmM9IiR7ZXNjKHAucmVmKX0iIGxvYWRpbmc9ImxhenkiIGFsdD0icHJvb2YiPjwvYT5gOwogIGlmKHAudHlwZT09PSd2aWRlbycpIHJldHVybiBgPGRpdiBjbGFzcz0icHJvb2YgdmlkIj48dmlkZW8gY2xhc3M9InB2aWQiIGNvbnRyb2xzIHByZWxvYWQ9Im1ldGFkYXRhIiBwbGF5c2lubGluZSBzcmM9IiR7ZXNjKHAucmVmKX0iPjwvdmlkZW8+YAogICAgICArIGA8YSBjbGFzcz0idmNhcCIgaHJlZj0iJHtlc2MocC5yZWYpfSIgdGFyZ2V0PSJfYmxhbmsiPuKWtiAke2VzYyhwLmNhcHRpb258fCd3YXRjaCBwcm9vZicpfSDihpc8L2E+PC9kaXY+YDsKICBpZihwLnR5cGU9PT0nbGluaycpICByZXR1cm4gYDxhIGNsYXNzPSJwcm9vZiIgaHJlZj0iJHtlc2MocC5yZWYpfSIgdGFyZ2V0PSJfYmxhbmsiPvCflJcgJHtlc2MocC5yZWYpfTwvYT5gOwogIHJldHVybiBgPHNwYW4gY2xhc3M9InByb29mIiB0aXRsZT0iJHtlc2MocC5yZWYpfSI+8J+TnSAke2VzYyhwLnJlZil9PC9zcGFuPmA7Cn0KZnVuY3Rpb24gaXNNZWRpYVByb29mKHApeyByZXR1cm4gcCAmJiAocC50eXBlPT09J2ltYWdlJ3x8cC50eXBlPT09J3ZpZGVvJyk7IH0KZnVuY3Rpb24gaG9tZVByb29mc0h0bWwocHJvb2ZzKXsKICBjb25zdCBwcz1wcm9vZnN8fFtdLCBtZWRpYT1wcy5maWx0ZXIoaXNNZWRpYVByb29mKTsKICBjb25zdCBzaG93bk1lZGlhPW5ldyBTZXQobWVkaWEuc2xpY2UoMCxIT01FX01FRElBX1BSRVZJRVdfTElNSVQpLm1hcChwPT5wLmlkKSk7CiAgbGV0IGh0bWw9cHMuZmlsdGVyKHA9PiFpc01lZGlhUHJvb2YocCl8fHNob3duTWVkaWEuaGFzKHAuaWQpKS5tYXAocHJvb2ZDaGlwKS5qb2luKCcnKTsKICBjb25zdCBoaWRkZW49bWVkaWEubGVuZ3RoLUhPTUVfTUVESUFfUFJFVklFV19MSU1JVDsKICBpZihoaWRkZW4+MCkgaHRtbCs9YDxidXR0b24gdHlwZT0iYnV0dG9uIiBjbGFzcz0icHJvb2YgbW9yZSIgdGl0bGU9Im9wZW4gY2FyZCB0byB2aWV3IGFsbCAke21lZGlhLmxlbmd0aH0gbWVkaWEgYXR0YWNobWVudHMiPiske2hpZGRlbn0gbW9yZTwvYnV0dG9uPmA7CiAgcmV0dXJuIGh0bWw7Cn0KCmZ1bmN0aW9uIHN5bmNUYXNrKGxpLHQpewogIGNvbnN0IHI9bGkuX3I7CiAgbGkuY2xhc3NMaXN0LnRvZ2dsZSgnZG9uZScsIHQuc3RhdGU9PT0nZG9uZScpOwogIGxpLmNsYXNzTGlzdC50b2dnbGUoJ2NhbmNlbGxlZCcsIHQuc3RhdGU9PT0nY2FuY2VsbGVkJyk7CiAgLy8gdGhlIENFTyBjYW4gbWFyayBkb25lIGZyb20gQU5ZIHN0YXRlIChSdWxlIDIxLCBvbmUgY2xpY2spIC0+IHRoZSBjaGVjayBpcyBhbHdheXMgZW5hYmxlZAogIHIuY2hlY2suY2xhc3NMaXN0LnRvZ2dsZSgnb24nLCB0LnN0YXRlPT09J2RvbmUnKTsKICByLmNoZWNrLmNsYXNzTGlzdC5yZW1vdmUoJ2Rpc2FibGVkJyk7CiAgci5jaGVjay50ZXh0Q29udGVudCA9IHQuc3RhdGU9PT0nZG9uZScgPyAn4pyTJyA6ICcnOwogIHIuY2hlY2sudGl0bGUgPSB0LnN0YXRlPT09J2RvbmUnID8gJ21hcmsgbm90LWRvbmUnIDogJ21hcmsgRE9ORSAoQ0VPLCBvbmUgY2xpY2spJzsKICAvLyB0ZXh0ICsgbWV0YSAobmV2ZXIgY2xvYmJlciBpZiB0aGUgQ0VPIGlzIGVkaXRpbmcpCiAgc2V0Q2xlYW5UZXh0KHIudGV4dCwgdC50ZXh0KTsKICByLmJhZGdlLnRleHRDb250ZW50PVNUTEFCRUxbdC5zdGF0ZV18fHQuc3RhdGU7IHIuYmFkZ2UuY2xhc3NOYW1lPSdiYWRnZSBzdC0nK3Quc3RhdGU7CiAgY29uc3QgdWM9dW5yZWFkQ291bnQodCk7CiAgaWYodWMpeyBzaG93KHIudW5yZWFkLHRydWUpOyByLnVucmVhZC50ZXh0Q29udGVudD11YysnIG5ldyc7IHIudW5yZWFkLnRpdGxlPXVjKycgdW5yZWFkIHRpbWVsaW5lIHVwZGF0ZScrKHVjPjE/J3MnOicnKTsgfQogIGVsc2Ugc2hvdyhyLnVucmVhZCxmYWxzZSk7CiAgY29uc3QgY2FuQXR0YWNoPWlzQXR0YWNoYWJsZSh0LmFzc2lnbmVlKTsKICByLmFzZ1RhZy50ZXh0Q29udGVudCA9IHQuYXNzaWduZWUgPyAnQCcrdC5hc3NpZ25lZSA6ICd1bmFzc2lnbmVkJzsKICByLmFzZ1RhZy5jbGFzc0xpc3QudG9nZ2xlKCdhdHRhY2gnLCBjYW5BdHRhY2gpOwogIHIuYXNnVGFnLnRpdGxlID0gY2FuQXR0YWNoID8gJ2NsaWNrIHRvIGF0dGFjaCB0byAnK3QuYXNzaWduZWUrJ+KAmXMgdGVybWluYWwnIDogJyc7CiAgc2hvdyhyLnZlciwgISF0LnZlcmlmaWVkKTsKICAvLyByZWxhdGlvbnMgaW5kaWNhdG9ycyAoaXNzdWUgIzMpOiBibG9ja2VkLWJ5LCBzdWJ0YXNrIHByb2dyZXNzLCBjaGlsZCBtYXJrZXIKICBjb25zdCBraWRzPWNoaWxkcmVuT2YodC5pZCksIHVtPXVubWV0RGVwcyh0KTsKICBsZXQgcmVsSHRtbD0nJzsKICBpZih1bS5sZW5ndGgpIHJlbEh0bWwrPWA8c3BhbiBjbGFzcz0icmVsIGJsb2NrZWQiIHRpdGxlPSJibG9ja2VkIGJ5ICR7dW0ubGVuZ3RofSB1bmZpbmlzaGVkIHByZXJlcXVpc2l0ZShzKSI+4puUIGJsb2NrZWQgYnkgJHt1bS5sZW5ndGh9PC9zcGFuPmA7CiAgaWYoa2lkcy5sZW5ndGgpeyBjb25zdCBkbj1raWRzLmZpbHRlcihrPT5pc1Rlcm1pbmFsKGsuc3RhdGUpKS5sZW5ndGg7IHJlbEh0bWwrPWA8c3BhbiBjbGFzcz0icmVsIHN1YnMiIHRpdGxlPSIke2RufSBvZiAke2tpZHMubGVuZ3RofSBzdWJ0YXNrcyBkb25lL2NhbmNlbGxlZCI+4oazICR7ZG59LyR7a2lkcy5sZW5ndGh9IHN1YnRhc2tzPC9zcGFuPmA7IH0KICBpZih0LnBhcmVudCYmYm9hcmQudGFza3NbdC5wYXJlbnRdKSByZWxIdG1sKz1gPHNwYW4gY2xhc3M9InJlbCBjaGlsZCIgdGl0bGU9InN1YnRhc2sgb2Y6ICR7ZXNjKHNob3J0VGl0bGUoYm9hcmQudGFza3NbdC5wYXJlbnRdKSl9Ij5zdWJ0YXNrPC9zcGFuPmA7CiAgaWYoci5yZWxzLmlubmVySFRNTCE9PXJlbEh0bWwpIHIucmVscy5pbm5lckhUTUw9cmVsSHRtbDsKICByLnBpbmcudGV4dENvbnRlbnQ9J+KGkWJvc3MgJysodC5waW5nc1RvQm9zc3x8MCk7CiAgLy8gZmllbGRzCiAgc2V0Q2xlYW4oci5jb25kLCB0LmRvbmVDb25kaXRpb258fCcnKTsKICBpZihyLl9wZW5kV3RkPT09dW5kZWZpbmVkKSByLnRvZ2dsZS5jbGFzc0xpc3QudG9nZ2xlKCdvbicsICEhdC53b3JrVG9Eb25lKTsgICAvLyBkb24ndCBjbG9iYmVyIGEgcGVuZGluZyAoZGVib3VuY2luZykgdG9nZ2xlCiAgci50b2dnbGUuY2xhc3NMaXN0LnRvZ2dsZSgnZGlzYWJsZWQnLCAhKHQuZG9uZUNvbmRpdGlvbnx8JycpLnRyaW0oKSk7ICAgLy8gd29yay10by1kb25lIHN0aWxsIG5lZWRzIGEgZG9uZS1jb25kaXRpb24gKHNlcnZlci1lbmZvcmNlZCkKICAvLyBicmFpbnN0b3JtCiAgaWYoKHQuYnJhaW5zdG9ybXx8JycpLnRyaW0oKSl7IHNob3coci5icmFpbix0cnVlKTsgaWYoci5ic0JvZHkudGV4dENvbnRlbnQhPT10LmJyYWluc3Rvcm0pIHIuYnNCb2R5LnRleHRDb250ZW50PXQuYnJhaW5zdG9ybTsgfSBlbHNlIHNob3coci5icmFpbixmYWxzZSk7CiAgLy8gbmVlZHMtYnJhaW5zdG9ybSBiYW5uZXIgKHNpbGVudC1uby1vcCBmaXgpOiBhIG5lZWRzX2JyYWluc3Rvcm0gY2FyZCBtdXN0IFNVUkZBQ0UsIG5ldmVyIHNpdCBzaWxlbnQKICBzaG93KHIubmVlZGJyYWluLCB0LnN0YXRlPT09J25lZWRzX2JyYWluc3Rvcm0nKTsKICAvLyBzdGF0dXMgbGluZQogIGlmKHQubGFzdFN0YXR1cyAmJiB0LnN0YXRlIT09J2RvbmUnICYmIHQuc3RhdGUhPT0nY2FuY2VsbGVkJyl7IHNob3coci5zdGF0dXMsdHJ1ZSk7IGNvbnN0IHM9J+KaoCAnK3QubGFzdFN0YXR1czsgaWYoci5zdGF0dXMudGV4dENvbnRlbnQhPT1zKSByLnN0YXR1cy50ZXh0Q29udGVudD1zOyB9IGVsc2Ugc2hvdyhyLnN0YXR1cyxmYWxzZSk7CiAgLy8gaG9tZXBhZ2UgcHJvb2YgcHJldmlld3M6IGNhcCBidWxreSBpbWFnZS92aWRlbyBtZWRpYTsgdGhlIGlzc3VlLXN0eWxlIGNhcmQgc3RpbGwgc2hvd3MgZXZlcnkgcHJvb2YuCiAgY29uc3Qgc2lnPSh0LnByb29mc3x8W10pLm1hcChwPT5bcC5pZCxwLnR5cGUscC5yZWYscC5jYXB0aW9uXS5qb2luKCc6JykpLmpvaW4oJywnKTsKICBpZihzaWchPT1yLnBzaWcpewogICAgci5wcm9vZkxpc3QuaW5uZXJIVE1MPWhvbWVQcm9vZnNIdG1sKHQucHJvb2ZzKTsKICAgIGNvbnN0IG1vcmU9ci5wcm9vZkxpc3QucXVlcnlTZWxlY3RvcignLnByb29mLm1vcmUnKTsKICAgIGlmKG1vcmUpIG1vcmUub25jbGljaz1lPT57IGUucHJldmVudERlZmF1bHQoKTsgZS5zdG9wUHJvcGFnYXRpb24oKTsgb3BlbkNhcmQodC5pZCk7IH07CiAgICByLnBzaWc9c2lnOwogIH0KfQoKZnVuY3Rpb24gbW92ZShpZCxkKXsgY29uc3Qgbz1ib2FyZC5vcmRlci5maWx0ZXIoeD0+Ym9hcmQudGFza3NbeF0pOyBjb25zdCBpPW8uaW5kZXhPZihpZCksaj1pK2Q7IGlmKGo8MHx8aj49by5sZW5ndGgpcmV0dXJuOyBbb1tpXSxvW2pdXT1bb1tqXSxvW2ldXTsgdXBkKHtvcDoncmVvcmRlcicsb3JkZXI6b30pLnRoZW4ocHVsbCk7IH0KCmZ1bmN0aW9uIGFkZCgpeyBjb25zdCB0PWlucHV0LnZhbHVlLnRyaW0oKTsgaWYoIXQpcmV0dXJuOyBpbnB1dC52YWx1ZT0nJzsgdXBkKHtvcDonYWRkJyx0ZXh0OnR9KS50aGVuKHB1bGwpOyB9CmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhZGRCdG4nKS5vbmNsaWNrPWFkZDsKaW5wdXQuYWRkRXZlbnRMaXN0ZW5lcigna2V5ZG93bicsZT0+eyBpZihlLmtleT09PSdFbnRlcicpIGFkZCgpOyB9KTsKCi8vIOKUgOKUgCBJU1NVRS1TVFlMRSBDQVJEIFZJRVcgKHNsaWNlIGIpIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAovLyBDbGlja2luZyBhIHRhc2sgb3BlbnMgYSBtb2RhbCB3aXRoIHRoZSBmdWxsLCBkdXJhYmxlIG1lc3NhZ2UgaGlzdG9yeSBmb3IgdGhhdCB0YXNrIOKAlAovLyBHaXRIdWItaXNzdWUgc3R5bGU6IHRoZSBvcGVuaW5nIGV2ZW50LCB0aGVuIEFJL2VuZ2luZWVyICsgQ0VPIGNvbW1lbnRzLCBzdGF0dXMgdXBkYXRlcywKLy8gc3RhdGUgdHJhbnNpdGlvbnMsIHRoZSBicmFpbnN0b3JtIGFydGlmYWN0LCBhbmQgaW1hZ2UvdmlkZW8gcHJvb2ZzLCBtZXJnZWQgYnkgdGltZXN0YW1wLgovLyBSZS1yZW5kZXJzIGxpdmUgb24gZXZlcnkgcG9sbCB3aGlsZSBvcGVuLCBzbyBuZXcgYWN0aXZpdHkgc3RyZWFtcyBpbiAoY29tcG9zZXIgaXMgbmV2ZXIKLy8gY2xvYmJlcmVkIOKAlCBpdCBsaXZlcyBvdXRzaWRlIHRoZSByZS1yZW5kZXJlZCByZWdpb247IGRpcnR5IHRleHQgKyBmb2N1cyBzdXJ2aXZlIHRoZSB0aWNrKS4KbGV0IGNhcmRPcGVuSWQ9bnVsbCwgX2hhc2hDaGVja2VkPWZhbHNlOwpjb25zdCBtb2RhbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FyZE1vZGFsJyk7CmNvbnN0IGNhcmRUaXRsZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FyZFRpdGxlJyksIGNhcmRTdWI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRTdWInKTsKY29uc3QgY2FyZENvbmQ9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRDb25kJyksIGNhcmRDb25kQm9keT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FyZENvbmRCb2R5Jyk7CmNvbnN0IGNhcmRBcnQ9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRBcnQnKSwgY2FyZEFydEJvZHk9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRBcnRCb2R5Jyk7CmNvbnN0IGNhcmRUaHJlYWQ9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRUaHJlYWQnKSwgY2FyZENvbXBvc2U9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRDb21wb3NlJyk7CmNvbnN0IGNhcmRRYT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FyZFFhJyksIGNhcmRTdGF0ZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FyZFN0YXRlJyksIGNhcmRSZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRSZWwnKTsKLy8gcmVsYXRpb25zIHBhbmVsIGluc2lkZSB0aGUgb3BlbmVkIGNhcmQgKGlzc3VlICMzKTogc3VidGFza3MgKyAnYmxvY2tlZCBieScgZGVwcyArIGhhcmQtZ2F0ZSB0b2dnbGUuCi8vIFNpZ25hdHVyZS1nYXRlZCBzbyBsaXZlIHBvbGxzIGRvbid0IGNsb2JiZXIgYSBoYWxmLXR5cGVkIHN1YnRpdGxlIG9yIHJlc2V0IHRoZSBkZXBlbmRlbmN5IHBpY2tlci4KZnVuY3Rpb24gcmVuZGVyUmVsYXRpb25zKHQpewogIGNvbnN0IGtpZHM9Y2hpbGRyZW5PZih0LmlkKSwgZGVwcz0odC5kZXBlbmRzT258fFtdKS5tYXAoaWQ9PmJvYXJkLnRhc2tzW2lkXSkuZmlsdGVyKEJvb2xlYW4pOwogIGNvbnN0IHNpZz1KU09OLnN0cmluZ2lmeShbdC5oYXJkR2F0ZSxraWRzLm1hcChrPT5bay5pZCxrLnN0YXRlLGsudGV4dF0pLGRlcHMubWFwKGQ9PltkLmlkLGQuc3RhdGUsZC50ZXh0XSksYm9hcmQub3JkZXIubGVuZ3RoXSk7CiAgaWYoY2FyZFJlbC5fc2lnPT09c2lnKXsgc2hvdyhjYXJkUmVsLHRydWUpOyByZXR1cm47IH0gY2FyZFJlbC5fc2lnPXNpZzsKICBjb25zdCBiYWRnZT1zPT5gPHNwYW4gY2xhc3M9ImJhZGdlIHN0LSR7c30iIHN0eWxlPSJmb250LXNpemU6OXB4O3BhZGRpbmc6MnB4IDdweCI+JHtlc2MoU1RMQUJFTFtzXXx8cyl9PC9zcGFuPmA7CiAgY29uc3QgZG9uZU49a2lkcy5maWx0ZXIoaz0+aXNUZXJtaW5hbChrLnN0YXRlKSkubGVuZ3RoOwogIGxldCBodG1sPWA8ZGl2IGNsYXNzPSJyZWwtc2VjIj48c3BhbiBjbGFzcz0iaCI+c3VidGFza3Mke2tpZHMubGVuZ3RoP2AgwrcgJHtkb25lTn0vJHtraWRzLmxlbmd0aH0gZG9uZWA6Jyd9PC9zcGFuPmA7CiAgaHRtbCs9IGtpZHMubGVuZ3RoID8ga2lkcy5tYXAoaz0+YDxkaXYgY2xhc3M9InJlbC1yb3ciPjxhIGNsYXNzPSJyZWwtbGluayIgZGF0YS1vcGVuPSIke2suaWR9Ij7ihrMgJHtlc2Moc2hvcnRUaXRsZShrKSl9PC9hPiR7YmFkZ2Uoay5zdGF0ZSl9PC9kaXY+YCkuam9pbignJykKICAgICAgICAgICAgICAgICAgICAgOiBgPGRpdiBjbGFzcz0icmVsLWVtcHR5Ij5ObyBzdWJ0YXNrcyB5ZXQuPC9kaXY+YDsKICBodG1sKz1gPGRpdiBjbGFzcz0icmVsLWFkZCI+PGlucHV0IGlkPSJyZWxTdWJUZXh0IiBwbGFjZWhvbGRlcj0ibmV3IHN1YnRhc2sgdGl0bGXigKYiIG1heGxlbmd0aD0iMjQwIj48YnV0dG9uIGlkPSJyZWxTdWJBZGQiPkFkZCBzdWJ0YXNrPC9idXR0b24+PC9kaXY+PC9kaXY+YDsKICBodG1sKz1gPGRpdiBjbGFzcz0icmVsLXNlYyI+PHNwYW4gY2xhc3M9ImgiPmJsb2NrZWQgYnkgKGRlcGVuZGVuY2llcyk8L3NwYW4+YDsKICBodG1sKz0gZGVwcy5sZW5ndGggPyBkZXBzLm1hcChkPT5gPGRpdiBjbGFzcz0icmVsLXJvdyI+PGEgY2xhc3M9InJlbC1saW5rIiBkYXRhLW9wZW49IiR7ZC5pZH0iPiR7aXNUZXJtaW5hbChkLnN0YXRlKT8n4pyTJzon4puUJ30gJHtlc2Moc2hvcnRUaXRsZShkKSl9PC9hPiR7YmFkZ2UoZC5zdGF0ZSl9PGJ1dHRvbiBjbGFzcz0icmVsLWRlbCIgZGF0YS1kZWxkZXA9IiR7ZC5pZH0iIHRpdGxlPSJyZW1vdmUgZGVwZW5kZW5jeSI+w5c8L2J1dHRvbj48L2Rpdj5gKS5qb2luKCcnKQogICAgICAgICAgICAgICAgICAgICAgOiBgPGRpdiBjbGFzcz0icmVsLWVtcHR5Ij5Ob3QgYmxvY2tlZCBieSBhbnl0aGluZy48L2Rpdj5gOwogIGNvbnN0IG9wdHM9Ym9hcmQub3JkZXIubWFwKGlkPT5ib2FyZC50YXNrc1tpZF0pLmZpbHRlcih4PT54JiZ4LmlkIT09dC5pZCYmISh0LmRlcGVuZHNPbnx8W10pLmluY2x1ZGVzKHguaWQpJiZ4LnBhcmVudCE9PXQuaWQpCiAgICAgLm1hcCh4PT5gPG9wdGlvbiB2YWx1ZT0iJHt4LmlkfSI+JHtlc2Moc2hvcnRUaXRsZSh4KSl9IOKAlCAke2VzYyhTVExBQkVMW3guc3RhdGVdfHx4LnN0YXRlKX08L29wdGlvbj5gKS5qb2luKCcnKTsKICBodG1sKz1gPGRpdiBjbGFzcz0icmVsLWFkZCI+PHNlbGVjdCBpZD0icmVsRGVwU2VsIj48b3B0aW9uIHZhbHVlPSIiPmFkZCBhIGRlcGVuZGVuY3nigKY8L29wdGlvbj4ke29wdHN9PC9zZWxlY3Q+PGJ1dHRvbiBpZD0icmVsRGVwQWRkIj5BZGQ8L2J1dHRvbj48L2Rpdj48L2Rpdj5gOwogIGh0bWwrPWA8ZGl2IGNsYXNzPSJyZWwtc2VjIj48bGFiZWwgY2xhc3M9InJlbC1nYXRlIj48c3BhbiBjbGFzcz0idG9nZ2xlJHt0LmhhcmRHYXRlPycgb24nOicnfSIgaWQ9InJlbEdhdGUiPjxzcGFuIGNsYXNzPSJzdyI+PC9zcGFuPjwvc3Bhbj4gaGFyZCBnYXRlIOKAlCBibG9jayBlbnRlcmluZyDigJx3b3JraW5n4oCdIHVudGlsIHByZXJlcXVpc2l0ZXMgYXJlIGRvbmUgPHNwYW4gY2xhc3M9ImdhdGUtaGludCI+KG9mZiBieSBkZWZhdWx0KTwvc3Bhbj48L2xhYmVsPjwvZGl2PmA7CiAgY2FyZFJlbC5pbm5lckhUTUw9aHRtbDsgc2hvdyhjYXJkUmVsLHRydWUpOwogIGNhcmRSZWwucXVlcnlTZWxlY3RvckFsbCgnW2RhdGEtb3Blbl0nKS5mb3JFYWNoKGE9PmEub25jbGljaz0oKT0+b3BlbkNhcmQoYS5kYXRhc2V0Lm9wZW4pKTsKICBjb25zdCBzdWJUZXh0PWNhcmRSZWwucXVlcnlTZWxlY3RvcignI3JlbFN1YlRleHQnKSwgc3ViQWRkPWNhcmRSZWwucXVlcnlTZWxlY3RvcignI3JlbFN1YkFkZCcpOwogIGlmKHN1YkFkZCkgc3ViQWRkLm9uY2xpY2s9KCk9PnsgY29uc3Qgdj0oc3ViVGV4dC52YWx1ZXx8JycpLnRyaW0oKTsgaWYoIXYpcmV0dXJuOyBzdWJBZGQuZGlzYWJsZWQ9dHJ1ZTsgdXBkKHtvcDonYWRkJyx0ZXh0OnYscGFyZW50OnQuaWR9KS50aGVuKHB1bGwpOyB9OwogIGlmKHN1YlRleHQpIHN1YlRleHQub25rZXlkb3duPWU9PnsgaWYoZS5rZXk9PT0nRW50ZXInKXtlLnByZXZlbnREZWZhdWx0KCk7IHN1YkFkZC5jbGljaygpO30gfTsKICBjb25zdCBkZXBTZWw9Y2FyZFJlbC5xdWVyeVNlbGVjdG9yKCcjcmVsRGVwU2VsJyksIGRlcEFkZD1jYXJkUmVsLnF1ZXJ5U2VsZWN0b3IoJyNyZWxEZXBBZGQnKTsKICBpZihkZXBBZGQpIGRlcEFkZC5vbmNsaWNrPSgpPT57IGNvbnN0IHY9ZGVwU2VsLnZhbHVlOyBpZighdilyZXR1cm47IHVwZCh7b3A6J3NldCcsaWQ6dC5pZCxkZXBlbmRzT246Wy4uLih0LmRlcGVuZHNPbnx8W10pLHZdfSkudGhlbihwdWxsKTsgfTsKICBjYXJkUmVsLnF1ZXJ5U2VsZWN0b3JBbGwoJ1tkYXRhLWRlbGRlcF0nKS5mb3JFYWNoKGI9PmIub25jbGljaz0oKT0+dXBkKHtvcDonc2V0JyxpZDp0LmlkLGRlcGVuZHNPbjoodC5kZXBlbmRzT258fFtdKS5maWx0ZXIoeD0+eCE9PWIuZGF0YXNldC5kZWxkZXApfSkudGhlbihwdWxsKSk7CiAgY29uc3QgZ2F0ZT1jYXJkUmVsLnF1ZXJ5U2VsZWN0b3IoJyNyZWxHYXRlJyk7CiAgaWYoZ2F0ZSkgZ2F0ZS5vbmNsaWNrPSgpPT51cGQoe29wOidzZXQnLGlkOnQuaWQsaGFyZEdhdGU6IXQuaGFyZEdhdGV9KS50aGVuKHB1bGwpOwp9Ci8vIG1hbnVhbCBzdGF0dXMgY29udHJvbDogYSBkcm9wZG93biBvbiB0aGUgY2FyZCB0byBtb3ZlIHN0YXRlIGJhY2sgKGUuZy4gcmV2aWV3IC0+IHdvcmtpbmcpIHdpdGhvdXQgZWRpdGluZyBKU09OCmNhcmRTdGF0ZS5pbm5lckhUTUw9U1RBVEVTLm1hcChzPT5gPG9wdGlvbiB2YWx1ZT0iJHtzfSI+JHtlc2MoU1RMQUJFTFtzXXx8cyl9PC9vcHRpb24+YCkuam9pbignJyk7CmNhcmRTdGF0ZS5vbmNoYW5nZT0oKT0+eyBjb25zdCB0PWNhcmRPcGVuSWQmJmJvYXJkLnRhc2tzW2NhcmRPcGVuSWRdOyBjb25zdCB2PWNhcmRTdGF0ZS52YWx1ZTsKICBpZighdHx8dj09PXQuc3RhdGUpIHJldHVybjsKICBzdGF0dXNBcGkoe2lkOmNhcmRPcGVuSWQsc3RhdGU6dixieTonQ0VPJ30pLnRoZW4ocj0+eyBpZihyJiZyLmVycm9yKSBhbGVydChyLmVycm9yKTsgcHVsbCgpOyB9KTsgfTsKCi8vIGJyYWluc3Rvcm0gZ2F0ZSAoc2xpY2UgZCk6IHJlbmRlciB0aGUgaW50ZXJhY3RpdmUgUSZBLiBSZWJ1aWxkcyBPTkxZIHdoZW4gdGhlIHNlcnZlci1zaWRlCi8vIHF1ZXN0aW9uL2Fuc3dlciBzdGF0ZSBjaGFuZ2VzIChzaWduYXR1cmUpLCBzbyBhIGhhbGYtdHlwZWQgYW5zd2VyICsgZm9jdXMgc3Vydml2ZSBsaXZlIHBvbGxzLgpmdW5jdGlvbiByZW5kZXJDYXJkUWEodCl7CiAgaWYodC5zdGF0ZSE9PSduZWVkc19icmFpbnN0b3JtJyl7IHNob3coY2FyZFFhLGZhbHNlKTsgY2FyZFFhLl9zaWc9bnVsbDsgcmV0dXJuOyB9CiAgY29uc3QgcXM9dC5xdWVzdGlvbnN8fFtdOwogIGNvbnN0IHVhPXFzLmZpbHRlcihxPT4hKHEuYW5zd2VyfHwnJykudHJpbSgpKS5sZW5ndGg7CiAgY29uc3QgaGFzQXJ0PSEhKHQuYnJhaW5zdG9ybXx8JycpLnRyaW0oKTsKICBjb25zdCByZWFkeT11YT09PTAgJiYgKHFzLmxlbmd0aD4wIHx8IGhhc0FydCk7CiAgc2hvdyhjYXJkUWEsdHJ1ZSk7CiAgY29uc3Qgc2lnPUpTT04uc3RyaW5naWZ5KHthc2s6dC5icmFpbnN0b3JtQXNrZWQsYXJ0Omhhc0FydCxxOnFzLm1hcChxPT5bcS5pZCwhIShxLmFuc3dlcnx8JycpLnRyaW0oKV0pfSk7CiAgaWYoY2FyZFFhLl9zaWc9PT1zaWcpIHJldHVybjsgICAgICAgICAgICAgICAgIC8vIG5vIHNlcnZlciBjaGFuZ2UgLT4gZG9uJ3QgY2xvYmJlciBpbnB1dHMvZm9jdXMKICBjYXJkUWEuX3NpZz1zaWc7CiAgbGV0IGh0bWw9Jyc7CiAgaWYocXMubGVuZ3RoKXsKICAgIGh0bWwgKz0gdWE+MAogICAgICA/IGA8ZGl2IGNsYXNzPSJxYS1iYW5uZXIgYmxvY2tlZCI+4pqgIE5vdCB3b3JrYWJsZSDigJQgJHt1YX0gb3BlbiBxdWVzdGlvbiR7dWE+MT8ncyc6Jyd9LiBBbnN3ZXIgdG8gdW5ibG9jayB0aGlzIHRhc2suPC9kaXY+YAogICAgICA6IGA8ZGl2IGNsYXNzPSJxYS1iYW5uZXIgcmVhZHkiPuKckyBBbGwgcXVlc3Rpb25zIGFuc3dlcmVkIOKAlCByZWFkeSB0byBwcm9tb3RlLjwvZGl2PmA7CiAgICBodG1sICs9ICc8ZGl2IGNsYXNzPSJxYS1saXN0Ij4nK3FzLm1hcChxPT57CiAgICAgIGNvbnN0IGE9KHEuYW5zd2VyfHwnJykudHJpbSgpOwogICAgICByZXR1cm4gYQogICAgICAgID8gYDxkaXYgY2xhc3M9InFhLWl0ZW0gYW5zd2VyZWQiPjxkaXYgY2xhc3M9InEiPiR7ZXNjKHEucSl9PC9kaXY+PGRpdiBjbGFzcz0icWEtYW5zIj4ke2VzYyhhKX08L2Rpdj48L2Rpdj5gCiAgICAgICAgOiBgPGRpdiBjbGFzcz0icWEtaXRlbSIgZGF0YS1xaWQ9IiR7ZXNjKHEuaWQpfSI+PGRpdiBjbGFzcz0icSI+JHtlc2MocS5xKX08L2Rpdj5gKwogICAgICAgICAgYDxkaXYgY2xhc3M9InFhLWFucy1yb3ciPjx0ZXh0YXJlYSBwbGFjZWhvbGRlcj0iQW5zd2Vy4oCmIj48L3RleHRhcmVhPjxidXR0b24gY2xhc3M9InFhLWFucy1idG4iPkFuc3dlcjwvYnV0dG9uPjwvZGl2PjwvZGl2PmA7CiAgICB9KS5qb2luKCcnKSsnPC9kaXY+JzsKICB9IGVsc2UgaWYoaGFzQXJ0KXsKICAgIGh0bWwgKz0gYDxkaXYgY2xhc3M9InFhLWJhbm5lciByZWFkeSI+4pyTIEJyYWluc3Rvcm1lZCDigJQgcmVhZHkgdG8gcHJvbW90ZSB0byB3b3JraW5nLjwvZGl2PmA7CiAgfSBlbHNlIHsKICAgIGh0bWwgKz0gYDxkaXYgY2xhc3M9InFhLWJhbm5lciBibG9ja2VkIj7ijIEgQnJhaW5zdG9ybWluZyDigJQgZ2VuZXJhdGluZyBjbGFyaWZ5aW5nIHF1ZXN0aW9ucyBmb3IgdGhlIENFT+KApjwvZGl2PmA7CiAgfQogIGlmKHJlYWR5KSBodG1sICs9IGA8YnV0dG9uIGNsYXNzPSJxYS1wcm9tb3RlIj5Qcm9tb3RlIHRvIHdvcmtpbmcg4oaSPC9idXR0b24+YDsKICBjYXJkUWEuaW5uZXJIVE1MPWh0bWw7CiAgY2FyZFFhLnF1ZXJ5U2VsZWN0b3JBbGwoJy5xYS1pdGVtW2RhdGEtcWlkXScpLmZvckVhY2goaXQ9PnsKICAgIGNvbnN0IHFpZD1pdC5kYXRhc2V0LnFpZCwgdGE9aXQucXVlcnlTZWxlY3RvcigndGV4dGFyZWEnKTsKICAgIGNvbnN0IHN1Ym1pdD0oKT0+eyBjb25zdCB2PXRhLnZhbHVlLnRyaW0oKTsgaWYoIXYpcmV0dXJuOyBhbnN3ZXJBcGkoe3Rhc2tfaWQ6Y2FyZE9wZW5JZCxxaWQsYW5zd2VyOnYsYnk6J0NFTyd9KS50aGVuKHB1bGwpOyB9OwogICAgaXQucXVlcnlTZWxlY3RvcignLnFhLWFucy1idG4nKS5vbmNsaWNrPXN1Ym1pdDsKICAgIHRhLm9ua2V5ZG93bj1lPT57IGlmKChlLm1ldGFLZXl8fGUuY3RybEtleSkmJmUua2V5PT09J0VudGVyJyl7IGUucHJldmVudERlZmF1bHQoKTsgc3VibWl0KCk7IH0gfTsKICB9KTsKICBjb25zdCBwYj1jYXJkUWEucXVlcnlTZWxlY3RvcignLnFhLXByb21vdGUnKTsKICBpZihwYikgcGIub25jbGljaz0oKT0+YnJhaW5zdG9ybUFwaSh7aWQ6Y2FyZE9wZW5JZCxwcm9tb3RlOid3b3JraW5nJ30pLnRoZW4ocHVsbCk7Cn0KCmZ1bmN0aW9uIHJlbHRpbWUodHMpeyBpZighdHMpcmV0dXJuJyc7IGNvbnN0IHM9TWF0aC5mbG9vcigoRGF0ZS5ub3coKS10cykvMTAwMCk7CiAgaWYoczw2MClyZXR1cm4gcysncyBhZ28nOyBjb25zdCBtPU1hdGguZmxvb3Iocy82MCk7IGlmKG08NjApcmV0dXJuIG0rJ20gYWdvJzsKICBjb25zdCBoPU1hdGguZmxvb3IobS82MCk7IGlmKGg8MjQpcmV0dXJuIGgrJ2ggYWdvJzsgY29uc3QgZD1NYXRoLmZsb29yKGgvMjQpOwogIHJldHVybiBkPDc/IGQrJ2QgYWdvJyA6IG5ldyBEYXRlKHRzKS50b0xvY2FsZURhdGVTdHJpbmcoKTsgfQpmdW5jdGlvbiBldkNsYXNzKGJ5LGtpbmQpeyBpZihraW5kPT09J2JyYWluc3Rvcm0nKXJldHVybidicmFpbic7IHJldHVybiAoYnl8fCcnKS50b0xvd2VyQ2FzZSgpPT09J2Nlbyc/J2Nlbyc6J2FnZW50JzsgfQpmdW5jdGlvbiBieUxhYmVsKGJ5KXsgaWYoIWJ5KXJldHVybidzeXN0ZW0nOyBpZihieS50b0xvd2VyQ2FzZSgpPT09J2NlbycpcmV0dXJuJ0NFTyc7IGlmKGJ5PT09J2JyYWluc3Rvcm0nKXJldHVybidCcmFpbnN0b3JtJzsgcmV0dXJuIGJ5OyB9CmZ1bmN0aW9uIGluaXRpYWxzKGJ5KXsgaWYoIWJ5KXJldHVybifigKInOyBpZihieS50b0xvd2VyQ2FzZSgpPT09J2NlbycpcmV0dXJuJ0NFTyc7IGlmKGJ5PT09J2JyYWluc3Rvcm0nKXJldHVybidCUic7CiAgY29uc3QgdGFpbD1ieS5zcGxpdCgnLycpLnBvcCgpLnNwbGl0KCc6JykucG9wKCk7IHJldHVybiAodGFpbHx8YnkpLnJlcGxhY2UoL1teYS16MC05XS9naSwnJykuc2xpY2UoMCwyKS50b1VwcGVyQ2FzZSgpfHwn4oCiJzsgfQoKZnVuY3Rpb24gZXZIdG1sKGl0KXsKICAvLyBjb21wYWN0IGNlbnRlcmVkIG1hcmtlcnM6IG9wZW5lZCwgc3RhdGUgdHJhbnNpdGlvbnMsIGJyYWluc3Rvcm0tc2F2ZWQuCiAgLy8gKHRoZSBicmFpbnN0b3JtIGFydGlmYWN0J3MgZnVsbCB0ZXh0IGlzIHBpbm5lZCBhYm92ZSB0aGUgdGhyZWFkLCBzbyB0aGUgdGltZWxpbmUKICAvLyAgb25seSBtYXJrcyBXSEVOIGl0IHdhcyBzYXZlZC91cGRhdGVkIOKAlCBubyBkdXBsaWNhdGVkIHdhbGwgb2YgdGV4dC4pCiAgaWYoaXQua2luZD09PSdzdGF0ZSd8fGl0LmtpbmQ9PT0nb3BlbmVkJ3x8aXQua2luZD09PSdicmFpbnN0b3JtJyl7CiAgICBjb25zdCB0eHQgPSBpdC5raW5kPT09J29wZW5lZCcgPyAnb3BlbmVkIHRoaXMgdGFzaycKICAgICAgICAgICAgICA6IGl0LmtpbmQ9PT0nYnJhaW5zdG9ybScgPyBgYnJhaW5zdG9ybSBhcnRpZmFjdCBzYXZlZCBieSAke2VzYyhieUxhYmVsKGl0LmJ5KSl9YAogICAgICAgICAgICAgIDogZXNjKGl0LmJvZHkpOwogICAgcmV0dXJuIGA8ZGl2IGNsYXNzPSJldiBzdGF0ZSI+PHNwYW4gY2xhc3M9ImV2LXRleHQiPuKMgSAke3R4dH0gwrcgJHtyZWx0aW1lKGl0LnRzKX08L3NwYW4+PC9kaXY+YDsKICB9CiAgbGV0IGJvZHk7CiAgLy8gY29tbWVudCAvIHN0YXR1cyAvIHByb29mLWNhcHRpb24gYm9kaWVzIHJlbmRlciBNQVJLRE9XTiAoWFNTLXNhZmU6IHNlZSBtZFRvSHRtbCkuCiAgaWYoaXQua2luZD09PSdwcm9vZicpewogICAgYm9keT0oaXQuYm9keT9gPGRpdiBjbGFzcz0iZXYtdGV4dCBtZCI+JHttZFRvSHRtbChpdC5ib2R5KX08L2Rpdj5gOicnKStgPGRpdiBjbGFzcz0iZXYtcHJvb2ZzIj4ke3Byb29mQ2hpcChpdC5wcm9vZil9PC9kaXY+YDsKICB9ZWxzZXsgYm9keT1gPGRpdiBjbGFzcz0iZXYtdGV4dCBtZCI+JHttZFRvSHRtbChpdC5ib2R5KX08L2Rpdj5gOyB9CiAgY29uc3Qga2luZExibCA9IGl0LmtpbmQ9PT0nY29tbWVudCcgPyAnJyA6IGA8c3BhbiBjbGFzcz0iZXYta2luZCI+JHtlc2MoaXQua2luZCl9PC9zcGFuPmA7CiAgcmV0dXJuIGA8ZGl2IGNsYXNzPSJldiBldi0ke2l0LmtpbmR9Ij48ZGl2IGNsYXNzPSJhdiAke2V2Q2xhc3MoaXQuYnksaXQua2luZCl9Ij4ke2VzYyhpbml0aWFscyhpdC5ieSkpfTwvZGl2PmArCiAgICBgPGRpdiBjbGFzcz0iZXYtYm9keSI+PGRpdiBjbGFzcz0iZXYtaGQiPjxzcGFuIGNsYXNzPSJldi1ieSI+JHtlc2MoYnlMYWJlbChpdC5ieSkpfTwvc3Bhbj4ke2tpbmRMYmx9YCsKICAgIGA8c3BhbiBjbGFzcz0iZXYtdGltZSI+JHtyZWx0aW1lKGl0LnRzKX08L3NwYW4+PC9kaXY+JHtib2R5fTwvZGl2PjwvZGl2PmA7Cn0KCi8vIFJlLXJlbmRlciBpcyBJTkNSRU1FTlRBTCBhbmQgbm9uLWRpc3J1cHRpdmU6IHRoZSBsaXZlIHBvbGwgbXVzdCBuZXZlciB5YW5rIHRoZSBtb2RhbCB0byB0aGUgdG9wCi8vIG9yIHN0ZWFsIGZvY3VzIGZyb20gdGhlIGNvbXBvc2VyLiBXZSBvbmx5IHRvdWNoIGEgcmVnaW9uIHdoZW4gaXRzIGRhdGEgYWN0dWFsbHkgY2hhbmdlZCwgYW5kIHRoZQovLyB0aHJlYWQgaXMgQVBQRU5ELU9OTFkgKG5ldyBldmVudHMgYXJlIGFkZGVkIHRvIHRoZSBlbmQ7IGV4aXN0aW5nIG5vZGVzIOKAlCBhbmQgdGhlaXIgaW1hZ2VzIOKAlCBhcmUKLy8gbmV2ZXIgcmVidWlsdCkuIFNvIHNjcm9sbFRvcCBob2xkcyBhbmQgdGhlIGNvbXBvc2VyJ3MgZm9jdXMvY2FyZXQvdHlwZWQgdGV4dCBzdXJ2aXZlIGV2ZXJ5IHRpY2suCmZ1bmN0aW9uIHJlbmRlckNhcmQoKXsKICBpZighY2FyZE9wZW5JZCkgcmV0dXJuOwogIGNvbnN0IHQ9Ym9hcmQudGFza3NbY2FyZE9wZW5JZF07CiAgaWYoIXQpeyBjbG9zZUNhcmQoKTsgcmV0dXJuOyB9ICAgICAgICAgICAgICAgICAvLyB0YXNrIGRlbGV0ZWQgd2hpbGUgb3BlbgogIGNvbnN0IHRpdGxlPXQudGV4dHx8Jyh1bnRpdGxlZCknOwogIGlmKGNhcmRUaXRsZS50ZXh0Q29udGVudCE9PXRpdGxlKSBjYXJkVGl0bGUudGV4dENvbnRlbnQ9dGl0bGU7CiAgLy8gc3ViLWhlYWRlcjogcmVidWlsZCBPTkxZIHdoZW4gYSBkaXNwbGF5ZWQgZmllbGQgY2hhbmdlcyAoYXZvaWRzIHBlci10aWNrIHJlZmxvdy9mb2N1cyBjaHVybikKICBjb25zdCBjYW5BdHRhY2g9aXNBdHRhY2hhYmxlKHQuYXNzaWduZWUpOwogIGNvbnN0IHN1YlNpZz1KU09OLnN0cmluZ2lmeShbdC5zdGF0ZSx0LmFzc2lnbmVlLHQud29ya1RvRG9uZSx0LnZlcmlmaWVkLGNhbkF0dGFjaF0pOwogIGlmKGNhcmRTdWIuX3NpZyE9PXN1YlNpZyl7IGNhcmRTdWIuX3NpZz1zdWJTaWc7CiAgICBjYXJkU3ViLmlubmVySFRNTD1gPHNwYW4gY2xhc3M9ImJhZGdlIHN0LSR7dC5zdGF0ZX0iPiR7ZXNjKFNUTEFCRUxbdC5zdGF0ZV18fHQuc3RhdGUpfTwvc3Bhbj5gKwogICAgICBgPHNwYW4gY2xhc3M9InRhZyR7Y2FuQXR0YWNoPycgYXR0YWNoJzonJ30iJHtjYW5BdHRhY2g/YCBkYXRhLWF0dGFjaD0iJHtlc2ModC5hc3NpZ25lZSl9IiB0aXRsZT0iY2xpY2sgdG8gYXR0YWNoIHRvICR7ZXNjKHQuYXNzaWduZWUpfeKAmXMgdGVybWluYWwiYDonJ30+YCsKICAgICAgYCR7dC5hc3NpZ25lZT8nQCcrZXNjKHQuYXNzaWduZWUpOid1bmFzc2lnbmVkJ308L3NwYW4+YCsKICAgICAgKHQud29ya1RvRG9uZT8nPHNwYW4gY2xhc3M9InRhZyI+d29yayDihpIgZG9uZTwvc3Bhbj4nOicnKSsKICAgICAgKHQudmVyaWZpZWQ/JzxzcGFuIGNsYXNzPSJiYWRnZSBzdC1kb25lIj52ZXJpZmllZDwvc3Bhbj4nOicnKSsKICAgICAgYDxzcGFuIGNsYXNzPSJjYXJkLWlkIj4jJHtlc2MoY2FyZE9wZW5JZCl9PC9zcGFuPmA7CiAgfQogIGlmKGRvY3VtZW50LmFjdGl2ZUVsZW1lbnQhPT1jYXJkU3RhdGUgJiYgY2FyZFN0YXRlLnZhbHVlIT09dC5zdGF0ZSkgY2FyZFN0YXRlLnZhbHVlPXQuc3RhdGU7ICAgLy8ga2VlcCB0aGUgc3RhdHVzIGNvbnRyb2wgaW4gc3luYyAoZG9uJ3QgZmlnaHQgdGhlIENFTyBtaWQtc2VsZWN0KQogIGlmKCh0LmRvbmVDb25kaXRpb258fCcnKS50cmltKCkpeyBpZihjYXJkQ29uZEJvZHkudGV4dENvbnRlbnQhPT10LmRvbmVDb25kaXRpb24pIGNhcmRDb25kQm9keS50ZXh0Q29udGVudD10LmRvbmVDb25kaXRpb247IHNob3coY2FyZENvbmQsdHJ1ZSk7IH0gZWxzZSBzaG93KGNhcmRDb25kLGZhbHNlKTsKICByZW5kZXJDYXJkUWEodCk7ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAvLyBicmFpbnN0b3JtIGdhdGUgKHNsaWNlIGQpLCBhbHJlYWR5IHNpZ25hdHVyZS1nYXRlZAogIGlmKCh0LmJyYWluc3Rvcm18fCcnKS50cmltKCkpeyBpZihjYXJkQXJ0Qm9keS50ZXh0Q29udGVudCE9PXQuYnJhaW5zdG9ybSkgY2FyZEFydEJvZHkudGV4dENvbnRlbnQ9dC5icmFpbnN0b3JtOyBzaG93KGNhcmRBcnQsdHJ1ZSk7IH0gZWxzZSBzaG93KGNhcmRBcnQsZmFsc2UpOwogIHJlbmRlclJlbGF0aW9ucyh0KTsgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC8vIHN1YnRhc2tzICsgZGVwZW5kZW5jaWVzIHBhbmVsIChpc3N1ZSAjMykKICAvLyB0aHJlYWQ6IGFwcGVuZCBvbmx5IHRoZSBldmVudHMgbm90IGFscmVhZHkgaW4gdGhlIERPTSAoa2V5ZWQpIOKAlCBuZXZlciByZWJ1aWxkIGV4aXN0aW5nIG5vZGVzCiAgY29uc3QgaXRlbXM9W3trZXk6J29wZW5lZCcsdHM6dC5jcmVhdGVkLGtpbmQ6J29wZW5lZCcsYnk6J0NFTycsYm9keTonJ31dOwogICh0LmNvbW1lbnRzfHxbXSkuZm9yRWFjaChjPT5pdGVtcy5wdXNoKHtrZXk6J2M6JytjLmlkLHRzOmMudHMsa2luZDpjLmtpbmQsYnk6Yy5ieSxib2R5OmMuYm9keX0pKTsKICAodC5wcm9vZnN8fFtdKS5mb3JFYWNoKHA9Pml0ZW1zLnB1c2goe2tleToncDonK3AuaWQsdHM6cC50cyxraW5kOidwcm9vZicsYnk6cC5ieSxib2R5OnAuY2FwdGlvbnx8JycscHJvb2Y6cH0pKTsKICBpdGVtcy5zb3J0KChhLGIpPT4oYS50c3x8MCktKGIudHN8fDApKTsKICBtYXJrVGFza1JlYWQoY2FyZE9wZW5JZCk7CiAgY29uc3QgaGF2ZT1uZXcgU2V0KFsuLi5jYXJkVGhyZWFkLmNoaWxkcmVuXS5tYXAobj0+bi5kYXRhc2V0LmspKTsKICBjb25zdCBuZWFyQm90dG9tPShtb2RhbC5zY3JvbGxIZWlnaHQtbW9kYWwuc2Nyb2xsVG9wLW1vZGFsLmNsaWVudEhlaWdodCk8NjA7CiAgbGV0IGFkZGVkPWZhbHNlOwogIGl0ZW1zLmZvckVhY2goaXQ9PnsgaWYoaGF2ZS5oYXMoaXQua2V5KSlyZXR1cm47CiAgICBjb25zdCB0bXA9ZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnZGl2Jyk7IHRtcC5pbm5lckhUTUw9ZXZIdG1sKGl0KTsgY29uc3Qgbm9kZT10bXAuZmlyc3RFbGVtZW50Q2hpbGQ7CiAgICBpZihub2RlKXsgbm9kZS5kYXRhc2V0Lms9aXQua2V5OyBjYXJkVGhyZWFkLmFwcGVuZENoaWxkKG5vZGUpOyBhZGRlZD10cnVlOyB9IH0pOwogIC8vIGFwcGVuZGVkIGV2ZW50cyBzaXQgQkVMT1cgdGhlIHZpZXdwb3J0LCBzbyBzY3JvbGxUb3AgaXMgdW5hZmZlY3RlZDsgb25seSBhdXRvLWZvbGxvdyBpZiB0aGUKICAvLyBDRU8gd2FzIGFscmVhZHkgYXQgdGhlIGJvdHRvbSAoZG9uJ3QgeWFuayBoaW0gdXAgaWYgaGUncyByZWFkaW5nL3Njcm9sbGVkIG1pZC10aHJlYWQpCiAgaWYoYWRkZWQgJiYgbmVhckJvdHRvbSkgbW9kYWwuc2Nyb2xsVG9wPW1vZGFsLnNjcm9sbEhlaWdodDsKfQoKZnVuY3Rpb24gb3BlbkNhcmQoaWQpeyBpZighYm9hcmQudGFza3NbaWRdKXJldHVybjsgY2FyZE9wZW5JZD1pZDsgbW9kYWwuY2xhc3NMaXN0LmFkZCgnc2hvdycpOwogIGRvY3VtZW50LmJvZHkuc3R5bGUub3ZlcmZsb3c9J2hpZGRlbic7IGNhcmRDb21wb3NlLnZhbHVlPScnOwogIGNhcmRUaHJlYWQuaW5uZXJIVE1MPScnOyBjYXJkU3ViLl9zaWc9bnVsbDsgY2FyZFFhLl9zaWc9bnVsbDsgY2FyZFJlbC5fc2lnPW51bGw7IG1vZGFsLnNjcm9sbFRvcD0wOyAgIC8vIGZyZXNoIHJlbmRlciBmb3IgdGhpcyBjYXJkCiAgbWFya1Rhc2tSZWFkKGlkKTsKICByZW5kZXJDYXJkKCk7CiAgaWYobG9jYXRpb24uaGFzaCE9PScjY2FyZC8nK2lkKXsgdHJ5e2hpc3RvcnkucmVwbGFjZVN0YXRlKG51bGwsJycsJyNjYXJkLycraWQpO31jYXRjaChlKXsgbG9jYXRpb24uaGFzaD0nY2FyZC8nK2lkOyB9IH0gfQpmdW5jdGlvbiBjbG9zZUNhcmQoKXsgY2FyZE9wZW5JZD1udWxsOyBtb2RhbC5jbGFzc0xpc3QucmVtb3ZlKCdzaG93Jyk7IGRvY3VtZW50LmJvZHkuc3R5bGUub3ZlcmZsb3c9Jyc7IGNhcmRDb21wb3NlLnZhbHVlPScnOwogIGlmKC9eI2NhcmRcLy8udGVzdChsb2NhdGlvbi5oYXNofHwnJykpeyB0cnl7aGlzdG9yeS5yZXBsYWNlU3RhdGUobnVsbCwnJyxsb2NhdGlvbi5wYXRobmFtZStsb2NhdGlvbi5zZWFyY2gpO31jYXRjaChlKXsgbG9jYXRpb24uaGFzaD0nJzsgfSB9IH0KLy8gZGVlcCBsaW5rOiAjY2FyZC88aWQ+IG9wZW5zIHRoYXQgY2FyZCBkaXJlY3RseSAodGhlIFdoYXRzQXBwIHBpbmcgbGlua3Mgc3RyYWlnaHQgdG8gdGhlIGNhcmQpCmZ1bmN0aW9uIGNoZWNrSGFzaCgpeyBjb25zdCBtPShsb2NhdGlvbi5oYXNofHwnJykubWF0Y2goL14jY2FyZFwvKFthLXowLTldKykkL2kpOwogIGlmKG0gJiYgYm9hcmQudGFza3NbbVsxXV0gJiYgY2FyZE9wZW5JZCE9PW1bMV0pIG9wZW5DYXJkKG1bMV0pOyB9CndpbmRvdy5hZGRFdmVudExpc3RlbmVyKCdoYXNoY2hhbmdlJyxjaGVja0hhc2gpOwpmdW5jdGlvbiBwb3N0Q29tbWVudCgpeyBjb25zdCB2PWNhcmRDb21wb3NlLnZhbHVlLnRyaW0oKTsgaWYoIXZ8fCFjYXJkT3BlbklkKXJldHVybjsKICBjYXJkQ29tcG9zZS52YWx1ZT0nJzsgY29tbWVudEFwaSh7dGFza19pZDpjYXJkT3BlbklkLGJvZHk6dixieTonQ0VPJ30pLnRoZW4ocHVsbCk7IH0KCmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYXJkQ2xvc2UnKS5vbmNsaWNrPWNsb3NlQ2FyZDsKY2FyZFN1Yi5vbmNsaWNrPWU9PnsgY29uc3QgYz1lLnRhcmdldC5jbG9zZXN0KCcudGFnLmF0dGFjaCcpOyBpZihjJiZjLmRhdGFzZXQuYXR0YWNoKSBhdHRhY2hUb0VuZ2luZWVyKGMuZGF0YXNldC5hdHRhY2gpOyB9Owpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FyZENvbW1lbnRCdG4nKS5vbmNsaWNrPXBvc3RDb21tZW50OwpjYXJkQ29tcG9zZS5vbmtleWRvd249ZT0+eyBpZigoZS5tZXRhS2V5fHxlLmN0cmxLZXkpJiZlLmtleT09PSdFbnRlcicpeyBlLnByZXZlbnREZWZhdWx0KCk7IHBvc3RDb21tZW50KCk7IH0gfTsKbW9kYWwub25jbGljaz1lPT57IGlmKGUudGFyZ2V0PT09bW9kYWwpIGNsb3NlQ2FyZCgpOyB9OyAgICAgICAgICAvLyBjbGljayBiYWNrZHJvcCB0byBjbG9zZQpkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCdrZXlkb3duJyxlPT57IGlmKGUua2V5PT09J0VzY2FwZScmJmNhcmRPcGVuSWQpIGNsb3NlQ2FyZCgpOyB9KTsKCmZ1bmN0aW9uIGNsb2NrKCl7IGNvbnN0IGQ9bmV3IERhdGUoKTsgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2Nsb2NrJykudGV4dENvbnRlbnQ9ZC50b0xvY2FsZVRpbWVTdHJpbmcoKTsgfQpzZXRJbnRlcnZhbChjbG9jaywxMDAwKTsgY2xvY2soKTsKaW5pdFZpZXdiYXIoKTsgcmVuZGVyVmlld2JhcigpOyAgIC8vIGJ1aWxkICsgcmVzdG9yZSB0aGUgZmlsdGVyL3NvcnQgY29udHJvbHMgYmVmb3JlIGZpcnN0IHBhaW50CnNldEludGVydmFsKHB1bGwsMTAwMCk7IHB1bGwoKTsgICAvLyAxcyBsaXZlIHBvbGwsIGluY3JlbWVudGFsIOKAlCBubyByZWxvYWQsIGRpcnR5IGZpZWxkcyBwcmVzZXJ2ZWQKaW5wdXQuZm9jdXMoKTsKPC9zY3JpcHQ+CjwvYm9keT4KPC9odG1sPgo= | base64 -d > "$INSTALL_DIR/bin/todos.html"
echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJ0b2RvLXJlY29uY2lsZSDigJQgdGhlIGRldGVybWluaXN0aWMgbWVjaGFuaWNzIG9mIEJvc3MgUnVsZSA0LgoKVGhlIEJvc3MgcnVucyB0aGlzIG9uIGV2ZXJ5IHBpbmcvU3RvcC9jaGFuZ2UuIEl0IGRvZXMgdGhlIG5vbi1qdWRnbWVudCBwYXJ0czoKICAtIHdvcmtpbmcgKyB3b3JrVG9Eb25lICsgdW5hc3NpZ25lZCAtPiBhc3NpZ24gYW4gaWRsZSBlbmdpbmVlciArIGRpc3BhdGNoCiAgLSB3b3JraW5nICsgcHJvb2YgcHJlc2VudCAgICAgICAgICAgIC0+IGF1dG8tdmVyaWZ5IG1hY2hpbmUtY2hlY2thYmxlIGNvbmRpdGlvbnMKSnVkZ21lbnQgcGFydHMgKGJyYWluc3Rvcm0gd29yZGluZywgZnV6enkgdmVyaWZpY2F0aW9uKSBzdGF5IHdpdGggdGhlIEJvc3MuCgpFbnY6CiAgVE9ET19IT1NUICAgICAgICgxMjcuMC4wLjE6OTkwMCkKICBRVUVVRV9TRUNSRVQgICAgKHNlbnQgb24gd3JpdGVzKQogIERJU1BBVENIICAgICAgICAnbXAnIChyZWFsOiBtcCBzZW5kKSB8ICdzaW0nIChydW4gRU5HSU5FRVJfU0lNKSB8ICdub25lJwogIEVOR0lORUVSX1BPT0wgICBjb21tYSBsaXN0IG9mIGlkbGUgZW5naW5lZXJzIChyZWFsOiBmcm9tIGBtcCBzdGF0dXNgKTsgZGVmYXVsdCAnbWFpbjplbmctMScKICBFTkdJTkVFUl9TSU0gICAgcGF0aCB0byBhIHNjcmlwdCBydW4gYXM6IDxzY3JpcHQ+IDx0YXNrX2lkPiAgIChESVNQQVRDSD1zaW0gb25seSkKIiIiCmltcG9ydCBvcywgcmUsIGpzb24sIHN5cywgc3VicHJvY2VzcywgdXJsbGliLnJlcXVlc3QKCkhPU1QgID0gb3MuZW52aXJvbi5nZXQoIlRPRE9fSE9TVCIsICIxMjcuMC4wLjE6OTkwMCIpClNFQyAgID0gb3MuZW52aXJvbi5nZXQoIlFVRVVFX1NFQ1JFVCIsICIiKQpESVNQICA9IG9zLmVudmlyb24uZ2V0KCJESVNQQVRDSCIsICJtcCIpClBPT0wgID0gW3ggZm9yIHggaW4gb3MuZW52aXJvbi5nZXQoIkVOR0lORUVSX1BPT0wiLCAibWFpbjplbmctMSIpLnNwbGl0KCIsIikgaWYgeF0KRVNJTSAgPSBvcy5lbnZpcm9uLmdldCgiRU5HSU5FRVJfU0lNIiwgIiIpCgpkZWYgYm9hcmQoKToKICAgIHJlcSA9IHVybGxpYi5yZXF1ZXN0LlJlcXVlc3QoZiJodHRwOi8ve0hPU1R9L3RvZG8vYm9hcmQiLAogICAgICAgIGhlYWRlcnM9eyJYLVF1ZXVlLVNlY3JldCI6IFNFQ30gaWYgU0VDIGVsc2Uge30pICAgIyBHRVQgL3RvZG8vYm9hcmQgaXMgYXV0aC1nYXRlZCBvbiBhIHNlY3VyZWQgcnVudGltZQogICAgcmV0dXJuIGpzb24ubG9hZCh1cmxsaWIucmVxdWVzdC51cmxvcGVuKHJlcSkpCmRlZiBwb3N0KHBhdGgsIGJvZHkpOgogICAgcmVxID0gdXJsbGliLnJlcXVlc3QuUmVxdWVzdChmImh0dHA6Ly97SE9TVH17cGF0aH0iLCBkYXRhPWpzb24uZHVtcHMoYm9keSkuZW5jb2RlKCksCiAgICAgICAgaGVhZGVycz17IkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIiwgKiooeyJYLVF1ZXVlLVNlY3JldCI6IFNFQ30gaWYgU0VDIGVsc2Uge30pfSkKICAgIHJldHVybiBqc29uLmxvYWQodXJsbGliLnJlcXVlc3QudXJsb3BlbihyZXEpKQoKZGVmIHBpY2tfaWRsZShiKToKICAgIHVzZWQgPSB7dC5nZXQoImFzc2lnbmVlIikgZm9yIHQgaW4gYlsidGFza3MiXS52YWx1ZXMoKSBpZiB0LmdldCgiYXNzaWduZWUiKX0KICAgIGZvciBlIGluIFBPT0w6CiAgICAgICAgaWYgZSBub3QgaW4gdXNlZDogcmV0dXJuIGUKICAgIHJldHVybiBQT09MWzBdIGlmIFBPT0wgZWxzZSBOb25lCgpkZWYgZGlzcGF0Y2goZW5nLCB0KToKICAgIHByb21wdCA9IChmInt0Wyd0ZXh0J119XG5ET05FLUNPTkRJVElPTjoge3RbJ2RvbmVDb25kaXRpb24nXX1cbiIKICAgICAgICAgICAgICBmIldoZW4gZG9uZSwgYXR0YWNoIHByb29mOiBQT1NUIC90b2RvL3Byb29mIChzdGF5ICd3b3JraW5nJyk7IHRoZSBCb3NzIHZlcmlmaWVzIC0+IGRvbmUuIikKICAgIGlmIERJU1AgPT0gIm1wIiBhbmQgKHN1YiA6PSBfX2ltcG9ydF9fKCdzaHV0aWwnKS53aGljaCgibXAiKSk6CiAgICAgICAgc3VicHJvY2Vzcy5ydW4oWyJtcCIsICJzZW5kIiwgZW5nLCBwcm9tcHRdLCB0aW1lb3V0PTE1KQogICAgZWxpZiBESVNQID09ICJzaW0iIGFuZCBFU0lNOgogICAgICAgIHN1YnByb2Nlc3MuUG9wZW4oW3N5cy5leGVjdXRhYmxlLCBFU0lNLCB0WyJpZCJdXSkKICAgICMgRElTUD1ub25lOiBqdXN0IHJlY29yZCB0aGUgYXNzaWdubWVudCAodGhlIEJvc3Mgd2lsbCBzZW5kIG1hbnVhbGx5KQoKZGVmIHZlcmlmeV9jb25kaXRpb24oY29uZCwgdCk6CiAgICAiIiJSZXR1cm4gVHJ1ZS9GYWxzZS9Ob25lLiBOb25lID0gbmVlZHMgQm9zcyBqdWRnbWVudCAobm90IG1hY2hpbmUtY2hlY2thYmxlKS4iIiIKICAgIG0gPSByZS5zZWFyY2gociJmaWxlXHMrKFxTKylccytjb250YWluc1xzKyguKykiLCBjb25kLCByZS5JKQogICAgaWYgbToKICAgICAgICBwYXRoLCB3YW50ID0gbS5ncm91cCgxKSwgbS5ncm91cCgyKS5zdHJpcCgpCiAgICAgICAgdHJ5OiByZXR1cm4gd2FudCBpbiBvcGVuKHBhdGgpLnJlYWQoKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IHJldHVybiBGYWxzZQogICAgbSA9IHJlLnNlYXJjaChyIkdFVFxzKyhcUyspXHMrcmV0dXJuc1xzKyhcZCspIiwgY29uZCwgcmUuSSkKICAgIGlmIG06CiAgICAgICAgdHJ5OgogICAgICAgICAgICBjb2RlID0gdXJsbGliLnJlcXVlc3QudXJsb3BlbihtLmdyb3VwKDEpLCB0aW1lb3V0PTUpLmdldGNvZGUoKQogICAgICAgICAgICByZXR1cm4gc3RyKGNvZGUpID09IG0uZ3JvdXAoMikKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiByZXR1cm4gRmFsc2UKICAgIHJldHVybiBOb25lICAjIGZyZWUtdGV4dCAtPiBCb3NzIGp1ZGdlcwoKZGVmIG1haW4oKToKICAgIGIgPSBib2FyZCgpOyBhY3RlZCA9IFtdCiAgICBmb3IgdGlkIGluIGIuZ2V0KCJvcmRlciIsIFtdKToKICAgICAgICB0ID0gYlsidGFza3MiXS5nZXQodGlkKQogICAgICAgIGlmIG5vdCB0IG9yIG5vdCB0LmdldCgid29ya1RvRG9uZSIpIG9yIHQuZ2V0KCJzdGF0ZSIpID09ICJkb25lIjoKICAgICAgICAgICAgY29udGludWUKICAgICAgICBzdCA9IHRbInN0YXRlIl0KICAgICAgICBpZiBzdCA9PSAid29ya2luZyIgYW5kIG5vdCB0LmdldCgiYXNzaWduZWUiKToKICAgICAgICAgICAgZW5nID0gcGlja19pZGxlKGIpCiAgICAgICAgICAgIGlmIGVuZzoKICAgICAgICAgICAgICAgIHBvc3QoIi90b2RvL3VwZGF0ZSIsIHsib3AiOiAic2V0IiwgImlkIjogdGlkLCAiYXNzaWduZWUiOiBlbmd9KQogICAgICAgICAgICAgICAgZGlzcGF0Y2goZW5nLCB0KTsgYWN0ZWQuYXBwZW5kKGYiZGlzcGF0Y2gge3RpZH0tPntlbmd9IikKICAgICAgICBlbGlmIHN0ID09ICJ3b3JraW5nIiBhbmQgdC5nZXQoInByb29mcyIpOgogICAgICAgICAgICByZXMgPSB2ZXJpZnlfY29uZGl0aW9uKHQuZ2V0KCJkb25lQ29uZGl0aW9uIiwgIiIpLCB0KQogICAgICAgICAgICBpZiByZXMgaXMgVHJ1ZToKICAgICAgICAgICAgICAgICMgQUkgdmVyaWZpZXMgdGhlIGRvbmUtY29uZGl0aW9uIGJ1dCBjYW4gb25seSBtb3ZlIFVQIFRPIHJldmlldyAoUnVsZSAyMTogb25seSB0aGUgQ0VPCiAgICAgICAgICAgICAgICAjIG1hcmtzIGRvbmUpLiBUaGUgY2FyZCB3YWl0cyBpbiByZXZpZXcgZm9yIHRoZSBDRU8ncyBvbmUtY2xpY2sgc2lnbi1vZmYuCiAgICAgICAgICAgICAgICBwb3N0KCIvdG9kby9zdGF0dXMiLCB7ImlkIjogdGlkLCAidmVyaWZpZWQiOiBUcnVlLCAic3RhdGUiOiAicmV2aWV3In0pCiAgICAgICAgICAgICAgICBhY3RlZC5hcHBlbmQoZiJ2ZXJpZmllZC0+cmV2aWV3IHt0aWR9IChhd2FpdGluZyBDRU8gc2lnbi1vZmYpIikKICAgICAgICAgICAgZWxpZiByZXMgaXMgRmFsc2U6CiAgICAgICAgICAgICAgICBwb3N0KCIvdG9kby9zdGF0dXMiLCB7ImlkIjogdGlkLCAic3RhdGUiOiAid29ya2luZyIsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgImxhc3RTdGF0dXMiOiAibm90IHJlYWR5IGJlY2F1c2UgZG9uZS1jb25kaXRpb24gbm90IHNhdGlzZmllZCBieSBwcm9vZiJ9KQogICAgICAgICAgICAgICAgYWN0ZWQuYXBwZW5kKGYicmVwaW5nIHt0aWR9IikKICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIGFjdGVkLmFwcGVuZChmIm5lZWRzLWJvc3MtanVkZ21lbnQge3RpZH0iKQogICAgcHJpbnQoanNvbi5kdW1wcyh7ImFjdGVkIjogYWN0ZWR9KSkKCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6CiAgICBtYWluKCkK | base64 -d > "$INSTALL_DIR/bin/todo-reconcile"
echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJ0b2RvLWJyYWluc3Rvcm0g4oCUIHRoZSBicmFpbnN0b3JtIEdBVEUgZ2VuZXJhdG9yIChzbGljZSBkKS4KCkZvciBldmVyeSBgbmVlZHNfYnJhaW5zdG9ybWAgdGFzayB0aGF0IGhhc24ndCBiZWVuIGJyYWluc3Rvcm1lZCB5ZXQgKGJyYWluc3Rvcm1Bc2tlZD1GYWxzZSksCmFzayBhIFJFQUwgYnJhaW5zdG9ybSAoaGVhZGxlc3MgYGNsYXVkZSAtcGAsIGdyb3VuZGVkIGluIHRoZSBZQyBvZmZpY2UtaG91cnMgbWV0aG9kKSB0bzoKICAtIGRlY2lkZSB3aGV0aGVyIHRoZSB0YXNrIGlzIHVuZGVyLXNwZWNpZmllZCwgYW5kIGlmIHNvIHByb2R1Y2UgdGhlIGNsYXJpZnlpbmcgUVVFU1RJT05TIGFuCiAgICBlbmdpbmVlciB3b3VsZCBuZWVkIGFuc3dlcmVkIGJlZm9yZSBzdGFydGluZyAocmV0dXJuZWQgdG8gdGhlIENFTyBhcyBxdWVzdGlvbnMgSU4gVEhFIENBUkQpLCBhbmQKICAtIHdyaXRlIGEgc2hvcnQgYnJhaW5zdG9ybSBmcmFtaW5nIHNhdmVkIGFzIHRoZSBkdXJhYmxlIGFydGlmYWN0LgpBIHRhc2sgdGhlIGJyYWluc3Rvcm0ganVkZ2VzIGFscmVhZHktY2xlYXIgZ2V0cyBaRVJPIHF1ZXN0aW9ucyArIGEgb25lLWxpbmUgZnJhbWluZyDihpIgaW1tZWRpYXRlbHkKcHJvbW90YWJsZS4gVGhlIHRhc2sgc3RheXMgYG5lZWRzX2JyYWluc3Rvcm1gIGFuZCBOT04td29ya2FibGUgdW50aWwgZXZlcnkgcXVlc3Rpb24gaXMgYW5zd2VyZWQuCgpUaGlzIGlzIHRoZSByZWFsIGZsb3cgYmVoaW5kICJjcmVhdGUtdGFzayB0cmlnZ2VycyB0aGUgYnJhaW5zdG9ybSBmbG93IiDigJQgbm8gaGFyZGNvZGVkIHF1ZXN0aW9ucy4KVGhlIEJvc3MgcnVucyBpdCBvbiB0aGUgbmVlZHNfYnJhaW5zdG9ybSBwaW5nIChtYWNoaW5lIChhKSksIHRoZSBzYW1lIHdheSBpdCBydW5zIHRvZG8tcmVjb25jaWxlLgoKRW52OgogIFRPRE9fSE9TVCAgICAgKDEyNy4wLjAuMTo5OTAwKQogIFFVRVVFX1NFQ1JFVCAgKHNlbnQgb24gd3JpdGVzKQogIEJSQUlOU1RPUk1fQ01EICBnZW5lcmF0b3IgYXJndjsgZGVmYXVsdCAnY2xhdWRlIC1wJyAocmVhZHMgdGhlIHByb21wdCBvbiBzdGRpbiwgcHJpbnRzIEpTT04pLgogICAgICAgICAgICAgICAgICBTZXQgQlJBSU5TVE9STV9DTUQ9c3R1YiBmb3IgYSBkZXRlcm1pbmlzdGljIG9mZmxpbmUgZ2VuZXJhdG9yICh1c2VkIGJ5ICMjIFZlcmlmeSkuCiAgQlJBSU5TVE9STV9NT0RFTCAgb3B0aW9uYWwgbW9kZWwgZm9yIGNsYXVkZSAoZS5nLiBjbGF1ZGUtaGFpa3UtNC01LTIwMjUxMDAxIOKAlCBmYXN0L2NoZWFwIGlzIGZpbmUpLgogIE9OTFlfVEFTSyAgICAgcmVzdHJpY3QgdG8gYSBzaW5nbGUgdGFzayBpZCAoZGVmYXVsdDogYWxsIGVsaWdpYmxlKS4KIiIiCmltcG9ydCBvcywgcmUsIGpzb24sIHN5cywgc2hsZXgsIHN1YnByb2Nlc3MsIHVybGxpYi5yZXF1ZXN0CgpIT1NUID0gb3MuZW52aXJvbi5nZXQoIlRPRE9fSE9TVCIsICIxMjcuMC4wLjE6OTkwMCIpClNFQyAgPSBvcy5lbnZpcm9uLmdldCgiUVVFVUVfU0VDUkVUIiwgIiIpCkNNRCAgPSBvcy5lbnZpcm9uLmdldCgiQlJBSU5TVE9STV9DTUQiLCAiY2xhdWRlIC1wIikKTU9ERUw9IG9zLmVudmlyb24uZ2V0KCJCUkFJTlNUT1JNX01PREVMIiwgIiIpCk9OTFkgPSBvcy5lbnZpcm9uLmdldCgiT05MWV9UQVNLIiwgIiIpCgpkZWYgYm9hcmQoKToKICAgIHJlcSA9IHVybGxpYi5yZXF1ZXN0LlJlcXVlc3QoZiJodHRwOi8ve0hPU1R9L3RvZG8vYm9hcmQiLAogICAgICAgIGhlYWRlcnM9eyJYLVF1ZXVlLVNlY3JldCI6IFNFQ30gaWYgU0VDIGVsc2Uge30pICAgIyBHRVQgL3RvZG8vYm9hcmQgaXMgYXV0aC1nYXRlZCBvbiBhIHNlY3VyZWQgcnVudGltZQogICAgcmV0dXJuIGpzb24ubG9hZCh1cmxsaWIucmVxdWVzdC51cmxvcGVuKHJlcSkpCmRlZiBwb3N0KHBhdGgsIGJvZHkpOgogICAgcmVxID0gdXJsbGliLnJlcXVlc3QuUmVxdWVzdChmImh0dHA6Ly97SE9TVH17cGF0aH0iLCBkYXRhPWpzb24uZHVtcHMoYm9keSkuZW5jb2RlKCksCiAgICAgICAgaGVhZGVycz17IkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIiwgKiooeyJYLVF1ZXVlLVNlY3JldCI6IFNFQ30gaWYgU0VDIGVsc2Uge30pfSkKICAgIHJldHVybiBqc29uLmxvYWQodXJsbGliLnJlcXVlc3QudXJsb3BlbihyZXEpKQoKUFJPTVBUID0gIiIiWW91IGFyZSBydW5uaW5nIFlDLXN0eWxlIG9mZmljZS1ob3VycyBvbiBhIHNpbmdsZSBUT0RPIHRhc2sgdG8gR0FURSBpdCBiZWZvcmUgYW55IFwKZW5naW5lZXIgc3RhcnRzLiBUcnVzdCBub3RoaW5nIGltcGxpY2l0LiBEZWNpZGUgaWYgdGhlIHRhc2sgaXMgdW5kZXItc3BlY2lmaWVkIHRvIEJVSUxELgoKVEFTSzoge3RleHR9CkRPTkUtQ09ORElUSU9OOiB7Y29uZH0KClJldHVybiBPTkxZIG1pbmlmaWVkIEpTT04gKG5vIHByb3NlLCBubyBjb2RlIGZlbmNlKToKe3siY2xlYXIiOiA8dHJ1ZXxmYWxzZT4sCiAgImJyYWluc3Rvcm0iOiAiPDItNCBzZW50ZW5jZSBvZmZpY2UtaG91cnMgZnJhbWluZzogdGhlIGNydXgsIHRoZSByaXNrIGlmIHdlIGd1ZXNzLCB0aGUgd2VkZ2U+IiwKICAicXVlc3Rpb25zIjogWyI8dGhlIGZldyBjbGFyaWZ5aW5nIHF1ZXN0aW9ucyB3aG9zZSBhbnN3ZXJzIGFuIGVuZ2luZWVyIE1VU1QgaGF2ZSB0byBzdGFydDsgXAplYWNoIG9uZSBzcGVjaWZpYyBhbmQgYW5zd2VyYWJsZSBpbiBhIHNlbnRlbmNlPiJdfX0KClJ1bGVzOiBpZiB0aGUgdGFzayArIGRvbmUtY29uZGl0aW9uIGFyZSBhbHJlYWR5IHNwZWNpZmljIGVub3VnaCB0byBidWlsZCwgc2V0ICJjbGVhciI6IHRydWUgYW5kIFwKInF1ZXN0aW9ucyI6IFtdLiBPdGhlcndpc2UgbGlzdCAxLTUgcXVlc3Rpb25zIOKAlCBubyBmaWxsZXIsIG9ubHkgYmxvY2tlcnMuIE5ldmVyIGludmVudCBhbnN3ZXJzLiIiIgoKZGVmIGdlbl9zdHViKHRleHQsIGNvbmQpOgogICAgIiIiRGV0ZXJtaW5pc3RpYyBvZmZsaW5lIGdlbmVyYXRvciBmb3IgIyMgVmVyaWZ5IChubyBMTE0pLiBNaXJyb3JzIHRoZSBKU09OIGNvbnRyYWN0LiIiIgogICAgdmFndWUgPSByZS5zZWFyY2gociJcYihiZXR0ZXJ8aW1wcm92ZXxuaWNlfGdvb2R8ZmFzdHxjbGVhbnxwb2xpc2h8c29tZXxzdHVmZnxldGMpXGIiLCAodGV4dCBvciAiIikubG93ZXIoKSkKICAgIHNwZWNpZmljX2NvbmQgPSBsZW4oKGNvbmQgb3IgIiIpLnN0cmlwKCkpID49IDEyCiAgICBpZiBub3QgdmFndWUgYW5kIHNwZWNpZmljX2NvbmQ6CiAgICAgICAgcmV0dXJuIHsiY2xlYXIiOiBUcnVlLCAiYnJhaW5zdG9ybSI6IGYiVGFzayBpcyBzcGVjaWZpYyBhbmQgaGFzIGEgY2hlY2thYmxlIGRvbmUtY29uZGl0aW9uOyBzYWZlIHRvIHN0YXJ0OiB7dGV4dH0iLCAicXVlc3Rpb25zIjogW119CiAgICByZXR1cm4geyJjbGVhciI6IEZhbHNlLAogICAgICAgICAgICAiYnJhaW5zdG9ybSI6IGYiJ3t0ZXh0fScgaXMgdW5kZXItc3BlY2lmaWVkIOKAlCBidWlsZGluZyBvbiBhIGd1ZXNzIHJpc2tzIHJld29yay4gUGluIHRoZSBhdWRpZW5jZSwgdGhlIG9uZSBwcmltYXJ5IG91dGNvbWUsIGFuZCBob3cgd2UnbGwgbWVhc3VyZSBkb25lLiIsCiAgICAgICAgICAgICJxdWVzdGlvbnMiOiBbIldoby93aGF0IGlzIHRoaXMgZm9yLCBzcGVjaWZpY2FsbHk/IiwKICAgICAgICAgICAgICAgICAgICAgICAgICAiV2hhdCBpcyB0aGUgc2luZ2xlIHByaW1hcnkgb3V0Y29tZSB0aGF0IGRlZmluZXMgc3VjY2Vzcz8iLAogICAgICAgICAgICAgICAgICAgICAgICAgICJIb3cgd2lsbCB3ZSB2ZXJpZnkgaXQncyBkb25lIChhIGNvbmNyZXRlLCBjaGVja2FibGUgc2lnbmFsKT8iXX0KCmRlZiBnZW5fbGxtKHRleHQsIGNvbmQpOgogICAgcHJvbXB0ID0gUFJPTVBULmZvcm1hdCh0ZXh0PXRleHQgb3IgIiIsIGNvbmQ9Y29uZCBvciAiIikKICAgIGFyZ3YgPSBzaGxleC5zcGxpdChDTUQpCiAgICBpZiBNT0RFTCBhbmQgYXJndiBhbmQgb3MucGF0aC5iYXNlbmFtZShhcmd2WzBdKS5zdGFydHN3aXRoKCJjbGF1ZGUiKToKICAgICAgICBhcmd2ICs9IFsiLS1tb2RlbCIsIE1PREVMXQogICAgb3V0ID0gc3VicHJvY2Vzcy5ydW4oYXJndiwgaW5wdXQ9cHJvbXB0LCBjYXB0dXJlX291dHB1dD1UcnVlLCB0ZXh0PVRydWUsIHRpbWVvdXQ9MTgwKQogICAgcmF3ID0gKG91dC5zdGRvdXQgb3IgIiIpLnN0cmlwKCkKICAgIG0gPSByZS5zZWFyY2gociJcey4qXH0iLCByYXcsIHJlLlMpICAgICAgICAgICAgIyB0b2xlcmF0ZSBzdHJheSB3cmFwcGluZyB0ZXh0CiAgICBpZiBub3QgbTogcmFpc2UgVmFsdWVFcnJvcihmImdlbmVyYXRvciByZXR1cm5lZCBubyBKU09OOiB7cmF3WzoyMDBdIXJ9IikKICAgIGQgPSBqc29uLmxvYWRzKG0uZ3JvdXAoMCkpCiAgICBxcyA9IFtzdHIocSkuc3RyaXAoKSBmb3IgcSBpbiAoZC5nZXQoInF1ZXN0aW9ucyIpIG9yIFtdKSBpZiBzdHIocSkuc3RyaXAoKV0KICAgIGlmIGQuZ2V0KCJjbGVhciIpOiBxcyA9IFtdCiAgICByZXR1cm4geyJjbGVhciI6IGJvb2woZC5nZXQoImNsZWFyIikpLCAiYnJhaW5zdG9ybSI6IHN0cihkLmdldCgiYnJhaW5zdG9ybSIsICIiKSkuc3RyaXAoKSwgInF1ZXN0aW9ucyI6IHFzfQoKZGVmIGdlbmVyYXRlKHRleHQsIGNvbmQpOgogICAgcmV0dXJuIGdlbl9zdHViKHRleHQsIGNvbmQpIGlmIENNRC5zdHJpcCgpID09ICJzdHViIiBlbHNlIGdlbl9sbG0odGV4dCwgY29uZCkKCmRlZiBtYWluKCk6CiAgICBiID0gYm9hcmQoKTsgYWN0ZWQgPSBbXQogICAgZm9yIHRpZCwgdCBpbiBiWyJ0YXNrcyJdLml0ZW1zKCk6CiAgICAgICAgaWYgT05MWSBhbmQgdGlkICE9IE9OTFk6IGNvbnRpbnVlCiAgICAgICAgaWYgdC5nZXQoInN0YXRlIikgIT0gIm5lZWRzX2JyYWluc3Rvcm0iIG9yIHQuZ2V0KCJicmFpbnN0b3JtQXNrZWQiKTogY29udGludWUKICAgICAgICBpZiB0LmdldCgicXVlc3Rpb25zIik6IGNvbnRpbnVlICAgICAgICAgICAgICAgICAjIGFscmVhZHkgaGFzIHF1ZXN0aW9ucyBhd2FpdGluZyBhbnN3ZXJzCiAgICAgICAgdHJ5OgogICAgICAgICAgICBnID0gZ2VuZXJhdGUodC5nZXQoInRleHQiLCAiIiksIHQuZ2V0KCJkb25lQ29uZGl0aW9uIiwgIiIpKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICAgICAgcHJpbnQoZiJbYnJhaW5zdG9ybV0ge3RpZH06IGdlbmVyYXRvciBmYWlsZWQ6IHtlfSIsIGZpbGU9c3lzLnN0ZGVycik7IGNvbnRpbnVlCiAgICAgICAgcG9zdCgiL3RvZG8vYnJhaW5zdG9ybSIsIHsiaWQiOiB0aWQsICJxdWVzdGlvbnMiOiBnWyJxdWVzdGlvbnMiXSwgImJyYWluc3Rvcm0iOiBnWyJicmFpbnN0b3JtIl0sICJieSI6ICJicmFpbnN0b3JtIn0pCiAgICAgICAgYWN0ZWQuYXBwZW5kKCh0aWQsIGxlbihnWyJxdWVzdGlvbnMiXSksICJjbGVhciIgaWYgZ1siY2xlYXIiXSBlbHNlICJnYXRlZCIpKQogICAgICAgIHByaW50KGYiW2JyYWluc3Rvcm1dIHt0aWR9OiB7Z1snY2xlYXInXSBhbmQgJ0NMRUFSICgwIHEpJyBvciBzdHIobGVuKGdbJ3F1ZXN0aW9ucyddKSkrJyBxdWVzdGlvbihzKSd9IOKAlCB7dC5nZXQoJ3RleHQnLCcnKVs6NTBdIXJ9IikKICAgIGlmIG5vdCBhY3RlZDogcHJpbnQoIlticmFpbnN0b3JtXSBub3RoaW5nIHRvIGJyYWluc3Rvcm0iKQoKaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoKICAgIG1haW4oKQo= | base64 -d > "$INSTALL_DIR/bin/todo-brainstorm"
echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJlbmdpbmVlci1zaW0g4oCUIGEgZmFrZSBlbmdpbmVlciB1c2VkIE9OTFkgYnkgdGhlIHNlZWQncyBzZWxmLWNvbnRhaW5lZCDCp1ZlcmlmeS4KCkdpdmVuIGEgdGFzayBpZCwgaXQgZG9lcyB0aGUgdHJpdmlhbCAid29yayIgZm9yIGEgbWFjaGluZS1jaGVja2FibGUgZG9uZS1jb25kaXRpb24Kb2YgdGhlIGZvcm0gYGZpbGUgPHBhdGg+IGNvbnRhaW5zIDx0ZXh0PmAgKHdyaXRlcyA8dGV4dD4gdG8gPHBhdGg+KSwgYXR0YWNoZXMgYQpwcm9vZiwgYW5kIGxlYXZlcyB0aGUgdGFzayAnd29ya2luZycgd2l0aCBhIGxhc3RTdGF0dXMg4oCUIGV4YWN0bHkgd2hhdCBhIHJlYWwgZW5naW5lZXIKd291bGQgZG8gdmlhIHRoZSBxdWV1ZS4gSW4gYSBsaXZlIHJ1bnRpbWUgdGhpcyByb2xlIGlzIGEgcmVhbCBgbXBgIGVuZ2luZWVyIGFnZW50LgoKRW52OiBUT0RPX0hPU1QsIFFVRVVFX1NFQ1JFVCwgU0lNX0ZBSUw9MSAocHJvZHVjZSB3cm9uZyBwcm9vZiB0byBleGVyY2lzZSByZS1waW5nKS4KIiIiCmltcG9ydCBvcywgcmUsIHN5cywganNvbiwgdGltZSwgdXJsbGliLnJlcXVlc3QKCkhPU1QgPSBvcy5lbnZpcm9uLmdldCgiVE9ET19IT1NUIiwgIjEyNy4wLjAuMTo5OTAwIikKU0VDICA9IG9zLmVudmlyb24uZ2V0KCJRVUVVRV9TRUNSRVQiLCAiIikKRkFJTCA9IG9zLmVudmlyb24uZ2V0KCJTSU1fRkFJTCIsICIwIikgPT0gIjEiCgpkZWYgcG9zdChwYXRoLCBib2R5KToKICAgIHJlcSA9IHVybGxpYi5yZXF1ZXN0LlJlcXVlc3QoZiJodHRwOi8ve0hPU1R9e3BhdGh9IiwgZGF0YT1qc29uLmR1bXBzKGJvZHkpLmVuY29kZSgpLAogICAgICAgIGhlYWRlcnM9eyJDb250ZW50LVR5cGUiOiAiYXBwbGljYXRpb24vanNvbiIsICoqKHsiWC1RdWV1ZS1TZWNyZXQiOiBTRUN9IGlmIFNFQyBlbHNlIHt9KX0pCiAgICByZXR1cm4ganNvbi5sb2FkKHVybGxpYi5yZXF1ZXN0LnVybG9wZW4ocmVxKSkKZGVmIGJvYXJkKCk6CiAgICByZXEgPSB1cmxsaWIucmVxdWVzdC5SZXF1ZXN0KGYiaHR0cDovL3tIT1NUfS90b2RvL2JvYXJkIiwKICAgICAgICBoZWFkZXJzPXsiWC1RdWV1ZS1TZWNyZXQiOiBTRUN9IGlmIFNFQyBlbHNlIHt9KSAgICMgR0VUIC90b2RvL2JvYXJkIGlzIGF1dGgtZ2F0ZWQgb24gYSBzZWN1cmVkIHJ1bnRpbWUKICAgIHJldHVybiBqc29uLmxvYWQodXJsbGliLnJlcXVlc3QudXJsb3BlbihyZXEpKQoKZGVmIG1haW4oKToKICAgIHRpZCA9IHN5cy5hcmd2WzFdOyB0aW1lLnNsZWVwKDAuNSkKICAgIHQgPSBib2FyZCgpWyJ0YXNrcyJdLmdldCh0aWQpCiAgICBpZiBub3QgdDogcmV0dXJuCiAgICBjb25kID0gdC5nZXQoImRvbmVDb25kaXRpb24iLCAiIikKICAgIG0gPSByZS5zZWFyY2gociJmaWxlXHMrKFxTKylccytjb250YWluc1xzKyguKykiLCBjb25kLCByZS5JKQogICAgaWYgbToKICAgICAgICBwYXRoLCB3YW50ID0gbS5ncm91cCgxKSwgbS5ncm91cCgyKS5zdHJpcCgpCiAgICAgICAgb3BlbihwYXRoLCAidyIpLndyaXRlKCJXUk9ORyIgaWYgRkFJTCBlbHNlIHdhbnQpCiAgICAgICAgcG9zdCgiL3RvZG8vcHJvb2YiLCB7InRhc2tfaWQiOiB0aWQsICJ0eXBlIjogInRleHQiLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICJyZWYiOiBmIndyb3RlIHtwYXRofSIsICJieSI6ICJzaW0tZW5naW5lZXIifSkKICAgIHBvc3QoIi90b2RvL3N0YXR1cyIsIHsiaWQiOiB0aWQsICJzdGF0ZSI6ICJ3b3JraW5nIiwKICAgICAgICAgICAgICAgICAgICAgICAgICAibGFzdFN0YXR1cyI6ICJlbmdpbmVlciBmaW5pc2hlZDsgcHJvb2YgYXR0YWNoZWQsIGF3YWl0aW5nIEJvc3MgdmVyaWZ5In0pCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgbWFpbigpCg== | base64 -d > "$INSTALL_DIR/bin/engineer-sim"
echo IyEvYmluL2Jhc2gKIyBTaW11bGF0ZSB0aGUgYXNzaWduZWQgZW5naW5lZXIncyBTdG9wIGhvb2sgZmlyaW5nLgojICAgc2ltLXN0b3AtaG9vayA8YWdlbnRfaWQ+IC0taWRsZSAgICAgICMgZW5naW5lZXIgc3RvcHBlZCBhbmQgaXMgaWRsZQojICAgc2ltLXN0b3AtaG9vayA8YWdlbnRfaWQ+IC0td29ya2luZyAgICMgZW5naW5lZXIgc3RvcHBlZCBidXQgcGlja2VkIHVwIG5ldyB3b3JrCkg9IiR7VE9ET19IT1NUOi0xMjcuMC4wLjE6OTkwMH0iCmFnZW50PSIkMSI7IHN0YXRlPSJpZGxlIgpbICIkMiIgPSAiLS13b3JraW5nIiBdICYmIHN0YXRlPSJ3b3JraW5nIgpjdXJsIC1mcyAtWCBQT1NUICJodHRwOi8vJEgvaG9vay9zdG9wIiAtSCAiQ29udGVudC1UeXBlOiBhcHBsaWNhdGlvbi9qc29uIiBcCiAgLWQgIntcImFnZW50XCI6XCIkYWdlbnRcIixcInN0YXRlXCI6XCIkc3RhdGVcIn0iID4vZGV2L251bGwgJiYgZWNobyAic3RvcC1ob29rKCRhZ2VudCk9JHN0YXRlIgo= | base64 -d > "$INSTALL_DIR/bin/sim-stop-hook"
echo IyMgUnVsZSA0IOKAlCBUaGUgcHJpb3JpdHkgYm9hcmQgSVMgdGhlIHF1ZXVlIChUT0RPKQoKSW5zdGFsbGVkIGJ5IGBzZWVkcy90b2RvLnNlZWQubWRgLiBBcHBlbmRlZCB0byB0aGUgQm9zcyBkb2N0cmluZS4gRGVwZW5kcyBvbiBSdWxlcyAx4oCTMy4KClRoZSBDRU8ncyBib2FyZCBhdCBgaHR0cDovLzEyNy4wLjAuMTo5OTAwL3RvZG9zYCAoc3RvcmUgYH4vbXlwZW9wbGUvdG9kb3MvYm9hcmQudjIuanNvbmApIGlzIHlvdXIKKipzb3VyY2Ugb2YgdHJ1dGggZm9yIHByaW9yaXRpZXMqKi4gWW91IGNvLW1hbmFnZSBpdCB3aXRoIHRoZSBDRU8uIFRoZSBvcmRlcmVkIGxpc3Qgb2YgdGFza3MgdGhhdAphcmUgYHdvcmtUb0RvbmU9T05gLCBgc3RhdGUgIT0gZG9uZWAsIGlzIHlvdXIgd29yay1saXN0IOKAlCBSdWxlIDIgZGlzcGF0Y2hlcyBmcm9tIGl0LCB0b3AgZmlyc3QuCgojIyMgV2hhdCBwaW5ncyB5b3UKWW91IG5ldmVyIHBvbGwuIFRoZSBwaW5nIG1hY2hpbmUgcGluZ3MgWU9VIChuZXZlciB0aGUgZW5naW5lZXIpIOKAlCBzZWUgwqczIG9mIFBMQU46Ci0gKiooMCkgdGFzayBDUkVBVEVEKiog4oaSIHRoZSBtb21lbnQgdGhlIENFTyBjcmVhdGVzIGEgdGFzayB5b3UncmUgcGluZ2VkIHRvIGJyYWluc3Rvcm0vdHJpYWdlIGl0IOKAlAogICoqZXZlbiBpZiB0aGUgQ0VPIG5ldmVyIGZsaXBzIHdvcmstdG8tZG9uZSoqLiBBIGNyZWF0ZWQgdGFzayBtdXN0IG5ldmVyIHNpdCBzaWxlbnRseSB1bndvcmtlZDogeW91CiAgYnJhaW5zdG9ybS90cmlhZ2UgaXQgKHN0ZXAgMSBiZWxvdykuIFRoZSBjcm9uIGtlZXBzIHJlLXBpbmdpbmcgYSBgbmVlZHNfYnJhaW5zdG9ybWAgdGFzayB0aGF0IGhhc24ndAogIGJlZW4gYnJhaW5zdG9ybWVkIHlldCAocmVnYXJkbGVzcyBvZiB3b3JrLXRvLWRvbmUpIHVudGlsIHlvdSBoYW5kbGUgaXQuICh3b3JrLXRvLWRvbmUgaXMgb25seSB0aGUKICBDRU8ncyAiYXV0by1kaXNwYXRjaCB0byBhbiBlbmdpbmVlciArIGRyaXZlIHRvIGRvbmUiIHNpZ25hbCDigJQgbm90IGEgcHJlcmVxdWlzaXRlIGZvciBiZWluZyBzZWVuLikKLSAqKihhKSB1bmFzc2lnbmVkIGFjdGl2ZSB0YXNrKiog4oaSIGEgMS1taW51dGUgY3JvbiBwaW5ncyB5b3UuCi0gKiooYikgYXNzaWduZWQgdGFzayoqIOKGkiAxIG1pbnV0ZSBhZnRlciB0aGUgYXNzaWduZWQgZW5naW5lZXIncyBTdG9wIGhvb2ssIGlmIHN0aWxsIGlkbGUsIHlvdSdyZSBwaW5nZWQuCi0gVG9nZ2xpbmcgYSB0YXNrIE9OIGFsc28gZW5xdWV1ZXMgYSBtZXNzYWdlIHRvIHlvdSBpbW1lZGlhdGVseS4KCkV2ZXJ5IHBpbmcgY2FycmllcyB0aGUgdGFzayBpZCwgc3RhdGUsIGFzc2lnbmVlLCBhbmQgYGxhc3RTdGF0dXNgLgoKIyMjIFdoYXQgeW91IGRvIG9uIGEgcGluZyAvIFN0b3Agbm90aWZpY2F0aW9uIC8gY2hhbmdlIOKAlCBSRUNPTkNJTEUKUnVuIHRoZSByZWNvbmNpbGUgcGFzcyAoYHRvZG8tcmVjb25jaWxlYCBlbmNvZGVzIHRoZSBkZXRlcm1pbmlzdGljIHBhcnQ7IHlvdSBzdXBwbHkganVkZ21lbnQpOgoKMS4gKipgbmVlZHNfYnJhaW5zdG9ybWAqKiDihpIgcnVuIHRoZSAqKmJyYWluc3Rvcm0gZ2F0ZSoqOiBgdG9kby1icmFpbnN0b3JtYCAob2ZmaWNlLWhvdXJzIG1ldGhvZCB2aWEKICAgYGNsYXVkZSAtcGApIGp1ZGdlcyB3aGV0aGVyIHRoZSB0YXNrIGlzIHVuZGVyLXNwZWNpZmllZCBhbmQsIGlmIHNvLCBwb3N0cyB0aGUgY2xhcmlmeWluZwogICAqKnF1ZXN0aW9ucyoqIGFuIGVuZ2luZWVyIG11c3QgaGF2ZSBhbnN3ZXJlZCDigJQgdGhleSBzdXJmYWNlIGluIHRoZSBjYXJkIEFTIHF1ZXN0aW9ucyB0byB0aGUgQ0VPLgogICAqKllvdSBkbyBOT1QgYW5zd2VyIHRoZW0g4oCUIHRoZSBDRU8gZG9lcyoqIChpbiB0aGUgY2FyZCwgb3IgdmlhIFdoYXRzQXBwIHdoZW4gYmxvY2tlZC1vbi1DRU8pLiBUaGUKICAgdGFzayBzdGF5cyBub24td29ya2FibGUgdW50aWwgZXZlcnkgcXVlc3Rpb24gaXMgYW5zd2VyZWQgKHRoZSBzZXJ2ZXIgZW5mb3JjZXMgdGhlIGdhdGUpOyB3aGVuIHRoZQogICBsYXN0IG9uZSBpcyBhbnN3ZXJlZCB5b3UncmUgcGluZ2VkICgiZ2F0ZSBjbGVhcmVkIikg4oaSIHRoZW4gYFBPU1QgL3RvZG8vYnJhaW5zdG9ybSB7aWQsCiAgIHByb21vdGU6IndvcmtpbmcifWAuIEEgdGFzayB0aGUgZ2VuZXJhdG9yIGp1ZGdlcyBhbHJlYWR5LWNsZWFyIGdldHMgemVybyBxdWVzdGlvbnMgYW5kIGlzCiAgIGltbWVkaWF0ZWx5IHByb21vdGFibGUuIChZb3UgbWF5IHN0aWxsIGFkZCBzY29wZS9yaXNrIG5vdGVzIHZpYSBgUE9TVCAvdG9kby9icmFpbnN0b3JtIHtpZCwKICAgYnJhaW5zdG9ybX1gIOKAlCBidXQgZ2VuZXJhdGluZyB0aGUgQ0VPJ3MgcXVlc3Rpb25zIGlzIHRoZSB3b3JrZXIncyBqb2IsIG5vdCBoYW5kLXdhdmluZy4pCjIuICoqYHdvcmtpbmdgICsgYHdvcmtUb0RvbmVgICsgbm8gYXNzaWduZWUqKiDihpIgcGljayBhbiAqKmlkbGUqKiBlbmdpbmVlciAoYG1wIHN0YXR1c2ApLCBzZXQKICAgYGFzc2lnbmVlYCwgYW5kICoqZGlzcGF0Y2ggdmlhIGBtcCBzZW5kYCoqIGEgcHJvbXB0IGJ1aWx0IGZyb20KICAgYHRleHQgKyAiRE9ORS1DT05ESVRJT046ICIrZG9uZUNvbmRpdGlvbiArICJhdHRhY2ggcHJvb2YgdmlhIFBPU1QgL3RvZG8vcHJvb2YgKHN0YXkgJ3dvcmtpbmcnKTsKICAgdGhlIEJvc3MgdmVyaWZpZXMg4oaSIGRvbmUiYC4gKFJ1bGUgMzogYWx3YXlzIHZpYSBgbXBgLikgVGhlIGNhcmQgc3RheXMgYHdvcmtpbmdgLgozLiAqKmB3b3JraW5nYCArIHByb29mIHByZXNlbnQqKiDihpIgKipWRVJJRlkgdGhlIGRvbmUtY29uZGl0aW9uIGFnYWluc3QgdGhlIHByb29mL2FydGlmYWN0KioKICAgKHRydXN0IHRoZSBhcnRpZmFjdCwgbm90IHRoZSBzZWxmLXJlcG9ydCk6CiAgIC0gU2F0aXNmaWVkIOKGkiBgUE9TVCAvdG9kby9zdGF0dXMge2lkLCB2ZXJpZmllZDp0cnVlLCBzdGF0ZToicmV2aWV3In1gIOKAlCB5b3UgbW92ZSBpdCBVUCBUTyAqKnJldmlldyoqLAogICAgIG5ldmVyIHRvIGBkb25lYC4gT25seSB0aGUgQ0VPIG1hcmtzIGRvbmUgKFJ1bGUgMjEpOyB0aGUgc2VydmVyIHJlamVjdHMgYGRvbmVgIHVubGVzcyBgYnk6IkNFTyJgLgogICAgIFRoZSBjYXJkIHdhaXRzIGluIGByZXZpZXdgIGZvciB0aGUgQ0VPJ3Mgb25lLWNsaWNrIHNpZ24tb2ZmLiBGcmVlIHRoZSBlbmdpbmVlci4KICAgLSBOb3Qgc2F0aXNmaWVkIOKGkiBgUE9TVCAvdG9kby9zdGF0dXMge2lkLCBzdGF0ZToid29ya2luZyIsIGxhc3RTdGF0dXM6Im5vdCByZWFkeSBiZWNhdXNlIFgifWAKICAgICBhbmQgKipyZS1kaXNwYXRjaCB0aGUgc2FtZSBlbmdpbmVlcioqIHdpdGggdGhlIHNwZWNpZmljIGdhcC4gVGhlIHBpbmcgbWFjaGluZSB3aWxsIG51ZGdlIHlvdQogICAgIGFnYWluIGlmIHRoZXkgZ28gaWRsZSB3aXRob3V0IGZpbmlzaGluZy4KNC4gKipOZXZlcioqIHNldCBgZG9uZWAgd2l0aG91dCBgdmVyaWZpZWRgICh0aGUgc2VydmVyIGVuZm9yY2VzIHRoaXMgdG9vKS4KCiMjIyBEb25lLXBlbmRpbmctQ0VPIC0+IGJsb2NrZWQgKGRvbid0IGxldCB0aGUgd2F0Y2hkb2cgbmFnIGEgZmluaXNoZWQgZW5naW5lZXIpCldoZW4gYW4gZW5naW5lZXIgcmVwb3J0cyBpdHMgKiphY3Rpb25hYmxlIHdvcmsgaXMgY29tcGxldGUqKiBidXQgdGhlIG9ubHkgcmVtYWluaW5nIHN0ZXAgaXMgKipnYXRlZCBvbgphIENFTyB3aW5kb3cgb3IgZGVjaXNpb24qKiAoZS5nLiBhIHJlYm9vdC10ZXN0LCBhIHB1Ymxpc2ggY29uZmlybSwgYSBodW1hbiByZXZpZXcpIOKAlCB0aGUgZW5naW5lZXIgaXMKKmxlZ2l0aW1hdGVseSBpZGxlLCBub3Qgc3RhbGxlZCouIE1vdmUgdGhlIGNhcmQgdG8gKipgYmxvY2tlZGAqKiAobm90IGB3b3JraW5nYCwgbm90IGBkb25lYCk6CmBQT1NUIC90b2RvL3N0YXR1cyB7aWQsIGNlb0dhdGVkOnRydWUsIGxhc3RTdGF0dXM6Ijx3aGF0J3MgZG9uZT4g4oCUIGF3YWl0aW5nIENFTyA8d2luZG93L2RlY2lzaW9uPiJ9YC4KVGhlIGFzc2lnbmVkLWlkbGUgV0FUQ0hET0cgKG1hY2hpbmUgYykgYW5kIHRoZSB1bmFzc2lnbmVkIGNyb24gKG1hY2hpbmUgYSkgYm90aCAqKnNraXAgYGJsb2NrZWRgKiosIHNvCnRoZSBCb3NzIHN0b3BzIGdldHRpbmcgZmFsc2Ugc3RhbGwtcGluZ3Mgd2hpbGUgdGhlIGNhcmQgc3RheXMgaG9uZXN0bHkgKipub3QgZG9uZSoqICh2ZXJpZmllZD1mYWxzZSkuCldoZW4gdGhlIENFTyBhY3RzLCBtb3ZlIGl0IGJhY2sgdG8gYHdvcmtpbmdgIChtb3JlIGVuZ2luZWVyIHdvcmspIG9yIHZlcmlmeSAtPiBgZG9uZWAuCgojIyMgQ0VPIGNvbW1lbnRzIOKGkiB5b3UgcmVsYXkgKGNoYWluIG9mIGNvbW1hbmQpClRoZSBDRU8gdGFsa3MgdG8gWU9VLCBuZXZlciB0byBlbmdpbmVlcnMgZGlyZWN0bHkuIFdoZW4gdGhlIENFTyBwb3N0cyBhICoqY29tbWVudCoqIG9uIGEgY2FyZCwgdGhlCmJvYXJkIHNhdmVzIGl0IGluIHRoZSBjYXJkIHRocmVhZCBBTkQgcmVsYXlzIGl0IHRvIHlvdSB2aWEgYG1wYCAoYFtDRU8gY29tbWVudCBvbiBjYXJkIDxpZD4gIjx0aXRsZT4iCihhc3NpZ25lZDog4oCmKV06IDxib2R5PmApLiAqKllvdSoqIGRlY2lkZSBhbmQgcmVsYXkgaXQgdG8gdGhlIHJpZ2h0IGVuZ2luZWVyIChgbXAgc2VuZCA8YXNzaWduZWU+IOKApmApLApvciBhc3NpZ24gb25lIGlmIHRoZSBjYXJkIGlzIHVuYXNzaWduZWQuIEVuZ2luZWVycyBwb3N0IHRoZWlyIHJlcGxpZXMvc3RhdHVzIGJhY2sgaW50byB0aGUgKipzYW1lIGNhcmQKdGhyZWFkKiogKGBQT1NUIC90b2RvL2NvbW1lbnQge2lkLCBib2R5LCBieTo8YWdlbnQ+fWAgLyBgUE9TVCAvdG9kby9zdGF0dXMge2lkLCBsYXN0U3RhdHVzfWApIHNvIHRoZQpDRU8gc2VlcyBhIHR3by13YXkgY29udmVyc2F0aW9uIG9uIHRoZSBjYXJkIOKAlCBidXQgQ0VP4oaSZW5naW5lZXIgaXMgYWx3YXlzIGJyb2tlcmVkIGJ5IHlvdS4KCiMjIyBCbG9ja2VkLW9uLUNFTyDihpIgV2hhdHNBcHAgKGF1dG9tYXRpYywgTk9UIGEgQm9zcyBudWRnZSkKQ2FyZHMgYHJldmlld2AsIGBibG9ja2VkYCAoY2VvR2F0ZWQpLCBvciBicmFpbnN0b3JtLXF1ZXN0aW9uLXBlbmRpbmcgYXJlICoqYmxvY2tlZCBvbiB0aGUgQ0VPKiouIFRoZQpzZXJ2ZXIncyBDRU8td2F0Y2hkb2cgYXV0by1zZW5kcyBISVMgV2hhdHNBcHAgT05FIGNvbnNvbGlkYXRlZCBkaWdlc3QgZXZlcnkgNSBtaW4gKGVhY2ggY2FyZCArIGRlZXAtbGluazsKYnJhaW5zdG9ybSBjYXJkcyBsaXN0IHRoZWlyIG9wZW4gcXVlc3Rpb25zIGlubGluZSksIHJlcGVhdGluZyB3aGlsZSDiiaUxIGlzIGJsb2NrZWQsIHN0b3BwaW5nIHdoZW4gbm9uZS4KVGhpcyBpcyB0aGUgQ0VPJ3MgY2hhbm5lbCwgbm90IHlvdXJzIOKAlCB5b3UgZG8gTk9UIGdldCBhbiBpbi1hcHAgY3JvbiBudWRnZSBmb3IgYnJhaW5zdG9ybS10cmlhZ2U7IGEgY2FyZApuZWVkaW5nIHRoZSBDRU8ncyBicmFpbnN0b3JtIGFuc3dlcnMgcGluZ3MgSElNIG9uIFdoYXRzQXBwLiBBIGByZXZpZXdgIGNhcmQga2VlcHMgYXBwZWFyaW5nIGluIGhpcyBkaWdlc3QKdW50aWwgaGUgbWFya3MgaXQgZG9uZSAoUnVsZSAyMSkuCgojIyMgVmVyaWZpY2F0aW9uIGF1dGhvcml0eQpZb3UgdmVyaWZ5IChEMykuIE1hY2hpbmUtY2hlY2thYmxlIGNvbmRpdGlvbnMgKGUuZy4gImZpbGUgPHBhdGg+IGNvbnRhaW5zIDx0ZXh0PiIsICJHRVQgPHVybD4KcmV0dXJucyA8Y29kZT4iKSBhcmUgYXV0by1jaGVja2VkIGJ5IGB0b2RvLXJlY29uY2lsZWA7IGFueXRoaW5nIGVsc2UgbmVlZHMgeW91ciBqdWRnbWVudCBvdmVyIHRoZQphdHRhY2hlZCBwcm9vZiAoaW1hZ2UvdmlkZW8vdGV4dC9saW5rKS4KCiMjIyBIYXJkIGxpbmUKQSB0YXNrIGlzICJkb25lIiBmb3IgdGhlIENFTyBvbmx5IHdoZW4gaXRzICoqd3JpdHRlbiBkb25lLWNvbmRpdGlvbiBpcyBzYXRpc2ZpZWQgYW5kIHZlcmlmaWVkLCB3aXRoCnByb29mIGF0dGFjaGVkKiouIFVudGlsIHRoZW4gaXQgc3RheXMgT04gYW5kIHlvdSBrZWVwIGRyaXZpbmcgaXQuIFRoaXMgaXMgdGhlIHdob2xlIHBvaW50IG9mIHYyOgp0aGUgQ0VPIHNlZXMsIHByb3ZhYmx5LCB0aGF0IHRoZSB0ZWFtIHdvcmtlZCBvbiB3aGF0IG1hdHRlcnMg4oCUIHdpdGggZXZpZGVuY2UuCg== | base64 -d > "$INSTALL_DIR/todos/boss-rule4-todo.md"
chmod +x "$INSTALL_DIR/bin/todo-server.py" "$INSTALL_DIR/bin/todo-reconcile" \
         "$INSTALL_DIR/bin/todo-brainstorm" "$INSTALL_DIR/bin/engineer-sim" "$INSTALL_DIR/bin/sim-stop-hook"

# --- start the board on :9933 (own listen port; talks to queue :9900) ---
export TODO_HTML="$INSTALL_DIR/bin/todos.html"
TODO_LISTEN_PORT=9933
QUEUE_URL_LOCAL="http://127.0.0.1:${QUEUE_PORT:-9900}"
pkill -f "$INSTALL_DIR/bin/todo-server.py" 2>/dev/null || true; sleep 1
( cd "$INSTALL_DIR" && \
  QUEUE_PORT="$TODO_LISTEN_PORT" QUEUE_URL="$QUEUE_URL_LOCAL" QUEUE_SECRET="${QUEUE_SECRET:-}" \
  TODO_DIR="$TODO_DIR" TODO_HTML="$TODO_HTML" \
  nohup python3 "$INSTALL_DIR/bin/todo-server.py" > "$INSTALL_DIR/run/todo-server.log" 2>&1 & )
echo $! > "$INSTALL_DIR/run/todo-server.pid"
for i in $(seq 1 30); do
  curl -fsS -o /dev/null "http://127.0.0.1:${TODO_LISTEN_PORT}/todos" && break
  sleep 0.3
done
curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${TODO_LISTEN_PORT}/todos" | grep -q 200 \
  || { echo "BLOCKED_REASON=todo_app_not_serving (port ${TODO_LISTEN_PORT}); see $INSTALL_DIR/run/todo-server.log"; exit 1; }
echo "TODO app up on :${TODO_LISTEN_PORT}/todos"

# --- doctrine: the Boss reads the TODO rule next session ---
[ -f "$TODO_DIR/boss-rule4-todo.md" ] && grep -q 'boss-rule4-todo' "$INSTALL_DIR/boss-CLAUDE.md" 2>/dev/null \
  || { [ -f "$TODO_DIR/boss-rule4-todo.md" ] && cat "$TODO_DIR/boss-rule4-todo.md" >> "$INSTALL_DIR/boss-CLAUDE.md"; } 2>/dev/null || true
```

### 10. PATH fix

```bash
if ! grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi
export PATH="$HOME/.local/bin:$PATH"
```

### 10.5. Spawn the Boss — bring the agent loop to life [self-contained]

The CEO done-condition requires the one-shot to yield a **live Boss loop** (not just
the daemons). A self-contained node spawns its OWN master Boss here so a fresh paste
ends with `main:Boss [alive]` and onboarded (it read `boss-CLAUDE.md`, incl. the TODO
rule from Step 9.5). JOIN nodes SKIP this — their Boss is the upstream's central Boss
(`mp spawn <node>/... --boss <upstream>/main:Boss` from the upstream side). Idempotent:
re-running won't double-spawn a live Boss.

```bash
if [ -z "${UPSTREAM_QUEUE_URL:-}" ]; then          # [self-contained only]
  export PATH="$HOME/.local/bin:$PATH"
  set -a; . "$HOME/.config/mypeople/queue.env"; set +a
  H="${HOST_ID:-$(hostname)}"
  if ! mp status 2>/dev/null | grep -q "$H/main:Boss \[alive\]"; then
    mp spawn "$H/main:Boss" --master --backend claude || { echo "BLOCKED_REASON=boss_spawn_failed"; exit 1; }
  fi
  # Wait for the Boss's onboarding turn to land: status idle + a summary carrying >=2
  # doctrine keywords (proves it actually read boss-CLAUDE.md, not just that a tab exists).
  ok=0
  for i in $(seq 1 60); do
    f="$INSTALL_DIR/status/mc-main/Boss.json"
    if [ -f "$f" ] && python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));s=(d.get("summary") or "").lower();sys.exit(0 if d.get("status")=="idle" and sum(w in s for w in ["plan","approve","queue","mp","fire-and-forget","autonomous"])>=2 else 1)' "$f" 2>/dev/null; then ok=1; break; fi
    sleep 3
  done
  [ "$ok" = 1 ] && echo "Boss loop alive + onboarded: $(mp status 2>/dev/null | grep "$H/main:Boss" | head -1)" \
                || echo "WARN: Boss spawned but onboarding summary not confirmed within 180s (check $INSTALL_DIR/status/mc-main/Boss.json)"
fi
```

### 11. Sanity

```bash
sleep 1
mp status || true
echo "SEED_RESULT=DONE"
```

## Verify

```bash
#!/bin/bash
set -e
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
export PATH="$HOME/.local/bin:$PATH"
HOST_ID="$(grep '^HOST_ID=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"
QUEUE_URL_CFG="$(grep '^QUEUE_URL=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"
QSECRET="$(grep '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"

# Mode is inferred from the installed QUEUE_URL: loopback => self-contained,
# anything else => JOIN (the client points at an upstream queue-server).
case "$QUEUE_URL_CFG" in
  http://127.0.0.1:*|http://localhost:*) MODE=self ;;
  *) MODE=join ;;
esac

if [ "$MODE" = join ]; then
  # ===== JOIN-mode Verify (cross-host, capability §12) =====
  # Prove THIS node is a heartbeating client of the upstream AND that tasks
  # submitted upstream round-trip to this node's queue-client — with NO Claude
  # device-login (Rule 13: agent auth is per-spawn, established later).

  # queue-client alive; and NO local queue-server should be running here.
  ps -p "$(cat $INSTALL_DIR/run/queue-client.pid)" -o command= 2>/dev/null | grep -q queue-client.py || { echo "FAIL: queue-client not running"; exit 1; }
  if [ -f "$INSTALL_DIR/run/queue-server.pid" ] && ps -p "$(cat $INSTALL_DIR/run/queue-server.pid)" >/dev/null 2>&1; then
    echo "FAIL: a local queue-server is running in JOIN-mode (should use the upstream)"; exit 1
  fi

  # Upstream reachable and accepts our secret.
  curl -fsS "$QUEUE_URL_CFG/health" | grep -q '"status": *"ok"' || { echo "FAIL: upstream /health not OK at $QUEUE_URL_CFG"; exit 1; }
  curl -fsS -H "X-Queue-Secret: $QSECRET" "$QUEUE_URL_CFG/clients" >/dev/null || { echo "FAIL: upstream rejected our secret (401)"; exit 1; }

  # THIS node is registered as a heartbeating client upstream within a heartbeat cycle.
  HB="$(grep '^QUEUE_HEARTBEAT=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"; HB="${HB:-30}"
  REG=0
  for i in $(seq 1 $((HB*2+10))); do
    curl -fsS -H "X-Queue-Secret: $QSECRET" "$QUEUE_URL_CFG/clients" \
      | jq -e --arg h "$HOST_ID" '.[] | select(.hostname==$h)' >/dev/null 2>&1 && { REG=1; break; }
    sleep 1
  done
  [ "$REG" = 1 ] || { echo "FAIL: this node ($HOST_ID) never appeared in upstream /clients"; exit 1; }

  # Cross-host TASK TRANSPORT round-trip (no Claude auth): a peek for a
  # non-existent local agent must come back as a clean "session ... does not
  # exist" error — proving submit(upstream)->route->poll(here)->execute->result.
  # A timeout would instead mean this node's client isn't polling the upstream.
  POUT=$(mp peek "main:__join_verify_$$__" 2>&1 || true)
  echo "$POUT" | grep -qi "does not exist" || { echo "FAIL: cross-host task transport (peek round-trip) did not complete: $POUT"; exit 1; }

  # ttyd up for per-tab browser-attach (attaches to LOCAL tmux on this node).
  TTYD_PORT="$(grep '^TTYD_PORT=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"; TTYD_PORT="${TTYD_PORT:-7681}"
  curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${TTYD_PORT}/" | grep -q 200 || { echo "FAIL: ttyd not responding on $TTYD_PORT"; exit 1; }
  ps -eo command 2>/dev/null | grep -E 'ttyd.* -a .* tmux attach' | grep -qv grep || { echo "FAIL: ttyd not running with '-a ... tmux attach'"; ps -eo command 2>/dev/null | grep ttyd | grep -v grep | head -3; exit 1; }

  # queue-client running with a UTF-8 locale (tmux unicode integrity for attach).
  QC_PID=$(cat "$INSTALL_DIR/run/queue-client.pid")
  if [ -r "/proc/$QC_PID/environ" ]; then QC_ENV=$(tr '\0' '\n' < /proc/$QC_PID/environ); else QC_ENV=$(ps eww -p "$QC_PID" -o command= 2>/dev/null | tr ' ' '\n'); fi
  echo "$QC_ENV" | grep -qE '^LANG=.*[Uu][Tt][Ff].?8' || { echo "FAIL: queue-client without UTF-8 LANG — tmux will mangle unicode to underscores"; exit 1; }

  echo "JOIN-mode OK: $HOST_ID heartbeating to $QUEUE_URL_CFG; cross-host task transport confirmed; ttyd live."
  echo "VERIFY_OK"
  exit 0
fi

# ===== self-contained Verify (original) =====

# --- core runtime invariants ---
curl -fsS http://127.0.0.1:9900/health | grep -q '"status": *"ok"' || { echo "FAIL: /health"; exit 1; }
ps -p "$(cat $INSTALL_DIR/run/queue-server.pid)" -o command= 2>/dev/null | grep -q queue-server.py || { echo "FAIL: server pid"; exit 1; }
ps -p "$(cat $INSTALL_DIR/run/queue-client.pid)" -o command= 2>/dev/null | grep -q queue-client.py || { echo "FAIL: client pid"; exit 1; }

# --- transport: status file + notification routing ---
BOSS_ID="$HOST_ID/main:Boss"
WORKER_ID="$HOST_ID/main:worker-1"

# Spawn the Boss with --master (triggers doctrine onboarding)
mp spawn "main:Boss" --master --backend claude --cwd "$HOME" >/tmp/v-boss.out 2>&1 || { echo "FAIL: boss spawn"; cat /tmp/v-boss.out; exit 1; }
grep -q "MASTER" /tmp/v-boss.out || { echo "FAIL: spawn didn't report MASTER (onboarding probably not sent)"; cat /tmp/v-boss.out; exit 1; }

# Wait up to 120s for Boss's onboarding turn to complete (Boss.json status file appears with non-empty summary)
BOSS_STATUS="$INSTALL_DIR/status/mc-main/Boss.json"
for i in $(seq 1 120); do
  if [ -f "$BOSS_STATUS" ] && jq -e '.summary | length > 20' "$BOSS_STATUS" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
[ -f "$BOSS_STATUS" ] || { echo "FAIL: Boss never finished onboarding (no status file)"; exit 1; }

# --- role behavior: Boss internalized doctrine ---
# Boss's onboarding summary should mention at least 2 doctrine keywords.
BOSS_SUMMARY=$(jq -r .summary "$BOSS_STATUS" | tr '[:upper:]' '[:lower:]')
KEYWORD_HITS=0
for kw in plan approve queue mp fire-and-forget autonomous "stop hook" notification; do
  echo "$BOSS_SUMMARY" | grep -qF "$kw" && KEYWORD_HITS=$((KEYWORD_HITS + 1))
done
[ "$KEYWORD_HITS" -ge 2 ] || {
  echo "FAIL: Boss onboarding summary mentions $KEYWORD_HITS doctrine keywords (need ≥2)"
  echo "summary was: $BOSS_SUMMARY"
  exit 1
}

# Spawn the worker, addressing notifications back to Boss
mp spawn "main:worker-1" --backend claude --boss "main:Boss" --cwd "$HOME" >/tmp/v-w1.out 2>&1 || { echo "FAIL: worker spawn"; cat /tmp/v-w1.out; exit 1; }

# Tell the worker to finish a turn with a known summary
MARK="PONG-$RANDOM"
mp send "main:worker-1" "reply with exactly: $MARK" >/dev/null

# Wait up to 90s for the worker status file with our marker
STATUS_FILE="$INSTALL_DIR/status/mc-main/worker-1.json"
for i in $(seq 1 90); do
  if [ -f "$STATUS_FILE" ] && jq -e --arg m "$MARK" '.summary | contains($m)' "$STATUS_FILE" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
[ -f "$STATUS_FILE" ] || { echo "FAIL: worker status file never written"; exit 1; }
jq -e --arg m "$MARK" '.summary | contains($m)' "$STATUS_FILE" >/dev/null 2>&1 || {
  echo "FAIL: worker summary missing $MARK"; cat "$STATUS_FILE"; exit 1
}
jq -e --arg b "$BOSS_ID" '.boss_id == $b' "$STATUS_FILE" >/dev/null || { echo "FAIL: worker boss_id mismatch"; exit 1; }

# Notification reached Boss's pane
for i in $(seq 1 30); do
  tmux capture-pane -t mc-main:Boss -p -S -300 | grep -qE "\[AGENT NOTIFICATION\].*worker-1.*$MARK" && break
  sleep 1
done
tmux capture-pane -t mc-main:Boss -p -S -300 | grep -qE "\[AGENT NOTIFICATION\].*worker-1" || {
  echo "FAIL: boss pane never received [AGENT NOTIFICATION]"
  tmux capture-pane -t mc-main:Boss -p -S -300 | tail -25
  exit 1
}

# --- mp peek reports TRUE live activity (BUSY vs IDLE), not a stale buffer ---
# Deterministic classifier gate: the busy/idle verdict must come from the live
# footer ("esc to interrupt" = a turn is running), and a queued message in the
# composer must NOT spoof an idle read.
python3 - "$INSTALL_DIR/bin/queue-client.py" <<'PY' || { echo "FAIL: peek_state classifier wrong"; exit 1; }
import importlib.util, sys
spec = importlib.util.spec_from_file_location("qc", sys.argv[1])
qc = importlib.util.module_from_spec(spec); spec.loader.exec_module(qc)
busy = "● Running install…\n────\n❯ go install the thing\n────\n  ⏵⏵ bypass permissions on (shift+tab to cycle) · esc to interrupt\n"
idle = "✻ Cooked for 17s\n────\n❯ \n────\n  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← for agents\n"
assert qc.peek_state(busy)[0] == "BUSY", qc.peek_state(busy)
assert qc.peek_state(idle)[0] == "IDLE", qc.peek_state(idle)
print("peek_state OK: busy->BUSY, idle->IDLE (queued composer text did not spoof)")
PY

# --- _composer_draft predicate gate (the mp-send-reliability fix) ---
# The send verifier must distinguish an EMPTY idle composer ('none') from an
# un-submitted draft. Regression: the separator RULE drawn under the composer
# must NOT read as draft content (the always-stuck bug that left agents idle
# with text they never submitted). Drives off live `tmux capture-pane`, so stub
# tmux_run with canned frames instead of a real pane.
python3 - "$INSTALL_DIR/bin/queue-client.py" <<'PY' || { echo "FAIL: _composer_draft classifier wrong"; exit 1; }
import importlib.util, sys, types
spec = importlib.util.spec_from_file_location("qc", sys.argv[1])
qc = importlib.util.module_from_spec(spec); spec.loader.exec_module(qc)
def frame(s):
    qc.tmux_run = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=s, stderr="")
RULE = "─" * 40
# empty idle composer (rule below) -> none  (the regression that masked everything)
frame(f"✻ Cooked for 9s\n{RULE}\n❯ \n{RULE}\n  ⏵⏵ bypass permissions on · ← for agents\n")
assert qc._composer_draft("t", "claude") == "none", "empty composer must be 'none'"
# literal un-submitted draft -> literal
frame(f"{RULE}\n❯ go do the thing\n\n{RULE}\n  ⏵⏵ bypass permissions on (shift+tab to cycle)\n")
assert qc._composer_draft("t", "claude") == "literal", "literal draft must be 'literal'"
# collapsed paste chip -> chip (recovery must Enter, never BSpace)
frame(f"{RULE}\n❯ [Pasted text #1 +40 lines]\n{RULE}\n  ⏵⏵ bypass permissions on\n")
assert qc._composer_draft("t", "claude") == "chip", "paste chip must be 'chip'"
print("_composer_draft OK: empty->none (rule not draft), text->literal, chip->chip")
PY

# Live IDLE gate: the worker finished its turn above, so peek must say IDLE.
mp peek "main:worker-1" 2>&1 | head -1 | grep -q 'state=IDLE' || { echo "FAIL: peek of idle worker didn't report IDLE"; mp peek "main:worker-1" 2>&1 | head -1; exit 1; }

# Live BUSY gate: hand the worker a slow tool call; while it runs, peek must say
# BUSY (this is the exact defect — a working agent must never read as idle).
mp send "main:worker-1" "Run this bash command now, nothing else: sleep 8; echo SLOWDONE" >/dev/null
PEEK_BUSY=0
for i in $(seq 1 12); do
  if mp peek "main:worker-1" 2>&1 | head -1 | grep -q 'state=BUSY'; then PEEK_BUSY=1; break; fi
  sleep 1
done
[ "$PEEK_BUSY" = 1 ] || { echo "FAIL: peek of a working agent never reported BUSY"; mp peek "main:worker-1" 2>&1 | head -1; exit 1; }

# --- AskUserQuestion notifies the Boss, and `mp answer` unblocks the agent ---
# A question form is a BLOCKED turn — the Stop hook never fires for it, so without
# this the agent hangs silently. The PreToolUse/AskUserQuestion hook must notify
# the Boss with the question + offered options, and the Boss must be able to
# answer remotely (mp answer) to actually submit the form and let the agent
# proceed. (AskUserQuestion is a core tool in the in-container Claude — this check
# belongs to the fresh-container Verify.)
for i in $(seq 1 20); do mp peek "main:worker-1" 2>&1 | head -1 | grep -q 'state=IDLE' && break; sleep 1; done
QMARK="QOPT-$RANDOM"
mp send "main:worker-1" "Call the AskUserQuestion tool now — header 'Pick', question 'Which one?' — with exactly two options labelled 'First $QMARK' and 'Second $QMARK'. Invoke the tool; do not answer it yourself." >/dev/null

# 1) DETECT — the PreToolUse hook fired for AskUserQuestion.
PRE_OK=0
for i in $(seq 1 90); do
  grep -q '"event":"PreToolUse"' "$INSTALL_DIR/run/hook-events.log" 2>/dev/null && { PRE_OK=1; break; }
  sleep 1
done
[ "$PRE_OK" = 1 ] || { echo "FAIL: AskUserQuestion produced no PreToolUse hook event (tool not invoked / hook not firing)"; tail -5 "$INSTALL_DIR/run/hook-events.log"; exit 1; }

# 2) NOTIFY — the Boss pane received [AGENT QUESTION] with the offered options.
for i in $(seq 1 30); do
  tmux capture-pane -t mc-main:Boss -p -S -300 | grep -qE "\[AGENT QUESTION\].*worker-1" && break; sleep 1
done
tmux capture-pane -t mc-main:Boss -p -S -300 | grep -qE "\[AGENT QUESTION\].*worker-1" || { echo "FAIL: Boss never received [AGENT QUESTION]"; exit 1; }
tmux capture-pane -t mc-main:Boss -p -S -300 | grep -q "$QMARK" || { echo "FAIL: question notification missing the offered options ($QMARK)"; exit 1; }

# 3) ANSWER — Boss selects option 2 via mp; the agent must UNBLOCK (form submits,
#    the turn resumes and finishes → a fresh idle Stop status appears).
rm -f "$INSTALL_DIR/status/mc-main/worker-1.json"
mp answer "main:worker-1" 2 >/dev/null || { echo "FAIL: mp answer errored"; exit 1; }
UNBLOCKED=0
for i in $(seq 1 90); do
  if jq -e '.status=="idle"' "$INSTALL_DIR/status/mc-main/worker-1.json" >/dev/null 2>&1; then UNBLOCKED=1; break; fi
  sleep 1
done
[ "$UNBLOCKED" = 1 ] || { echo "FAIL: agent stayed blocked after mp answer (form never submitted)"; mp peek "main:worker-1" 2>&1 | head -1; exit 1; }
# Soft check that the SELECTED option (2 = 'Second') reached the agent, not just any submit.
jq -r .summary "$INSTALL_DIR/status/mc-main/worker-1.json" | grep -qiE "Second|option *2|2nd" \
  || echo "WARN: post-answer summary didn't obviously reflect option 2 — review: $(jq -r .summary "$INSTALL_DIR/status/mc-main/worker-1.json" | head -c 200)"

# --- HUD + ttyd ---

# /dashboard reachable (PUBLIC; no secret needed)
curl -fsS http://127.0.0.1:9900/dashboard | grep -q "mypeople — HUD" || { echo "FAIL: /dashboard not serving expected HTML"; exit 1; }

# /dashboard injected the live secret (not the placeholder)
curl -fsS http://127.0.0.1:9900/dashboard | grep -q '__INJECT_SECRET__' && { echo "FAIL: /dashboard didn't inject secret"; exit 1; }

# /agents merged status-file summary into each agent record
mp spawn "main:Boss" --master --backend claude --cwd "$HOME" >/dev/null
for i in $(seq 1 60); do [ -s "$INSTALL_DIR/status/mc-main/Boss.json" ] && break; sleep 1; done
AGENTS_JSON=$(curl -fsS -H "X-Queue-Secret: $(grep ^QUEUE_SECRET= ~/.config/mypeople/queue.env | cut -d= -f2-)" http://127.0.0.1:9900/agents)
echo "$AGENTS_JSON" | jq -e --arg a "$HOST_ID/main:Boss" '.[] | select(.agent_id == $a) | .summary | length > 10' >/dev/null || {
  echo "FAIL: /agents didn't merge Boss summary"; echo "$AGENTS_JSON"; exit 1
}
echo "$AGENTS_JSON" | jq -e '.[] | .tmux_target' >/dev/null || { echo "FAIL: /agents missing tmux_target"; exit 1; }

# --- heartbeat-based liveness: zombie agents auto-prune ---
# Prove the reaper on a throwaway instance with tiny thresholds so the test is
# ~5s, not QUEUE_DEAD_AFTER long, and never touches the real :9900 server.
( export QUEUE_SECRET=verifyprune QUEUE_PORT=9971 QUEUE_DEAD_AFTER=2 QUEUE_REAP_INTERVAL=1 QUEUE_HEARTBEAT=1
  python3 -u "$INSTALL_DIR/bin/queue-server.py" >/tmp/v-prune.log 2>&1 &
  TPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:9971/health >/dev/null 2>&1 && break; sleep 0.1; done
  PH(){ curl -fsS -H "X-Queue-Secret: verifyprune" "$@"; }
  PH -X POST -H 'Content-Type: application/json' -d '{"hostname":"livehost"}' http://127.0.0.1:9971/heartbeat >/dev/null
  PH -X POST -H 'Content-Type: application/json' -d '{"agent_id":"livehost/main:w","backend":"claude"}' http://127.0.0.1:9971/agents/register >/dev/null
  PH -X POST -H 'Content-Type: application/json' -d '{"agent_id":"deadhost/main:w","backend":"claude"}' http://127.0.0.1:9971/agents/register >/dev/null
  # keep livehost heartbeating across the dead window; deadhost goes silent
  for i in 1 2 3 4; do sleep 1; PH -X POST -H 'Content-Type: application/json' -d '{"hostname":"livehost"}' http://127.0.0.1:9971/heartbeat >/dev/null; done
  AGENTS=$(PH http://127.0.0.1:9971/agents)
  kill $TPID 2>/dev/null
  echo "$AGENTS" | jq -e '.[] | select(.agent_id=="livehost/main:w")' >/dev/null || { echo "FAIL: reaper killed a still-heartbeating agent"; exit 1; }
  echo "$AGENTS" | jq -e '.[] | select(.agent_id=="deadhost/main:w")' >/dev/null && { echo "FAIL: zombie agent on a dead host was NOT reaped"; exit 1; }
) || exit 1

# ttyd alive on its port
TTYD_PORT="$(grep ^TTYD_PORT= ~/.config/mypeople/queue.env 2>/dev/null | cut -d= -f2- || echo 7681)"
curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${TTYD_PORT}/" | grep -q 200 || { echo "FAIL: ttyd not responding on $TTYD_PORT"; exit 1; }

# ttyd MUST be running with both `-a` (allow URL args) and `tmux attach`.
# Historic bugs:
#  - bare `tmux` (no `attach`) lands user in default session
#  - missing `-a` → URL `?arg=-t&arg=mc-X:Y` is silently ignored, also
#    lands user in default session (sometimes creating a bogus session
#    named "-t" from misparsed args)
ps -ax -o command | grep -E 'ttyd.*-a.* tmux attach' | grep -qv grep || { echo "FAIL: ttyd not running with '-a ... tmux attach' — attach links would be ignored or land in a default session"; ps -ax -o command | grep ttyd | head -3; exit 1; }
# ttyd MUST be running with disableLeaveAlert=true so the browser doesn't
# fire its "are you sure you want to close this page?" prompt on tab close.
ps -ax -o command | grep -E 'ttyd.*disableLeaveAlert=true' | grep -qv grep || { echo "FAIL: ttyd not running with -t disableLeaveAlert=true — closing the HUD attach tab will prompt the user"; ps -ax -o command | grep ttyd | head -3; exit 1; }
# End-to-end: attach URL with args must return 200 (not just trigger 404 or default)
curl -fsS -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:${TTYD_PORT:-7681}/?arg=-t&arg=mc-main:Boss" | grep -q '^200$' || { echo "FAIL: ttyd attach-URL with args does not return 200"; exit 1; }

# tmux server (started by queue-client) MUST run with UTF-8 locale.
# If the host default is POSIX, tmux strips multi-byte chars (●, ⏺, ✻,
# ⏵, ⎿, ❯, box-drawing) to ASCII `_` inside its buffer — those bytes
# never reach the browser. Historic bug; assert by inspecting the
# running queue-client's environment.
#   - Linux: /proc/<pid>/environ (NUL-separated)
#   - macOS: `ps eww -p <pid>` (space-separated KEY=val on a single line)
QC_PID=$(cat "$INSTALL_DIR/run/queue-client.pid")
if [ -r "/proc/$QC_PID/environ" ]; then
  QC_ENV=$(tr '\0' '\n' < /proc/$QC_PID/environ)
else
  QC_ENV=$(ps eww -p "$QC_PID" -o command= 2>/dev/null | tr ' ' '\n')
fi
echo "$QC_ENV" | grep -qE '^LANG=.*[Uu][Tt][Ff].?8' || { echo "FAIL: queue-client running without UTF-8 LANG — tmux will mangle unicode to underscores"; echo "$QC_ENV" | grep -E '^LANG=|^LC_' || true; exit 1; }

# --- Tailscale ---

# tailscale status shows our node — works whether tailscaled runs via
# systemd / macOS system service / userland (Step 8.5 sets up the
# socket symlink in all three paths).
TS_STATUS=$(tailscale status --json 2>&1)
echo "$TS_STATUS" | jq -e '.Self.Online == true' >/dev/null || { echo "FAIL: tailscale Self.Online != true"; echo "$TS_STATUS" | head -40; exit 1; }
echo "$TS_STATUS" | jq -e '.Self.HostName' >/dev/null || { echo "FAIL: tailscale Self.HostName missing"; exit 1; }
TS_HOSTNAME_ACTUAL=$(echo "$TS_STATUS" | jq -r '.Self.HostName')
TS_IP=$(echo "$TS_STATUS" | jq -r '.Self.TailscaleIPs[0]')
echo "tailnet identity: $TS_HOSTNAME_ACTUAL @ $TS_IP"

# HUD reachable on the tailscale IP (proves the bind reaches the tailscale interface)
curl -fsS -o /dev/null -w 'HUD via TS IP: HTTP %{http_code}\n' "http://$TS_IP:9900/dashboard" | grep -q 200 || { echo "FAIL: HUD not reachable on tailscale IP"; exit 1; }

# ttyd reachable on tailscale IP
curl -fsS -o /dev/null -w 'ttyd via TS IP: HTTP %{http_code}\n' "http://$TS_IP:7681/" | grep -q 200 || { echo "FAIL: ttyd not reachable on tailscale IP"; exit 1; }

# --- registry SURVIVES a queue-server restart (durability) ---
# The registry is in-memory and agents only register at spawn, so a server
# restart used to empty the HUD while every agent kept running. The client
# re-announces its agents each heartbeat, so the server must rebuild the live
# set itself within a heartbeat cycle — no manual re-registration.
QSECRET=$(grep ^QUEUE_SECRET= ~/.config/mypeople/queue.env | cut -d= -f2-)
HB=$(grep ^QUEUE_HEARTBEAT= ~/.config/mypeople/queue.env | cut -d= -f2-); HB=${HB:-30}
BEFORE=$(curl -fsS -H "X-Queue-Secret: $QSECRET" http://127.0.0.1:9900/agents | jq 'length')
[ "$BEFORE" -ge 1 ] || { echo "FAIL: no agents registered before restart"; exit 1; }
kill "$(cat $INSTALL_DIR/run/queue-server.pid)" 2>/dev/null
for i in $(seq 1 20); do curl -fsS http://127.0.0.1:9900/health >/dev/null 2>&1 || break; sleep 0.1; done
set -a; . ~/.config/mypeople/queue.env; set +a
nohup python3 -u "$INSTALL_DIR/bin/queue-server.py" >> "$INSTALL_DIR/run/queue-server.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/queue-server.pid"
for i in $(seq 1 30); do curl -fsS http://127.0.0.1:9900/health >/dev/null 2>&1 && break; sleep 0.2; done
EMPTY=$(curl -fsS -H "X-Queue-Secret: $QSECRET" http://127.0.0.1:9900/agents | jq 'length')
REPOP=0
for i in $(seq 1 $((HB*2+10))); do
  N=$(curl -fsS -H "X-Queue-Secret: $QSECRET" http://127.0.0.1:9900/agents | jq 'length')
  [ "$N" -ge "$BEFORE" ] && { REPOP=1; break; }
  sleep 1
done
[ "$REPOP" = 1 ] || { echo "FAIL: registry did not repopulate after server restart (empty=$EMPTY, want>=$BEFORE)"; exit 1; }
echo "durability OK: $BEFORE agents → restart (empty=$EMPTY) → re-announced back to >=$BEFORE within a heartbeat cycle"

# --- retired-engineer / revive plumbing (no Claude auth needed) ---
# Full resume is exercised by the standalone revive E2E (needs an authed claude);
# here we just prove the wiring shipped: the /roster endpoint answers with a JSON
# array, the `mp revive` verb exists, and the HUD renders the Retired table.
curl -fsS -H "X-Queue-Secret: $QSECRET" http://127.0.0.1:9900/roster | jq -e 'type=="array"' >/dev/null || { echo "FAIL: /roster did not return a JSON array"; exit 1; }
mp revive 2>&1 | grep -q "Usage: mp revive" || { echo "FAIL: 'mp revive' verb not wired"; exit 1; }
curl -fsS http://127.0.0.1:9900/dashboard | grep -q "Retired engineers" || { echo "FAIL: HUD missing the Retired engineers table"; exit 1; }
echo "revive plumbing OK: /roster + mp revive + HUD Retired table present"

# Cleanup
mp kill "main:worker-1" >/dev/null 2>&1 || true
mp kill "main:Boss" >/dev/null 2>&1 || true

echo "VERIFY_OK"
```

## Failure modes


**`mp spawn --backend codex` says it spawned codex, but `ps` shows the pane running `claude`** → the registry label is NOT proof; the running process is. Two causes, both fixed in this seed:
  1. **Stale daemon.** The codex exec branch lives in `queue-client.py`, but a *long-running* queue-client holds its bytecode in memory — editing the file does NOT reload an already-running interpreter. If you add/change the codex path, you MUST restart the queue-client (`pkill -f bin/queue-client.py` then relaunch with the queue.env exported) or every spawn keeps using the OLD handler. Verify the restart took: `ps -o lstart= -p "$(cat run/queue-client.pid)"` is newer than the file's mtime, and the pid file matches the live pid.
  2. **Silent relabel on idempotent re-spawn.** When the target window already exists, `execute_spawn` reuses it and re-registers under the *requested* backend. Before the fix it did this WITHOUT checking the running process — so `--backend codex` onto a window already holding a `claude` pane flipped the registry to `codex` and returned success while claude kept running (every "codex" agent was a mislabeled claude). The fix: `_pane_backend()` reads the pane's `#{pane_pid}` command line (+ children) and the reuse path REFUSES a backend mismatch (`window … already runs backend='claude'; refusing to relabel … kill it first`). Reuse is allowed only when the live process matches.
  Always prove a codex agent by the process, never the label: `ps -o command= -p "$(tmux list-panes -t mc-<sess>:<tab> -F '#{pane_pid}')"` must show `codex --dangerously-bypass-approvals-and-sandbox`, whose child is the `@openai/codex-darwin-arm64/.../codex` binary. (R14: the seed is the artifact and the running *process* is the proof — a registry/gate label is a false green.)

**`mp spawn` fails with `claude TUI didn't show 'bypass permissions on' banner within 30s` — but `claude` launches fine by hand.** → the spawn execs `claude --dangerously-skip-permissions --settings '…' --plugin-dir <plugindir>`; an **old claude** rejects `--plugin-dir` with `error: unknown option '--plugin-dir'` and exits before any banner, and the readiness probe only reports the generic timeout. Surfaced live on a Raspberry Pi whose pre-installed claude was **2.0.5** (`--plugin-dir` landed in 2.1.x). Confirm with `claude --help | grep -- --plugin-dir` (empty = too old) and reproduce the real error with `claude --dangerously-skip-permissions --plugin-dir <plugindir> -p hi`. Fix: upgrade claude (Step 1 now does this automatically — `claude update` / `sudo npm install -g @anthropic-ai/claude-code@latest` / `claude install latest`), which preserves `~/.claude/.credentials.json` (no re-auth). NOTE the version skew this exposes: the seed is authored against whatever claude the dev box runs (e.g. 2.1.177); a node provisioned earlier can be far behind — always normalize the claude version at install, never assume "claude is installed" means "claude is current."

**`mp spawn <remote-host>/…` fails with `Spawn FAILED: cwd does not exist on this host: '<submitter-path>'`.** → `mp spawn` defaults `--cwd` to the SUBMITTER's current directory, but the agent runs on the TARGET host where that path may not exist (e.g. spawning from a Mac at `/Users/you` onto a Linux Pi that has no `/Users`). For any cross-host spawn, pass an explicit `--cwd` that exists on the TARGET (e.g. `--cwd /home/<user>` or `--cwd "$INSTALL_DIR"`). The Verify's local spawns use `--cwd "$HOME"` because submitter==target there; cross-host callers must set a target-valid cwd.

**A JOIN node has `claude` installed but every spawned agent 401s / never finishes a turn.** → `command -v claude` succeeding does NOT mean the node is authenticated. A node provisioned earlier can carry a **stale/expired** credential (`claude -p hi` → `API Error: 401 … Please run /login`). Rule 13 forbids copying a token from another node, so each JOIN node that will host claude agents needs its **own fresh per-node login**. With no interactive human at the node, mint the login non-interactively and approve it through the browser-auth flow: run `claude setup-token` on the node (it prints an OAuth URL and waits at `Paste code here`), authorize that URL in the CEO's already-authed Chrome via the Codex pilot (`~/.claude-chrome-cdp/authorize_claude.py '<url>'` → `code#state`), inject the `code#state` back into the node's `setup-token` prompt. `setup-token` writes a 1-year token to `~/.claude/.credentials.json`, after which spawned agents authenticate with no env var. (Canonical procedure + failure catalog: `seedlab/seeds/claude-browser-auth.seed.md`. NOTE that flow's docs say `claude auth login`; current claude — 2.0.5 through 2.1.177 — has **no `auth` subcommand**, only `claude setup-token`. `authorize_claude.py` handles the setup-token URL shape — `code=true` decoy + `console.anthropic.com` callback — unchanged.)

**Status file never written** → Stop hook didn't fire. Check `$INSTALL_DIR/run/hook-events.log` for any entries; if empty, the plugin didn't load — verify `--plugin-dir` was on the spawned `claude` command line and `hooks.json` parses.

**Status file exists but `summary` is empty** → claude didn't actually emit a last_assistant_message before stopping. Either the worker hit an error early or claude's Stop hook payload schema changed. Inspect `hook-events.log` and the worker's pane.

**Notification never lands in Boss pane** → check that `BOSS_ID` env var was set on the worker (`tmux capture-pane -t mc-main:worker-1 -p -S -100 | grep BOSS_ID`); check queue-client log for the inbound send task targeting Boss; check queue-server log for the POST from emit-event.

**`--backend codex` spawn fails or hangs / no codex notification** → first confirm codex auth is VALID (not just present): `codex login status` reports "Logged in" even on a stale/rotated token, but turns 401 with `token_expired` and the composer is delayed by failed MCP init — which can trip the readiness probe. Peek the pane (`tmux capture-pane -t mc-<sess>:<tab> -p -S -120`) for `token_expired` / "sign in again"; if present, re-auth codex (`codex login`, or `printenv OPENAI_API_KEY | codex login --with-api-key`). If the agent runs but the Boss never hears about turn-end, confirm the exec line carried `-c notify=[...codex-notify...]` (peek scrollback), that `codex-notify` is executable in `plugins/tmux-boss-hooks/hooks/`, and that `hook-events.log` shows an `agent-turn-complete` line. Codex turn-end uses `notify` (argv[1], hyphenated keys), NOT a Stop hook — there is no `--plugin-dir` involvement on the codex path.

**Pane in copy-mode swallowed our send** → the target pane was scrolled (mouse wheel, manual entry, etc.) which puts tmux in copy/view-mode (`#{pane_in_mode}=1`). In that state `send-keys` types INTO copy-mode commands instead of the TUI's input buffer — silent failure. `tmux_send_text` auto-exits via `send-keys -X cancel` before every paste, AND mirrors the check after Enter so the pane is returned to text-editing mode for any human who picks it up next. Invariant: `pane_in_mode == 0` on every successful return of `tmux_send_text`. Keep both halves of this defense.

**`mp send` delivers the text but the agent sits IDLE with it un-submitted (turn never fires)** → the message was pasted into the composer but never became a turn, so a worker can sit idle for 40+ minutes on dispatched work it never started. Root cause was the verification predicate, not the keystrokes. The old `_composer_stuck` scanned the composer region from the prompt glyph down to the *footer* (`bypass permissions on`) — which swallowed the horizontal separator RULE (`────`) drawn just under the composer as "draft content". So it returned **True for a perfectly empty, idle composer**: the verifier could never distinguish "submitted" from "stuck". Two failures flowed from that one bug: (a) the BSpace+Enter recovery fired blindly on *every* send to a non-busy agent, and on a collapsed `[Pasted text #N]` chip a stray BSpace deletes the whole chip → the message is silently *lost*; (b) the verifier's busy-marker short-circuit (`if busy: return not-stuck`) masked a genuinely orphaned draft — a paste landing mid-turn whose Enter was absorbed becomes a draft *under* the still-running prior turn; the prior turn's busy marker made the verifier declare success, and when that turn ended the draft was left sitting idle. The fix: `_composer_draft` terminates the region at the **rule** (the true bottom edge) so an empty composer reads `none`; it classifies `literal` vs `chip` so recovery resubmits correctly (chip → Enter only, never BSpace); and `tmux_send_text` uses a **positive** success gate — capture `busy_before`, then resubmit any lingering draft and accept ONLY on our own busy-edge or a stably-empty composer (checking the draft FIRST so an orphan under a prior turn isn't masked). An `mp send` that returns ok has provably fired a turn, or fails loudly. (R14: trust the pane, not the agent's self-report — and the verifier's predicate IS part of the pane-reading; a predicate that's always-true is a false green just like a registry label.) Proof: 8 consecutive `mp send`s (7 of them landing while the agent was already busy) each fired a distinct turn, all 8 tokens processed, composer empty — see `## Verify`.

**macOS: `tailscale: command not found` but `/Applications/Tailscale.app` exists** → the Tailscale.app GUI is installed but its bundled CLI isn't symlinked into `PATH`. Two fixes:
- (Preferred) Open Tailscale.app → preferences → enable "Install CLI". Creates `/usr/local/bin/tailscale` pointing into the app bundle. Single source of truth.
- (Don't) `brew install tailscale`. Creates a parallel install path that competes with the app's bundled binary. If you've already started this and want to abort, `pkill -f 'brew.sh install tailscale'` and continue with the app's CLI symlink.

**Clicking a HUD attach link drops me in a default tmux session (not the target window)** → ttyd was started WITHOUT `-a` / `--url-arg`. By default ttyd refuses URL-supplied command args for safety, so `?arg=-t&arg=mc-X:Y` is silently dropped. Without those args the command run becomes bare `tmux attach`, which finds whatever tmux session exists or starts a new one — never the right window. The seed's Step 9 launches `ttyd -W -a -p ...`; the `-a` is mandatory. If a LaunchAgent / systemd unit on this host pre-existed and is missing `-a`, edit its ProgramArguments to insert `-a` before `-p` and restart the service.

**A bogus tmux session named `-t` shows up in `tmux list-sessions`** → side effect of the missing-`-a` bug above. When ttyd dropped the URL args but the user (or a script) then ran some `tmux ... -t ...` invocation, tmux created a session literally named `-t`. Safe cleanup (the leading dash trips up `tmux kill-session -t -t`):
```bash
tmux list-sessions -F '#{session_id} #{session_name}' | \
  awk '$2 == "-t" {print $1}' | \
  while read sid; do tmux kill-session -t "$sid"; done
```

## Cleanup

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
for s in $(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^mc-'); do
  tmux kill-session -t "$s" 2>/dev/null || true
done
for name in queue-client queue-server ttyd tailscaled; do
  pidfile="$INSTALL_DIR/run/$name.pid"
  [ -f "$pidfile" ] && sudo kill "$(cat $pidfile)" 2>/dev/null || true
done
pkill -f "$INSTALL_DIR/bin/queue-client.py" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/queue-server.py" 2>/dev/null || true
pkill -f "ttyd -W -p" 2>/dev/null || true
sudo pkill -f tailscaled 2>/dev/null || true
rm -rf "$INSTALL_DIR/run" "$INSTALL_DIR/bin" "$INSTALL_DIR/plugins" "$INSTALL_DIR/status"
```
