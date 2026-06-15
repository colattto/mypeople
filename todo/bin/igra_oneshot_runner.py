#!/usr/bin/env python3
"""Faithful one-shot installer/verifier for the Instagram Reply Automation seed.

Extracts the fenced ```bash blocks under '## Step 0', '## Step 1' and '## Verify'
from the seed markdown and runs them in order, exactly as a human pasting the seed
would. No mocks: Verify spawns/reuses a REAL MyPeople worker via the real mp queue.
"""
import re, subprocess, sys, os

SEED = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/igra.seed.md")
WANT = ("## Step 0", "## Step 1", "## Verify")

text = open(SEED).read()
# split into sections by '## ' headings
parts = re.split(r"(?m)^(## .*)$", text)
# parts: [pre, head1, body1, head2, body2, ...]
sections = {}
for i in range(1, len(parts), 2):
    sections[parts[i].strip()] = parts[i + 1]

def bash_blocks(body):
    return re.findall(r"```bash\n(.*?)```", body, re.S)

# Concatenate every block into ONE shell session, exactly as a human pasting
# the seed into a single terminal would — so exports persist across steps.
combined = []
for head in WANT:
    match = next((h for h in sections if h.startswith(head)), None)
    if not match:
        print(f"SEED_PARSE_ERROR missing {head}", flush=True)
        sys.exit(3)
    blocks = bash_blocks(sections[match])
    if not blocks:
        print(f"SEED_PARSE_ERROR no bash in {head}", flush=True)
        sys.exit(3)
    for b in blocks:
        combined.append(f'\necho "========== RUN {match} =========="\n')
        combined.append(b)

script = "set -e\n" + "".join(combined) + '\necho "ONE_SHOT_COMPLETE"\n'
r = subprocess.run(["bash", "-c", script])
sys.exit(r.returncode)
