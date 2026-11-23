# Home Repo

Ponto de partida do agente: os skills que valem em qualquer repo e os ponteiros para os outros repos.

Na primeira mensagem de cada sessão, rode `python scripts/crew.py board` e resuma ao usuário onde paramos: decisões pendentes, o que roda e o que travou.

## Skills

Os skills daqui valem para qualquer repo; o que serve a um repo só vive nele. Skill novo entra aqui quando o usuário pedir.

Um skill daqui age no repo do trabalho: glossário, ADRs, specs, tickets e pesquisas vão para o repo de que a tarefa trata, seguindo o `docs/agents/` dele quando existir. Ficam neste repo (`GLOSSARY.md` no lugar de `CONTEXT.md`) só quando a tarefa é sobre ele ou cruza repos.

## Freios

`python scripts/freios/freios.py --commit` confere tamanho e comentários do que está no commit; `--tudo` confere o índice inteiro e os commits da branch. Cada verificação diz o conserto quando falha. O que já existia na `main` (comentários, arquivos grandes, skills e links) está em `scripts/freios/linha-de-base.json`: só avisa, e arquivo novo ou que piora reprova. Depois de uma limpeza, rode `--tudo --atualizar-linha-de-base` e versione o arquivo; ele só encolhe. Os tetos ficam em `limites.json` e as exceções, com motivo, em `excecoes.json`; mudar um deles é decisão do dono. Ligue os ganchos uma vez por clone com `git config core.hooksPath .githooks`.

## Wiki

`wiki/index.md` lista o que se sabe sobre o usuário e o trabalho dele fora do código. Consulte-o antes de perguntar algo ao usuário e grave lá o que ele ensinar de duradouro.

## Outros repos

Antes de trabalhar em um deles, rode `git pull` (o clone local fica atrás do GitHub) e leia o AGENTS.md dele. Os skills de um repo não carregam aqui: quando a tarefa pedir um, leia o `SKILL.md` dele em `.claude/skills/<nome>/` como arquivo e siga-o.

Para delegar a agentes, cada um no seu worktree: `python scripts/crew.py --help`. Os caminhos e remotes dos repos estão em `repos.json`.

- Nova-AI (port do Nova AI para macOS + iPhone, em Electron).
- PerpetualMiner (extensão Chrome que minera frases e as envia ao Anki).
