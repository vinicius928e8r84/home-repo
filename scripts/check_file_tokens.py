"""Refuse files too big for an agent to read and edit in one go.

From sf-kit (project-template/scripts/check-file-tokens.mjs). Tokens are estimated as bytes / 4.
Usage: python -I scripts/check_file_tokens.py <file>...  (the pre-commit hook passes the staged files)
Exit 0 when every file is at or under the ceiling; 1 otherwise.
"""
import os
import re
import sys

MAX_TOKENS = 5000
BYTES_PER_TOKEN = 4

# Lock files and images nobody edits by hand, and workflow files, which GitHub reads as one file each.
IGNORED = [
    re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$"),
    re.compile(r"\.svg$"),
    re.compile(r"^\.github/workflows/[^/]+\.ya?ml$"),
]

ADVICE = """
Split each file before you commit. Do not delete code or squash it onto fewer lines.
Find the seams: groups of functions, components or tests that change together and share
little with the rest. Move each group to its own file. Split tests by the behaviour under test.
Then commit again."""


def oversized(files):
    found = []
    for file in files:
        if any(p.search(file.replace("\\", "/")) for p in IGNORED):
            continue
        if not os.path.isfile(file) or os.path.islink(file):
            continue
        with open(file, "rb") as f:
            contents = f.read()
        if b"\0" in contents[:8000]:  # binary
            continue
        tokens = -(-len(contents) // BYTES_PER_TOKEN)
        if tokens > MAX_TOKENS:
            found.append((file, tokens))
    return found


def main(files):
    found = oversized(files)
    if not found:
        return 0
    print(f"These files are over {MAX_TOKENS} tokens (bytes / 4):\n", file=sys.stderr)
    for file, tokens in found:
        print(f"  {file}: ~{tokens} tokens", file=sys.stderr)
    print(ADVICE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
