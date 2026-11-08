#!/usr/bin/env bash
# Commit state.json to the `state` branch using a separate worktree, so the
# running checkout is never touched. Safe to call repeatedly.
set -euo pipefail

SRC="${1:-state.json}"
[ -f "$SRC" ] || exit 0
SRC="$(cd "$(dirname "$SRC")" && pwd)/$(basename "$SRC")"

WT="${RUNNER_TEMP:-/tmp}/state-worktree"
git config user.name "quarterly-bot"
git config user.email "quarterly-bot@users.noreply.github.com"

rm -rf "$WT"
git worktree prune
if git fetch -q origin state 2>/dev/null; then
  git worktree add -q -B state "$WT" FETCH_HEAD
else
  git worktree add -q --detach "$WT"
  git -C "$WT" checkout -q --orphan state
  git -C "$WT" rm -rfq . || true
fi

cp "$SRC" "$WT/state.json"
git -C "$WT" add state.json
if git -C "$WT" diff --cached --quiet; then
  echo "State unchanged"
else
  git -C "$WT" commit -qm "state: $(date -u +%FT%TZ)"
  git -C "$WT" push -q origin state
  echo "State saved"
fi

git worktree remove --force "$WT"
