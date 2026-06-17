# SEED: pr-autoapprove

> seed-format: 1

> **You're an AI agent reading this seed.** Your job: run `## Step 0 Interview` to gather inputs, then execute every Step in order, then run the `## Verify` block in a sub-shell. On exit code 0 print `SEED_RESULT=DONE` and stop. On any blocker print `BLOCKED_REASON=<short reason>` and stop. Do not ask the user what to do with this file — that's already specified below.

## Goal

Watch tracked GitHub repos for new PR comments / reviews / mentions, deliver them to the Boss via the mypeople queue, and **auto-approve** any PR whose comment contains a configurable approve-command (default `/<GITHUB_USER>-approve`) by running `gh pr review --approve`.

This is a sibling of [`mypeople.seed.md`](mypeople.seed.md) — a separate layer that depends on mypeople already being installed and the queue running.

After install: a `pr-autoapprove` daemon runs on this host, polls GitHub every N seconds for new events on `WATCHED_REPOS`, pushes each relevant event as an `mp send` task targeting the Boss, and auto-approves PRs where someone typed the approve-command in a comment.

It also acts as a **SEED REVIEWER**: it discovers open-PR repos org-wide under `WATCHED_ORGS` (one rate-safe `gh search` call, throttled to `ORG_POLL_INTERVAL`), and when a comment **@-mentions us** (`SELF_USER`) on a repo under `SEED_REVIEW_PREFIXES`, it spawns `seed-reviewer.py` — a persona-seeded headless `claude` engineer in a tmp folder that clones the PR head, decides whether it's a SEED project, checks the **>=90% instructions / <=10% code** bar (almanac/teleprompter as the reference), and posts the verdict as a PR comment.

## Depends on

- **mypeople** is installed and healthy on this host. The Boss agent (`<host>/main:Boss` by default) exists and is reachable via the queue. Step 0 Interview verifies with `mp status` showing the Boss alive.
- `gh` CLI installed and authenticated (`gh auth status` reports a logged-in user).

If either is missing: `BLOCKED_REASON=mypeople_not_installed` or `BLOCKED_REASON=gh_not_authed`.

## Done

- `~/mypeople/bin/gh-pr-watcher.py` and `~/mypeople/bin/seed-reviewer.py` exist and are executable.
- `~/.config/mypeople/gh-pr-watcher.env` contains `WATCHED_REPOS`, `SELF_USER`, `APPROVE_COMMAND`, `POLL_INTERVAL`, `BOSS_TARGET` (and, for the seed reviewer, `WATCHED_ORGS`, `SEED_REVIEW_PREFIXES`, `ORG_POLL_INTERVAL`).
- Seed reviewer smoke: a comment `@<SELF_USER>` on a PR in a `SEED_REVIEW_PREFIXES` repo → within `ORG_POLL_INTERVAL` + `claude` runtime, a verdict comment is posted on the PR (valid SEED / not-a-proper-seed / "I do not review PRs that are not SEED projects").
- A `gh-pr-watcher` daemon process is alive (poll loop running), **supervised** so it survives sleep / reboot / network blips: a launchd LaunchAgent (`com.mypeople.gh-pr-watcher`) on macOS, or a systemd `--user` unit (`gh-pr-watcher.service`) on Linux, both with restart-on-exit. The supervisor — not a bare PID file — owns the process lifecycle.
- State file `~/mypeople/run/gh-pr-watcher-state.json` exists; first run initializes seen-ids without spamming.
- Smoke: comment `/<SELF_USER>-approve` on a tracked test PR → within `POLL_INTERVAL`+`gh latency` seconds:
  - `gh pr view <pr> --json reviews` shows a review by SELF_USER with state APPROVED;
  - the Boss's pane has received an `[AUTO-APPROVED] <repo>#<pr> ...` line via `mp send`.

## Inputs

| name | required | default | detect | ask |
|---|---|---|---|---|
| `SELF_USER` | yes | none | `gh api user --jq .login` returns a login | "Your GitHub username (used to (a) form the approve-command `/<user>-approve` and (b) decide what counts as 'mentions me' / 'own-PR'). Default suggestion: `$(gh api user --jq .login)`." |
| `WATCHED_REPOS` | yes | none | `[ -s ~/.config/mypeople/gh-pr-watcher.env ] && grep -q WATCHED_REPOS=` | "Comma-separated `owner/repo` list to poll (e.g. `cncorp/plow,cncorp/codel-text`). At least one." |
| `APPROVE_REPOS` | no | (same as `WATCHED_REPOS`) | env file | "Subset of WATCHED_REPOS where `/<SELF_USER>-approve` actually triggers `gh pr review --approve`. Other repos: notify-only. Default: all watched repos." |
| `APPROVE_COMMAND` | no | `/<SELF_USER>-approve` | env file | "The comment marker that triggers auto-approval. Default: `/<SELF_USER>-approve`. Word-boundary matched so near-misses like `/<user>-approve-later` don't trigger." |
| `POLL_INTERVAL` | no | `15` (seconds) | env file | "How often to poll GitHub. With the `?since=<ts>` delta-fetch, each poll is ~3 calls/repo, so 15s = ~240 polls/hr × 3 = well under the 5000/hr authed limit. Lower for tighter latency; raise if you watch many repos." |
| `BOSS_TARGET` | no | `<host>/main:Boss` | env file | "Full agent_id of the Boss to notify. Default: this host's main:Boss." |
| `IGNORED_USERS` | no | `corgea[bot]` | env file | "Comma-separated GH users to silence entirely (bots, self-reviews). Comments / reviews from these users never trigger notifications. Approve-commands from these users are still honored (intentional — a bot can post the marker after CI passes)." |
| `WATCHED_ORGS` | no | (empty) | env file | "Comma-separated GH orgs (e.g. `plow-pbc`). Each cycle, open-PR repos in these orgs are discovered org-wide via one `gh search` call and folded into the watch set — so the Boss is notified of activity across ALL of an org's repos without listing each. Empty = static `WATCHED_REPOS` only." |
| `SEED_REVIEW_PREFIXES` | no | (empty) | env file | "Comma-separated `owner/`-or-`owner/repo` prefixes (e.g. `plow-pbc/`). A comment that @-mentions `SELF_USER` on a PR in a matching repo spawns the seed reviewer. Empty = seed review disabled." |
| `ORG_POLL_INTERVAL` | no | `120` (seconds) | env file | "How often org-discovered repos are re-polled. Slower than `POLL_INTERVAL` to stay under the rate limit; the per-repo `since` watermark means a longer gap just widens the delta window, so no events are missed." |
| `gh` CLI authed | yes | host-provided | `gh auth status` reports `Logged in` | `BLOCKED_REASON=gh_not_authed` — run `gh auth login` first. |
| mypeople healthy | yes | from prior seed | `mp status` lists the Boss alive | `BLOCKED_REASON=mypeople_not_installed` — install [`mypeople.seed.md`](mypeople.seed.md) first. |

