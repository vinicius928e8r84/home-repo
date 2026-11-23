"""Check model_routing.json against the models this machine's Pi can reach.

Usage: python -I scripts/check_routing.py
Exit 0 when every route names a model Pi lists and a valid thinking level; 1 otherwise.
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEVELS = {"off", "minimal", "low", "medium", "high", "xhigh", "max"}


def pi_models():
    pi = shutil.which("pi")
    if not pi:
        sys.exit("error: `pi` is not on PATH")
    out = subprocess.run([pi, "--list-models"], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        sys.exit("error: `pi --list-models` failed: " + out.stderr.strip())
    models = {}
    for line in out.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3:
            models[parts[0] + "/" + parts[1]] = parts[2]
    return models


def main():
    cfg = json.load(open(os.path.join(ROOT, "model_routing.json"), encoding="utf-8"))
    routes = cfg.get("routes", {})
    models = pi_models()
    bad = []
    if cfg.get("default") not in routes:
        bad.append("default %r is not a route" % cfg.get("default"))
    for task, route in routes.items():
        model, level = route.get("model"), route.get("thinking")
        if model not in models:
            bad.append("%s: model %r is not in `pi --list-models`" % (task, model))
        if level not in LEVELS:
            bad.append("%s: thinking %r is not one of %s" % (task, level, sorted(LEVELS)))
        if not bad or not bad[-1].startswith(task + ":"):
            print("ok    %-12s %s:%s (context %s)" % (task, model, level, models.get(model)))
    for line in bad:
        print("FAIL  " + line)
    sys.exit(1 if bad else 0)


main()
