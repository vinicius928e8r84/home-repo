# PerpetualMiner: a dieta dos `.md`

Fonte: o relatório do worker `pm-docs-inventario` (`state/crew/pm-docs-inventario/report.md`) e o inventário em `PerpetualMiner@cc92a1ca` (branch `pi/docs-inventario`, `docs-inventario.md`), sobre `origin/main@284ecb92`.

## Princípio do dono (2026-11-23)

Apagar o que é duplicado, sedimento ou no-op. O CODING_STANDARDS guarda só as regras que nenhuma lint rule ou trava já garante. "O contexto da arquitetura é a própria codebase."

## Fatos do inventário (em `284ecb92`)

- São 153 `.md` e 1,15 MB. Os maiores blocos são `docs/design/` (35 arquivos, 348 KB), `features/` do verify (27 arquivos, 180 KB) e `docs/` sem design (19 arquivos, 163 KB).
- Cada tela é descrita três vezes: em `docs/design/<tela>`, na skill de superfície e em `features/<tela>.md`. Só `features/` tem trava de CI.
- Apagar a pasta `docs/arquivos/` inteira desliga a regra `indice-de-arquivos` em silêncio.
- No CODING_STANDARDS, dependem só de revisão: a tabela de skills (duplicada), a regra 6, partes das regras 1, 3, 7, 8 e 11 e "What blocks a merge". `test_registro_da_pr.js` lê a linha que começa com `15. `.
- Achados laterais: a regra 6 aponta para o arquivo errado da C8; a linha de base de `tokens-veio` aceita `painel/painel.css` sem exceção documentada; `lancamento-da-conexao.md` e `commit-verde.md` se contradizem; `envio-no-complemento.md` descreve `bridge/`, que já não existe.

Status em 2026-11-23: nada decidido ainda. A conversa vem depois do glossário.
