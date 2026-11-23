#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
WIZARD="$SKILL_DIR/scripts/register-vps.sh"

if [[ "${HERDR_ENV:-}" != 1 ]]; then
  printf 'Run this command in a human-controlled terminal:\n  %q\n' "$WIZARD"
  exit 2
fi

command -v herdr >/dev/null 2>&1 || {
  printf 'Herdr is active but its CLI is unavailable. Run manually: %s\n' "$WIZARD" >&2
  exit 1
}
command -v jq >/dev/null 2>&1 || {
  printf 'jq is required to open the aaPanel registration tab.\n' >&2
  exit 1
}

response=$(herdr tab create \
  --workspace "$HERDR_WORKSPACE_ID" \
  --cwd "$HOME" \
  --label "Cadastrar VPS aaPanel" \
  --focus)
pane_id=$(jq -er '.result.root_pane.pane_id' <<<"$response")
quoted_wizard=$(printf '%q' "$WIZARD")
herdr pane run "$pane_id" "$quoted_wizard"
printf 'Opened aaPanel registration wizard in Herdr pane %s.\n' "$pane_id"
