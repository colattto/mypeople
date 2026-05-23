# Image Drag-and-Drop + `mp send-image` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow dragging screenshots/images into the ttyd browser terminal and add `mp send-image` CLI command for native-terminal workflows.

**Architecture:** queue-server gains two new routes (`GET /attach`, `POST /upload`) and two helpers (`_parse_multipart`, `_tmux_inject`). The `/attach` page wraps ttyd in an iframe and intercepts file drops via the pointer-events trick, uploading to `/upload` which saves the file and injects the path into the tmux pane. `mp send-image` copies the image to uploads dir and sends the path via the existing task queue. HUD "attach" links change from direct `:7681` URLs to `/attach?target=...`.

**Tech Stack:** Python 3.8+ stdlib only (no pip deps), vanilla JS (no frameworks), tmux send-keys, existing bracketed-paste logic.

---

## File Map

| File (inside `seeds/mypeople.seed.md`) | Changes |
|---|---|
| `queue-server.py` (embedded heredoc) | +2 helpers, +2 routes, +1 constant, modify imports and do_POST |
| `dashboard.html` (embedded heredoc) | change attach link URL pattern |
| `mp` CLI (embedded heredoc) | +1 command function, update COMMANDS dict |
| `## Verify` block | +3 assertions for new routes |

---

## Task 1: Add verification assertions first (TDD gate)

**Files:**
- Modify: `seeds/mypeople.seed.md` — `## Verify` section (after the last ttyd check, before end of block)

- [ ] **Step 1: Add `/attach` and `/upload` verify assertions to seed**

Find the line:
```bash
curl -fsS -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:${TTYD_PORT:-7681}/?arg=-t&arg=mc-main:Boss" | grep -q '^200$' || { echo "FAIL: ttyd attach-URL with args does not return 200"; exit 1; }
```

Add immediately after it:
```bash
# /attach wrapper page served by queue-server
curl -fsS "http://127.0.0.1:9900/attach?target=mc-main:Boss" | grep -q 'mypeople — terminal' || { echo "FAIL: /attach not serving wrapper page"; exit 1; }
curl -fsS "http://127.0.0.1:9900/attach?target=mc-main:Boss" | grep -q '__INJECT_SECRET__' && { echo "FAIL: /attach didn't inject secret"; exit 1; }
curl -fsS "http://127.0.0.1:9900/attach?target=mc-main:Boss" | grep -q 'pointer-events' || { echo "FAIL: /attach missing pointer-events drag fix"; exit 1; }

# /upload rejects missing secret
curl -fsS -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:9900/upload" | grep -q '401' || { echo "FAIL: /upload should 401 without secret"; exit 1; }

# dashboard attach links point to /attach (not direct :7681)
QUEUE_SECRET_VAL="$(grep ^QUEUE_SECRET= ~/.config/mypeople/queue.env | cut -d= -f2-)"
curl -fsS -H "X-Queue-Secret: $QUEUE_SECRET_VAL" "http://127.0.0.1:9900/dashboard" | grep -q '/attach?target=' || { echo "FAIL: dashboard attach links still point to :7681 instead of /attach"; exit 1; }

# mp send-image --help / usage
mp send-image 2>&1 | grep -q 'Usage: mp send-image' || { echo "FAIL: mp send-image missing usage"; exit 1; }
```

- [ ] **Step 2: Confirm assertions fail before implementation**

