# Home Repo

Meu repositório-base: docs para agentes e ponteiros para os meus outros repos. Rode o agente a partir daqui.

## Skills

Em `.agents/skills/` (o Claude Code os vê por `.claude/skills/`), copiados da VPS sem alteração.

Um skill só entra aqui se vale para todos os repos e não custa contexto (`disable-model-invocation: true`; a única exceção é o `pr`, de uma linha). Skills de engenharia (tdd, triage, wayfinder, code-review...) e de front-end vivem no repo que precisa deles, e entram lá quando o projeto pedir.

## Outros repos

- Nova-AI (port do Nova AI para macOS + iPhone, Electron): `~/Nova-AI`. Clone de https://github.com/vinicius928e8r84/Nova-AI se faltar. Leia o AGENTS.md dele primeiro: nunca edite a `main`; uma branch por tarefa, `agent/<ferramenta>/<tarefa>-AAAAMMDD`.
- PerpetualMiner (extensão Chrome que minera frases e envia ao Anki, mais o complemento do Anki): `~/PerpetualMiner`. Clone de https://github.com/vinicius928e8r84/PerpetualMiner se faltar. A fonte da verdade é a `main` no GitHub (construída e atualizada na VPS): rode `git pull` antes de trabalhar. Leia o AGENTS.md dele primeiro.
