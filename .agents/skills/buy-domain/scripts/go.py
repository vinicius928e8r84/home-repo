#!/usr/bin/env python3
"""One command from a domain name to a live site: go.py <domain> [--site-dir DIR] [--profile P] [--ip IP] [--confirm-price USD]

Resumable and idempotent: rerun after any stop. Steps, each printed as one line:
  1 zone   a zone already on our Cloudflare account skips the purchase (a domain bought elsewhere and added as a zone lands here)
  2 buy    live check, then purchase only when registrable AND --confirm-price equals the live price (otherwise print the price and stop)
  3 vps    the one registered aaPanel profile (or --profile); its host is the A-record IP unless --ip is given
  4 site   create the site, publish --site-dir (or a placeholder page when the site is empty)
  5 dns    proxied A records for @ and www
  6 cert   Let's Encrypt, retried while DNS spreads
  7 verify HTTPS from outside
Exit codes: 0 live, 2 not registrable, 3 buy it on Hostinger (not on Cloudflare), 4 price shown, confirmation needed, 5 no VPS registered, 6 several VPS (pass --profile), 7 a step failed.
"""
import glob, ipaddress, json, os, socket, subprocess, sys, tempfile, time, urllib.parse, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cf_domain as cf  # noqa: E402
import aa_site as aa  # noqa: E402

PLACEHOLDER = "<!doctype html><meta charset=utf-8><title>%s</title><p>%s</p>"


def say(step, msg):
    print("[%s] %s" % (step, msg), flush=True)


def stop(code, msg):
    print("STOP %d: %s" % (code, msg))
    sys.exit(code)


def has_zone(domain):
    s, d = cf.call("GET", "/zones?name=" + domain)
    return s == 200 and bool(d.get("result"))


def public_ip(host):
    try:
        ip = socket.gethostbyname(host)
    except OSError:
        return None
    return None if ipaddress.ip_address(ip).is_private or ip.startswith("100.") else ip


def cert_ok(domain, ip):
    """True when the origin already serves a certificate for the domain with more than 20 days left."""
    cmd = "echo | openssl s_client -connect %s:443 -servername %s 2>/dev/null | openssl x509 -noout -subject -checkend 1728000" % (ip, domain)
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    return ("CN = " + domain) in out and "will not expire" in out


def pick_profile(want):
    names = sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.expanduser("~/.config/aapanel/servers/*.json")))
    if want:
        if want not in names:
            stop(5, "no aaPanel profile %r; registered: %s" % (want, names or "none"))
        return want
    if not names:
        stop(5, "no VPS registered. Run ~/.agents/skills/aapanel/scripts/open-register-vps.sh and walk the person through it, then rerun.")
    if len(names) > 1:
        stop(6, "several VPS registered (%s): ask which one, then pass --profile" % ", ".join(names))
    return names[0]


def buy(domain, confirmed):
    it = cf.live_price(domain)
    price = (it.get("pricing") or {}).get("registration_cost")
    if not it.get("registrable"):
        reason = it.get("reason", "unknown")
        if reason.startswith("extension_not_supported"):
            stop(3, "%s is not sold through our Cloudflare API: the captain buys it on Hostinger, adds it to Cloudflare as a zone and sets the nameservers, then rerun." % domain)
        stop(2, "%s not registrable (%s). Try: cf_domain.py search <words>" % (domain, reason))
    if domain.endswith(".shop"):
        stop(3, "%s: the captain buys .shop on Hostinger (cheaper; Cloudflare asks US$%s), adds it to Cloudflare as a zone and sets the nameservers, then rerun." % (domain, price))
    if confirmed is None or float(price) != float(confirmed):
        stop(4, "%s is available: US$%s to register, US$%s per year to renew. Tell the captain the price and wait for his yes, then rerun with --confirm-price %s." % (domain, price, it["pricing"]["renewal_cost"], price))
    s, d = cf.call("POST", "/accounts/%s/registrar/registrations" % cf.account(), {"domain_name": domain}, {"Prefer": "respond-async"})
    if s not in (200, 201, 202):
        stop(7, "purchase refused: %s" % json.dumps(d.get("errors")))
    say("buy", "ordered %s for US$%s (renews US$%s)" % (domain, price, it["pricing"]["renewal_cost"]))
    for _ in range(30):
        s, d = cf.call("GET", "/accounts/%s/registrar/registrations/%s/registration-status" % (cf.account(), domain))
        r = d.get("result") or {}
        if r.get("completed"):
            if r.get("state") != "succeeded":
                stop(7, "registration ended %s: %s" % (r.get("state"), json.dumps(r.get("error"))))
            return
        time.sleep(6)
    stop(7, "registration still in progress; never buy again, run: cf_domain.py status %s" % domain)


