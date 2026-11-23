# PerpetualMiner: o glossário fala só de linguagem

Fonte: o grilling de 2026-11-23 com o dono (páginas lavish `.lavish/pm-glossario*.html`). Base: `docs/glossary.md` em `vinicius928e8r84/PerpetualMiner@284ecb92`, com 260 linhas, 16,5 KB e 44 termos.

## Decidido em 2026-11-23

- O glossário fala só da linguagem do domínio: nada técnico, nenhuma regra de código, nenhum termo óbvio (botão, componente).
- `docs/glossary.md` e `docs/CODING_STANDARDS.md` voltam para a raiz. O glossário mantém o nome `glossary.md`, não vira `CONTEXT.md`, e por isso `docs/agents/domain.md` continua a redirecionar os skills para ele.
- Todas as linhas `_Nome no código_` saem.
- As notas "a tela de hoje ainda diz X" viram issues e saem do glossário. O dono lembrou que as funções também usam outro vocabulário, e isso pode merecer um ADR (pergunta em aberto).
- Cada definição tem uma ou duas frases dizendo o que a coisa é, mais a linha `_Avoid_`.
- Saem os termos Extensão, Área, Popup, Overlay, Complemento, Abridor, Consertar sozinho, Motor, Remessa, Detalhes, Veio e Voz.
- O dono achou "Palavra" genérica e ambígua, "Frase" aberta demais, "Exportada" quase sem uso e "Tipo de nota" um nome ruim. Esses quatro voltaram para a rodada 2.
- Princípio do dono para toda a documentação: apagar o que é duplicado, sedimento ou no-op. O CODING_STANDARDS deve guardar só as regras que nenhuma lint rule ou trava já garante. "O contexto da arquitetura é a própria codebase." O inventário está com o worker `pm-docs-inventario`.

Relacionada: [campanha da nota 10](campanha-nota-10.md). Nenhuma mudança de comportamento entra enquanto a campanha durar.
