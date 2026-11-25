#!/usr/bin/env python3
import os, re, sys

KEBAB = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
GONE = [
    (re.compile(r'\bTask tool\b|\bTask call\b|subagent_type'), 'the Task tool does not exist in Pi'),
    (re.compile(r'\bSkill tool\b'), 'the Skill tool does not exist in Pi; cite the SKILL.md path'),
    (re.compile(r'\bAskQuestion\b'), 'AskQuestion does not exist in Pi; ask in chat'),
    (re.compile(r'~/\.cursor|\.cursor/'), 'Cursor paths do not exist here'),
    (re.compile(r'/tmp/apiw'), '/tmp/apiw does not exist; workers are spawned through bin/fm-spawn.sh'),
]
SKILL_PATH = re.compile(r'(?:~|\$HOME|/home/[\w.-]+)/(?:\.agents/skills|\.pi/agent/skills)/([\w.-]+)(/[\w./-]*)?')
REL_LINK = re.compile(r'\]\((?!https?:|#|mailto:)([^)\s#]+)')
REL_TICK = re.compile(r'`((?:references|scripts|assets|agents)/[\w./-]+)`')

USO = """validate.py <skill dir>...  check a skill before calling it done.

Errors (exit 1): missing or malformed frontmatter, name not equal to the folder or not kebab-case,
description missing or over 1024 characters, a relative file the skill points at that does not exist,
a cited skill path (~/.agents/skills/<name>/..., ~/.pi/agent/skills/<name>/...) that does not resolve.
Warnings (exit 0): tools and paths this Time does not have (Task or Skill tool, AskQuestion, ~/.cursor,
/tmp/apiw), a SKILL.md over 500 lines, a reference file over 300 lines without a table of contents.
"""


def frontmatter(text):
    if not text.startswith('---\n'):
        return None, 'no frontmatter (file must start with ---)'
    end = text.find('\n---', 4)
    if end < 0:
        return None, 'frontmatter is not closed'
    fm, key, lines = {}, None, []
    for raw in text[4:end].split('\n'):
        m = re.match(r'^([A-Za-z][\w-]*):\s*(.*)$', raw)
        if m and not raw.startswith(' '):
            if key is not None:
                fm[key] = join(lines)
            key, lines = m.group(1), [m.group(2)]
        elif key is not None:
            lines.append(raw.strip())
    if key is not None:
        fm[key] = join(lines)
    return fm, None


def join(lines):
    v = ' '.join(x for x in lines if x).strip()
    if v in ('>-', '>', '|', '|-'):
        return ''
    if v[:2] in ('>-', '|-'):
        v = v[2:].strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
        v = v[1:-1].replace('\\"', '"')
    return v


def roots():
    h = os.path.expanduser('~')
    return [os.path.join(h, '.agents/skills'), os.path.join(h, '.pi/agent/skills'), os.path.join(os.getcwd(), '.agents/skills')]


def check_frontmatter(fm, d):
    errs = []
    name, desc = fm.get('name', ''), fm.get('description', '')
    if not name:
        errs.append('frontmatter has no name')
    elif not KEBAB.match(name) or len(name) > 64:
        errs.append('name %r must be kebab-case and at most 64 characters' % name)
    elif name != os.path.basename(d):
        errs.append('name %r differs from the folder %r' % (name, os.path.basename(d)))
    if not desc:
        errs.append('frontmatter has no description')
    elif len(desc) > 1024:
        errs.append('description is %d characters (limit 1024)' % len(desc))
    if fm.get('disable-model-invocation', 'true') not in ('true', 'false'):
        errs.append('disable-model-invocation must be true or false')
    return errs


def check_relative_links(d, dirpath, rel, body):
    errs = []
    for m in list(REL_LINK.finditer(body)) + list(REL_TICK.finditer(body)):
        target = m.group(1)
        if not os.path.exists(os.path.normpath(os.path.join(dirpath if m.re is REL_LINK else d, target))):
            errs.append('%s points at %s, which does not exist' % (rel, target))
    return errs


def check_skill_paths(rel, body):
    errs = []
    for m in SKILL_PATH.finditer(body):
        name2, rest = m.group(1), m.group(2) or ''
        found = [r for r in roots() if os.path.isdir(os.path.join(r, name2))]
        if not found:
            errs.append('%s cites skill %r, which is not installed' % (rel, name2))
        elif rest.strip('/') and not os.path.exists(os.path.join(found[0], name2, rest.strip('/'))):
            errs.append('%s cites %s/%s, which does not exist' % (rel, name2, rest.strip('/')))
    return errs


def check_markdown(d, dirpath, rel, body):
    errs = check_relative_links(d, dirpath, rel, body) + check_skill_paths(rel, body)
    warns = []
    if dirpath != d and body.count('\n') > 300 and not re.search(r'(?im)^#+\s*(table of )?contents', body):
        warns.append('%s has %d lines and no table of contents' % (rel, body.count('\n')))
    return errs, warns


def check_file(d, dirpath, fn):
    p = os.path.join(dirpath, fn)
    body = open(p, encoding='utf-8', errors='replace').read()
    rel = os.path.relpath(p, d)
    warns = []
    for rx, why in GONE:
        m = rx.search(body)
        if m and not fn.endswith(('.py', '.sh')):
            warns.append('%s: "%s": %s' % (rel, m.group(0), why))
    if not fn.endswith('.md'):
        return [], warns
    errs, md_warns = check_markdown(d, dirpath, rel, body)
    return errs, warns + md_warns


def check(d):
    errs, warns = [], []
    d = os.path.abspath(d)
    sk = os.path.join(d, 'SKILL.md')
    if not os.path.isfile(sk):
        return ['no SKILL.md in %s' % d], []
    text = open(sk, encoding='utf-8', errors='replace').read()
    fm, err = frontmatter(text)
    if err:
        return [err], []
    errs.extend(check_frontmatter(fm, d))
    n = text.count('\n') + 1
    if n > 500:
        warns.append('SKILL.md has %d lines (aim under 500; move branch material to a reference file)' % n)
    for dirpath, _, files in os.walk(d):
        for fn in files:
            if not fn.endswith(('.md', '.yaml', '.yml', '.txt', '.py', '.sh')):
                continue
            file_errs, file_warns = check_file(d, dirpath, fn)
            errs.extend(file_errs)
            warns.extend(file_warns)
    return errs, warns


def main():
    if len(sys.argv) < 2:
        sys.exit(USO)
    bad = 0
    for d in sys.argv[1:]:
        errs, warns = check(d)
        print('%s: %s' % (d, 'FAIL' if errs else 'ok'))
        for e in errs:
            print('  error: ' + e)
        for w in warns:
            print('  warning: ' + w)
        bad += bool(errs)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
