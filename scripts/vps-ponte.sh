#!/usr/bin/env bash
set -euo pipefail
CREW_HOME="${CREW_HOME:-$HOME/.local/share/crew}"
PONTE="$CREW_HOME/ponte"

mkdir -p "$PONTE"
cat > "$PONTE/herdr.new" <<'WRAPPER'
#!/usr/bin/env bash
REAL="${CREW_HOME:-$HOME/.local/share/crew}/bin/herdr"
session=default
if [ "${1:-}" = "--session" ]; then session="${2:-default}"; fi
case "$session" in
  crew) unit=crew-herdr ;;
  *) unit="crew-herdr-$session" ;;
esac
answers() { "$REAL" --session "$session" status server 2>/dev/null | grep -q 'status: running'; }
case "${3:-}" in
  remote-client-bridge|remote-api-bridge) ;;
  *) exec "$REAL" "$@" ;;
esac
case " $* " in
  *" --check "*) exec "$REAL" "$@" ;;
esac
if ! answers; then
  systemctl --user start "$unit.service" 2>/dev/null || true
  for _ in $(seq 1 30); do
    answers && break
    sleep 1
  done
fi
if ! answers; then
  echo "herdr: no server answers for session $session and $unit.service did not start one; not starting another" >&2
  exit 1
fi
exec "$REAL" "$@"
WRAPPER
chmod +x "$PONTE/herdr.new"
mv -f "$PONTE/herdr.new" "$PONTE/herdr"

if ! grep -q 'LC_CREW_PONTE' "$HOME/.bashrc"; then
  tmp="$(mktemp)"
  line="[ -n \"\${LC_CREW_PONTE:-}\" ] && export PATH=\"$PONTE:\$PATH\""
  LINE="$line" awk '/^case \$- in/ && !done { print ENVIRON["LINE"]; done = 1 } { print }' "$HOME/.bashrc" > "$tmp"
  grep -q 'LC_CREW_PONTE' "$tmp" || { echo "no interactive guard in ~/.bashrc to insert before" >&2; exit 1; }
  cat "$tmp" > "$HOME/.bashrc"
  rm -f "$tmp"
fi

echo "ponte: $PONTE/herdr"
