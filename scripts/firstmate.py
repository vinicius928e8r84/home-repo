import json
import shlex
import shutil
import subprocess
import sys
import uuid

HOST = "main-vps-factory"
INBOX = "FM_HOME=/home/factory/firstmate /home/factory/firstmate/bin/fm-inbox.sh"
TAG = "[home-repo] "
USO = """firstmate: talk to the firstmate on the main VPS from the Home Repo.

The firstmate is the supervisor that runs the PerpetualMiner and Nova-AI fleet
on the VPS. This script reaches its captain inbox over SSH (through WSL, which
already holds the key `main-vps-factory`). It never changes anything on the VPS
except adding a note.

  python scripts/firstmate.py ready                 is the firstmate up and listening?
  python scripts/firstmate.py note "text"           send a note; prints its id
  python scripts/firstmate.py replies [--all]       our notes and the answers (--all: every inbox note)
  python scripts/firstmate.py status                what the fleet is doing (read-only)

A note arrives in the firstmate's session as a wake. It is tagged
"[home-repo]", so the firstmate reads it as coming from this agent, not as an
order typed by the owner: an order that needs the owner's word still needs it.
The firstmate answers with `fm-inbox.sh reply`; read it with `replies`.
Every command prints the VPS output as is and exits with its exit code."""


def ssh_cmd():
    if sys.platform == "win32":
        return ["wsl.exe", "-e", "ssh"]
    return [shutil.which("ssh") or "ssh"]


def call(remote, stdin=None):
    cmd = ssh_cmd() + ["-o", "ConnectTimeout=8", "-o", "BatchMode=yes", HOST, remote]
    data = stdin.encode("utf-8") if stdin is not None else None
    try:
        out = subprocess.run(cmd, input=data, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return 1, "", "error: the VPS did not answer in 60 s\n"
    return out.returncode, out.stdout.decode("utf-8", "replace"), out.stderr.decode("utf-8", "replace")


def run(remote, stdin=None):
    rc, out, err = call(remote, stdin)
    sys.stdout.write(out)
    sys.stderr.write(err)
    return rc


def replies(show_all):
    rc, out, err = call(INBOX + " receipts --all-handled --all-pending --all-replies")
    if rc != 0:
        sys.stderr.write(err)
        return rc
    data = json.loads(out)
    notes = [(n, "respondida" if n.get("reply") else "lida") for n in data.get("handled", [])]
    notes += [(n, "esperando") for n in data.get("pending", [])]
    notes = [x for x in notes if show_all or x[0].get("body", "").startswith(TAG)]
    notes.sort(key=lambda x: x[0].get("at", ""))
    for n, state in notes:
        print("%s  %s  %s" % (n.get("at", ""), state, n.get("body", "").strip()[:200]))
        if n.get("reply"):
            print("    -> " + n["reply"].get("body", "").strip())
    return 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USO)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "ready":
        return run(INBOX + " ready")
    if cmd == "status":
        return run(INBOX + " status")
    if cmd == "replies":
        return replies("--all" in rest)
    if cmd == "note":
        text = " ".join(rest).strip()
        if not text:
            sys.stderr.write("error: note needs text\n")
            return 2
        rid = "home-repo-" + uuid.uuid4().hex[:12]
        return run(INBOX + " note --request-id " + shlex.quote(rid) + " -", stdin=TAG + text + "\n")
    sys.stderr.write("error: unknown command %r (see --help)\n" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