## Components

| Component | Source | Notes |
|---|---|---|
| `gh-pr-watcher.py` | **inline in this seed** | polls GH (static repos + org-discovered), decides relevance, posts to queue, runs approve-command, spawns the seed reviewer on @-mention |
| `seed-reviewer.py` | **inline in this seed** | persona-seeded headless `claude` engineer in a tmp folder: clones the PR head, judges seed-or-not + the 90/10 instructions/code bar, posts the verdict comment |
| state file | `~/mypeople/run/gh-pr-watcher-state.json` | `last_polled_at` per repo (ISO 8601 UTC) drives delta-fetch via `?since=`; `seen_ids[]` dedupes the 5s overlap window |
| event archive | `~/.gh-pr-watcher/inbox/*.json` | full payloads so Boss can read more than the message snippet |
| `gh` CLI | host-provided | `gh api`, `gh pr view`, `gh pr review --approve` |

## Steps

### 0. Interview (mandatory)

Detect each `## Inputs` row. Send ONE consolidated message to the CEO listing what's satisfied, what's missing, and what defaults will be used. Wait for reply. Then run autonomously.

### 1. Verify prerequisites

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
command -v mp >/dev/null || { echo "BLOCKED_REASON=mypeople_not_installed"; exit 1; }
mp status >/dev/null 2>&1 || { echo "BLOCKED_REASON=mypeople_queue_unreachable"; exit 1; }
command -v gh >/dev/null || { echo "BLOCKED_REASON=gh_not_installed"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "BLOCKED_REASON=gh_not_authed (run: gh auth login)"; exit 1; }
```

### 2. Stop any prior watcher

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
# Stop the supervisor FIRST on idempotent re-install, or it will relaunch the
# process the moment we kill it below. Step 6 re-creates it cleanly.
case "$(uname -s)" in
  Darwin) launchctl bootout "gui/$(id -u)/com.mypeople.gh-pr-watcher" 2>/dev/null || true ;;
  Linux)  systemctl --user disable --now gh-pr-watcher.service 2>/dev/null || true ;;
esac
# Legacy bare-nohup PID file from pre-supervisor installs.
[ -f "$INSTALL_DIR/run/gh-pr-watcher.pid" ] && kill "$(cat $INSTALL_DIR/run/gh-pr-watcher.pid)" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/gh-pr-watcher.py" 2>/dev/null || true
```

### 3. Write `~/.config/mypeople/gh-pr-watcher.env`

```bash
mkdir -p "$HOME/.config/mypeople"
SELF_USER="${SELF_USER:?must be set}"
WATCHED_REPOS="${WATCHED_REPOS:?must be set}"
APPROVE_REPOS="${APPROVE_REPOS:-$WATCHED_REPOS}"
APPROVE_COMMAND="${APPROVE_COMMAND:-/${SELF_USER}-approve}"
POLL_INTERVAL="${POLL_INTERVAL:-15}"
BOSS_TARGET="${BOSS_TARGET:-$(hostname -s)/main:Boss}"
IGNORED_USERS="${IGNORED_USERS:-corgea[bot]}"
WATCHED_ORGS="${WATCHED_ORGS:-}"
SEED_REVIEW_PREFIXES="${SEED_REVIEW_PREFIXES:-}"
ORG_POLL_INTERVAL="${ORG_POLL_INTERVAL:-120}"
cat > "$HOME/.config/mypeople/gh-pr-watcher.env" <<EOF
WATCHED_REPOS=${WATCHED_REPOS}
APPROVE_REPOS=${APPROVE_REPOS}
SELF_USER=${SELF_USER}
APPROVE_COMMAND=${APPROVE_COMMAND}
POLL_INTERVAL=${POLL_INTERVAL}
BOSS_TARGET=${BOSS_TARGET}
IGNORED_USERS=${IGNORED_USERS}
WATCHED_ORGS=${WATCHED_ORGS}
SEED_REVIEW_PREFIXES=${SEED_REVIEW_PREFIXES}
ORG_POLL_INTERVAL=${ORG_POLL_INTERVAL}
EOF
chmod 600 "$HOME/.config/mypeople/gh-pr-watcher.env"
```

### 4. Write `gh-pr-watcher.py` (inline)

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/run" "$HOME/.gh-pr-watcher/inbox"
cat > "$INSTALL_DIR/bin/gh-pr-watcher.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople gh-pr-watcher.

Polls WATCHED_REPOS for new PR comments / reviews / inline review comments
using GitHub's `since=<ts>` delta-fetch endpoints (1 call per repo per kind,
not 3 calls per PR). Two outputs per relevant event:
  1. Push an `mp send` task to the Boss via the queue.
  2. If the event body contains APPROVE_COMMAND and the repo is in
     APPROVE_REPOS, run `gh pr review --approve` and surface that to Boss
     with an [AUTO-APPROVED] line.