def publish(p, h, domain, site_dir):
    root = "/www/wwwroot/" + domain
    if site_dir:
        zp = os.path.join(tempfile.mkdtemp(prefix="bd-"), "site.zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for base, _, files in os.walk(site_dir):
                for f in files:
                    full = os.path.join(base, f)
                    z.write(full, os.path.relpath(full, site_dir))
        p.upload_unzip(root, zp)
        say("site", "published %s" % site_dir)
    else:
        names = [i.split(";")[0] for i in (p.listdir(root).get("FILES") or [])]
        if "index.html" not in names:
            p.save_file(root + "/index.html", PLACEHOLDER % (domain, domain))
            say("site", "placeholder page written (ready for the real files)")


def main(a):
    if not a or a[0].startswith("-"):
        sys.exit(__doc__)
    domain = a[0].lower()
    opt = dict(zip(a[1::2], a[2::2]))
    confirmed = opt.get("--confirm-price")

    if has_zone(domain):
        say("zone", "%s already on our Cloudflare account, no purchase" % domain)
    else:
        buy(domain, confirmed)
        for _ in range(20):
            if has_zone(domain):
                break
            time.sleep(6)
        else:
            stop(7, "zone not visible yet; rerun in a minute")
        say("buy", "zone ready")

    profile = pick_profile(opt.get("--profile"))
    prof = json.load(open(os.path.expanduser("~/.config/aapanel/servers/%s.json" % profile)))
    ip = opt.get("--ip") or public_ip(urllib.parse.urlparse(prof["url"]).hostname)
    if not ip:
        stop(7, "cannot tell the VPS public IP from profile %s: pass --ip" % profile)
    say("vps", "profile %s, ip %s" % (profile, ip))

    p, h = aa.login(profile)
    aa.main([profile, "ensure", domain])
    publish(p, h, domain, opt.get("--site-dir"))

    for line in subprocess.run([sys.executable, "-I", os.path.join(HERE, "cf_domain.py"), "dns", domain, ip],
                               capture_output=True, text=True).stdout.splitlines():
        say("dns", line)

    for attempt in range(0 if cert_ok(domain, ip) else 6):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aa_site.py"), profile, "cert", domain],
                           capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        if "certificate installed" in out:
            say("cert", "installed")
            break
        say("cert", "try %d: %s" % (attempt + 1, out[:140]))
        time.sleep(20)
    else:
        if not cert_ok(domain, ip):
            stop(7, "certificate not issued; check the DNS records and rerun")
        say("cert", "already valid, kept")

    bad = 0
    for host in (domain, "www." + domain):
        r = subprocess.run(["curl", "-s", "-m", "25", "-L", "-o", "/dev/null", "-w", "%{http_code} %{ssl_verify_result}", "https://%s/" % host],
                           capture_output=True, text=True).stdout.strip()
        say("verify", "https://%s/ -> %s" % (host, r))
        bad += not r.startswith("200 0")
    if bad:
        stop(7, "verify not green (a 525 means set the Cloudflare SSL mode to Full); rerun to retry")
    say("done", "live: https://%s/" % domain)


if __name__ == "__main__":
    main(sys.argv[1:])
