---
name: buy-domain
description: Buy a domain and put the site live on our VPS in one run. Say the domain; it checks, buys, points and publishes.
disable-model-invocation: true
---

The captain names a domain; one command does the rest and stops where a person is needed, first of all at the price. The scripts hold every mechanical step; you hold judgment: alternatives when a name is taken, and the conversation when the run stops. Run with `python3 -I`.

```
scripts/go.py <domain> [--site-dir DIR] [--profile P] [--ip IP] [--confirm-price USD]
```

It is resumable: after any stop, fix the cause and rerun the same command. It never repeats a purchase (a zone already on our Cloudflare account skips the buy).

## Price first, then the captain's yes

Every purchase waits for his explicit yes to the live price: the first run prints "available: US$X to register, US$Y to renew" and stops (exit 4); tell him both numbers and the renewal month, and only after his yes rerun with `--confirm-price X`. The run refuses when the live price differs from the confirmed one. A "yes" to another name or an older price does not count. Auto-renew stays off and WHOIS privacy on. A purchase is never retried while `in_progress`.

## What it does

1. **zone**: skips the purchase when the domain is already ours.
2. **buy**: live check, then registration through the Cloudflare Registrar API once `--confirm-price` matches.
3. **vps**: the single registered aaPanel profile; its public IP feeds the DNS. This run uses that profile without asking, as the captain asked for autonomy; with several profiles it stops (exit 6) so you ask which.
4. **site**: creates the site in aaPanel, publishes `--site-dir` (zipped and unpacked into the webroot), or writes a placeholder page when the site is empty so it is ready for the files.
5. **dns**: proxied A records for `@` and `www`.
6. **cert**: Let's Encrypt, retried while DNS spreads; skipped when the origin already serves a valid one. The certificate is what keeps visitors from seeing another site on the same VPS.
7. **verify**: HTTPS 200 with a valid certificate on `@` and `www`.

Done when the last line reads `[done] live: https://<domain>/`. Afterwards, check that the other sites on that VPS still answer.

## When it stops

- **2, not registrable**: run `scripts/cf_domain.py search <words>` and offer three close alternatives with their live prices.
- **3, buy on Hostinger** (`.shop` and TLDs Cloudflare cannot sell): the captain buys it there, since it is cheaper, adds the domain to Cloudflare as a free zone and sets the two Cloudflare nameservers at Hostinger. Walk him through it, then rerun `go.py`.
- **4, price to confirm**: see "Price first".
- **5, no VPS registered**: run `~/.agents/skills/aapanel/scripts/open-register-vps.sh` and set the VPS up with the person (the `aapanel` skill owns that wizard), then rerun.
- **6, several VPS**: ask which, rerun with `--profile`.
- **7, a step failed**: the line before it names the step. A 525 on verify means the Cloudflare SSL mode must be Full; set it in the dashboard.

## After it is live

Tell the captain the domain, the price paid, and the expiry date (auto-renew is off, so a reminder is on you). The Cloudflare token needs Registrar Domains (Admin) and Zone DNS (Edit); a missing permission shows as "Authentication error", so ask for that exact one. Revoke or narrow the token when the work ends.

Individual steps run alone through `scripts/cf_domain.py` (`search`, `check`, `buy`, `status`, `dns`, `txt`, `verify`) and `scripts/aa_site.py <profile> ensure|cert|remove <domain>`.