```bash
cd ~/code/mypeople
bash -c "$(sed -n '/## Verify/,/^```$/p' seeds/mypeople.seed.md | tail -n +3 | head -n -1)" 2>&1 | grep "FAIL: /attach\|FAIL: /upload\|FAIL: dashboard attach\|FAIL: mp send-image" | head -5
```
Expected: lines containing `FAIL: /attach`, `FAIL: /upload`, `FAIL: dashboard attach`, `FAIL: mp send-image`.

- [ ] **Step 3: Commit**

```bash
cd ~/code/mypeople
git add seeds/mypeople.seed.md
git commit -m "test: add verify assertions for /attach, /upload, send-image"
```

---

## Task 2: Add helpers and constants to queue-server

**Files:**
- Modify: `seeds/mypeople.seed.md` — queue-server.py heredoc (lines ~266–470)

- [ ] **Step 1: Add `subprocess` to queue-server imports**

Find:
```python
import http.server, json, os, sys, threading, time, uuid
```
Replace with:
```python
import http.server, json, os, subprocess, sys, threading, time, uuid
```

- [ ] **Step 2: Add `INSTALL_DIR` module-level constant**

Find in queue-server.py:
```python
SECRET = os.environ.get("QUEUE_SECRET", "")
```
Add after it:
```python
INSTALL_DIR = os.environ.get("INSTALL_DIR", os.path.expanduser("~/mypeople"))
```

- [ ] **Step 3: Add `_parse_multipart` helper**

Add after the `INSTALL_DIR` line (before `class Handler`):
```python
def _parse_multipart(content_type, body):
    """Parse multipart/form-data body. Returns dict of name -> (filename, bytes)."""
    if "boundary=" not in content_type:
        return {}
    boundary = content_type.split("boundary=", 1)[1].strip().encode()
    parts = {}
    for chunk in body.split(b"--" + boundary):
        if not chunk or chunk in (b"\r\n", b"--\r\n", b"--"):
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        sep = chunk.find(b"\r\n\r\n")
        if sep == -1:
            continue
        header_raw = chunk[:sep].decode("utf-8", errors="replace")
        data = chunk[sep + 4:]
        if data.endswith(b"\r\n"):
            data = data[:-2]
        name = filename = None
        for line in header_raw.splitlines():
            if line.lower().startswith("content-disposition:"):
                for part in line.split(";"):
                    part = part.strip()
                    if part.startswith("name="):
                        name = part[5:].strip('"')
                    elif part.startswith("filename="):
                        filename = part[9:].strip('"')
        if name:
            parts[name] = (filename, data)
    return parts
```

- [ ] **Step 4: Add `_tmux_inject` helper**

Add after `_parse_multipart`:
```python
def _tmux_inject(target, text):
    """Inject text into a tmux pane via bracketed paste, exiting copy-mode first.

    Mirrors tmux_send_text in queue-client — kept in sync manually.
    Called directly by the /upload handler (no queue roundtrip needed
    since queue-server is always co-located with tmux on the same host).
    """
    PASTE_START = "\x1b[?2004h\x1b[200~"
    PASTE_END   = "\x1b[201~\x1b[?2004l"
    def _run(*args):
        return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=5)
    r = _run("display-message", "-t", target, "-p", "#{pane_in_mode}")
    if r.returncode == 0 and r.stdout.strip() == "1":
        _run("send-keys", "-t", target, "-X", "cancel")
        time.sleep(0.1)
    safe = text.replace(PASTE_END, "").replace(PASTE_START, "")
    payload = f"{PASTE_START}{safe}{PASTE_END}"
    r = _run("send-keys", "-t", target, "-l", "--", payload)
    if r.returncode != 0:
        return False, r.stderr.strip()
    time.sleep(0.1)
    r = _run("send-keys", "-t", target, "Enter")
    if r.returncode != 0:
        return False, r.stderr.strip()
    return True, ""