"""

from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG = Path.home() / ".config" / "mypeople" / "gh-pr-watcher.env"
INSTALL_DIR = Path(os.environ.get("INSTALL_DIR", str(Path.home() / "mypeople")))
STATE_FILE = INSTALL_DIR / "run" / "gh-pr-watcher-state.json"
INBOX_DIR = Path.home() / ".gh-pr-watcher" / "inbox"
QUEUE_ENV = Path.home() / ".config" / "mypeople" / "queue.env"
GH_TIMEOUT = 20
OVERLAP_SECONDS = 5  # re-query a small window each poll; seen_ids dedupes


def load_env(path: Path) -> dict:
    d = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d


CFG = load_env(CONFIG)
QC = load_env(QUEUE_ENV)
SELF_USER = CFG.get("SELF_USER", "")
WATCHED_REPOS = [r.strip() for r in CFG.get("WATCHED_REPOS", "").split(",") if r.strip()]
APPROVE_REPOS = set(r.strip() for r in CFG.get("APPROVE_REPOS", "").split(",") if r.strip()) or set(WATCHED_REPOS)
APPROVE_COMMAND = CFG.get("APPROVE_COMMAND", f"/{SELF_USER}-approve")
POLL_INTERVAL = int(CFG.get("POLL_INTERVAL", "15"))
BOSS_TARGET = CFG.get("BOSS_TARGET", "")
IGNORED_USERS = set(u.strip() for u in CFG.get("IGNORED_USERS", "").split(",") if u.strip())

# Orgs whose open-PR repos are discovered org-wide and folded into the watch set
# each cycle (one cheap `gh search` call), in addition to the static
# WATCHED_REPOS. This is how "Boss notified of PR activity across ALL plow-pbc/*
# repos" is satisfied without statically enumerating ~40 repos.
WATCHED_ORGS = [o.strip() for o in CFG.get("WATCHED_ORGS", "").split(",") if o.strip()]
# Repos under these prefixes get a SEED REVIEW spawned when a comment @-mentions
# us (SELF_USER). The reviewer analyses the PR and posts a verdict.
SEED_REVIEW_PREFIXES = [p.strip() for p in CFG.get("SEED_REVIEW_PREFIXES", "").split(",") if p.strip()]
SEED_REVIEWER = CFG.get("SEED_REVIEWER", str(INSTALL_DIR / "bin" / "seed-reviewer.py"))
# Org-discovered repos are polled on a slower cadence than the static repos to
# stay well under GitHub's rate limit. The per-repo `since` watermark means a
# longer gap just widens the delta window — no events are missed.
ORG_POLL_INTERVAL = int(CFG.get("ORG_POLL_INTERVAL", "120"))

QUEUE_URL = QC.get("QUEUE_URL", "http://127.0.0.1:9900")
QUEUE_SECRET = QC.get("QUEUE_SECRET", "")

MENTION_RE = re.compile(rf"(?<![A-Za-z0-9_])@{re.escape(SELF_USER)}\b", re.IGNORECASE) if SELF_USER else None
APPROVE_RE = re.compile(rf"(?<![A-Za-z0-9_/]){re.escape(APPROVE_COMMAND)}(?![A-Za-z0-9_-])")
ISSUE_N_RE = re.compile(r"/issues/(\d+)$")
PULL_N_RE = re.compile(r"/pulls/(\d+)$")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def shift_iso(iso_ts: str, delta_seconds: int) -> str:
    dt = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (dt + timedelta(seconds=delta_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def mentions_self(body: str) -> bool:
    return bool(MENTION_RE and MENTION_RE.search(body or ""))


def is_approve_command(event: dict) -> bool:
    if event["repo"] not in APPROVE_REPOS:
        return False
    if event["kind"] not in ("comment", "review", "review_comment"):
        return False
    return bool(APPROVE_RE.search(event.get("body") or ""))


def approve_pr(repo: str, pr: int) -> tuple[bool, str]:
    try:
        r = subprocess.run(["gh", "pr", "review", str(pr), "--approve", "--repo", repo],
                           capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, str(e)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "").strip()
    return True, (r.stdout or "").strip()


def notify_reason(event: dict, pr_author: str) -> str | None:
    if event["user"] in IGNORED_USERS:
        return None
    if pr_author == SELF_USER:
        return "own-PR"
    if mentions_self(event.get("body", "")):
        return "mention"
    return None


def push_to_boss(message: str) -> bool:
    if not BOSS_TARGET or "/" not in BOSS_TARGET:
        print("  ERROR: BOSS_TARGET not set or malformed", file=sys.stderr)
        return False
    target_host = BOSS_TARGET.split("/", 1)[0]
    task = {
        "action": "send",
        "target_host": target_host,
        "target_agent": BOSS_TARGET,
        "payload": {"message": message},
    }
    body = json.dumps(task).encode()
    headers = {"Content-Type": "application/json", "X-Queue-Secret": QUEUE_SECRET}
    req = urllib.request.Request(f"{QUEUE_URL}/task/submit", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            r = json.loads(resp.read())
            print(f"  → queued task {r.get('task_id', '?')[:8]}")
            return True
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  ERROR push: {e}", file=sys.stderr)
        return False


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"seen_ids": [], "last_polled_at": {}, "last_org_poll": 0}
    try:
        d = json.loads(STATE_FILE.read_text())
        d.setdefault("seen_ids", [])
        d.setdefault("last_polled_at", {})
        d.setdefault("last_org_poll", 0)
        return d
    except json.JSONDecodeError:
        return {"seen_ids": [], "last_polled_at": {}, "last_org_poll": 0}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["seen_ids"] = state["seen_ids"][-2000:]
    STATE_FILE.write_text(json.dumps(state, indent=2))


def gh_api(path: str, paginate: bool = True) -> list | dict:
    cmd = ["gh", "api"]
    if paginate:
        cmd.append("--paginate")
    cmd.append(path)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"  gh api {path!r} failed: {e}", file=sys.stderr)
        return []
    if r.returncode != 0:
        print(f"  gh api {path!r} returncode={r.returncode}: {r.stderr[:200]}", file=sys.stderr)
        return []
    out = r.stdout.strip()
    if not out:
        return []
    if paginate:
        merged = []
        for chunk in out.replace("][", ",").split("\n"):
            try:
                v = json.loads(chunk)
                if isinstance(v, list):
                    merged.extend(v)
                else:
                    merged.append(v)
            except json.JSONDecodeError:
                pass
        return merged
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def discover_org_repos(orgs: list[str]) -> list[str]:
    """Return repos in the given orgs that currently have >=1 open PR, via a
    single search call per org (rate-safe). Only repos with open PRs are polled,
    so the per-cycle cost stays small even across a large org."""
    repos: set[str] = set()
    for org in orgs:
        try:
            r = subprocess.run(
                ["gh", "search", "prs", "--owner", org, "--state", "open",
                 "--limit", "200", "--json", "repository"],
                capture_output=True, text=True, timeout=GH_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError) as e:
            print(f"  discover_org_repos({org}) failed: {e}", file=sys.stderr)
            continue
        if r.returncode != 0:
            print(f"  discover_org_repos({org}) rc={r.returncode}: {r.stderr[:200]}", file=sys.stderr)
            continue
        try:
            for item in json.loads(r.stdout or "[]"):
                name = (item.get("repository") or {}).get("nameWithOwner", "")
                if name:
                    repos.add(name)
        except json.JSONDecodeError:
            pass
    return sorted(repos)


def is_seed_review_repo(repo: str) -> bool:
    return any(repo.startswith(pfx) for pfx in SEED_REVIEW_PREFIXES)


def launch_seed_review(event: dict) -> None:
    """Spawn the seed-reviewer detached to analyse this PR and post a verdict."""
    cmd = [sys.executable, SEED_REVIEWER,
           "--repo", event["repo"], "--pr", str(event["pr"]),
           "--trigger-comment-id", str(event["id"]),
           "--trigger-user", event.get("user", "")]
    log_path = INSTALL_DIR / "run" / "seed-reviewer.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(log_path, "a")
        subprocess.Popen(cmd, stdout=f, stderr=f, stdin=subprocess.DEVNULL,
                         start_new_session=True, env={**os.environ, "INSTALL_DIR": str(INSTALL_DIR)})
        print(f"  → spawned seed-reviewer for {event['repo']}#{event['pr']} (trigger {event['id']})")
    except OSError as e:
        print(f"  ERROR spawning seed-reviewer: {e}", file=sys.stderr)


def list_open_prs(repo: str) -> dict[int, dict]:
    """Return {pr_number: {author, updated_at}} for open PRs."""
    prs = gh_api(f"/repos/{repo}/pulls?state=open&per_page=100", paginate=True)
    out = {}
    for p in prs or []:
        out[int(p["number"])] = {"author": p["user"]["login"], "updated_at": p.get("updated_at") or ""}
    return out


def fetch_new_events(repo: str, since_iso: str, open_prs: dict[int, dict]) -> list[dict]:
    """Delta-fetch new events repo-wide via since=<ts>. Filters to open PRs only."""
    events: list[dict] = []

    # 1. Issue comments (covers PR conversation comments — PRs are issues at the API level)
    ics = gh_api(f"/repos/{repo}/issues/comments?since={since_iso}&per_page=100&sort=created&direction=asc")
    for ic in ics or []:
        m = ISSUE_N_RE.search(ic.get("issue_url", "") or "")
        if not m:
            continue
        n = int(m.group(1))
        if n not in open_prs:
            continue
        events.append({"kind": "comment", "id": ic["id"], "user": ic["user"]["login"],
                       "body": ic.get("body") or "", "repo": repo, "pr": n, "extra": {}})

    # 2. PR review comments (inline diff comments)
    rcs = gh_api(f"/repos/{repo}/pulls/comments?since={since_iso}&per_page=100&sort=created&direction=asc")
    for rc in rcs or []:
        m = PULL_N_RE.search(rc.get("pull_request_url", "") or "")
        if not m:
            continue
        n = int(m.group(1))
        if n not in open_prs:
            continue
        events.append({"kind": "review_comment", "id": rc["id"], "user": rc["user"]["login"],
                       "body": rc.get("body") or "", "repo": repo, "pr": n, "extra": {}})

    # 3. Reviews: no repo-wide since endpoint exists, so only fetch on PRs touched since last poll.
    for pr_n, info in open_prs.items():
        if info["updated_at"] and info["updated_at"] <= since_iso:
            continue
        rvs = gh_api(f"/repos/{repo}/pulls/{pr_n}/reviews?per_page=100", paginate=True)
        for rv in rvs or []:
            submitted = rv.get("submitted_at") or ""
            if submitted and submitted <= since_iso:
                continue
            events.append({"kind": "review", "id": rv["id"], "user": (rv.get("user") or {}).get("login", ""),
                           "body": rv.get("body") or "", "repo": repo, "pr": pr_n,
                           "extra": {"state": rv.get("state") or ""}})

    return events


def archive_event(event: dict) -> Path:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{event['repo'].replace('/', '__')}-pr{event['pr']}-{event['kind']}-{event['id']}.json"
    p = INBOX_DIR / name
    p.write_text(json.dumps(event, indent=2))
    return p


def format_message(event: dict, archive_path: Path, reason: str) -> str:
    snippet = (event.get("body") or "").strip().replace("\n", " ")[:200]
    head = f"[{reason.upper()}] {event['repo']}#{event['pr']} {event['kind']} by @{event['user']}"
    extra = ""
    if event["kind"] == "review":
        extra = f" ({(event.get('extra') or {}).get('state', '?')})"
    return f"{head}{extra}: {snippet}  (full: {archive_path})"


def poll_once(state: dict, dry_run: bool = False) -> None:
    seen = set(state["seen_ids"])
    last_polled = state["last_polled_at"]
    cycle_start = now_iso()

    repos = list(WATCHED_REPOS)
    if WATCHED_ORGS and (time.time() - state.get("last_org_poll", 0)) >= ORG_POLL_INTERVAL:
        org_repos = discover_org_repos(WATCHED_ORGS)
        state["last_org_poll"] = time.time()
        print(f"org-discover {WATCHED_ORGS}: {len(org_repos)} repo(s) with open PRs")
        repos += org_repos
    repos = list(dict.fromkeys(repos))
    for repo in repos:
        # First-time bootstrap for a repo: just stamp now() and skip notifications.
        if repo not in last_polled:
            last_polled[repo] = cycle_start
            print(f"poll[{repo}]: first-encounter — stamping {cycle_start}, no notifications")
            continue

        since_iso = shift_iso(last_polled[repo], -OVERLAP_SECONDS)
        open_prs = list_open_prs(repo)
        events = fetch_new_events(repo, since_iso, open_prs)
        print(f"poll[{repo}]: since={since_iso} → {len(events)} new event(s) across {len(open_prs)} open PR(s)")

        for ev in events:
            eid = f"{ev['kind']}:{ev['id']}"
            if eid in seen:
                continue
            seen.add(eid)

            pr_author = open_prs.get(ev["pr"], {}).get("author", "")
            reason = notify_reason(ev, pr_author)
            approve = is_approve_command(ev)
            if not reason and not approve:
                continue

            archive_path = archive_event(ev)

            # SEED REVIEW: a comment @-mentioning us on a seed-review repo spawns
            # the persona-seeded reviewer to analyse the PR and post a verdict.
            # Gated on the @-mention itself (per spec: "analyze ONLY when a
            # comment @-mentions us"), independent of who authored the PR.
            if mentions_self(ev.get("body", "")) and is_seed_review_repo(ev["repo"]) \
                    and ev["kind"] in ("comment", "review_comment", "review"):
                if dry_run:
                    print(f"  DRY: would spawn seed-reviewer for {ev['repo']}#{ev['pr']}")
                else:
                    launch_seed_review(ev)

            if approve and not dry_run:
                ok, info = approve_pr(ev["repo"], ev["pr"])
                marker = "AUTO-APPROVED" if ok else "AUTO-APPROVE-FAILED"
                msg = f"[{marker}] {ev['repo']}#{ev['pr']} via {APPROVE_COMMAND} by @{ev['user']}: {info[:200]}"
                push_to_boss(msg)
            if reason:
                msg = format_message(ev, archive_path, reason)
                if dry_run:
                    print(f"  DRY: {msg}")
                else:
                    push_to_boss(msg)

        # Advance the watermark only on success.
        last_polled[repo] = cycle_start

    state["seen_ids"] = list(seen)
    state["last_polled_at"] = last_polled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="seconds between polls (0 = one-shot)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--init", action="store_true", help="mark current state as seen, push nothing")
    args = ap.parse_args()

    if not SELF_USER or not WATCHED_REPOS:
        print("FATAL: SELF_USER and WATCHED_REPOS required in ~/.config/mypeople/gh-pr-watcher.env", file=sys.stderr)
        sys.exit(1)
    if not BOSS_TARGET:
        print("FATAL: BOSS_TARGET required in ~/.config/mypeople/gh-pr-watcher.env", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    if args.init:
        stamp = now_iso()
        state["last_polled_at"] = {repo: stamp for repo in WATCHED_REPOS}
        save_state(state)
        print(f"initialized: last_polled_at={stamp} for {len(WATCHED_REPOS)} repo(s)")
        return

    interval = args.loop if args.loop > 0 else POLL_INTERVAL
    if args.loop == 0:
        poll_once(state, dry_run=args.dry_run)
        save_state(state)
        return

    print(f"loop: polling every {interval}s. Ctrl-C to stop.")
    try:
        while True:
            try:
                poll_once(state, dry_run=args.dry_run)
                save_state(state)
            except Exception as e:
                print(f"  poll FAILED: {e}", file=sys.stderr)
            time.sleep(interval)
    except KeyboardInterrupt:
        save_state(state)


if __name__ == "__main__":
    main()
PY_EOF
chmod +x "$INSTALL_DIR/bin/gh-pr-watcher.py"
```

### 4b. Write `seed-reviewer.py` (inline)

The watcher spawns this when a comment **@-mentions us** on a `SEED_REVIEW_PREFIXES` repo. It clones the PR head into a tmp folder, seeds a persona `CLAUDE.md` (the seed-reviewer engineer), runs a headless `claude` that judges seed-or-not and the **>=90% instructions / <=10% code** bar (almanac/teleprompter as the reference), cross-checked by a deterministic fenced-code line-ratio, then posts the verdict as a PR comment. (4-backtick fence: the script itself contains 3-backtick sequences.)

````bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
cat > "$INSTALL_DIR/bin/seed-reviewer.py" <<'SEED_REVIEWER_PY'
#!/usr/bin/env python3
"""mypeople seed-reviewer.

