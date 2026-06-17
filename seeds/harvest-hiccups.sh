#!/usr/bin/env bash
# Rule 27 — systematic per-run hiccup harvest from in-container gen engineers.
# Usage: harvest-hiccups.sh <node1> [node2 ...]   (nodes = docker containers on $DOCKER_HOST)
# Pulls per node: Verify FAIL/retry lines, the gen agent's wiki, self-noted divergences.
# Appends a dated, triage-ready block to HICCUPS.md. Triage by hand → fold into the seed.
set -u
: "${DOCKER_HOST:=ssh://server}"; export DOCKER_HOST
LEDGER="$(cd "$(dirname "$0")" && pwd)/HICCUPS.md"
STAMP="${HARVEST_STAMP:-$(date -u +%Y-%m-%dT%H:%MZ 2>/dev/null || echo undated)}"
{
  echo; echo "## HARVEST $STAMP"
  for n in "$@"; do
    echo "### $n"
    docker exec "$n" bash -lc '
      echo "- verify FAIL/retry lines:";
      { grep -rhiE "FAIL|retry|missing|undefined|Traceback|Error" ~/mypeople/*.log 2>/dev/null | tail -8; } | sed "s/^/    /"
      echo "- gen agent wiki tail:";
      tail -12 ~/workspace/master-tmux/wiki/agents/*/*.md 2>/dev/null | sed "s/^/    /"
      echo "- self-noted divergences (NOTE:/HICCUP:/had to):";
      grep -rhiE "NOTE:|HICCUP:|had to|diverged|not in (the )?seed" ~/mypeople 2>/dev/null | grep -ivE "node_modules" | tail -8 | sed "s/^/    /"
    ' 2>/dev/null || echo "    (node unreachable)"
  done
  echo "_triage: fold each into the seed (cite §) or move to OPEN above._"
} >> "$LEDGER"
echo "appended HARVEST $STAMP for: $* → $LEDGER"