```

- [ ] **Step 5: Add `ATTACH_HTML_TEMPLATE` constant**

Add after `_tmux_inject` (before `class Handler`):
```python
ATTACH_HTML_TEMPLATE = """\
<!doctype html>
<html><head><meta charset="utf-8">
<title>__INJECT_TARGET__ — mypeople terminal</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { width:100vw; height:100vh; overflow:hidden; background:#000; }
iframe { width:100%; height:100%; border:none; display:block; }
#drop-ol {
  display:none; position:fixed; inset:0;
  background:rgba(31,111,235,0.18); border:3px dashed #1f6feb;
  z-index:1000; align-items:center; justify-content:center;
  font:bold 22px system-ui; color:#1f6feb; pointer-events:none;
}
#drop-ol.on { display:flex; }
#toast {
  display:none; position:fixed; bottom:16px; right:16px;
  padding:10px 16px; border-radius:6px; font:14px system-ui;
  color:#fff; z-index:2000;
}
</style></head>
<body>
<div id="drop-ol">📎 Solte a imagem aqui</div>
<div id="toast"></div>
<iframe id="term"></iframe>
<script>
const SECRET  = "__INJECT_SECRET__";
const TARGET  = "__INJECT_TARGET__";
const TPORT   = "__INJECT_TTYD_PORT__";
const iframe  = document.getElementById('term');
const overlay = document.getElementById('drop-ol');
const toast   = document.getElementById('toast');
// Set iframe src via JS so we can use location.hostname at runtime.
iframe.src = `http://${location.hostname}:${TPORT}/?arg=-t&arg=${encodeURIComponent(TARGET)}`;

function showToast(msg, err) {
  toast.textContent = msg;
  toast.style.background = err ? '#a52a2a' : '#1e6e2c';
  toast.style.display = 'block';
  setTimeout(() => { toast.style.display = 'none'; }, 3500);
}

// Pointer-events trick: disabling pointer events on the cross-origin
// iframe routes dragover/drop to the parent document, which can then
// call preventDefault() to own the drop (instead of the browser
// navigating the tab to the dropped file).
let dragDepth = 0;
document.addEventListener('dragenter', e => {
  if (!(e.dataTransfer && e.dataTransfer.types.includes('Files'))) return;
  if (++dragDepth === 1) { iframe.style.pointerEvents = 'none'; overlay.classList.add('on'); }
});
document.addEventListener('dragleave', e => {
  if (!(e.dataTransfer && e.dataTransfer.types.includes('Files'))) return;
  if (--dragDepth <= 0) { dragDepth = 0; iframe.style.pointerEvents = ''; overlay.classList.remove('on'); }
});
document.addEventListener('dragover', e => {
  if (e.dataTransfer && e.dataTransfer.types.includes('Files')) {
    e.preventDefault(); e.dataTransfer.dropEffect = 'copy';
  }
});
document.addEventListener('drop', async e => {
  e.preventDefault();
  dragDepth = 0; iframe.style.pointerEvents = ''; overlay.classList.remove('on');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  if (!file.type.startsWith('image/')) { showToast('Apenas imagens suportadas', true); return; }
  const fd = new FormData(); fd.append('file', file); fd.append('target', TARGET);
  try {
    const r = await fetch('/upload', { method:'POST', headers:{'X-Queue-Secret': SECRET}, body: fd });
    const j = await r.json();
    if (j.ok) showToast(`📎 ${j.path.split('/').pop()} enviado`, false);
    else showToast('Erro: ' + (j.error || '?'), true);
  } catch(err) { showToast('Falha no upload: ' + err.message, true); }
});
</script>
</body></html>
"""
```

- [ ] **Step 6: Commit**

```bash
cd ~/code/mypeople
git add seeds/mypeople.seed.md
git commit -m "feat(queue-server): add _parse_multipart, _tmux_inject, ATTACH_HTML_TEMPLATE"
```

---

## Task 3: Add `GET /attach` and `POST /upload` routes to queue-server

**Files:**
- Modify: `seeds/mypeople.seed.md` — queue-server.py `do_GET` and `do_POST`

- [ ] **Step 1: Add `GET /attach` handler**

In `do_GET`, find:
```python
        if p == "/dashboard":
```
Add before it:
```python
        if p == "/attach":
            qs = parse_qs(u.query)
            target = qs.get("target", [""])[0]
            if not target:
                return self._json(400, {"error": "target required"})
            ttyd_port = os.environ.get("TTYD_PORT", "7681")
            html = (ATTACH_HTML_TEMPLATE
                    .replace("__INJECT_SECRET__", SECRET)
                    .replace("__INJECT_TTYD_PORT__", ttyd_port)
                    .replace("__INJECT_TARGET__", target))
            data = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
```

Note: `/attach` is PUBLIC (no secret check) — same as `/dashboard`. The secret is injected into the HTML so the in-page fetch calls to `/upload` can authenticate.

- [ ] **Step 2: Add `POST /upload` handler**

In `do_POST`, find:
```python
    def do_POST(self):
        if not self._ok_secret():
            return self._json(401, {"error": "unauthorized"})
        u = urlparse(self.path)
        p = u.path
        data = self._read_json()
        if data is None:
            return self._json(400, {"error": "bad json"})