Spawned (by gh-pr-watcher, or run by hand) to review ONE pull request and post
a verdict comment. The flow, per the spec card 811bfe8cba9d:

  1. Make a tmp work folder and seed it with a persona CLAUDE.md (the
     "seed-reviewer engineer").
  2. Clone the PR head into that folder so the engineer reads the real repo.
  3. Compute a deterministic instruction/code line-ratio over the seed
     artifact(s) as an objective signal.
  4. Run a persona-seeded headless `claude` in the folder; it returns a verdict.
  5. Post the verdict as a PR comment:
       - not a SEED project -> "I do not review PRs that are not SEED projects."
       - a SEED, >=90% instructions / <=10% code -> valid
       - a SEED, but too much code -> not a proper seed

The 90/10 bar (almanac/teleprompter are the named reference seeds): a SEED is
mostly INSTRUCTIONS (prose telling an agent what to build + how to verify), with
minimal literal CODE EXAMPLES. "code" = non-blank lines inside fenced blocks
tagged with a real programming language (py/js/ts/tsx/jsx/go/rust/...). Shell,
console, text, yaml/json/toml, dockerfile, env and prose count as instructions
(they are commands to run, config, or output — not product source).

Usage:
  seed-reviewer.py --repo plow-pbc/almanac-seed --pr 12 [--trigger-comment-id 123]
  seed-reviewer.py --repo plow-pbc/seedbank --pr 49 --dry-run
