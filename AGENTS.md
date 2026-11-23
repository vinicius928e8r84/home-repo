# Home Repo

Ponto de partida do agente: os skills que valem em qualquer repo e os ponteiros para os outros repos.

## Skills

Os skills daqui valem para qualquer repo; o que serve a um repo só vive nele. Skill novo entra aqui quando o usuário pedir.

Um skill daqui age no repo do trabalho: glossário, ADRs, specs, tickets e pesquisas vão para o repo de que a tarefa trata, seguindo o `docs/agents/` dele quando existir. Ficam neste repo (`GLOSSARY.md` no lugar de `CONTEXT.md`) só quando a tarefa é sobre ele ou cruza repos.

## Wiki

`wiki/index.md` lista o que se sabe sobre o usuário e o trabalho dele fora do código. Consulte-o antes de perguntar algo ao usuário e grave lá o que ele ensinar de duradouro.

## Outros repos

Antes de trabalhar em um deles, rode `git pull` (o clone local fica atrás do GitHub) e leia o AGENTS.md dele. Os skills de um repo não carregam aqui: quando a tarefa pedir um, leia o `SKILL.md` dele em `.claude/skills/<nome>/` como arquivo e siga-o.

Para delegar a agentes, cada um no seu worktree: `python scripts/crew.py --help`. Os caminhos e remotes dos repos estão em `repos.json`.

- Nova-AI (port do Nova AI para macOS + iPhone, em Electron).
- PerpetualMiner (extensão Chrome que minera frases e as envia ao Anki).
