# Que sinais dizem por que um worker parou

Pesquisa do ticket [Que sinais dizem por que um worker parou](https://github.com/vinicius928e8r84/home-repo/issues/30), do mapa [Frota e painel do home-repo](https://github.com/vinicius928e8r84/home-repo/issues/26). Feita em 25/11/2026 contra o Pi 1.6.0 (`@earendil-works/pi-coding-agent`, instalado em `%APPDATA%/npm/node_modules`; código na tag [`v1.6.0`](https://github.com/earendil-works/pi/tree/v1.6.0)), o `pi-claude-bridge` 0.13.0 (`~/.pi/agent/npm/node_modules/pi-claude-bridge`; código no commit [`5ea9bb8`](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/), o `gitHead` do npm) e as sessões em `~/.pi/agent/sessions`.

## Resposta curta

O Pi entrega a causa da parada a uma extensão, mas não no evento que o `crew-state.ts` usa hoje. O `agent_settled` só traz `aborted`. O desfecho (`completed`, `aborted`, `error`) vem no `agent_before_settle`, e a mensagem de erro vem na última resposta do modelo, que chega no `turn_end` (`event.message.stopReason` e `event.message.errorMessage`). Toda causa vista desde 23/11 está nesse `errorMessage`, como texto: o Pi não tem um código de erro tipado. Morte do processo não passa por evento nenhum. Para pegá-la, a extensão precisa gravar o `process.pid` e uma batida de tempo em tempo, e o vigia confere as duas.

## 1. Sinais que uma extensão recebe

Fonte: [`docs/extensions.md`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/extensions.md) (seções [*Lifecycle Overview*](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/extensions.md#lifecycle-overview), [*agent_start / agent_end / agent_before_settle / agent_settled*](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/extensions.md#agent_start--agent_end--agent_settled), [*turn_start / turn_end*](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/extensions.md#turn_start--turn_end), [*tool_execution_*](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/extensions.md#tool_execution_start--tool_execution_update--tool_execution_end), [*session_shutdown*](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/extensions.md#session_shutdown)) e os tipos em `dist/core/extensions/types.d.ts` do Pi 1.6.0 ([`src/core/extensions/types.ts`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/src/core/extensions/types.ts)).

| Sinal | Onde chega | O que diz | Limite |
|---|---|---|---|
| `stopReason` da resposta | `turn_end` → `event.message.stopReason` (também `message_end` e `agent_end.messages`) | `stop`, `length`, `toolUse`, `error`, `aborted` (tipo `StopReason` em `pi-ai/dist/types.d.ts`, [`ai/src/types.ts`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/ai/src/types.ts)) | fica em cada resposta, inclusive nas tentativas que o Pi repete depois |
| `errorMessage` da resposta | `turn_end` → `event.message.errorMessage` | o texto do erro: a única coisa que separa disco, crédito, limite, rede etc. | texto livre; a causa sai de padrão no texto |
| `turn_end` com erro | `agent-loop.js` ([`agent/src/agent-loop.ts`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/agent/src/agent-loop.ts)) emite `turn_end` com a resposta de erro e `toolResults: []` | o turno acabou em erro | — |
| `outcome` | `agent_before_settle` → `event.outcome` (tipo `AgentActivityOutcome`) | `completed`, `aborted` ou `error` do fim real | um turno abortado pula o `agent_before_settle` (docs, *Lifecycle Overview*) |
| `aborted` | `agent_settled` → `event.aborted` | alguém apertou Esc ou a execução foi cancelada | é o único campo do `agent_settled` |
| fim de verdade | `agent_settled` | o Pi não vai mais tentar, compactar nem seguir sozinho | `agent_end` não serve para isso: depois dele ainda pode vir nova tentativa (docs, *agent_start / agent_end…*) |
| ferramenta em curso | `tool_execution_start` (`toolName`, `args`, `toolCallId`) e `tool_execution_end` (`isError`, `durationMs`) | qual ferramenta está rodando e há quanto tempo | a extensão guarda o par por conta própria; não há "ferramenta atual" para consultar |
| compactação que falhou | `session_compact_failed` → `errorMessage`, `aborted`, `willRetry` | a compactação quebrou | — |
| saída | `session_shutdown` → `reason`: `quit`, `reload`, `new`, `resume`, `fork` | o Pi saiu ou trocou de sessão de propósito | só em saída limpa (Ctrl+C, Ctrl+D, SIGHUP, SIGTERM, segundo a doc); processo morto à força ou queda não dispara |
| arquivo da sessão | `ctx.sessionManager.getSessionFile()` (`dist/core/session-manager.d.ts`); o Herdr também mostra em `herdr pane get` → `agent_session.value` | onde ler a última resposta sem depender da extensão | — |

O que a extensão **não** recebe:

- **As tentativas automáticas.** `auto_retry_start` e `auto_retry_end` (com `errorMessage`, `attempt`, `finalError`) existem no modo JSON e no SDK ([`docs/json.md`, *Retry events*](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/json.md#retry-events); [`src/core/agent-session.ts`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/src/core/agent-session.ts)), mas não estão no `ExtensionEvent` de `types.d.ts`. Para a extensão, a tentativa aparece só como outro `agent_start` depois do `agent_end`. O padrão é 3 tentativas ([`settings-defaults.ts`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/src/core/settings-defaults.ts), `retry.maxRetries: 3`).
- **O status HTTP pelo claude-bridge.** `after_provider_response` traz `status` e `headers`, mas [a doc](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/extensions.md#lifecycle-overview) avisa que "Provider hooks run only when the transport exposes the corresponding stage". O bridge fala com o Claude Code, não por HTTP, então o 401 ou o 429 só aparecem dentro do `errorMessage`.
- **O aviso de limite do bridge.** Quando o Claude Code rejeita por limite, o bridge mostra `Claude subscription rate limit reached (<tipo>) — resets at <hora>` por `piUI.notify` ([`src/index.ts`, perto da linha 1515](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/src/index.ts#L1515-L1517)), que não fica gravado. O erro do turno, sim, fica: `Claude quota exceeded — rate limit (<tipo>) — resets <hora>: <falha>` ([`describeRateLimitFailure`, `src/index.ts` linha 340](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/src/index.ts#L340-L344)).

Quais erros o Pi repete sozinho: `isRetryableAssistantError` em `pi-ai/dist/utils/retry.js` ([`ai/src/utils/retry.ts`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/ai/src/utils/retry.ts#L284)). Primeiro testa a lista dos que **não** se repetem (`quota exceeded`, `billing`, `insufficient_quota`, `out of budget`…) e depois a dos que se repetem (`overloaded`, `rate limit`, `429`, `5xx`, `ECONNRESET`, `ENOTFOUND`, `fetch failed`, `socket hang up`, `timeout`, `terminated`…). `ENOSPC`, `Cut boundary` e `safeguards flagged` não estão em nenhuma das duas: o Pi não tenta de novo e para na hora. `credit balance is too low … Plans & Billing` casa `billing` e também não se repete.

### Processo vivo: pid e batida

- O Pi não tem evento de batida nem expõe pid à extensão, mas a extensão roda no mesmo processo Node: `process.pid` é o pid do Pi. Um `setInterval(...).unref()` grava uma batida sem segurar o processo vivo (é o que o próprio `herdr-agent-state.ts` faz com os seus temporizadores).
- O Herdr não dá pid: `herdr pane get <pane>` devolve `agent` (`pi`), `agent_status` (`working`, `blocked`, `idle`), `agent_session` (o caminho da sessão) e `cwd`, conferido neste painel.
- Conferir o pid no Windows exige cuidado: no Windows, `os.kill(pid, sig)` com qualquer sinal que não seja `CTRL_C_EVENT` ou `CTRL_BREAK_EVENT` mata o processo via `TerminateProcess` ([docs do Python, `os.kill`](https://docs.python.org/3/library/os.html#os.kill)). `os.kill(pid, 0)` só serve na VPS (Linux). No PC, use `tasklist /FI "PID eq <pid>"` ou `OpenProcess` pelo `ctypes`.
- O pid sozinho engana quando o Windows reaproveita o número. Pid **e** batida recente juntos dizem "vivo". Pid morto diz "o Pi saiu". Pid vivo com batida velha diz "congelado".

### O que o `crew-state.ts` faz hoje

`.pi/extensions/crew-state.ts` grava `idle` no `agent_settled` sem olhar `aborted` nem a última resposta. Por isso o turno que morreu com `ENOSPC` grava o mesmo `{"state": "idle"}` de um turno que terminou bem. O painel do time (`scripts/crew_sessao.py`, `resumo`) já lê o `errorMessage` da última resposta no arquivo da sessão e mostra `ERRO: …`. O `state.json` e o vigia não leem.

## 2. Mensagens reais desde 23/11, por causa

Método: todas as sessões do PC em `~/.pi/agent/sessions` mexidas desde 23/11 (137 arquivos), entradas `type: "message"` com `role: "assistant"` e `stopReason` igual a `error` ou `aborted`, com `timestamp` a partir de 23/11. São 43 respostas. A VPS não tem sessão nova desde 15/11 (`ssh vps ls -t ~/.pi/agent/sessions/*/*.jsonl`), então tudo abaixo é do PC. Os caminhos são relativos a `~/.pi/agent/sessions/`, com a linha do arquivo `.jsonl`.

| Causa | Vezes (sessões) | Provedor | Mensagem real | Exemplo |
|---|---|---|---|---|
| disco | 17 (17), 23/11 14:00–14:05 | claude-bridge | `ENOSPC: no space left on device, write` | `--C--Users-<usuário>-worktrees-Nova-AI-pesquisa-130--/2026-11-23T13-57-51-996Z_01a208b2-e6fb-768f-b7f8-e998861f89ea.jsonl:122` |
| claude-bridge | 11 (10), 23/11 14:27–14:30 | claude-bridge | `Cut boundary 9847936c-… is not on the primary parent chain` | o mesmo arquivo, `:124` |
| claude-bridge | (incluídas acima) | claude-bridge | `Session boundary 9f6fcd05-… is absent from the transcript` | `--C--Users-<usuário>-worktrees-Nova-AI-pesquisa-121--/2026-11-23T13-57-01-872Z_01a208b2-232f-738f-9f6f-6133e8c3d195.jsonl:117` |
| claude-bridge | 1 (1), 23/11 13:11 | claude-bridge | `Claude Code process exited with code 3` | `--C--Users-<usuário>-home-repo--/2026-11-23T13-05-03-203Z_01a20882-8ce1-7685-a1ae-7f96aa4e081c.jsonl:48` |
| crédito | 4 (3), 23/11 09:57–10:01 | anthropic | `400 {"type":"error","error":{"type":"invalid_request_error","message":"Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."},…}` | `--C--Users-<usuário>-worktrees-scratch-hello--/2026-11-23T10-01-29-413Z_01a207da-7e44-734f-8b53-5e73e7276ba9.jsonl:6` |
| crédito | (incluída acima) | anthropic | a mesma, sem o `400` na frente: `{"type":"error","error":{"details":null,"type":"invalid_request_error","message":"Your credit balance is too low…"}}` | `--C--Users-<usuário>-home-repo--/2026-11-23T09-30-30-869Z_01a207be-2255-75b0-bcb0-9084b55641eb.jsonl:84` |
| recusa | 1 (1), 23/11 14:01 | claude-bridge | `API Error: Opus 5's safeguards flagged this message (https://www.anthropic.com/legal/aup). … Claude Code can't respond to this message with Opus 5.` | `--C--Users-<usuário>-worktrees-Nova-AI-code-health-10-.wt-mobile--/2026-11-23T13-51-40-765Z_01a208ad-3cdb-768e-9fbc-4f4f7aa57500.jsonl:146` |
| interrompido | 9 (3), 23/11 10:39–16:44 | claude-bridge | `Operation aborted` (`stopReason: "aborted"`) | `--C--Users-<usuário>-home-repo--/2026-11-23T09-30-30-869Z_01a207be-2255-75b0-bcb0-9084b55641eb.jsonl:188` |
| credencial | 0 desde 23/11 | — | o último é de 28/07, kimi-coding: `401 {"error":{"type":"authentication_error","message":"The API Key appears to be invalid or may have expired. Please verify your credentials and try again."}…}` | `--C--Users-<usuário>--/2026-07-28T09-37-44-247Z_019fa816-5737-77…jsonl:6` |
| limite de uso | 0 | — | nenhuma real. O texto que o bridge produz: `Claude quota exceeded — rate limit (<tipo>) — resets <hora>: You're out of extra usage · resets <hora>` | [`pi-claude-bridge/src/index.ts:340`](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/src/index.ts#L340) |
| API fora | 0 | — | nenhuma real. Os padrões são os de `retry.js` (`overloaded`, `529`, `5xx`); só chegam ao fim do turno depois das 3 tentativas | `pi-ai/dist/utils/retry.js` |
| rede | 0 | — | nenhuma real. Os padrões são os de `retry.js` (`ECONNRESET`, `ENOTFOUND`, `EAI_AGAIN`, `fetch failed`, `socket hang up`) | `pi-ai/dist/utils/retry.js` |

O "401" que aparece no painel do time e nos planos de 23/11 não vem de sessão real desde 23/11: está no exemplo do plano `painel-do-time.md` e no teste `scripts/test_crew_painel.py`. A contagem antiga do plano `frota-duravel.md` (7× 401) pegava sessões de todas as datas.

### O que os números mostram

- **O disco cheio derrubou o bridge na retomada.** Das 17 sessões com `ENOSPC`, 10 receberam às 14:27 a mensagem `[chief] Chief: o disco do PC encheu (ENOSPC) e seu turno parou no meio. Liberei espaço; continue de onde parou.` e responderam na hora com `Cut boundary …` ou `Session boundary …` (o exemplo de `pesquisa-130` acima, linhas 122 a 124). Esses erros vêm de `src/session-transcript.ts` do bridge ([`boundaryIndex`](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/src/session-transcript.ts#L35-L38) e [`resolveCut`](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/src/session-transcript.ts#L42-L53)): o transcript do Claude Code que o bridge guarda ficou sem o ponto em que a sessão do Pi estava, provavelmente porque a gravação foi cortada pelo disco cheio. Mandar "continue" na mesma sessão não basta depois de um `ENOSPC` no bridge. Das 7 restantes, 4 seguiram com resposta normal e 3 terminaram no `ENOSPC`.
- **Interrompido não é parada.** Das 9 respostas `Operation aborted`, 6 foram seguidas de resposta normal na mesma sessão: foi alguém apertando Esc e seguindo a conversa.
- **Um só campo carrega tudo.** Toda causa real veio só no `errorMessage`, com `stopReason: "error"` (ou `aborted`). Classificar é casar padrão de texto; o bridge diz o mesmo no [comentário de `describeRateLimitFailure`](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/src/index.ts#L328) ("pi has no typed rate-limit error … the sole carrier is `errorMessage`").

## Fontes

- Pi 1.6.0 (tag [`v1.6.0`](https://github.com/earendil-works/pi/tree/v1.6.0)): [`docs/extensions.md`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/extensions.md), [`docs/json.md`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/json.md), [`docs/session-format.md`](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/session-format.md); `dist/core/extensions/types.d.ts` (`TurnEndEvent`, `AgentSettledEvent`, `AgentActivityOutcome`, `SessionShutdownEvent`, `ToolExecution*Event`); `dist/core/agent-session.js` (`_prepareRetry`, `_isRetryableError`); `dist/core/settings-defaults.js`.
- `@earendil-works/pi-agent-core`: `dist/agent-loop.js` (`turn_end` com a resposta de erro).
- `@earendil-works/pi-ai`: `dist/types.d.ts` (`StopReason`, `AssistantMessage.errorMessage`); `dist/utils/retry.js` (`isRetryableAssistantError`).
- `pi-claude-bridge` 0.13.0 (commit [`5ea9bb8`](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/)): [`src/index.ts`](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/src/index.ts) (`describeRateLimitFailure`, `rate_limit_event`, `failStream`); [`src/session-transcript.ts`](https://github.com/elidickinson/pi-claude-bridge/blob/5ea9bb88bd54395c1fe38cc95ec2ce1dbdcf15cc/src/session-transcript.ts).
- `~/.pi/agent/extensions/herdr-agent-state.ts` (integração do Herdr, versão 9) e `herdr pane get`.
- [`.pi/extensions/crew-state.ts`](../../.pi/extensions/crew-state.ts) e [`scripts/crew_sessao.py`](../../scripts/crew_sessao.py) deste repo.
- [Python, `os.kill`](https://docs.python.org/3/library/os.html#os.kill).
- As sessões citadas em cada linha da tabela.