"""

from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

# Ensure user-local bins (claude) and homebrew (gh) are reachable even when
# spawned from launchd, whose PATH omits ~/.local/bin.
for _extra in (str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin"):
    if _extra not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = _extra + os.pathsep + os.environ.get("PATH", "")

INSTALL_DIR = Path(os.environ.get("INSTALL_DIR", str(Path.home() / "mypeople")))
REVIEW_ROOT = INSTALL_DIR / "run" / "seed-reviews"
DONE_DIR = REVIEW_ROOT / "done"
LOG_FILE = INSTALL_DIR / "run" / "seed-reviewer.log"

GH_TIMEOUT = 60
CLAUDE_TIMEOUT = 600  # the engineer gets up to 10 min to reason

NOT_A_SEED_MSG = "I do not review PRs that are not SEED projects."
SIGNATURE = "— 🌱 seed-reviewer (mypeople)"

# Fence info-strings that mean "literal product source" -> counts as CODE.
CODE_LANGS = {
    "py", "python", "js", "javascript", "jsx", "ts", "typescript", "tsx",
    "go", "golang", "rust", "rs", "java", "kotlin", "kt", "swift", "c", "cpp",
    "c++", "cs", "csharp", "ruby", "rb", "php", "scala", "html", "vue", "svelte",
    "css", "scss", "sass", "sql",
}
SEED_FILE_RE = re.compile(r"(^|/)(seed\.md|.*\.seed\.md|SEED\.md)$", re.IGNORECASE)


# --- logging -------------------------------------------------------------

def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass


# --- shell helpers -------------------------------------------------------

def run(cmd: list[str], cwd: Path | None = None, timeout: int = GH_TIMEOUT) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (subprocess.TimeoutExpired, OSError) as e:
        return 1, "", str(e)


def gh_token() -> str:
    rc, out, _ = run(["gh", "auth", "token"])
    return out.strip() if rc == 0 else ""


# --- deterministic instruction/code metric -------------------------------

def code_ratio(text: str) -> dict:
    """Classify every non-blank line as code (real-language fence) or
    instruction (prose, shell, config, output). Returns a metrics dict."""
    total = code = 0
    in_fence = False
    fence_lang = None
    for raw in text.split("\n"):
        s = raw.strip()
        m = re.match(r"^(```+|~~~+)(.*)$", s)
        if m:
            if not in_fence:
                in_fence = True
                info = m.group(2).strip().split()
                fence_lang = (info[0].lower() if info else "")
            else:
                in_fence = False
                fence_lang = None
            continue  # fence markers themselves are neither
        if not s:
            continue
        total += 1
        if in_fence and fence_lang in CODE_LANGS:
            code += 1
    if total == 0:
        return {"total_lines": 0, "code_lines": 0, "code_pct": 0.0, "instruction_pct": 100.0}
    code_pct = round(100.0 * code / total, 1)
    return {
        "total_lines": total,
        "code_lines": code,
        "code_pct": code_pct,
        "instruction_pct": round(100.0 - code_pct, 1),
    }


def find_seed_files(repo_dir: Path) -> list[Path]:
    found = []
    for p in repo_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(repo_dir).as_posix()
        if "/.git/" in "/" + rel + "/":
            continue
        if SEED_FILE_RE.search(rel):
            found.append(p)
    # root-level seed files first, then by size desc
    found.sort(key=lambda p: (len(p.relative_to(repo_dir).parts), -p.stat().st_size))
    return found


# --- PR fetch ------------------------------------------------------------

def clone_pr_head(repo: str, pr: int, dest: Path) -> bool:
    token = gh_token()
    if not token:
        log("  ERROR: no gh token")
        return False
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    rc, _, err = run(["git", "clone", "--depth", "1", url, str(dest)], timeout=GH_TIMEOUT)
    if rc != 0:
        log(f"  clone failed: {err[:300]}")
        return False
    rc, _, err = run(["git", "fetch", "--depth", "1", "origin", f"pull/{pr}/head:pr"],
                     cwd=dest, timeout=GH_TIMEOUT)
    if rc != 0:
        log(f"  fetch pr head failed: {err[:300]}")
        return False
    rc, _, err = run(["git", "checkout", "pr"], cwd=dest, timeout=GH_TIMEOUT)
    if rc != 0:
        log(f"  checkout pr failed: {err[:300]}")
        return False
    return True


def pr_meta(repo: str, pr: int) -> dict:
    rc, out, _ = run(["gh", "pr", "view", str(pr), "--repo", repo, "--json",
                      "title,body,author,headRefName,files,additions,deletions"])
    if rc != 0:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


# --- persona + engineer --------------------------------------------------

PERSONA = """# You are the SEED REVIEWER — a seedlab engineer

