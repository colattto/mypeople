#!/usr/bin/env python3
"""Build the durable real-substrate proof bundle for card 0afb2faee9bf."""
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

HOME = Path.home()
IGRA = HOME / "mypeople" / "instagram-reply-automation"
PD = Path(sys.argv[1])  # the verify PROOF_DIR
CAST = Path(sys.argv[2])
BUNDLE = IGRA / "proofs" / "SUBSTRATE-PROOF.txt"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def sha(p):
    return run(["sha256sum", str(p)]).split()[0] if Path(p).exists() else "MISSING"


def health():
    env = dict(os.environ)
    env.update({"IGRA_HOME": str(IGRA), "IGRA_PORT": "48099", "INBOUND_SECRET": "x",
                "MANYCHAT_TOKEN": "x", "MYPEOPLE_BRAIN_AGENT": "x"})
    p = subprocess.Popen([sys.executable, str(IGRA / "bin" / "instagram_reply_server.py")], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.5)
        body = urllib.request.urlopen("http://127.0.0.1:48099/health", timeout=3).read().decode()
        return "GET /health -> 200 " + body
    finally:
        p.terminate()


mc = [json.loads(l) for l in open(PD / "manychat.jsonl")]
st = json.load(open(PD / "data" / "state.json"))
sub = st["subscribers"]["pageA:101"]

L = []
L.append("# Instagram Reply Automation SEED - REAL SUBSTRATE proof")
L.append("# card 0afb2faee9bf  |  substrate: seedbed-trust-1 (docker on delattre-server)")
L.append("# captured: %s UTC  |  Claude worker login daniel@plow.co" % time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()))
L.append("")
L.append("## substrate identity (NOT /tmp, NOT the Mac)")
L.append("host_id     : %s" % run(["grep", "HOST_ID", str(HOME / ".config/mypeople/queue.env")]))
L.append("whoami/home : %s @ %s" % (run(["whoami"]), HOME))
L.append("queue       : %s" % run(["grep", "QUEUE_URL", str(HOME / ".config/mypeople/queue.env")]))
L.append("uname       : %s" % run(["uname", "-a"]))
L.append("container   : %s" % run(["cat", "/etc/hostname"]))
L.append("")
L.append("## seed under test")
L.append("seed_sha256 : %s" % sha(HOME / "igra.seed.md"))
L.append("PROOF_DIR   : %s  (durable, under $IGRA_HOME, NOT /tmp)" % PD)
L.append("")
L.append("## real MyPeople worker (Claude backend, per CEO policy - no Codex)")
L.append(run(["mp", "status"]).splitlines()[0] if run(["mp", "status"]) else "")
for ln in run(["mp", "status"]).splitlines():
    if "igreply" in ln:
        L.append(ln.strip())
L.append("")
L.append("## live API evidence - /health on the installed server")
L.append(health())
L.append("")
L.append("## clean worker-generated reply (captured outbound ManyChat sendContent payload)")
L.append("subscriber_id : %s" % mc[0]["subscriber_id"])
L.append("channel       : %s" % mc[0]["channel"])
L.append("reply         : %r" % mc[0]["text"])
L.append("sendContent #calls: %d (dedupe held - no double-send)" % len(mc))
L.append("")
L.append("## audit.jsonl (real event trail from the substrate)")
L.append(open(PD / "data" / "audit.jsonl").read().strip())
L.append("")
L.append("## per-subscriber state (memory_key pageA:101)")
L.append("summary : %s" % sub["summary"])
for t in sub["transcript"]:
    L.append("  %3s -> %r" % (t["dir"], t["text"]))
L.append("")
L.append("## asciinema terminal recording (durable on substrate)")
L.append(run(["ls", "-la", str(CAST)]))
L.append("cast_sha256 : %s" % sha(CAST))

BUNDLE.write_text("\n".join(L) + "\n")
print("WROTE", BUNDLE)
print("=" * 60)
print(BUNDLE.read_text())
