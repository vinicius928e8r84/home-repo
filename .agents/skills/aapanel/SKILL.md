---
disable-model-invocation: true
name: aapanel
description: Deploy and manage files on any aaPanel (bt-panel) server. Use when the user wants to deploy or publish a site/build to aaPanel, upload/replace/edit files on a VPS running aaPanel, restore a backup, or automate aaPanel file operations. Reach for it whenever a task targets an aaPanel-hosted site (e.g. usealivina.com, biolabnatural.com).
---

# aaPanel deploy & file ops

Drive any aaPanel server's file API from Python via `aa_client.py` (class `AaPanel`).
Handles the auth (cert-pinning + RSA login) and the two gotchas that waste hours.

## Two gotchas that cause silent failure

- **Fake 404 on the entrance.** aaPanel returns an nginx-style `404 Not Found` to
  any request on the security entrance that carries `X-Requested-With`. The client
  hits the entrance as a plain browser and adds that header only on `/login` and
  `/files` calls. A 404 from a URL you know is live = this, not a dead panel.
- **`RestartServer` reboots the whole VPS.** Never call `system?action=RestartServer`.
  Config changes on aaPanel/Apache are usually honored live; if a reload is truly
  needed use `ServiceAdmin` with `type:"reload"`.

## Get credentials

The panel needs a full login URL (incl. security entrance), username, password —
supplied by the caller, never hardcoded. In order of preference:
`AaPanel.from_env()` (`AAPANEL_URL`/`AAPANEL_USER`/`AAPANEL_PWD`) ·
`AaPanel.from_config(path)` (JSON `{url,user,pwd}`) ·
`AaPanel(base_url, entrance, user, pwd)`.
If none are available, ask the user for the login URL + credentials before proceeding.

## Deploy a site (steps)

1. **Login and map the target.** `p = AaPanel(...).login()`, then `p.listdir(webroot)`
   — note `DIR` (subfolders) and `FILES` separately. Confirm the real layout before
   writing; touch only the files this deploy owns.
2. **Back up before overwrite.** `p.get_file(path)` every file you will replace and
   write the returned `data` to a local timestamped `.bak`. Completion: a local
   backup exists for every remote file the deploy will overwrite.
3. **Push the changes.** Single text file → `p.save_file(remote, text)`. One binary
   → `p.upload(remote_dir, local)` (auto-chunks >2 MB). A whole built site →
   `p.upload_unzip(webroot, local_zip, wait_for="assets/<hashed>.css")` (zip flat:
   `index.html` + asset dirs; exclude throwaway/prototype routes). Completion: every
   changed file's call returned `status: true`.
4. **Verify live.** `curl` each public URL with a cache-buster; assert HTTP 200 and
   that a distinctive marker of the new content is present (a new price, headline,
   or hashed asset name). Completion: every deployed URL serves the new marker.

## Restore

Re-`save_file`/`upload` the `.bak` files. aaPanel also keeps server-side version
history for `SaveFileBody` writes (returned as `historys`).

## API surface

`listdir · get_file · save_file · upload · unzip · upload_unzip · delete` on
`AaPanel`. For actions not wrapped, call `p._api("<Action>", {...})` — the aaPanel
file API is `POST /files?action=<Action>` under the apsess prefix with the
`X-Http-Token` header (both set by `login()`).