You review a single pull request and decide, with a clear head, two things:

1. **Is this a SEED project at all?** A SEED is a self-contained, paste-into-a-
   fresh-agent product spec: a `SEED.md` / `*.seed.md` that tells a coding agent
   WHAT to build and HOW to verify it — the agent authors the code. Repos that
   are ordinary apps, websites, libraries, config, or tooling (even if they live
   alongside seeds) are NOT seed projects.

2. **If it is a seed, is it a PROPER seed?** The doctrine: a seed is
   **>= 90% instructions and <= 10% code examples**. almanac-seed and
   teleprompter-seed are the reference bar — almanac is ~0% literal code.
   "code" = literal product source embedded in the seed (fenced blocks tagged
   python/js/ts/tsx/go/rust/... — source you could paste straight into a file).
   Shell commands to run, verify steps, config, expected output, and prose are
   INSTRUCTIONS, not code. A proper seed describes the product and lets the agent
   write it; an improper seed is a code dump with a thin prose wrapper.

You are given a deterministic line-ratio in `metrics.json` as an objective
signal. Trust it, but apply judgement: a giant shell heredoc that simply writes
hundreds of lines of source files verbatim is *code in disguise* — count it
against the seed even if the fence is tagged `sh`. Conversely a couple of tiny
illustrative snippets do not make an otherwise-prose seed improper.

## Your job
Read `TASK.md`, inspect the cloned repo under `repo/`, read `metrics.json`, then
write your verdict to `verdict.json` (and print it). Be terse and decisive.
"""

TASK_TMPL = """# Review task

Repo: {repo}
PR #{pr}: {title}
Author: @{author}
Changed files ({nfiles}): +{adds}/-{dels}

The PR head is checked out under `./repo/`. Seed artifact(s) detected:
{seed_list}

`metrics.json` holds the deterministic instruction/code line-ratio computed over
the seed artifact(s) (code = fenced real-language source lines / total non-blank
lines).

## Produce `verdict.json` with EXACTLY this schema:

{{
  "is_seed": true | false,
  "verdict": "valid" | "not-a-proper-seed" | "not-a-seed",
  "code_pct": <number>,
  "instruction_pct": <number>,
  "reasoning": "<=2 sentences, concrete"
}}

Rules:
- If this is not a SEED project -> is_seed=false, verdict="not-a-seed".
- If it is a seed AND instructions >= 90% and code <= 10% -> verdict="valid".
- If it is a seed but too much code -> verdict="not-a-proper-seed".
- For code_pct/instruction_pct, start from metrics.json but adjust if you found
  code-in-disguise (large verbatim source heredocs); explain in reasoning.

