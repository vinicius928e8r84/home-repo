# Skill mechanics

The skill-specific branch of [`writing-for-agents`](SKILL.md): what changes when the document is a skill (frontmatter, the invocation choice, and router skills). Everything else about writing it is the universal reference in `SKILL.md`.

## Invocation

Two choices, trading the two loads:

- A **model-invoked** skill keeps a `description`, so the agent can fire it autonomously, and other skills can reach it. You can still type its name: model-invocation always _includes_ user reach; a description only ever adds agent discovery, never removes the human's. The description is the skill's top-level context pointer, forced to stay loaded at all times: permanent context load in exchange for discoverability. A model-invoked skill whose content is all reference is also one home for shared reference: another skill can invoke it, so reference needed by several skills lives in one place. Mechanics: omit `disable-model-invocation`, and write a model-facing description carrying the trigger branches (the pointer-writing rules in `SKILL.md` apply in full).
- A **user-invoked** skill strips the description from the agent's reach: only the human typing its name can invoke it, and no other skill can. Zero context load, but it spends cognitive load: you are the index that must remember it exists. Mechanics: set `disable-model-invocation: true`; the `description` becomes human-facing: a one-line summary, trigger lists stripped.

Pick model-invocation only when the agent must reach the skill on its own, or another skill must. If it only ever fires by hand, make it user-invoked and pay no context load.

Shared reference that two user-invoked skills both need can live in neither: with no descriptions, neither can fire the other. Push it to a plain file outside the skill system: external reference any skill can point at.

## Splitting by invocation

The invocation cut of splitting (the sequence cut lives in `SKILL.md`): split off a model-invoked skill when you have a distinct leading word that should trigger it on its own (a trigger word you actually use in your prompts), or another skill must reach it. You pay context load for the new always-loaded description, so that independent reach has to be worth it.

## Router skills

When user-invoked skills multiply past what you can remember, that piled-up cognitive load is cured by a **router skill**: one user-invoked skill that names the others and when to reach for each, so the human has one skill to remember instead of many. It can only hint, never fire them: user-invoked skills have no description, so nothing but the human can reach them.

## Frontmatter

- `name`: lowercase letters, digits and single hyphens, at most 64 characters, equal to the folder name.
- `description`: non-empty, at most 1024 characters, third person, saying what the skill does and when to reach for it. All "when to use" belongs here, not in the body, because the body is only read after the skill fires.
- `disable-model-invocation: true` for a user-invoked skill. Put it as the first frontmatter line; `scripts/validate.py` does not care about order, but the Time's hide tooling does.
- Quote a `description` that contains a colon, or use `description: >-` with indented continuation lines, so it stays one YAML scalar.

## Description

A model-invoked description is the skill's only trigger, so write it to fire. State the outcome in the leading words, then list the distinct situations that should reach the skill, using the phrases the owner and the briefs actually use. Agents tend to under-trigger skills, so lean toward naming the borderline situations that belong to a branch. The pruning rule still holds: one trigger per branch, no synonym for a branch already named, no identity the body already carries.

## Where a skill lives in this Time

Every skill belongs to exactly one of three classes. Pick the class before writing the file.

- **Listed**: appears in the prompt of the roles that use it on their own (the role lines in `~/.local/share/firstmate/worker-skills.conf`, the primary launcher's `--skill` list). Pays prompt bytes on every request of those roles. Reserve it for skills a role reaches without being told.
- **Invoke-only**: `disable-model-invocation: true`. Costs nothing in the prompt. The owner calls it by `/skill:<name>`, and a worker uses it only when the brief or another skill gives the **path** of its `SKILL.md`. A bare name does not load a skill: Pi has no tool that loads a skill by name, so a name in a brief was opened in 2 of 9 measured scheduled runs, the written path in 18 of 19.
- **Removed**: moved out of every search path to a dated backup, never deleted.

Where it goes: a personal skill in `~/.agents/skills/<name>/`; a project skill in that project's `.agents/skills/<name>/` (committed with the project, so it loads for that project only); a skill for the firstmate repo itself in that repo's `.agents/skills/` through its normal delivery. A skill that cites another must cite its path (`~/.agents/skills/<name>/SKILL.md`), because the cited one is often invoke-only.
