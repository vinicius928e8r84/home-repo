# Plano: frota durável e contínua

Pedido do dono em 2026-11-23: nenhum worker morre calado; cada um continua sozinho depois de queda de energia, reinício do PC, queda de internet, API fora do ar ou limite de uso, e disco cheio; e o chief sabe na hora quando um worker para.

Este documento é só o plano. Parte da `main` em `fbc296c`, já com as PRs #7, #1 e #6 (`crew.py` com 943 linhas). Só o que é da VPS espera a #11.

## O que aconteceu e o que foi medido

- 11:00: o disco C: chegou a 87 MB livres. 14 workers pararam com `ENOSPC: no space left on device, write`. Os arquivos de estado deles dizem `{"state": "idle", "turns": 2}`, igual a um turno que terminou bem. O vigia emitiu `turn_ended` ("terminou um turno") e o chief só soube lendo painel por painel.
- O restore do Herdr reabriu workers como `claude --resume`, sem contexto. Com `resume_agents_on_restore = true`, o Herdr só sabe o caminho da sessão do Pi (`herdr pane get`, `agent_session`): reabre sem `crew-state.ts`, `--approve` e `CREW_STATE_FILE`, e o worker volta mudo. Nunca foi testado.
- Workers que rodaram `pi` dentro do próprio painel geraram "o painel fechou" falso: o Pi filho herda `CREW_STATE_FILE`, carrega o `crew-state.ts` e escreve `gone` no estado do pai ao sair.
- Erros reais nas sessões do Pi (`errorMessage` em `~/.pi/agent/sessions`): 17× `ENOSPC: no space left on device, write`; 7× `401 ... authentication_error`; 5× `400 ... credit balance is too low`; 10× `Cut boundary ...`/`Session boundary ...` e 1× `Claude Code process exited with code 3` (claude-bridge); 1× `safeguards flagged this message`; 3× `Operation aborted`.
- PC (11:30): C: com 9,1 GB livres; 1,2 GB de RAM livre de 16 GB; 43 workers abertos (35 `node`, 1,8 GB; 13 `claude.exe`, 2,4 GB). Os worktrees não têm `node_modules`; 3 pastas são órfãs. O espaço foi para o WSL, o Docker (10 GB) e o `vm_bundle` do Claude (8 GB).
- VPS: 60 GB livres de 193 GB, 5 GB de RAM disponíveis de 16 GB, `crew-herdr.service` ativo.

## Princípios

1. Um estado por causa. "Parou" nunca se confunde com "terminou": um turno que acaba sem relatório e sem decisão aberta é sempre `parou`, com a causa que se conseguir provar.
2. A fonte da causa é dado estruturado, não tela: o `crew-state.ts` grava o desfecho do turno (o `stopReason` e o `errorMessage` da última resposta). O vigia acrescenta o que o Pi não vê: disco, memória, painel, processo, rede, VPS. Ler a tela do painel fica como último recurso e só para descrever, nunca para decidir.
3. A classificação mora em Python (`crew.py`), com uma tabela de padrões testada contra as mensagens reais acima. Mensagem nova vira linha da tabela e caso de teste, não texto no AGENTS.md.
4. Um aviso por causa, agrupado: "PAROU por disco cheio: 14 workers (lista)". Nada de 14 linhas iguais.
5. Retomar sozinho só o que é transitório e tem como se provar que passou (o disco voltou, a rede voltou, o limite zerou). O resto espera o chief ou o dono, com um aviso só.

## 1. Detecção

### O que o `crew-state.ts` passa a gravar

O arquivo de estado ganha campos; os que já existem não mudam de sentido.

| Campo | Quando muda | Para quê |
|---|---|---|
| `ended`: `ok`, `error`, `aborted` | `agent_settled` (o fim real do turno, depois das tentativas do próprio Pi) | separa "terminou" de "parou" |
| `error` (texto, cortado em 500 caracteres) | `message_end` da resposta com `stopReason` `error` ou `aborted`; limpo no `agent_start` | a causa |
| `activity_at` | `turn_start`, `tool_execution_start/end`, `message_update` (no máximo um a cada 15 s) | travado sem progresso |
| `tool`: nome, comando curto, início | `tool_execution_start`; some no `tool_execution_end` | processo filho pendurado |
| `alive_at`, `pid` | um temporizador de 30 s (sem segurar o processo vivo) | o Pi morreu ou congelou sem `session_shutdown` |
| `session` (caminho do `.jsonl`) | `session_start` | retomada |