```
Replace with:
```python
    def do_POST(self):
        if not self._ok_secret():
            return self._json(401, {"error": "unauthorized"})
        u = urlparse(self.path)
        p = u.path

        if p == "/upload":
            ct = self.headers.get("Content-Type", "")
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length)
            fields = _parse_multipart(ct, body)
            file_entry   = fields.get("file")
            target_entry = fields.get("target")
            if not file_entry or not target_entry:
                return self._json(400, {"error": "file and target fields required"})
            filename, file_bytes = file_entry
            _, target_bytes = target_entry
            target_str = target_bytes.decode("utf-8", errors="replace").strip()
            ext = os.path.splitext(filename or "")[1] or ".png"
            upload_dir = os.path.join(INSTALL_DIR, "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            save_path = os.path.join(upload_dir, f"{uuid.uuid4().hex}{ext}")
            with open(save_path, "wb") as fh:
                fh.write(file_bytes)
            ok, err = _tmux_inject(target_str, save_path)
            if ok:
                return self._json(200, {"ok": True, "path": save_path})
            return self._json(500, {"ok": False, "error": err})

        data = self._read_json()
        if data is None:
            return self._json(400, {"error": "bad json"})
```

- [ ] **Step 3: Commit**

```bash
cd ~/code/mypeople
git add seeds/mypeople.seed.md
git commit -m "feat(queue-server): add GET /attach wrapper and POST /upload endpoints"
```

---

## Task 4: Update dashboard.html attach links

**Files:**
- Modify: `seeds/mypeople.seed.md` — `dashboard.html` heredoc

- [ ] **Step 1: Change attach URL pattern**

Find in `dashboard.html`:
```javascript
      const url = `http://${ttydHost}:7681/?arg=-t&arg=${encodeURIComponent(target)}`;
```
Replace with:
```javascript
      const url = `/attach?target=${encodeURIComponent(target)}`;
```

The URL is now relative (same origin, port 9900) so it works through Tailscale without hardcoding the port.

- [ ] **Step 2: Remove unused `ttydHost` variable**

Find:
```javascript
    const ttydHost = location.hostname || '127.0.0.1';
    const rows = a.map(x => {
```
Replace with:
```javascript
    const rows = a.map(x => {
```

- [ ] **Step 3: Commit**

```bash
cd ~/code/mypeople
git add seeds/mypeople.seed.md
git commit -m "feat(dashboard): attach links use /attach wrapper instead of direct :7681"
```

---

## Task 5: Add `mp send-image` command

**Files:**
- Modify: `seeds/mypeople.seed.md` — mp CLI heredoc

- [ ] **Step 1: Add `cmd_send_image` function**

Find in mp CLI:
```python
def cmd_upgrade_config(cfg, args):
```
Add before it:
```python
def cmd_send_image(cfg, args):
    """Copy a local image to ~/mypeople/uploads/ and send its path to an agent.

    The path is typed into the agent's pane via tmux bracketed-paste, where
    Claude Code reads it as an image attachment — identical to dragging a
    file into a native terminal session.

    Usage: mp send-image <agent_id> <image_path>
    """
    if len(args) < 2:
        print("Usage: mp send-image <agent_id> <image_path>", file=sys.stderr)
        sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    src = os.path.expanduser(args[1])
    if not os.path.isfile(src):
        print(f"File not found: {src}", file=sys.stderr)
        sys.exit(1)
    import shutil, uuid as _uuid
    install_dir = os.path.expanduser(cfg.get("INSTALL_DIR", "~/mypeople"))
    upload_dir = os.path.join(install_dir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(src)[1] or ".png"
    dst = os.path.join(upload_dir, f"{_uuid.uuid4().hex}{ext}")
    shutil.copy2(src, dst)
    body = {"action": "send", "target_agent": aid, "payload": {"message": dst}}
    t = submit_and_wait(cfg, body, timeout=10)
    if t["status"] == "done":
        print(f"Image sent to {aid}: {dst}")
    else:
        print(f"Send FAILED: {t.get('error', '?')}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 2: Add to COMMANDS dict**

Find:
```python
COMMANDS = {"status": cmd_status, "spawn": cmd_spawn, "send": cmd_send, "peek": cmd_peek, "kill": cmd_kill, "upgrade-config": cmd_upgrade_config}
```
Replace with:
```python
COMMANDS = {"status": cmd_status, "spawn": cmd_spawn, "send": cmd_send, "peek": cmd_peek, "kill": cmd_kill, "upgrade-config": cmd_upgrade_config, "send-image": cmd_send_image}
```

- [ ] **Step 3: Commit**

```bash
cd ~/code/mypeople
git add seeds/mypeople.seed.md
git commit -m "feat(mp): add send-image command"
```

---

## Task 6: Apply changes to locally installed files + smoke test

**Files:**
- Modify: `~/mypeople/bin/queue-server.py` (installed file, same changes as seed)
- Modify: `~/mypeople/bin/dashboard.html` (installed file, same changes as seed)
- Modify: `~/mypeople/bin/mp` (installed file, same changes as seed)

- [ ] **Step 1: Apply queue-server changes to installed file**

```bash
# Restart queue-server after patching
kill "$(cat ~/mypeople/run/queue-server.pid)" 2>/dev/null || true
# (apply the same edits from Tasks 2-3 to ~/mypeople/bin/queue-server.py)
# Then restart:
set -a; . ~/.config/mypeople/queue.env; set +a
nohup python3 -u ~/mypeople/bin/queue-server.py > ~/mypeople/run/queue-server.log 2>&1 &
echo $! > ~/mypeople/run/queue-server.pid
sleep 1 && curl -fsS http://127.0.0.1:9900/health
```
Expected: `{"status": "ok", ...}`

- [ ] **Step 2: Apply dashboard.html changes**

```bash
# (apply the same edit from Task 4 to ~/mypeople/bin/dashboard.html)
curl -fsS http://127.0.0.1:9900/dashboard | grep '/attach?target='
```
Expected: output contains `/attach?target=`

- [ ] **Step 3: Apply mp changes**

```bash
# (apply the same edits from Task 5 to ~/mypeople/bin/mp)
mp send-image 2>&1
```
Expected: `Usage: mp send-image <agent_id> <image_path>`

- [ ] **Step 4: Smoke test `/attach`**

```bash
curl -fsS "http://127.0.0.1:9900/attach?target=mc-main:Boss" | grep -E "mypeople — terminal|pointer-events|drop-ol"
```
Expected: 3 matching lines.

- [ ] **Step 5: Smoke test `/upload` auth**

```bash
curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:9900/upload
```
Expected: `401`

- [ ] **Step 6: Smoke test full drag flow (manual)**

1. Open `http://localhost:9900/dashboard` in browser
2. Click "attach" on any alive agent — should open `/attach?target=...` page (not `:7681`)
3. Take a screenshot (Cmd+Shift+4 on macOS)
4. Drag the screenshot PNG from Desktop into the browser terminal
5. Blue dashed overlay should appear
6. On drop: toast "📎 <filename> enviado" appears
7. Agent pane receives the file path typed in

- [ ] **Step 7: Final commit**

```bash
cd ~/code/mypeople
git add seeds/mypeople.seed.md
git commit -m "chore: all image drop + send-image changes complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ Drag image into ttyd browser terminal → pointer-events trick intercepts → upload → inject path
- ✅ `mp send-image` for native terminal / CLI workflow
- ✅ HUD attach links updated to use wrapper
- ✅ Verify assertions added for both features

**Placeholder scan:** None found.

**Type consistency:**
- `_parse_multipart(ct, body)` → returns `dict[str, tuple[str|None, bytes]]` — used correctly in `/upload` handler
- `_tmux_inject(target, text)` → returns `(bool, str)` — matched in caller `ok, err = _tmux_inject(...)`
- `ATTACH_HTML_TEMPLATE` uses three placeholders: `__INJECT_SECRET__`, `__INJECT_TTYD_PORT__`, `__INJECT_TARGET__` — all replaced in `GET /attach` handler ✅
- `cmd_send_image` uses `canonicalize_agent_id`, `submit_and_wait`, `cfg["HOST_ID"]`, `cfg["INSTALL_DIR"]` — all available in mp CLI context ✅
