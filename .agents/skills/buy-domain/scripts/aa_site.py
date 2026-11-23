#!/usr/bin/env python3
"""aaPanel site and certificate steps for the buy-domain skill (uses the aapanel skill's client and saved profile).

  aa_site.py <profile> ensure <domain>   create the static site <domain> (+ www) when missing; root /www/wwwroot/<domain>
  aa_site.py <profile> cert <domain>     issue a Let's Encrypt certificate for <domain> + www by file validation and install it
  aa_site.py <profile> remove <domain>   delete a site this skill created (site and its folder)

A profile is a file ~/.config/aapanel/servers/<profile>.json. Run with python3 -I.
The domain must already resolve to this server (or through the Cloudflare proxy) before `cert`.
"""
import json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/.agents/skills/aapanel"))
from aa_client import AaPanel  # noqa: E402


def login(profile):
    prof = json.load(open(os.path.expanduser("~/.config/aapanel/servers/%s.json" % profile)))
    base, ent = AaPanel._split_login_url(prof["url"])
    p = AaPanel(base, ent, prof["user"], Path(prof["password_file"]).read_text(),
                AaPanel.fetch_fingerprint(prof["url"])).login()
    h = {"X-Requested-With": "XMLHttpRequest"}
    if p.http_token:
        h["X-Http-Token"] = p.http_token
    return p, h


def post(p, h, path, data, timeout=180):
    r = p.session.post(p.base + p.apsess + path, data=data, headers=h, timeout=timeout)
    try:
        return r.json()
    except Exception:
        return {"status": False, "msg": r.text[:200]}


def site(p, h, domain):
    d = post(p, h, "/data?action=getData&table=sites", {"p": 1, "limit": 200, "type": -1, "search": domain})
    for s in d.get("data", []):
        if s.get("name") == domain:
            return s


def main(a):
    if len(a) != 3:
        sys.exit(__doc__)
    profile, cmd, dom = a
    p, h = login(profile)
    s = site(p, h, dom)
    if cmd == "ensure":
        if s:
            print("site exists id=%s" % s["id"])
            return
        webname = json.dumps({"domain": dom, "domainlist": ["www." + dom], "count": 0})
        r = post(p, h, "/site?action=AddSite", {
            "webname": webname, "path": "/www/wwwroot/" + dom, "type_id": 0, "type": "PHP",
            "version": "00", "port": 80, "ps": "buy-domain skill", "ftp": "false", "sql": "false", "codeing": "utf8"})
        print("created" if r.get("siteStatus") else "FAILED %s" % json.dumps(r)[:300])
    elif cmd == "cert":
        if not s:
            sys.exit("no site %s: run ensure first" % dom)
        d = {"domains": json.dumps([dom, "www." + dom]), "auth_type": "http", "auth_to": "/www/wwwroot/" + dom,
             "auto_wildcard": "0", "id": str(s["id"])}
        r = post(p, h, "/acme?action=apply_cert_api", d)
        if not r.get("cert"):
            sys.exit("certificate not issued: %s" % json.dumps(r)[:300])
        full = r["cert"] + ("\n" + r["root"] if r.get("root") else "")
        key = r.get("private_key") or r.get("key")
        o = post(p, h, "/site?action=SetSSL", {"type": "1", "siteName": dom, "key": key, "csr": full})
        print("certificate installed" if o.get("status") else "FAILED %s" % json.dumps(o)[:200])
    elif cmd == "remove":
        if not s:
            print("no such site")
            return
        r = post(p, h, "/site?action=DeleteSite", {"id": s["id"], "webname": dom, "ftp": 1, "path": 1, "database": 1})
        print(json.dumps(r)[:200])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
