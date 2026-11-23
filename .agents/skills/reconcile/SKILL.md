---
name: reconcile
description: End-of-wave proof that a surface's build is complete and faithful to its prototypes. Run when a wayfinder map's frontier looks empty and you want the "AFK done" verdict before the next wave.
disable-model-invocation: true
---

# Reconcile

A wave is **done** when two things hold at once: the map's **frontier is empty**, and every prototype has a build that closed **through the gate** — proven green, with its screenshot on file. Reconcile checks both and writes the verdict. It asserts *presence and green*; **you judge the pixel** — the report sets the prototype and the build screenshot side by side for your eye, because UI fidelity is the one thing the gate cannot see.

Argument: a wayfinder map (URL or number) or a surface name. Without one, reconcile every `wayfinder:map` in the repo.

## Steps

1. **Fix the surface set.** Union of two sources: the map's `Surface:` line (in its Notes) and every `docs/prototypes/<slug>/` directory on the current branch. Each `<slug>` is one surface to account for. *Done when:* you have the list, and every slug is named below exactly once (exhaustive — no prototype left unlisted).

2. **Read the frontier.** Query the map's open children (the tracker doc's frontier query). **Any open child — blocked, claimed, or free — means the wave is not done.** Record their count and titles; they become the `⏳ frontier` line of the report. An empty frontier is the first half of the verdict.

3. **Account for every prototype.** For each `docs/prototypes/<slug>/`:
   - **Find its build ticket** — the closed issue whose body carries `## Prototype` naming this slug (`gh issue list --state closed --search "<slug>"`, then confirm the block). None → mark `❌ sem build` (a prototype nobody built; the sharpest failure — a surface that fell in the crack).
   - **Confirm it closed through the gate** — the close comment names the acceptance-test and cites `<red-proof>`, a `<red-proof>` comment exists on the issue, and the screenshot exists at `docs/proof/issue-<ID>/`. Any missing → `⚠️ fechou sem prova` (closed by a path that skipped the gate — investigate).
   - **Re-run its acceptance-test** — take the `Acceptance-test: <file> -t "<name>"` line and run exactly that. Green → the behaviour still holds; red → `❌ regrediu`, paste the output.
   - **Collect the build screenshot** path(s) under `docs/proof/issue-<ID>/` for the side-by-side.
   *Done when:* every slug from step 1 carries one status above.

4. **Catch the Req-1 gaps.** Any surface named on the map with **no** `docs/prototypes/<slug>/` → mark `🕳️ superfície sem protótipo` (should have a prototype and doesn't — the coverage hole). *Done when:* every map surface is either matched to a slug in step 3 or listed here.

5. **Write the report** to `docs/reconcile/<surface>-<YYYY-MM-DD>.md`. Header states the frontier line from step 2. Then one row per surface:

   | Surface | Prototype | Build screenshot | AC-test | Fidelidade |
   |---|---|---|---|---|
   | `<slug>` | link to `docs/prototypes/<slug>/index.html` | `![](../proof/issue-<ID>/<name>.png)` | ✅ / ❌ regrediu | ⬜ **você julga** |

   The `Fidelidade` column stays `⬜` — it is the human's call, made by looking at the two columns to its left. Every other column is machine-filled. Close with a **verdict line**: `AFK done` only if the frontier is empty **and** every surface is `✅` with its screenshot present; otherwise list what blocks it (`⏳` open tickets, `❌` missing builds/regressions, `🕳️` missing prototypes).

6. **Post the gist.** Comment on the map issue: the verdict line plus a link to the report file. *Done when:* the comment is posted and the report path is in it.

## Status legend

- `✅ provado` — built, closed through the gate, acceptance-test green, screenshot present. *Fidelity still pending your eye.*
- `⏳ frontier` — open children remain; the wave is mid-build, not done.
- `❌ sem build` — a prototype with no closed ticket. The #66/#67 failure: a surface that was never ticketed.
- `❌ regrediu` — the acceptance-test that once passed now fails.
- `⚠️ fechou sem prova` — closed by a path that skipped the gate (no red-proof / no screenshot / git-state shortcut). Investigate before trusting.
- `🕳️ superfície sem protótipo` — a map surface with no prototype; the coverage hole that lets UI ship unspecified.