Pi aninhado: ao iniciar, a extensão grava `CREW_STATE_OWNER=<pid>` no próprio ambiente. Um Pi filho que encontra essa variável com outro pid não grava nada nem fala com o Herdr. Rodar `pi` dentro do painel deixa de ser perigoso.

Disco cheio: a gravação do estado também falha. A extensão guarda o último estado em memória e regrava a cada batida. O vigia mede o disco por conta própria e, com disco crítico ou um `ENOSPC` na frota, trata `alive_at` velho como `parou: disco cheio`, nunca como `Pi congelado`, e não roda `relaunch` até o disco voltar.

O próprio vigia também grava no disco (`watch.heartbeat`, `events.jsonl`, o inbox do chief). Cada gravação passa a tratar `OSError`: o evento ou aviso fica numa fila em memória e é regravado a cada rodada. Enquanto o inbox não grava, o aviso de disco cheio vai por `herdr notification show`, que não usa o disco. Como o heartbeat pode ficar velho com o vigia vivo, `watcher_alive` passa a conferir também o pid gravado, para não abrir um segundo vigia.

### Estados no board e avisos

Cada linha é um estado distinto no `board` e um aviso "PAROU por X" (ou "em risco: X") ao chief, pelo inbox da PR #6.

| Modo de falha | Sinal | Estado | Como evitar falso positivo |
|---|---|---|---|
| Erro do Pi no fim do turno | `ended=error` e `error` sem padrão conhecido | `parou: erro do Pi` | só com `ended=error` vindo do `agent_settled`; as tentativas internas do Pi (`agent_end` seguido de nova tentativa) não contam |
| Disco cheio | `error` casa `ENOSPC` | `parou: disco cheio` | padrão literal do Node |
| Token inválido | `401`, `authentication_error`, `invalid x-api-key` | `parou: credencial` | padrão do provedor |
| Crédito esgotado | `credit balance is too low`, `billing` | `parou: crédito` | padrão do provedor; nunca se mistura com limite |
| Limite de uso da janela (5 h, semana) | `usage limit`, `limit reached`, `resets at` | `parou: limite` (com a hora de reset, quando a mensagem traz) | padrão do provedor |
| API instável | `5xx`, `overloaded`, `529`, e `429`/`rate_limit` por minuto | `parou: API fora` | só depois do fim real do turno, quando as 3 tentativas do Pi já falharam |
| Rede | `ECONNRESET`, `ENOTFOUND`, `EAI_AGAIN`, `ETIMEDOUT`, `fetch failed`, `socket hang up` | `parou: rede` | confirmado pelo teste de rede do vigia (abaixo) |
| Bridge do Claude | `Cut boundary`, `Session boundary`, `Claude Code process exited` | `parou: claude-bridge` | padrão do bridge |
| Recusa do modelo | `safeguards flagged` | `parou: recusa do modelo` | padrão do provedor |
| Abortado | `ended=aborted` | `parou: interrompido` | um Esc de alguém no painel; não se retoma sozinho |
| Turno normal sem saída | `ended=ok`, sem relatório, sem decisão aberta | `parou: sem relatório` | é o caso que o board já mostra como "parou sem relatório e sem pedir decisão"; o vigia passa a avisar |
| Painel morto | `herdr pane get` falha | `parou: painel fechou` | não conta quando o `close` marcou `closing` (PR #7) |
| Pi saiu, painel ficou | painel vivo, `agent` do Herdr vazio ou shell, `alive_at` velho | `parou: Pi saiu` | exige as duas coisas |
| Outro agente no painel | `agent` do Herdr diferente de `pi` | `parou: não é Pi` | já na main (`not_pi`) |
| Pi congelado | `state=working`, `alive_at` com mais de 3 min, painel ainda com Pi, disco fora do crítico | `parou: Pi congelado` | o temporizador roda mesmo com ferramenta longa; com disco crítico vale `disco cheio` |
| Travado sem progresso | `working`, sem `tool` em curso, `activity_at` com mais de 20 min | `em risco: sem progresso` | soma-se à tela e aos commits que o `stalled` da main já mede (`quiet_minutes`); resposta a decisão zera |
| Processo filho pendurado | `tool` em curso há mais de 30 min | `em risco: comando pendurado (bash: npm test)` | o tempo é por ferramenta; um `sleep` pedido não passa de 30 min |
| Nunca começou | já na PR #7 (`never_started`) | `parou: nunca começou` | — |
| Disco baixo | `shutil.disk_usage` dos discos de `~/worktrees`, `state/`, `~/.pi` e `%TEMP%` | da frota: `disco baixo` / `disco crítico` | limiar com histerese: avisa ao cruzar, só avisa de novo depois de voltar acima |
| Memória baixa | RAM livre (`GlobalMemoryStatusEx` no Windows, `/proc/meminfo` na VPS) | da frota: `memória baixa` | média de 3 rodadas, para não avisar por um pico |
| Sem internet | resolução de DNS e TCP 443 em `api.anthropic.com` e `github.com` | da frota: `sem rede` | dois alvos e duas rodadas seguidas |
| VPS inalcançável | `ssh` sai com 255 na sincronização (PR #11) | da frota: `VPS fora`; os workers dela aparecem "sem notícia desde HH:MM", não "parou" | duas sincronizações seguidas; quando volta, um aviso "VPS voltou" |
| Vigia morto | heartbeat com mais de 90 s | da frota: `vigia parado` | a guarda de fim de turno da PR #1 religa; o board diz quando não conseguiu |

O `turn_ended` continua no `events.jsonl`, mas não acorda o chief (como a PR #6 já faz). O texto ao chief deixa de ter "terminou um turno": ele recebe "PAROU por disco cheio: nova-pesquisa-130, nova-pesquisa-135 (+12). Disco C: 87 MB livres." O board ganha a seção "Pararam", agrupada por causa, acima de "Rodando agora".

## 2. Retomada

### O que se retoma sozinho

O vigia retoma com `crew.py resume <worker>`: manda ao painel `[chief] Retomada automática: o seu último turno parou por <causa>. Confira git status e continue de onde parou.` Cada tentativa fica em `meta.json` (`retries`) e no `events.jsonl`; um turno que termina `ok` zera a contagem.

| Causa | Sozinho? | Condição antes de tentar | Tentativas e espera |
|---|---|---|---|
| disco cheio | sim | disco acima do limiar de spawn | sem limite de tentativas; espera o disco, não o relógio |
| rede | sim | teste de rede passa | sem limite; espera a rede |
| API fora, bridge | sim | — | 4 tentativas: 2, 5, 15 e 30 min; depois, o chief |
| limite de uso da janela | sim | passou a hora de reset (ou 30 min, quando a mensagem não diz) | uma por janela de reset; o dono recebe um aviso só |
| Pi congelado, Pi saiu, painel fechou, não é Pi | sim, por `revive` e `relaunch` (abaixo) | o worktree existe e o disco não está crítico | 2 tentativas, 1 e 5 min; depois, o chief |
| sem relatório | não: o chief lê o painel e decide | — | — |
| erro do Pi desconhecido | uma tentativa em 2 min; depois, o chief | — | 1 |
| credencial, crédito esgotado, recusa, interrompido | não: o dono | — | — |

O `429` por minuto (`rate_limit` sem janela de reset) é API instável: 2, 5, 15 e 30 min. Só o limite da janela de 5 horas ou da semana espera o reset.

Retomar muitos de uma vez gasta limite: a retomada vai em lotes de 4 workers a cada 2 minutos.

### Volta depois de reinício ou queda de energia

A conversa do worker vive no arquivo de sessão do Pi; o que se perde é o processo. A retomada passa a ser do crew, com o Herdr só disparando:

1. `spawn` abre o Pi com `--session-id crew-<worker>-<AAAAMMDDhhmm>`; o id fica no `meta.json`. Abrir de novo com o mesmo id devolve a mesma conversa.
2. Comando novo `crew.py relaunch <worker>`: põe `CREW_STATE_FILE` e `CREW_AGENT_NAME` no ambiente e roda o mesmo `pi --approve -e crew-state.ts --model <modelo do worker> --session-id <id>`. Na VPS, com o `herdr` e o `pi` próprios da PR #11.
3. O `crew-state.ts` registra no Herdr o comando de retomada do painel: `herdr pane report-agent-session <painel> --source crew --agent pi -- python <home>/scripts/crew.py relaunch <worker>`. No restore, o Herdr reabre o worker por esse comando, com extensão, modelo e ambiente. A integração pi v9 só informa o caminho da sessão e não se desliga por painel; falta provar que o registro do `crew`, feito depois, é o que vale. Se não for, `resume_agents_on_restore = false` e vale o passo 4 (D40).
4. `crew.py revive`: para cada worker aberto com painel morto, ou com painel vivo que não é Pi (por restore do Herdr ou por qualquer outro motivo; é o único tratamento de `não é Pi`), abre uma aba nova e roda `relaunch`. O painel antigo fica aberto, para nada se perder, e o chief recebe o aviso. Roda no início do vigia e no `board`.
5. Depois de voltar, o vigia manda a mensagem de retomada com a causa "o computador reiniciou". O turno que estava no meio se perde; a mensagem manda conferir o `git status`.

No PC, alguém precisa acordar depois do boot. Uma tarefa do Agendador de Tarefas "ao fazer logon" roda `crew.py boot`: sobe o servidor do Herdr, roda `revive` e liga o vigia. O vigia hoje exige o painel do chief vivo; passa a rodar sem ele, deixando os avisos no inbox, e o chief os lê quando abrir.

### Como se prova

`crew.py drill`, com um worker de brinquedo que guarda uma palavra no primeiro turno e a devolve num relatório depois da falha:

| Cenário | Como se provoca | Passa quando |
|---|---|---|
| restart do Herdr | `herdr server stop`, depois `herdr` | o painel volta Pi, o estado volta a bater, o relatório traz a palavra |
| Pi morto | `taskkill` no pid do `state.json` | `parou: Pi saiu` em até 1 min; `relaunch` sozinho; relatório com a palavra |
| painel fechado | `herdr pane close` | `revive` abre aba nova; relatório com a palavra |
| disco cheio | `CREW_DISK_FREE_OVERRIDE` baixo no vigia e um `ENOSPC` injetado no estado | aviso "PAROU por disco cheio" uma vez; retomada quando o override sobe |
| rede | erro `fetch failed` injetado e teste de rede falso | aviso uma vez; retomada quando a rede "volta" |
| VPS | `systemctl --user restart crew-herdr` e depois `sudo reboot` | os workers da VPS voltam com a palavra; o PC mostra "VPS fora" e depois "VPS voltou" |
| reinício do PC | manual, uma vez, com o roteiro do `drill --reboot` | depois do logon, o board mostra os workers de volta sem ninguém mexer |

Os cenários rodam no `test_crew.py` com Herdr falso; o `drill` usa Herdr e Pi de verdade.

## 3. Prevenção

### Disco

Limiares por disco medido, com histerese:

| Livre | Efeito |
|---|---|
| abaixo de 20 GB | aviso "disco baixo" ao chief |
| abaixo de 10 GB | `spawn` enfileira; aviso de novo |
| abaixo de 3 GB | "disco crítico": aviso ao chief com o que o `gc` liberaria |

Com 9,1 GB livres hoje, o `spawn` local já enfileiraria. O que fazer com WSL, Docker e o bundle do Claude é a D46.

### Limpeza

Fechamento automático (D45): a cada rodada, o vigia roda `close` de verdade em todo worker com relatório e branch na base há mais de 1 hora; a branch fica, e o chief recebe um aviso com os nomes.

`crew.py gc` (só lista; `--apply` executa):

- pastas de `~/worktrees` sem worker aberto (hoje 3) e `git worktree prune` em cada repo;
- `events.jsonl` acima de 5 MB: arquivado em `events-AAAAMM.jsonl.gz`;
- pastas de estado de workers fechados há mais de 30 dias.

O vigia roda o `gc` sem `--apply` uma vez por dia e manda o resumo ao chief; com "disco crítico" roda na hora.

### Teto de workers simultâneos

O `spawn` confere o que há antes de abrir: número de workers abertos no host, RAM livre (abaixo de 2 GB) e disco livre (abaixo de 10 GB). Acima do teto, o pedido sempre entra numa fila (`state/crew/queue.jsonl`) e o vigia o abre quando sobrar espaço, avisando o chief. Os tetos ficam em `fleet.json`, um por host: 10 no PC e 6 na VPS (D43).

## 4. A VPS como lugar durável

A VPS fica no ar sem depender do PC: o systemd religa o servidor do Herdr (`Restart=on-failure`, linger ligado), não há suspensão nem Windows Update, o disco é outro (60 GB livres) e a internet é de datacenter. O que deve rodar lá por padrão:

- Os workers de todo repo que não precisa do Windows: o `host` padrão de cada entrada do `repos.json` vira `vps`, e `--host local` fica para o que exige o PC (testes do Electron no Windows, extensão do Chrome com navegador, o que mexe em arquivos do PC).
- Um vigia da VPS, como serviço systemd do usuário: as mesmas detecções e retomadas para os workers de lá, com o PC desligado. Ele grava os avisos num inbox na VPS; o vigia do PC os puxa na sincronização da PR #11 e os entrega ao chief. O `boot` da VPS é o próprio systemd (`crew-keeper.service` com `crew.py boot`).
- O `drill` da VPS faz parte da prova da PR do vigia de lá.

Riscos: a VPS é uma só e já roda o firstmate; o claude-bridge precisa de login lá; com o PC desligado, o chief só lê os avisos quando voltar.

## 5. Ordem das PRs

#7, #1 e #6 já estão na main. Só a PR 9 e o `VPS fora` da PR 3 esperam a #11. Cada uma pequena, com teste que falha antes e passa depois.

| # | PR | Mexe em | Teste |
|---|---|---|---|
| 1 | Desfecho do turno no estado: `ended`, `error`, `activity_at`, `tool`, `alive_at`, `session`; guarda contra Pi aninhado | `crew-state.ts` | Pi de verdade com modelo que falha (chave inválida): `ended=error` e a mensagem; `pi -p` dentro do painel não mexe no estado do pai |
| 2 | Causas e avisos "PAROU por X": `classify`, estados do board, seção "Pararam", aviso agrupado | `crew.py`, `test_crew.py` | tabela com as mensagens reais de hoje; 14 estados com `ENOSPC` viram um aviso só |
| 3 | Saúde da frota: disco, memória, rede, VPS fora, vigia parado; gravações do vigia que sobrevivem a `ENOSPC`; `crew.py doctor` | `crew.py` | discos e rede falsos; histerese; ssh que sai com 255; `open` que falha com `ENOSPC` não derruba o vigia e o aviso sai depois |
| 4 | Teto e fila no `spawn`, `fleet.json` | `crew.py` | spawn acima do teto vai para a fila; o vigia abre quando libera |
| 5 | Retomada automática: `resume`, política por causa, lotes | `crew.py` | relógio falso: tentativas, esperas e o fim no chief |
| 6 | Volta depois de reinício: `--session-id`, `relaunch`, `revive`, comando de retomada no Herdr | `crew.py`, `crew-state.ts` | `drill` real: restart do Herdr, Pi morto, painel fechado |
| 7 | Boot do PC: `crew.py boot`, tarefa de logon, vigia sem painel do chief | `crew.py`, script de instalação da tarefa | `drill --reboot` uma vez |
| 8 | Fechamento automático do mesclado e `crew.py gc` | `crew.py` | repositório git temporário: o mesclado fecha sozinho, o órfão só aparece na lista |
| 9 | VPS durável: vigia como serviço, `host` padrão, `drill` lá | `crew_remote.py`, `vps-setup.sh`, `repos.json` | `drill` na VPS com `sudo reboot` |

O `crew.py` já tem 943 linhas; o teto de tamanho que vem das PRs de freios vai pegar. As PRs 3 a 9 já nascem em módulos (`crew_health.py`, `crew_resume.py`, `crew_gc.py`), como a #11 fez com o `crew_remote.py`.

## O que vira regra ou check

- `test_crew.py` ganha a tabela de mensagens reais; uma causa nova só entra com o caso de teste dela.
- `crew.py doctor` (determinístico): integrações do Herdr na versão esperada, `resume_agents_on_restore` coerente com a escolha da retomada, vigia vivo, disco e RAM acima dos limiares, todo worker aberto com `session_id`, nenhum worktree órfão. O `board` mostra as falhas dele no topo; o AGENTS.md não ganha texto.
- O `drill` vira prova obrigatória de PR que mexe em `crew-state.ts`, `relaunch`, `revive` ou `boot`; o CI da #14 pode exigir "drill: passou" no corpo dela.
- "Não rode `pi` no painel" sai dos briefs quando a PR 1 entrar.

## Escolhas que só o dono faz

1. **D40** (decidida: o crew) Quem retoma o worker: o comando do crew no Herdr, com o `revive` como recuo.
2. **D41** (decidida) A política de retomada da seção 2; crédito esgotado espera o dono.
3. **D42** (decidida: só a tarefa de logon) O PC não liga sozinho nem entra sem senha.
4. **D43** (decidida: 10 no PC, 6 na VPS, fila) Tetos e limiares de disco e RAM da seção 3.
5. **D44** (decidida: sim, com vigia próprio) A VPS como lugar padrão dos workers.
6. **D45** (decidida: sim) Fechar sozinho o worker mesclado e com relatório.
7. **D46** O espaço do C: hoje (WSL, Docker, bundle do Claude).
