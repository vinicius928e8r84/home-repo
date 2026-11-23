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

## Decidido em 2026-11-23, rodada 2

- **Termo** substitui Palavra: é o que o Cartão ensina, com uma ou mais palavras. "palavra" passa a ser só a palavra solta. Evitar: palavra-chave, keyword.
- **Frase**: o texto que a pessoa minerou, guardado no Histórico com o seu Idioma e o seu Contexto. Qualquer tamanho conta, e o que ainda não foi minerado não é Frase.
- A Exportada sai do glossário e ganha uma issue para decidir, depois da campanha, se o recurso .txt sai do produto.
- Tipo de nota sai do glossário. Contra a recomendação do chief, que era manter o nome do Anki.
- Ficam como nomes de tela Painel, Boas-vindas, Minerar de uma foto, Ajustes de envio e IA dos cartões. Custos sai. Nas palavras do dono, "o glossary tem que espelhar no código e na experiência".
- O ADR 0001 diz que nome novo no código segue o glossário. Os nomes antigos viram issues de renomeação depois da campanha.
- A regra `glossario-so-linguagem` reprova crase, a linha `_Nome no código_` e definição com mais de duas frases.
- O que sai do glossário não vai para nenhum outro doc.

## Achados (2026-11-23)

- Os dois arquivos foram para `docs/` pelo próprio dono no commit `vinicius928e8r84/PerpetualMiner@fbdcee51` (19/11). Esse commit também criou `scripts/ci/test_docs_fora_da_raiz.js`, que reprova se os arquivos estiverem na raiz. A mensagem do commit não dá o motivo. Pergunta Q15 da rodada 3.
- O inventário dos `.md` foi feito pelo worker `pm-docs-inventario` (relatório em `state/crew/pm-docs-inventario/report.md`; inventário em `pi/docs-inventario@cc92a1ca`, `docs-inventario.md`). Ver [dieta dos .md](dieta-dos-md.md).

## Decidido em 2026-11-23, rodada 3 (o dono confirmou a lista inteira)

- `glossary.md` e `CODING_STANDARDS.md` voltam para a raiz, e `scripts/ci/test_docs_fora_da_raiz.js` é apagado. A volta desfaz `fbdcee51`.
- Relações: `Fonte → Minerar → Frase (no Histórico) → Enviar ao Anki → Envio (um por Idioma) → Cartão (um por Termo) → Baralho`.
- As Ambiguidades resolvidas que ficam: cartão (só o item do Anki), termo e palavra, nível, estilo e sub-baralho, e trecho (não é Frase; é Marcação até ser minerado). A de "grupo" sai.
- Execução: uma PR feita por um worker, já, em paralelo aos lotes da campanha. O mesmo worker abre as issues (textos de tela com o nome velho, o .txt da Exportada e uma por conceito a renomear no código), marcadas para depois da campanha.
- Merge: o chief deixa a PR verde e revisada e avisa, e o dono mescla.
