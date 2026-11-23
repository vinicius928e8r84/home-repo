---
disable-model-invocation: true
name: aapanel
description: Deploy and manage sites or files on one of several registered aaPanel VPS servers. Use when publishing a site, updating production code, uploading or restoring hosted files, registering an aaPanel VPS, or choosing which VPS owns a domain.
---

# aaPanel deployments

Use `aa_client.py` from this skill directory for aaPanel file operations.
Treat every server write as production work.

## Target lock

Before any remote read or write:

1. List `~/.config/aapanel/servers/*.json` when the directory exists.
2. When no profile exists or the requested alias is unknown, run `scripts/open-register-vps.sh` from this skill directory. In Herdr it opens and focuses a dedicated wizard tab automatically; elsewhere it prints the manual command. Stop until the wizard's read-only validation succeeds.
3. Ask the user which named VPS and which site/environment to target, even when only one profile exists.
4. Repeat the selected alias, hostname, domain, and webroot before changing anything.

A domain name, repository name, prior deployment, or current terminal never selects a VPS implicitly.
The registration wizard is the default path for every new VPS; manual profile creation is reserved for an explicit user request.
Completion: one wizard-validated profile and one exact webroot are explicitly selected for this operation.

## Registered profiles

Keep one mode-`0600` JSON file per server at `~/.config/aapanel/servers/<alias>.json`:

```json
{
  "url": "https://host:port/security-entrance",
  "user": "panel-user",
  "password_file": "/home/user/.config/aapanel/credentials/prod.password",
  "fingerprint": "SHA256_HEX"
}
```

`url`, `user`, and `fingerprint` are required.
The wizard writes a separate `password_file` with mode `0600`; `password_env` remains available when the user prefers a secret manager or session environment.
A profile may contain `pwd` only when the user explicitly chooses a local plaintext credential file; keep that profile mode `0600` and never print, commit, or copy its secret into logs.

Load a profile:

```python
from aa_client import AaPanel
panel = AaPanel.from_config("~/.config/aapanel/servers/prod.json").login()
```

## Register a VPS

Start registration with:

```bash
~/.agents/skills/aapanel/scripts/open-register-vps.sh
```

In Herdr this opens and focuses a dedicated interactive tab automatically.
Outside Herdr, run the manual command it prints.
The wizard owns the normal first-registration sequence below.
Collect and confirm:

- a short unique alias;
- provider or purpose;
- full aaPanel login URL including port and security entrance;
- panel username;
- credential source (wizard-managed `password_file` by default, or `password_env` when requested);
- domains and their exact webroots;
- production, staging, or another environment.

Fetch the presented certificate fingerprint with `AaPanel.fetch_fingerprint(url)` and show it to the user.
Require explicit acceptance after they compare it with the VPS or aaPanel certificate details; first-contact observation alone is not identity proof.
Write the profile atomically with mode `0600`, then log in and perform only a read-only `listdir` against the confirmed webroot.
Completion: profile permissions are `0600`, certificate identity is accepted, login succeeds, and the expected webroot is readable.

## Deploy

1. **Preflight.** Log in, call `listdir(webroot)`, and verify the returned files match the intended site. Confirm the local build and destination environment.
2. **Backup.** Call `get_file` for every remote file that will be replaced. Store timestamped backups under a local directory containing the VPS alias and domain. For a directory deployment, create a server-side or downloaded archive before overwrite. Completion: every overwritten path has a recoverable copy.
3. **Upload.** Use `save_file` for text, `upload` for one binary, or `upload_unzip` for a complete built site. A deployment ZIP is flat at its root (`index.html` plus asset directories) and excludes caches, prototypes, credentials, source maps unless required, and unrelated files. Require every mutation response to report success.
4. **Verify.** Request each public URL with a cache-buster. Require HTTP 200, the expected content marker, required assets, and absence of obvious server errors. Verify the selected domain resolves to the selected VPS.
5. **Report.** Name the VPS alias, domain, changed paths, backup location, and live verification result.

Completion: backup, successful mutation responses, and public verification all agree on the same release.

## Restore

Select the same VPS and site again through **Target lock**.
Show the backup set and affected remote paths, then obtain explicit restore approval.
Restore only those paths, verify mutation responses, and repeat public verification.

## Safety boundaries

- `system?action=RestartServer` reboots the whole VPS. Never call it.
- Use `ServiceAdmin` with `type: "reload"` only when a documented configuration change requires it and the user explicitly approves that service reload.
- Deletion, database changes, DNS changes, SSL replacement, service restart/reload, and restoring production data each require explicit approval naming the VPS and target.
- Use only the wrapped file methods by default. Call `_api` for another action only after consulting current aaPanel documentation and obtaining approval for that exact action.
- Treat the source VPS as read-only during migrations until destination verification and cutover approval are complete.

## aaPanel protocol gotchas

- The security entrance can return a fake nginx-style 404 when `X-Requested-With` is present. The client omits that header on the entrance and adds it only to login and file API requests.
- The client requires an accepted SHA-256 certificate fingerprint. It does not silently trust the certificate currently presented by the network.
- aaPanel login tokens are HTML `data` attributes and credentials use aaPanel's RSA/MD5 login protocol; keep this implementation detail inside `aa_client.py`.
