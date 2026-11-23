# Creating or changing a skill

The workflow branch of [`writing-for-agents`](SKILL.md). The writing levers in `SKILL.md` and the frontmatter and placement rules in [`SKILL-MECHANICS.md`](SKILL-MECHANICS.md) apply to every step. Each step ends on its completion criterion.

## 1. Capture intent

Start from the conversation: the user may already have walked through the workflow, with tools used, the order of steps, corrections made and formats seen. Extract those answers first and ask only for the gaps. Settle four things:

1. What the skill lets an agent do.
2. When it should trigger: the phrases and situations.
3. The expected output form.
4. Whether it needs test prompts. A skill with checkable output (file transforms, extraction, code generation, a fixed sequence of steps) gains from them; a skill about taste or voice rarely does.

Done when you can state the skill's one job and its trigger branches in two sentences. If an existing skill already covers the job, extend that skill instead.

## 2. Research

Ask about edge cases, input and output formats, example files, success criteria and dependencies before writing a line of the skill. Read the neighbouring skills so the new one cites them by path instead of repeating them. Check the environment (`--help`, config, the directory layout) for facts the skill would otherwise cache: a skill states what the agent cannot find by looking.

## 3. Draft

Write the `SKILL.md` as a first draft, then look at it again with fresh eyes before anyone else does.

- Structure: `SKILL.md` carries the steps every run needs. Bundled resources sit beside it: `scripts/` for deterministic or repeated work (run, not read), `references/` for material only some branches need, `assets/` for files used in output. Reach each from the `SKILL.md` with a pointer that says when to read it.
- Size: aim under 500 lines. Past that, add a layer: move branch-specific material to a reference file. Give any reference over about 300 lines a table of contents. Keep references one level deep; a reference that points at another reference gets read partially.
- Degrees of freedom: where the path is fragile (a migration, a release step) give the exact command and say not to vary it; where many paths work, give the goal and the constraint. Match precision to the cost of a wrong step.
- Imperative form. Give the reason once where a rule would confuse without it, and say it in plain words; do not shout. `ALWAYS` or `NEVER` in capitals is a sign to reframe the rule as a reason plus the positive target.
- Terms: one name per concept across the whole skill. No time-sensitive facts ("before March"), no Windows-style paths in a Unix skill, no menu of five options where one default and an escape hatch will do.
- A skill must not surprise its owner in intent: nothing that exfiltrates, hides what it does, or is described as something it is not.

Done when every step has a checkable completion criterion and nothing in the file is a restatement of something stated elsewhere.

## 4. Validate

```bash
python3 -I ~/.agents/skills/writing-for-agents/scripts/validate.py <skill dir>
```

It checks the frontmatter, that the name matches the folder, that every file the skill points at exists, that every cited skill path resolves, and it flags references to Cursor-only tools and paths and to the retired API worker lane. Fix every error. Read every warning once and either fix it or keep it on purpose.

## 5. Test

Skip this step for a subjective skill; vibe-check it with the owner instead.

Write 2 or 3 realistic prompts, the kind of thing the owner would actually say, and show them to the owner before running anything. Run each with the skill and, for a new skill, once without it as the baseline. A fresh worker session per run keeps the runs independent. This costs model quota, so say how many runs you plan before starting and keep it small. Read the transcripts, not only the outputs: a skill that makes the agent spend time on unproductive steps shows there.

Done when each prompt's output was judged against what the owner expected and the judgment is written down.

## 6. Iterate

Change the skill from the feedback, then rerun the same prompts.

1. Generalize. A skill is used many times across many prompts; a fix that serves only the three test prompts is overfitting. When one issue stays stubborn, try a different framing or pattern before adding another rule.
2. Keep it lean. Remove lines that do not pull their weight; the transcripts show which ones send the agent off on detours.
3. Explain the reason behind a rule the agent keeps getting wrong, then restate the rule positively.
4. Bundle repeated work. When every test run wrote the same helper script, put it in `scripts/` once and have the skill call it.

Stop when the owner is satisfied, the feedback is empty, or two rounds in a row produce no real improvement.

## 7. Tune the description

Do this only when the skill fails to trigger when it should, or fires when it should not.

1. Write about 10 queries in the owner's phrasing: about half that should trigger the skill and half near-misses that share vocabulary but belong elsewhere. Make them substantive; a one-step request like "read this file" will not trigger a skill however good the description is.
2. For each, decide from the description alone whether an agent scanning the skill list would pick this skill. If you can afford the quota, check by running the query in a fresh worker whose only listed skills are the candidates.
3. Revise the description toward the misses, keeping one trigger per branch. Hold two or three queries back and check them last, so the fix is not fitted to the set it was tuned on.
4. Show the owner the before and after.

## 8. Land

- A personal skill: write it to `~/.agents/skills/<name>/`. Decide its class (SKILL-MECHANICS, "Where a skill lives"): invoke-only by default; listed only with a role that must reach it on its own, added to that role's line in `worker-skills.conf` or to the primary launcher.
- A project skill: it ships with the project through the project's normal delivery.
- A skill another skill or a brief depends on: make sure the dependent cites its path.
- Tell the owner where it is and how to call it.
