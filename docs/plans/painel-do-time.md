# Plano: painel do time e conversa entre chief e workers

Pedido do dono em 2026-11-23: ver o time numa olhada, com a cota da conta Claude, guardar números para depois, classificar as PRs pelo propósito, acordar o chief só quando vale, deixar o worker falar com o chief e levar ao dono só o que é escolha dele.

Este documento é só o plano. Parte da `main` em `fbc296c` (`crew.py` com 943 linhas e 43.113 bytes) e conta com o plano da frota durável (`docs/plans/frota-duravel.md`, PR #15), que fica com detecção, causa e retomada de worker parado. Aqui, "frota PR N" é a linha N da tabela "Ordem das PRs" daquele plano.

## O que foi medido

- Sessões do Pi em `~/.pi/agent/sessions/<cwd codificado>/<data>_<id>.jsonl`. Cada resposta do modelo é uma linha `message` com `role: assistant`, `model`, `thinkingLevel`, `usage` (`input`, `output`, `cacheRead`, `cacheWrite`, `cost`), `stopReason` e, no erro, `errorMessage`. Ler as 114 sessões desta máquina (46 MB) leva 0,18 s: sem leitura incremental.
- O tamanho do contexto agora é o `usage` da última resposta: `input + cacheRead + cacheWrite + output`. É o cálculo do `ctx.getContextUsage()` do Pi.
- Pelo claude-bridge, o `cost` vem zerado (`totalFromProvider: false`).
- Cada compactação é uma linha `compaction` na sessão, com hora e `tokensBefore`.
- `~/.pi/agent/models-store.json` tem, por modelo, o nome ("Claude Opus 5.5"), a janela (`contextWindow`: 1.000.000).
- O `.pi/settings.json` do home-repo compacta o Opus 5.5 com `reserveTokens` 850.000, ou seja, aos 150k de 1M (D20). O global faz o mesmo com o Sonnet 5.5.
- O pi-claude-bridge recebe do Claude Code um `rate_limit_event` por requisição e o entrega ao hook `after_provider_response` do Pi como cabeçalhos `anthropic-ratelimit-unified-*`: `status` (`allowed`, `allowed_warning`, `rejected`), `overage-status`, e uso e reset das janelas `5h` e `7d` (`src/rate-limit.ts`). `isUsingOverage` e `overageInUse` não viram cabeçalho.
- `crew.py tell chief "..."` falha: `no worker named 'chief'`. O worker não tem como falar com o chief; o `ask` só registra Decisão do dono.
- O vigia já não avisa por turno (`turn_ended` fora do `NOTIFY`, PR #6) e o "parado" já é 20 min sem mudar tela nem commits (`--stall 20`).
- `state/` não vai para o git.

## Princípios

1. O painel só lê arquivos. Quem chama `herdr`, `git` e `gh` é o vigia, que grava o que viu; o painel lê em menos de 1 s com 45 workers.
2. Números vêm de dado estruturado (sessão do Pi, `meta.json`, `state.json`, catálogo do Pi), nunca da tela.
3. Tudo determinístico vai para Python com teste (`test_crew.py`); o skill do chief guarda só o que não dá para checar.
4. Não duplicar a frota durável: o painel mostra os estados que ela cria ("PAROU por X", "em risco: X"); não os detecta de novo.
5. Código novo nasce em módulos (`crew_painel.py` e afins), como o `crew_remote.py` da PR #11: a catraca reprova `crew.py` maior (D49, D55).

## 1. Painel do time: `crew.py time`

Uma linha por worker, quem precisa de atenção no topo. O nome `time` é do dono; `board` (o Quadro) passa a usar as mesmas linhas na seção dos workers, para não haver duas versões.

```
! home-crew-na-vps    home-repo · implement  Sonnet 5.5 high  ERRO: 401 authentication_error  aberto 10:12  faltam 62k até compactar  PR #11 13438c9 espera conserto do CI
! home-freios-script  home-repo · implement  Sonnet 5.5 high  parado há 34 min  aberto 11:02 · turno 41 min  faltam 18k até compactar  PR #12 d9687ff espera revisão
? home-fila-merge     home-repo · merge  Opus 5.5 medium  espera dono: Mesclar a #11 antes da #5?  aberto 12:30  faltam 77k até compactar  sem PR
  home-painel-do-time home-repo · plan  Opus 5.5 medium  trabalhando  aberto 13:32 · turno 12 min  faltam 61k até compactar · 1 compactação (14:02)  sem PR
- home-skills-links   home-repo · implement  Sonnet 5.5 high  fechado  aberto 11:40 · fechou 13:53  PR #13 mesclada
```

| Coluna | Fonte | Regra |
|---|---|---|
| marca | estado | `!` erro, parou ou parado; `?` espera alguém; vazio rodando ou ocioso; `-` fechado |
| nome, repo, tipo | `meta.json` (`name`, `repo`, `type`) | — |
| modelo e esforço | última resposta da sessão (`model`, `thinkingLevel`); sem resposta ainda, `meta.json` (`model`, `thinking`) | nome do catálogo do Pi sem "Claude ": "Opus 5.5 medium". Modelo fora do catálogo aparece com o id inteiro |
| contexto | `usage` da última resposta; janela e limiar de compactação do catálogo e do `settings.json` (o do worktree sobre o global) | "faltam 61k até compactar" (D56). Depois de uma compactação, até a próxima resposta, "compactou às HH:MM" |
| compactações | linhas `compaction` das sessões do worker | "2 compactações (11:40, 13:05)"; nada quando não houve |
| estado | `state.json`, decisões e perguntas abertas, estados da frota PR 2, `stalled` do último `watch.json` | um só, nesta ordem: ERRO (com os primeiros 60 caracteres da mensagem), PAROU por X, parado há N min, espera dono (título da Decisão), espera chief (título da Pergunta), trabalhando, ocioso há N |
| abriu, fechou, turno | `meta.json` (`started`, `closed`); `state.json` (`at` do último `working`) | horário local HH:MM; "turno N min" só trabalhando |
| PR, head, o que espera | cache de PRs do vigia (seção 1.1) | "espera CI", "espera conserto do CI", "espera revisão", "espera Prova real", "espera merge", "mesclada" |

Ordem das linhas: `!`, depois `?`, depois rodando, depois ociosos; dentro de cada grupo, o mais antigo primeiro. Fechados só com `--fechados` ou quando fecharam nas últimas 12 horas.

Antes da frota PR 2, ERRO é o `errorMessage` da última resposta com `stopReason: "error"`; depois, vale a classificação dela ("PAROU por credencial").

A sessão do worker: o campo `session` que a frota PR 1 grava no `state.json`. Até lá, os `.jsonl` da pasta do cwd do worktree criados depois do `started`, somados (um `/new` abre outro arquivo).

### 1.1 O que o vigia passa a gravar para o painel

- A cada 2 minutos, uma chamada `gh pr list --state all --json number,headRefName,headRefOid,isDraft,state,reviewDecision,statusCheckRollup,body` por repo com worker aberto, gravada em `state/crew/prs.json`. O painel casa a PR pela branch do worker.
- No `watch.json` de cada worker: o head da branch, que ele já lê para o "parado".
- "O que espera" sai de regra fixa: rascunho ou checks rodando = "espera CI"; check vermelho = "espera conserto do CI"; sem registro de revisão `CLEAN` no head = "espera revisão"; atenção ALTA sem Prova real no head = "espera Prova real"; tudo verde = "espera merge".

### 1.2 Cota da conta Claude

A cota é da conta, não do worker: uma linha só, no topo do painel e do Quadro.

```
Cota Claude: 5h 62% (zera 15:00) · semana 81% (zera seg 09:00) · Extra Usage: não · lida 14:31
```

- Extensão nova e pequena, `.pi/extensions/crew-cota.ts`: no `after_provider_response`, se houver cabeçalho `anthropic-ratelimit-unified-status`, grava em `state/crew/cota.json` (temporário e `rename`) `{at, status, reset, overage_status, overage_reset, janelas: {"5h": {uso, reset}, "7d": {uso, reset}}, por: <worker>}`. O último a gravar vale. Fica fora do `crew-state.ts` para não brigar com a frota PR 1, que mexe nele.
- O chief a carrega sozinho (está em `.pi/extensions/` do home-repo). O worker de outro repo não: o `spawn` passa a abrir o Pi com `-e crew-cota.ts` além do `-e crew-state.ts`.
- "Extra Usage: sim" quando `status` é `rejected` e `overage-status` é `allowed` ou `allowed_warning`. Como os campos que diriam isso direto não viram cabeçalho, a regra é confirmada na PR com um valor real; se não bastar, a extensão também lê o `overage-reset`.
- Escala do `utilization` (0 a 1 ou 0 a 100): conferida com um valor real no começo da PR, antes do teste.
- Mais de 30 minutos sem leitura: "lida há N min", para não mostrar número velho como atual.
- Workers da VPS usam a conta de lá: a cota da VPS fica para quando a #11 entrar.

O vigia acorda o chief (seção 4) ao passar de 80% em qualquer janela e ao chegar no limite (`status` `rejected`), e ao entrar no Extra Usage. Um aviso por janela e por motivo: só avisa de novo depois que o `reset` daquela janela passar. O "parou: limite" de cada worker continua com a frota PR 2; este aviso é o da conta, antes de alguém parar.

## 2. Métricas

Ao fechar um worker (`close`), o `crew.py` grava uma linha em `state/crew/metricas.jsonl`:

`worker`, `repo`, `tarefa`, `tipo`, `modelo`, `esforco`, `abriu`, `fechou`, `minutos_trabalhando`, `turnos`, `tokens` (`entrada`, `saida`, `cache_lido`, `cache_escrito`), `compactacoes` (a hora e o `tokensBefore` de cada uma), `pr`, `categoria`, `atencao`, `mesclada`, `sessoes`. Este worker, no meio do plano: 46 de entrada, 14.860 de saída, 1.179.416 de cache lido, 86.811 de cache escrito.

- Tokens: soma do `usage` de todas as respostas das sessões do worker, compactações incluídas.
- Custo não se grava (D57): sai depois dos tokens.
- `minutos_trabalhando`: soma dos intervalos `working` do `state.json`, acumulada pelo vigia.
- Categoria e atenção: da linha do corpo da PR (seção 3), pelo cache de PRs.

Relatório: `crew.py metricas [--por tarefa|tipo|categoria|repo|modelo] [--desde AAAA-MM-DD]`, uma tabela com workers, horas, tokens por tipo e compactações por grupo, mais o total. `--abertos` inclui os workers ainda abertos, lidos na hora.

Retroativo: `crew.py metricas --recolher` grava os workers já fechados cuja sessão está no disco.

Os workers da VPS (PR #11) gravam a linha no `state/` de lá; a sincronização da #11 a traz. Fica para quando a #11 entrar.

## 3. Categoria de PR

Cada PR diz o propósito numa linha do corpo, separada da atenção:

```
**Categoria:** conserto
```

Valores, lista provisória (D58; o dono fará a definitiva): `freio` (regra, lint, check, guarda), `conserto`, `recurso` (recurso novo), `limpeza`, `refatoração`, `plano` (plano ou documento), `pesquisa`. Uma só por PR; uma PR que é duas coisas vira duas PRs.

- A lista mora num lugar só, `scripts/freios/categorias.json`; o Registro, o template e as métricas a leem dali. Trocar a lista é editar esse arquivo, que vale depois de mesclado (o Registro roda as regras da base).
- O check Registro da PR (PR #14, `scripts/freios/registro_da_pr.py`) passa a exigir uma única linha `Categoria:` com um desses valores, pelo mesmo caminho da linha `Atenção:` (`valores_de`, sem caixa e sem acento). Falta ou valor fora da lista: o check falha dizendo os valores válidos.
- `.github/PULL_REQUEST_TEMPLATE.md` ganha `**Categoria:**` abaixo de `**Atenção:**`, e o comentário aponta para o `categorias.json`.
- Como o Registro roda as regras da base, a exigência só vale para PRs abertas depois de mesclada; a própria PR que a cria ainda passa sem ela.
- Sem rótulo do GitHub (D58).

## 4. Supervisão filtrada

O vigia acorda o chief (pelo inbox da PR #6) só por:

| Motivo | Evento |
|---|---|
| cota | 80% da janela de 5h ou da semanal, limite alcançado, entrada no Extra Usage (seção 1.2) |
| erro ou parou | os da frota PR 2 (`parou` com a causa), `spawn_failed`, `never_started`, `not_pi`, e `gone` sem `closing` até a frota cobrir |
| parado | `stalled` (20 min sem mudar tela, commits nem atividade; a frota soma o `activity_at`) |
| pedido | `decision_needed` (para o dono) e `question_for_chief` (seção 5) |
| PR pronta para revisão | PR aberta, fora de rascunho, CI verde e sem registro de revisão no head; ou `report_written` de worker sem PR (pesquisa, plano sem PR) |
| PR pronta para merge | revisão `CLEAN` no head, Registro verde e, com ALTA, Prova real no head |

O resto (`merged`, `closed`, `spawned`, `told`, `turn_ended`, `report_written` de quem já tem PR, contexto abaixo de 10% até compactar) entra no resumo: a cada 30 minutos, se houve algo, uma linha só no inbox: "Resumo 14:00–14:30: 2 PRs mescladas (#13, #9), 3 turnos, home-x a 8k de compactar". Sem nada, sem resumo.

- Um aviso de acordar por motivo e por rodada, agrupado como na frota ("PR pronta para revisão: #12 e #14").
- O texto do aviso traz o título da Decisão ou da Pergunta, nunca só o número.
- `--resumo 30` no `watch`; o resumo tem cursor próprio.

## 5. `crew.py ask --para chief|dono`

Glossário: Decisão é o que só o dono responde. O que o worker quer do chief passa a se chamar Pergunta (termo novo: entra no glossário numa rodada do dono).

- `ask "..." --recommend "..." --para chief` grava em `decisions.jsonl` com `para: "chief"` e id próprio (`P1`, `P2`…), emite `question_for_chief` e acorda o chief na hora.
- `ask ... --para dono` é a Decisão de hoje (`D56`…), que vai para a fila do dono (seção 6).
- Sem `--para`, vale `chief`. O chief responde com `answer P3 "..."` (entrega ao worker como hoje) ou sobe ao dono com `crew.py subir P3`, que vira uma Decisão com o mesmo texto e o worker avisado.
- `tell chief "..."` passa a funcionar: grava no inbox do chief (painel do `watch.heartbeat`). Serve para aviso sem pergunta.
- O brief do `spawn` troca o bloco "Decisão que cabe ao dono" por dois comandos: `ask --para chief` para dúvida de trabalho, `ask --para dono` com `--titulo`, `--muda`, `--opcao` e `--recommend` para escolha do dono.
- O Quadro separa "Perguntas ao chief" de "Decisões esperando por você"; só a segunda entra no bloco "Suas decisões".

## 6. Fila de decisões do dono

Uma página fixa, `state/crew/decisoes/index.html`, refeita pelo `crew.py` a cada `ask --para dono`, `answer` e `subir`.

- Cada Decisão é um cartão: título em linguagem normal (o `--titulo`, até 80 caracteres), "o que muda" (`--muda`, uma frase), as opções (`--opcao`, repetível, de 2 a 4) com a recomendada marcada e o porquê (`--recommend`), o repo e o worker em letra miúda, há quanto tempo espera. O número fica no canto, nunca sozinho.
- `ask --para dono` sem `--titulo` ou com menos de duas opções falha, dizendo o que falta. Decisões antigas (D1 a D55) aparecem com a pergunta como título e "sem opções: responda em texto".
- O dono marca uma opção ou escreve em cada cartão que quiser e clica "Enviar respostas" uma vez. A página segue o playbook `input` do lavish.
- Quem recebe: o vigia mantém um `lavish-axi poll` da página como processo filho e lê a saída a cada rodada. Cada resposta vira `answer Dn "..."` (gravada e entregue ao worker, como hoje) e o chief é acordado com uma linha por Decisão respondida, com o título. Com o vigia parado, as respostas esperam na fila do lavish.
- Aberta uma vez com `npx -y lavish-axi state/crew/decisoes/index.html`; o link vai no chat e no bloco "Suas decisões".
- Sem aviso no celular.

A conferir no começo da PR, antes de escrever o resto: se o lavish recarrega a página quando o arquivo muda, e se "Send & End" encerra a sessão de vez (o botão da página precisa ser "Enviar", não "Encerrar"). Se não recarregar, a página faz a própria leitura de um `decisoes.json` ao lado a cada 30 s.

## 7. Regras de chat do chief

No skill `chief-of-staff`, o bloco "On a `[crew]` message" vira:

- Uma Decisão sempre aparece com o título e a recomendação; o número vem entre parênteses, nunca sozinho.
- Uma mensagem ao dono leva um aviso curto só; o resto espera a próxima ou vai no "Suas decisões".
- Lavish só quando o dono vai escolher entre opções ou ler uma tabela ou um diagrama; resposta de uma linha fica no chat. A fila de decisões é a exceção fixa.

O que dá para fazer em código vai para o código: o bloco "Suas decisões" do `board` e todo aviso do vigia passam a imprimir título e número juntos, e o teste falha se um aviso citar `D\d+` sem o título.

## 8. Ordem das PRs

Toda PR mexe em caminho sensível do Registro: é ALTA, com revisão de outro agente e Prova real. A divisão do `crew.py` (item 8 da ordem de merge do chief) vem antes, porque a catraca reprova o `crew.py` maior.

| # | PR | Mexe em | Depende de | Teste |
|---|---|---|---|---|
| 1 | `ask --para`, Perguntas ao chief, `subir`, `tell chief`; brief novo | `crew_conversa.py`, `crew.py`, `test_crew.py` | divisão do `crew.py` | worker falso pergunta ao chief: inbox recebe na hora; `subir` vira Decisão; `tell chief` grava no inbox |
| 2 | Painel `time`: sessão do Pi, catálogo, ordem das linhas; o Quadro usa as mesmas linhas | `crew_painel.py`, `crew.py`, `test_crew.py` | 1 (estado "espera chief") | sessões `.jsonl` de exemplo tiradas das reais (com `/new` e com compactação); 45 workers falsos em menos de 1 s |
| 3 | Cota da conta Claude: `crew-cota.ts`, linha no painel, avisos de 80%, limite e Extra Usage | `.pi/extensions/crew-cota.ts`, `crew_painel.py`, `crew.py` | 2 | cabeçalhos reais gravados viram o `cota.json` esperado; relógio falso: um aviso por janela até o reset |
| 4 | Cache de PRs do vigia e coluna PR, head, o que espera | `crew_painel.py`, `crew.py` | 2 | saídas de `gh` gravadas em arquivo: cada caso de "espera" |
| 5 | Supervisão filtrada, resumo de 30 min, PR pronta para revisão e para merge, regras de chat do chief | `crew.py`, `chief-of-staff/SKILL.md`, `test_crew.py` | 4, frota PR 2 | relógio falso: o resumo sai a cada 30 min só com novidade; `merged` não acorda; aviso sem título reprova |
| 6 | Categoria no Registro da PR e no template | `scripts/freios/`, `.github/PULL_REQUEST_TEMPLATE.md` | #14 mesclada | casos do `test_registro_da_pr.py`: sem linha, duas linhas, valor fora da lista, valor com acento, lista trocada no `categorias.json` |
| 7 | Fila de decisões do dono na página lavish e respostas pelo vigia | `crew_decisoes.py`, `crew.py` | 1, 5 | saída de `poll` gravada vira `answer` e aviso ao chief; Prova real: uma rodada com o dono |
| 8 | Métricas: linha no `close`, `metricas`, `--recolher` | `crew_metricas.py`, `crew.py` | 2, 6 | sessões de exemplo: somas e compactações batem com a conta à mão |

Com a frota durável, a ordem sugerida é: divisão do `crew.py` → painel 1 → painel 2 → painel 3 → frota 1 → frota 2 → painel 4 → painel 5 → painel 6 (assim que a #14 entrar) → frota 3 a 9 e painel 7 e 8, intercalados. Painel 5 e frota 2 mexem no mesmo `notify`; quem vier depois rebaseia. O aviso de cota da PR 3 entra direto como motivo de acordar, sem esperar a PR 5.

## O que pode ser cortado

O essencial são as PRs 1, 2 e 5: o worker fala com o chief, o chief vê o time numa olhada e só é acordado quando vale. Cabe em 3 PRs; com a cota (3) e a categoria (6), 5.

| Corte | O que se perde | Ganha |
|---|---|---|
| PR 7 inteira (página lavish) | o dono responde no chat, pelo bloco "Suas decisões" que já existe, agora com título e opções | a parte mais arriscada: processo `poll` vivo e recarga de página |
| PR 8 inteira (métricas) | os números; as sessões ficam no disco para um `--recolher` futuro | uma PR |
| PR 4 (coluna PR) | o painel mostra só a branch e o head; "PR pronta" no vigia passa a vir só do relatório | as chamadas ao `gh` |
| Extra Usage na PR 3 | ficam só as porcentagens e o limite | a regra que ainda pede valor real |
| `subir` | o chief sobe com um `ask --para dono` novo e responde a Pergunta com "subiu" | um comando |

## Decisões do dono

Registradas com `crew.py ask`, todas respondidas:

1. **Contexto: contar até a compactação ou até a janela** (D56) — decidida: até a compactação, e marcar quantas compactações houve e quando, no painel e nas métricas.
2. **Custo: estimar pelo preço da API** (D57) — decidida: não; só tokens, e o custo se calcula depois.
3. **Categorias de PR e onde marcar** (D58) — decidida: só a linha no corpo; as sete são provisórias, num arquivo só.
4. **Quantas PRs fazer** (D59) — decidida pelo chief, sem objeção do dono: as oito, na ordem acima, com corte possível depois da 6.
