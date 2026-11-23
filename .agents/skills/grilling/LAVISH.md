# Grilling on a lavish page

The interview runs on one lavish page in place of chat rounds: read `.agents/skills/lavish/SKILL.md` and follow it to open the page and receive the user's feedback.

The page is the design tree, kept current:

- **Settled**: every decision made so far, one line each.
- **This round**: the whole frontier, each question numbered, with your recommended answer.
- **Later**: the branches that wait on an open question.

The user answers by annotating the page. After each round, update the same page: move the answered questions into Settled, recompute the frontier, show the next round. In chat, say only that the page has a new round.

The session is done when This round and Later are empty and the user confirms the Settled list.
