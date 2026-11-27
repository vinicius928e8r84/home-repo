#!/usr/bin/env bash
set -euo pipefail
HERDR_VERSION="${HERDR_VERSION:-0.9.5}"
PI_VERSION="${PI_VERSION:-1.6.0}"
SESSION="${CREW_REMOTE_SESSION:-crew}"
CREW_HOME="${CREW_HOME:-$HOME/.local/share/crew}"
HERDR="$CREW_HOME/bin/herdr"
PI="$CREW_HOME/bin/pi"
PI_AGENT_DIR="$CREW_HOME/pi-agent"
STATE_DIR="${CREW_REMOTE_DIR:-$HOME/crew-state}"
GH_OWNER="${GH_OWNER:-vinicius928e8r84}"
MODEL="${MODEL:-claude-bridge/claude-sonnet-5-5}"
export PATH="$CREW_HOME/bin:$HOME/.local/bin:/opt/factory/toolchain/bin:$PATH"

step() { printf '\n== %s\n' "$*"; }

step "directories"
mkdir -p "$CREW_HOME/bin" "$PI_AGENT_DIR" "$STATE_DIR" "$HOME/worktrees" "$HOME/.config/systemd/user"

step "herdr $HERDR_VERSION in $HERDR"
if [ "$("$HERDR" --version 2>/dev/null || true)" = "herdr $HERDR_VERSION" ]; then
  echo "already there"
else
  case "$(uname -m)" in x86_64) asset=linux-x86_64 ;; aarch64) asset=linux-aarch64 ;; *) echo "no herdr build for $(uname -m)" >&2; exit 1 ;; esac
  tmp="$(mktemp -d)"
  curl -fsSL https://herdr.dev/latest.json -o "$tmp/latest.json"
  read -r url sum < <(python3 - "$tmp/latest.json" "$HERDR_VERSION" "$asset" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
rel = data["releases"][sys.argv[2]]
print(rel["assets"][sys.argv[3]], rel.get("sha256", {}).get(sys.argv[3]) or data["sha256"][sys.argv[3]])
PY
)
  curl -fsSL "$url" -o "$tmp/herdr"
  echo "$sum  $tmp/herdr" | sha256sum -c -
  chmod +x "$tmp/herdr"
  mv -f "$tmp/herdr" "$HERDR.new" && mv -f "$HERDR.new" "$HERDR"
  rm -rf "$tmp"
fi
"$HERDR" --version

step "herdr does not restore agents (the spawn command is the one way back; this holds for every herdr session here)"
python3 - "${HERDR_CONFIG_PATH:-$HOME/.config/herdr/config.toml}" <<'PY'
import os, re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
line = "resume_agents_on_restore = false"
if re.search(r"(?m)^resume_agents_on_restore\s*=", text):
    text = re.sub(r"(?m)^resume_agents_on_restore\s*=.*$", line, text)
elif re.search(r"(?m)^\[session\]\s*$", text):
    text = re.sub(r"(?m)^\[session\]\s*$", "[session]\n" + line, text, count=1)
else:
    text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + "[session]\n" + line + "\n"
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as f:
    f.write(text)
PY
"$HERDR" config check

step "systemd user service crew-herdr (session $SESSION)"
cat > "$CREW_HOME/bin/crew-herdr-run" <<'EOF'
#!/usr/bin/env bash
herdr="$1"
session="$2"
told=0
while "$herdr" --session "$session" status server 2>/dev/null | grep -q 'status: running'; do
  [ "$told" = 1 ] || echo "herdr session $session is served from outside this unit; waiting for it to stop"
  told=1
  sleep 5
done
exec "$herdr" --session "$session" server
EOF
chmod +x "$CREW_HOME/bin/crew-herdr-run"
cat > "$HOME/.config/systemd/user/crew-herdr.service" <<EOF
[Unit]
Description=Herdr headless server for crew workers (session $SESSION)

[Service]
Type=simple
Environment=PATH=$CREW_HOME/bin:$HOME/.local/bin:/opt/factory/toolchain/bin:/usr/local/bin:/usr/bin:/bin
Environment=HERDR_SESSION=$SESSION
WorkingDirectory=$HOME
ExecStart=$CREW_HOME/bin/crew-herdr-run $HERDR $SESSION
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable crew-herdr.service
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]; then
  loginctl enable-linger "$USER" || echo "WARNING: could not enable linger; the server will stop when the last login ends" >&2
fi
systemctl --user start crew-herdr.service
for _ in $(seq 1 20); do
  "$HERDR" --session "$SESSION" status server 2>/dev/null | grep -q 'status: running' && break
  sleep 1
done
"$HERDR" --session "$SESSION" status server

step "pi $PI_VERSION for crew, agent directory $PI_AGENT_DIR"
if [ "$("$CREW_HOME/pi/node_modules/.bin/pi" --version 2>/dev/null | tail -1 || true)" = "$PI_VERSION" ]; then
  echo "already there"
else
  mkdir -p "$CREW_HOME/pi"
  npm install --silent --no-audit --no-fund --prefix "$CREW_HOME/pi" "@earendil-works/pi-coding-agent@$PI_VERSION" </dev/null
fi
printf '%s\n' '#!/usr/bin/env bash' \
  "export PI_CODING_AGENT_DIR=\"$PI_AGENT_DIR\"" \
  "export PATH=\"$CREW_HOME/bin:$HOME/.local/bin:/opt/factory/toolchain/bin:\$PATH\"" \
  "exec \"$CREW_HOME/pi/node_modules/.bin/pi\" \"\$@\"" > "$PI"
chmod +x "$PI"
"$PI" --version | tail -1

step "herdr integration for pi (in $PI_AGENT_DIR/extensions)"
PI_CODING_AGENT_DIR="$PI_AGENT_DIR" "$HERDR" integration install pi
PI_CODING_AGENT_DIR="$PI_AGENT_DIR" "$HERDR" integration status | grep -E '^pi:'

step "pi-claude-bridge"
if grep -q 'pi-claude-bridge' "$PI_AGENT_DIR/settings.json" 2>/dev/null; then
  echo "already in settings"
else
  "$PI" install npm:pi-claude-bridge </dev/null
fi
"$PI" list </dev/null

step "repos from repos.json"
clone_or_fetch() {
  local dir="$1" name="$2"
  if [ -d "$dir/.git" ]; then
    git -C "$dir" fetch --quiet origin && echo "$dir: already cloned, fetched"
  else
    git clone --quiet "https://github.com/$GH_OWNER/$name" "$dir" </dev/null && echo "$dir: cloned"
  fi
}
clone_or_fetch "$HOME/home-repo" home-repo
clone_or_fetch "$HOME/Nova-AI" Nova-AI
clone_or_fetch "$HOME/PerpetualMiner" PerpetualMiner

step "herdr bridge for the PC machine (scripts/vps-ponte.sh from origin/main)"
git -C "$HOME/home-repo" show origin/main:scripts/vps-ponte.sh | CREW_HOME="$CREW_HOME" bash

step "pi answers through $MODEL"
reply="$(cd "$HOME" && timeout 180 "$PI" --model "$MODEL" -p 'Reply with exactly the word: pong' </dev/null 2>&1 | tail -5)"
echo "$reply"
if ! printf '%s' "$reply" | grep -qi pong; then
  echo "FAILED: pi did not answer through $MODEL" >&2
  exit 1
fi

step "done"
echo "crew session: $HERDR --session $SESSION"
