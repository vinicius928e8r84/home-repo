#!/usr/bin/env python3
"""Cloudflare Registrar and DNS helper for the buy-domain skill. Standard library only.

  cf_domain.py search "<words>"            candidate names with cached prices (discovery only)
  cf_domain.py check <domain>...           live availability and price (the price to show the captain)
  cf_domain.py buy <domain> --price X.XX   register; refuses unless X.XX equals the live price right now
  cf_domain.py status <domain>             registration state after a buy
  cf_domain.py dns <domain> <ip>           upsert proxied A records for @ and www, idempotent
  cf_domain.py txt <domain> <value>        upsert a TXT record on the apex (Google Search Console and similar ownership checks)
  cf_domain.py verify <domain> [path...]   HTTP and certificate probe from outside (default path /)

Token: CF_API_TOKEN in ~/.config/firstmate-secrets/cloudflare.env (mode 600), never printed.
"""
import json, os, ssl, subprocess, sys, urllib.request, urllib.error, urllib.parse

ENV = os.path.expanduser("~/.config/firstmate-secrets/cloudflare.env")
API = "https://api.cloudflare.com/client/v4"


def token():
    for line in open(ENV):
        k, _, v = line.strip().partition("=")
        if k in ("CF_API_TOKEN", "export CF_API_TOKEN"):
            return v.strip().strip("'\"")
    sys.exit("CF_API_TOKEN missing in " + ENV)


def call(method, path, body=None, headers=None):
    h = {"Authorization": "Bearer " + token(), "Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(API + path, method=method, headers=h,
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"success": False, "errors": [{"message": "HTTP %d" % e.code}]}


def account():
    s, d = call("GET", "/zones?per_page=1")
    if s == 200 and d.get("result"):
        return d["result"][0]["account"]["id"]
    s, d = call("GET", "/accounts?per_page=1")
    if s == 200 and d.get("result"):
        return d["result"][0]["id"]
    sys.exit("cannot find the account id: " + json.dumps(d.get("errors")))


def zone(domain):
    s, d = call("GET", "/zones?name=" + domain)
    if s != 200 or not d.get("result"):
        sys.exit("no Cloudflare zone for %s (%s). For a domain bought elsewhere, add it in the Cloudflare dashboard and point the registrar's nameservers to Cloudflare." % (domain, json.dumps(d.get("errors"))))
    return d["result"][0]["id"]


def live_price(domain):
    s, d = call("POST", "/accounts/%s/registrar/domain-check" % account(), {"domains": [domain]})
    if s != 200 or not d.get("success"):
        sys.exit("check failed: " + json.dumps(d.get("errors")))
    return d["result"]["domains"][0]


def show(item):
    p = item.get("pricing") or {}
    print("%-28s registrable=%-5s reg=%s renew=%s %s %s" % (
        item["name"], item.get("registrable"), p.get("registration_cost", "-"), p.get("renewal_cost", "-"),
        p.get("currency", ""), item.get("reason", "")))


def main(a):
    if len(a) < 2:
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == "search":
        s, d = call("GET", "/accounts/%s/registrar/domain-search?q=%s&limit=10" % (account(), urllib.parse.quote(" ".join(a[1:]))))
        for it in d.get("result", {}).get("domains", []):
            show(it)
        if s != 200:
            sys.exit(json.dumps(d.get("errors")))
    elif cmd == "check":
        s, d = call("POST", "/accounts/%s/registrar/domain-check" % account(), {"domains": a[1:]})
        if s != 200:
            sys.exit(json.dumps(d.get("errors")))
        for it in d["result"]["domains"]:
            show(it)
    elif cmd == "buy":
        if len(a) != 4 or a[2] != "--price":
            sys.exit("usage: buy <domain> --price X.XX")
        it = live_price(a[1])
        if not it.get("registrable"):
            sys.exit("not registrable: " + it.get("reason", "unknown"))
        if float(it["pricing"]["registration_cost"]) != float(a[3]):
            sys.exit("price moved: live %s, you confirmed %s. Show the captain the live price again." % (it["pricing"]["registration_cost"], a[3]))
        s, d = call("POST", "/accounts/%s/registrar/registrations" % account(), {"domain_name": a[1]}, {"Prefer": "respond-async"})
        print(s, json.dumps(d.get("result") or d.get("errors")))
        print("Never retry a buy that returned in_progress: run status until it settles.")
    elif cmd == "status":
        s, d = call("GET", "/accounts/%s/registrar/registrations/%s/registration-status" % (account(), a[1]))
        r = d.get("result") or {}
        print(s, r.get("state"), r.get("completed"), json.dumps(d.get("errors") or ""))
    elif cmd == "dns":
        if len(a) != 3:
            sys.exit("usage: dns <domain> <ip>")
        z = zone(a[1])
        for name in (a[1], "www." + a[1]):
            s, d = call("GET", "/zones/%s/dns_records?type=A&name=%s" % (z, name))
            body = {"type": "A", "name": name, "content": a[2], "proxied": True, "ttl": 1}
            if d.get("result"):
                s, d = call("PUT", "/zones/%s/dns_records/%s" % (z, d["result"][0]["id"]), body)
                act = "updated"
            else:
                s, d = call("POST", "/zones/%s/dns_records" % z, body)
                act = "created"
            print(name, act if d.get("success") else "FAILED " + json.dumps(d.get("errors")))
    elif cmd == "txt":
        if len(a) != 3:
            sys.exit("usage: txt <domain> <value>")
        z = zone(a[1])
        s, d = call("GET", "/zones/%s/dns_records?type=TXT&name=%s" % (z, a[1]))
        if any(r["content"].strip('"') == a[2] for r in d.get("result", [])):
            print("TXT already present")
        else:
            s, d = call("POST", "/zones/%s/dns_records" % z, {"type": "TXT", "name": a[1], "content": a[2], "ttl": 300})
            print("created" if d.get("success") else "FAILED " + json.dumps(d.get("errors")))
    elif cmd == "verify":
        dom = a[1]
        for host in (dom, "www." + dom):
            for path in (a[2:] or ["/"]):
                url = "https://%s%s" % (host, path)
                r = subprocess.run(["curl", "-s", "-m", "25", "-L", "-o", "/dev/null", "-w", "%{http_code} %{ssl_verify_result}", url],
                                   capture_output=True, text=True)
                print(url, r.stdout.strip(), "(ssl 0 = valid)")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