Write the file with the Write tool, then print the JSON. Nothing else.
"""


def run_engineer(workdir: Path, repo: str, pr: int, meta: dict, seed_files: list[str],
                 metrics: dict) -> dict | None:
    (workdir / "CLAUDE.md").write_text(PERSONA)
    (workdir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    seed_list = "\n".join(f"  - {s}" for s in seed_files) or "  (none found)"
    (workdir / "TASK.md").write_text(TASK_TMPL.format(
        repo=repo, pr=pr, title=meta.get("title", "?"),
        author=(meta.get("author") or {}).get("login", "?"),
        nfiles=len(meta.get("files") or []), adds=meta.get("additions", 0),
        dels=meta.get("deletions", 0), seed_list=seed_list))

    prompt = ("Read TASK.md and CLAUDE.md, inspect ./repo and ./metrics.json, "
              "then write ./verdict.json per the schema and print it.")
    log(f"  running engineer (claude -p) in {workdir} ...")
    rc, out, err = run(["claude", "-p", prompt, "--dangerously-skip-permissions"],
                       cwd=workdir, timeout=CLAUDE_TIMEOUT)
    (workdir / "engineer.stdout").write_text(out)
    if err:
        (workdir / "engineer.stderr").write_text(err)
    if rc != 0:
        log(f"  engineer rc={rc}: {err[:200]}")

    # Prefer verdict.json on disk; fall back to JSON in stdout.
    vfile = workdir / "verdict.json"
    if vfile.exists():
        try:
            return json.loads(vfile.read_text())
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


# --- verdict -> comment --------------------------------------------------

def build_comment(verdict: dict, metrics: dict) -> str:
    is_seed = bool(verdict.get("is_seed"))
    v = verdict.get("verdict", "")
    reasoning = (verdict.get("reasoning") or "").strip()
    code_pct = verdict.get("code_pct", metrics.get("code_pct"))
    instr_pct = verdict.get("instruction_pct", metrics.get("instruction_pct"))

    if not is_seed or v == "not-a-seed":
        body = NOT_A_SEED_MSG
        if reasoning:
            body += f"\n\n_{reasoning}_"
        return f"{body}\n\n{SIGNATURE}"

    ratio = f"**{instr_pct}% instructions / {code_pct}% code** (bar: ≥90% / ≤10%)"
    if v == "valid":
        head = f"✅ **Valid SEED** — {ratio}."
    else:
        head = f"❌ **Not a proper seed** — {ratio}. A seed must be ≥90% instructions / ≤10% code."
    if reasoning:
        head += f"\n\n{reasoning}"
    return f"{head}\n\n{SIGNATURE}"


def post_comment(repo: str, pr: int, body: str) -> bool:
    rc, out, err = run(["gh", "pr", "comment", str(pr), "--repo", repo, "--body", body])
    if rc != 0:
        log(f"  post comment failed: {err[:300]}")
        return False
    log(f"  posted: {out.strip()}")
    return True


# --- main ----------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--trigger-comment-id", default="")
    ap.add_argument("--trigger-user", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the work folder")
    args = ap.parse_args()

    repo, pr = args.repo, args.pr
    # Idempotency: never review the same trigger twice.
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    sentinel = None
    if args.trigger_comment_id:
        sentinel = DONE_DIR / f"{repo.replace('/', '__')}__pr{pr}__{args.trigger_comment_id}"
        if sentinel.exists() and not args.dry_run:
            log(f"already reviewed {repo}#{pr} trigger {args.trigger_comment_id}; skipping")
            return 0

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir = REVIEW_ROOT / f"{repo.replace('/', '__')}__pr{pr}__{ts}"
    workdir.mkdir(parents=True, exist_ok=True)
    log(f"=== seed-review {repo}#{pr} (trigger=@{args.trigger_user} {args.trigger_comment_id}) -> {workdir}")

    repo_dir = workdir / "repo"
    if not clone_pr_head(repo, pr, repo_dir):
        log("  ABORT: could not fetch PR head")
        return 1

    meta = pr_meta(repo, pr)
    seed_paths = find_seed_files(repo_dir)
    seed_rel = [p.relative_to(repo_dir).as_posix() for p in seed_paths]
    log(f"  seed files: {seed_rel or '(none)'}")

    combined = "\n".join(p.read_text(errors="replace") for p in seed_paths[:5])
    metrics = code_ratio(combined) if combined else {
        "total_lines": 0, "code_lines": 0, "code_pct": 0.0, "instruction_pct": 0.0}
    metrics["seed_files"] = seed_rel
    log(f"  deterministic metrics: {metrics}")

    verdict = run_engineer(workdir, repo, pr, meta, seed_rel, metrics)
    if not verdict:
        log("  ABORT: engineer produced no verdict")
        return 1
    (workdir / "verdict.final.json").write_text(json.dumps(verdict, indent=2))
    log(f"  verdict: {verdict}")

    body = build_comment(verdict, metrics)
    log(f"  comment:\n{body}")

    if args.dry_run:
        log("  DRY-RUN: not posting")
    else:
        if not post_comment(repo, pr, body):
            return 1
        if sentinel:
            sentinel.write_text(json.dumps({"ts": ts, "verdict": verdict}, indent=2))

    if not args.keep and not args.dry_run:
        # keep the artifacts; only drop the heavy clone
        shutil.rmtree(repo_dir, ignore_errors=True)
    log(f"=== done {repo}#{pr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
SEED_REVIEWER_PY
chmod +x "$INSTALL_DIR/bin/seed-reviewer.py"
````

### 5. Initialize state (bootstrap — stamp `last_polled_at = now()`)

**Why**: the watcher does delta fetches via GitHub's `?since=<ts>` parameter. `--init` records the current UTC timestamp per repo so the first poll only sees events created after install — no blast of pre-existing comments. (Without this stamp, the first poll's `since` would be missing and the auto-bootstrap inside `poll_once` would still skip the first cycle, but running `--init` explicitly is cheaper and clearer.)

```bash
python3 "$INSTALL_DIR/bin/gh-pr-watcher.py" --init
```

### 6. Start the watcher daemon **under a supervisor** (reboot-proof)

**Why a supervisor, not `nohup &`**: a bare `nohup python3 ... &` has no one to restart it. The watcher runs a long-lived poll loop that makes network calls every `POLL_INTERVAL` seconds; a laptop sleep, a Wi-Fi blip, a transient `error connecting to api.github.com`, or a reboot can kill the loop, and nothing brings it back — auto-approval silently dies until someone notices. Install it under the host's init supervisor with **restart-on-exit** so it self-heals and comes up on boot/login.

Pick the supervisor for THIS host:

- **macOS → launchd LaunchAgent** (`KeepAlive` = restart on any exit, `RunAtLoad` = start on login).
- **Linux → systemd `--user` unit** (`Restart=always`, `WantedBy=default.target`; `loginctl enable-linger <user>` so it runs without an active login session, matching the always-on intent).
- **Other / no init supervisor** → fall back to the legacy `nohup` form documented at the end of this Step, but log that the watcher is **NOT reboot-proof** on this host.

Use the absolute path to `python3` (a supervisor's `PATH` is minimal) and export `PATH` so the watcher's `gh` subprocess calls resolve.

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
POLL_INTERVAL="${POLL_INTERVAL:-15}"
PY="$(command -v python3)"; GH_DIR="$(dirname "$(command -v gh)")"
WATCHER="$INSTALL_DIR/bin/gh-pr-watcher.py"
LOG="$INSTALL_DIR/run/gh-pr-watcher.log"
OS="$(uname -s)"

# A stale bare-nohup PID file from a previous (unsupervised) install is no longer
# the source of truth — the supervisor owns liveness now. Remove it to avoid confusion.
rm -f "$INSTALL_DIR/run/gh-pr-watcher.pid"

if [ "$OS" = "Darwin" ]; then
  # ── macOS: launchd LaunchAgent ──────────────────────────────────────────
  LABEL="com.mypeople.gh-pr-watcher"
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>-u</string>
        <string>$WATCHER</string>
        <string>--loop</string>
        <string>$POLL_INTERVAL</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>ThrottleInterval</key><integer>10</integer>
    <key>WorkingDirectory</key><string>$HOME</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key><string>$HOME</string>
        <key>INSTALL_DIR</key><string>$INSTALL_DIR</string>
        <key>PATH</key><string>$GH_DIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>LANG</key><string>C.UTF-8</string>
    </dict>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
  plutil -lint "$PLIST"
  UID_N="$(id -u)"
  launchctl bootout "gui/$UID_N/$LABEL" 2>/dev/null || true   # idempotent re-install
  launchctl bootstrap "gui/$UID_N" "$PLIST"
  launchctl enable "gui/$UID_N/$LABEL"
  launchctl kickstart -k "gui/$UID_N/$LABEL"
  sleep 2
  launchctl print "gui/$UID_N/$LABEL" 2>&1 | grep -E 'state =|pid =' | head

elif [ "$OS" = "Linux" ]; then
  # ── Linux: systemd --user unit ──────────────────────────────────────────
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/gh-pr-watcher.service" <<EOF
[Unit]
Description=mypeople gh-pr-watcher (PR auto-approve + Boss notify)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=INSTALL_DIR=$INSTALL_DIR
Environment=PATH=$GH_DIR:/usr/local/bin:/usr/bin:/bin
ExecStart=$PY -u $WATCHER --loop $POLL_INTERVAL
Restart=always
RestartSec=10
StandardOutput=append:$LOG
StandardError=append:$LOG

[Install]
WantedBy=default.target
EOF
  loginctl enable-linger "$(whoami)" 2>/dev/null || true   # run without an active login session
  systemctl --user daemon-reload
  systemctl --user enable --now gh-pr-watcher.service
  sleep 2
  systemctl --user --no-pager status gh-pr-watcher.service | head -5

else
  # ── Fallback: no known init supervisor — NOT reboot-proof ────────────────
  echo "WARN: unknown OS '$OS' — no supervisor available; starting bare nohup (NOT reboot-proof)."
  nohup "$PY" -u "$WATCHER" --loop "$POLL_INTERVAL" > "$LOG" 2>&1 &
  echo $! > "$INSTALL_DIR/run/gh-pr-watcher.pid"
  sleep 2
  ps -p "$(cat $INSTALL_DIR/run/gh-pr-watcher.pid)" -o pid,command 2>&1
fi
```

The supervisor relaunches the watcher on any exit (crash, network error, sleep-wake) and starts it automatically on boot/login — so auto-approval stays live without manual intervention. Inspect logs the same way regardless of supervisor: `tail -f "$INSTALL_DIR/run/gh-pr-watcher.log"`.

## Verify

```bash
#!/bin/bash
set -e
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"

# 1. Daemon alive AND supervised (survives reboot). Check the process exists, then
#    confirm a supervisor owns it (launchd on macOS / systemd --user on Linux).
pgrep -f "$INSTALL_DIR/bin/gh-pr-watcher.py" >/dev/null || { echo "FAIL: gh-pr-watcher daemon not running"; exit 1; }
case "$(uname -s)" in
  Darwin) launchctl print "gui/$(id -u)/com.mypeople.gh-pr-watcher" 2>/dev/null | grep -q 'state = running' \
            || { echo "FAIL: watcher running but not supervised by launchd — will NOT survive reboot"; exit 1; } ;;
  Linux)  systemctl --user is-active --quiet gh-pr-watcher.service \
            || { echo "FAIL: watcher running but not supervised by systemd — will NOT survive reboot"; exit 1; } ;;
esac

# 2. Config + state files
[ -s "$HOME/.config/mypeople/gh-pr-watcher.env" ] || { echo "FAIL: gh-pr-watcher.env missing"; exit 1; }
[ -f "$INSTALL_DIR/run/gh-pr-watcher-state.json" ] || { echo "FAIL: state file missing (--init didn't run?)"; exit 1; }

# 3. gh CLI reachable + authed
gh auth status >/dev/null 2>&1 || { echo "FAIL: gh auth lost"; exit 1; }

# 4. Boss still reachable on the queue (this seed depends on mypeople)
mp status >/dev/null 2>&1 || { echo "FAIL: mypeople queue unreachable"; exit 1; }

# 5. Sample log line to prove the daemon completed at least one poll
sleep "$(( $(grep ^POLL_INTERVAL= $HOME/.config/mypeople/gh-pr-watcher.env | cut -d= -f2-) + 5 ))"
grep -q '^poll\[' "$INSTALL_DIR/run/gh-pr-watcher.log" || { echo "FAIL: no 'poll[<repo>]' line in log — watcher never completed a poll"; tail -20 "$INSTALL_DIR/run/gh-pr-watcher.log"; exit 1; }

echo "VERIFY_OK"
```

## Failure modes

**Watcher died and never came back (the bug this seed used to have)** → the daemon must run under a supervisor (Step 6), not a bare `nohup &`. Confirm it's supervised: macOS `launchctl print "gui/$(id -u)/com.mypeople.gh-pr-watcher"` should show `state = running` with a `pid`; Linux `systemctl --user status gh-pr-watcher.service` should show `active (running)`. If a `gh-pr-watcher` process is alive but neither supervisor knows about it, you're on a legacy bare-nohup start — re-run Step 6 to install the supervisor.

**Supervisor restart-loops (process exits immediately, keeps relaunching)** → check the log for the crash. Common causes: `python3`/`gh` not on the supervisor's `PATH` (Step 6 hard-codes absolute `python3` and exports `PATH` including `gh`'s dir — verify those resolve on this host), or `SELF_USER`/`WATCHED_REPOS`/`BOSS_TARGET` missing from `gh-pr-watcher.env` (the script exits non-zero on missing required config). macOS `ThrottleInterval` / Linux `RestartSec` cap the loop at one relaunch per 10s so it won't spin hot.

**`gh: command not found`** → `gh` CLI not installed. macOS: `brew install gh`. Debian: `sudo apt-get install gh`. Note the supervisor runs with a minimal `PATH`; Step 6 injects `gh`'s directory, but if you installed `gh` somewhere unusual, add it to the plist/unit `PATH`.

**`gh auth status` reports not logged in** → run `gh auth login` and complete the OAuth flow. The watcher uses the host user's authenticated session — no separate token.

**Approve-command fired but `gh pr review --approve` returned non-zero** → likely "Can not approve your own pull request" (GitHub forbids self-approval) or the PR is in a state that doesn't allow reviews. Inspect `$INSTALL_DIR/run/gh-pr-watcher.log` for the stderr.

**First start floods Boss with hundreds of notifications** → unlikely with the delta-fetch implementation: if `last_polled_at` is missing for a repo, the first poll stamps `now()` and skips. But if you wanted a tighter watermark before launch, stop the daemon, `rm "$INSTALL_DIR/run/gh-pr-watcher-state.json"`, run `--init`, restart.

**Daemon was offline for hours; restarts and floods Boss with backlog** → expected behavior of `?since=<watermark>`: while the daemon was down, comments were still happening. When it resumes, it catches up. To skip the backlog: stop the daemon, run `--init` to re-stamp `last_polled_at = now()`, then restart.

**Auto-approves a PR you didn't want approved** → the marker matched somewhere unexpected. The regex is word-boundary anchored (`/<SELF_USER>-approve` followed by non-word, non-`-`) but a comment containing the literal marker IS the contract. To revoke: `gh pr review <pr> --request-changes --repo <repo>`. To prevent on a specific repo: remove it from `APPROVE_REPOS` in `gh-pr-watcher.env` and restart the daemon.

**Notifications never reach Boss** → check the queue: `mp status` should show Boss alive; tail `$INSTALL_DIR/run/queue-server.log` for incoming `/task/submit` from the watcher; check the watcher log for `→ queued task ...` lines.

## Cleanup

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
# Tear down the supervisor first so it doesn't relaunch the process we're about to kill.
case "$(uname -s)" in
  Darwin)
    launchctl bootout "gui/$(id -u)/com.mypeople.gh-pr-watcher" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/com.mypeople.gh-pr-watcher.plist" ;;
  Linux)
    systemctl --user disable --now gh-pr-watcher.service 2>/dev/null || true
    rm -f "$HOME/.config/systemd/user/gh-pr-watcher.service"
    systemctl --user daemon-reload 2>/dev/null || true ;;
esac
# Legacy bare-nohup PID file, if any prior install left one.
[ -f "$INSTALL_DIR/run/gh-pr-watcher.pid" ] && kill "$(cat $INSTALL_DIR/run/gh-pr-watcher.pid)" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/gh-pr-watcher.py" 2>/dev/null || true
rm -f "$INSTALL_DIR/bin/gh-pr-watcher.py" "$INSTALL_DIR/run/gh-pr-watcher.pid" "$INSTALL_DIR/run/gh-pr-watcher.log" "$INSTALL_DIR/run/gh-pr-watcher-state.json"
rm -f "$HOME/.config/mypeople/gh-pr-watcher.env"
# To also drop the event archive: rm -rf ~/.gh-pr-watcher
```
