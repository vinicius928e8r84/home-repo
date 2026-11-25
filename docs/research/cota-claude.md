# Como medir e mostrar a cota da conta Claude

Pesquisa do ticket [Como medir e mostrar a cota da conta Claude](https://github.com/vinicius928e8r84/home-repo/issues/31), do mapa [Frota e painel do home-repo](https://github.com/vinicius928e8r84/home-repo/issues/26). Feita em 25/11/2026 no PC do dono.

Versões lidas: quota-axi 0.1.69 (commit `053d364`, 24/11/2026), pi-claude-bridge 0.13.0, Claude Agent SDK 0.3.321 (o `claude.exe` que o bridge roda), Pi 1.6.0.

## Resposta curta

Usar os dois, cada um no que faz melhor:

- **Cabeçalhos do bridge** para o rodapé do Pi e para gravar a cota a cada chamada de modelo. Não custam nada e chegam no mesmo instante em que o uso muda, mas só existem enquanto alguma sessão está chamando o modelo.
- **quota-axi** (ou a mesma chamada que ele faz) no vigia, de tempos em tempos, para a leitura não envelhecer quando a frota está parada e para os detalhes do Extra Usage, que os cabeçalhos não trazem.

Os dois gravam o mesmo arquivo, `state/crew/_cota.json`, no formato da seção [Formato de leitura](#formato-de-leitura). Quem lê (o vigia, `crew.py time`, a olhada do dono) só lê esse arquivo.

## 1. O que o quota-axi mede e de onde lê

- Para Claude, lê o token OAuth de `CLAUDE_CODE_OAUTH_TOKEN`, de `$CLAUDE_CONFIG_DIR/.credentials.json` ou de `~/.claude/.credentials.json` (no macOS, do Keychain com permissão). Não lê o `auth.json` do Pi para Claude. Fonte: README do quota-axi, tabela de fontes de credencial (linha "Claude").
- Com o token, chama `GET https://api.anthropic.com/api/oauth/usage` com `anthropic-beta: oauth-2025-04-20` e o User-Agent do Claude Code, e depois `GET /api/oauth/profile` para a identidade da conta. Fonte: `src/providers/claude.ts`, constantes `API_URL`, `PROFILE_API_URL`, `OAUTH_BETA` e a função `fetchOauthUsage`.
- Janelas que monta: `five_hour`, `seven_day`, `seven_day_opus` e `extra_usage`; quando a resposta traz a lista `limits`, usa ela no lugar (por isso aparece `model:fable`). `utilization` e `percent` são porcentagem usada (0 a 100). Fonte: `normalizeClaudeApiUsage` e `normalizeExtraUsage` em `src/providers/claude.ts`; README, tabela de janelas por provedor (linhas "Claude" e "Claude scoped limits").
- Extra Usage: só vira janela quando `extra_usage.is_enabled === true`; o gasto e o limite vêm de `used_credits` e `monthly_limit` divididos por `10^decimal_places`. Fonte: `normalizeExtraUsage`.
- Roda no Windows (o README marca macOS, Linux e Windows) e respondeu no PC: `npx -y quota-axi@0.1.69 --provider claude --json` devolveu plano `max`, semana com 41% usado (59% restante, reset 29/11 22:00 UTC) e Fable com 7% usado, mais o ritmo (`pace`) e a projeção de quando a semana acaba (`projectedExhaustedAt` 28/11 12:28 UTC).
- Cache: desligado por padrão; `--max-age` ou `QUOTA_AXI_MAX_AGE` (até 1 h) liga, e várias chamadas ao mesmo tempo esperam uma só leitura do fornecedor. Fonte: README, seção de cache.
- Licença MIT.

**Serve para o Pi com o bridge?** Serve, porque o bridge não tem login próprio: roda o `claude.exe` do Agent SDK, que usa o mesmo `~/.claude/.credentials.json`. O quota-axi lê a conta que o bridge gasta. O que ele não faz é mostrar algo dentro do Pi: é um CLI (e uma TUI); para o rodapé é preciso uma extensão.

Ressalva: `/api/oauth/usage` é um endpoint interno do Claude Code, sem documentação pública, e o quota-axi se apresenta com o User-Agent do Claude Code. Pode mudar sem aviso; quem acompanha a mudança é o mantenedor do quota-axi, e esse é o motivo para usar o CLI em vez de copiar a chamada.

## 2. O que o bridge já entrega

- O Claude Code não devolve cabeçalhos HTTP ao bridge; manda mensagens `rate_limit_event` com um `rate_limit_info`. O bridge guarda a última e a reentrega ao Pi no hook `after_provider_response` como cabeçalhos `anthropic-ratelimit-unified-*`, sempre com status 200. Fonte: README do bridge, seção "Plan usage for footers and quota extensions"; `src/rate-limit.ts` (`rateLimitResponse`); `src/index.ts`, tratamento de `rate_limit_event` em `consumeQuery`.
- Cabeçalhos montados: `-status`, `-reset`, `-representative-claim`, `-overage-status`, `-overage-reset` e, para cada janela, `-<j>-utilization` e `-<j>-reset`, com `j` = `5h`, `7d` ou `7d_oi`. Fonte: `src/rate-limit.ts`, tabela `WINDOW_ABBREVIATIONS`.
- O evento chega quando uma janela muda, não em toda resposta; o que chega depois de um turno que terminou em ferramenta só aparece na chamada seguinte. Fonte: README do bridge, mesma seção.
- O tipo público do SDK (`SDKRateLimitInfo` em `sdk.d.ts`) traz `status`, `resetsAt`, `rateLimitType`, `utilization`, `overageStatus`, `overageResetsAt`, `overageDisabledReason`, `isUsingOverage`, `overageInUse`, `surpassedThreshold`. O campo `unifiedWindows`, que o bridge usa para as janelas, não está no tipo público, mas está no esquema embutido no `claude.exe` (janelas `five_hour`, `seven_day` e `seven_day_overage_included`, cada uma com `utilization`, `resetsAt`, `status` e `surpassedThreshold`).
- `status` e `overageStatus` são `allowed`, `allowed_warning` ou `rejected`. O `allowed_warning` com `surpassedThreshold` é o aviso de "perto do limite" que a frota quer antes de um worker parar.

**Escala, conferida com valor real.** Uma extensão de teste no hook `after_provider_response` (`pi -p --no-session -e rl-probe.ts --model claude-bridge/claude-haiku-5-5 "Responda só: OK"`) gravou, às 05:08:57 UTC de 25/11:

```
anthropic-ratelimit-unified-status: allowed
anthropic-ratelimit-unified-reset: 1795989600
anthropic-ratelimit-unified-representative-claim: seven_day
anthropic-ratelimit-unified-overage-status: rejected
anthropic-ratelimit-unified-7d-utilization: 0.4
anthropic-ratelimit-unified-7d-reset: 1795989600
```

No mesmo minuto, `/api/oauth/usage` deu `seven_day.utilization: 41.0` e reset `2026-11-29T22:00:00Z`. Logo:

- `utilization` do cabeçalho é **fração de 0 a 1** (0.4 ≈ 41%, arredondado), e a do endpoint é **porcentagem de 0 a 100**.
- `reset` é **segundos Unix** (1795989600 = 29/11/2026 22:00 UTC, o mesmo reset).
- Sem janela de 5 h ativa, não vem `5h-*` (o endpoint dava `five_hour: null`).

**Regra do Extra Usage.** O cabeçalho só diz se o Extra Usage pode servir (`overage-status`) e quando renova (`overage-reset`); não traz gasto nem limite. Na conta, hoje: `overage-status: rejected`, e o endpoint mostra o motivo, `extra_usage.is_enabled: false` com `user_disabled: true` (o dono desligou). Quando uma janela do plano está `rejected`, o pedido ainda passa se o `overage-status` for `allowed`; por isso o bridge manda sempre 200 e só o status diz o que houve (comentário de `rateLimitResponse`). O bridge avisa à parte quando um pedido foi cobrado no Extra Usage sem o plano ter acabado (`overageInUse` sem `isUsingOverage`, em `consumeQuery`). Gasto e limite em dólar só pelo endpoint (`extra_usage.used_credits`, `monthly_limit`, `decimal_places`, e o bloco `spend`).

## 3. Como mostrar no Pi do chief e onde gravar

- O Pi dá `ctx.ui.setStatus(chave, texto)` para uma linha de status no rodapé, `setWidget` para linhas acima ou abaixo do editor e `setFooter` para trocar o rodapé inteiro. Fonte: `docs/extensions.md` do Pi, seção "Widgets, Status, and Footer". O `after_provider_response` dá `event.status` e `event.headers`, e "a disponibilidade dos cabeçalhos depende do provedor" (mesma doc, seção do hook). Toda a frota roda pelo `claude-bridge` (`model_routing.json`), que os entrega.
- Recomendação: `setStatus("cota", "sem 41% · 5h —")`, não `setFooter`, que apagaria o rodapé atual. O lugar natural é o `crew-state.ts` (já carregado no chief e em cada worker) ou uma extensão nova ao lado em `.pi/extensions/`.
- A mesma extensão grava `state/crew/_cota.json` a cada cabeçalho, junto do `_chief/` que o `crew-state.ts` já usa. Como a cota é da conta, não do worker, o arquivo é um só: quem grava por último ganha, e o campo `at` diz a idade.
- O vigia, quando o arquivo passar de uns 30 min sem atualizar, roda `quota-axi --provider claude --json` e regrava o arquivo com `fonte: "quota-axi"`.

## Formato de leitura

`state/crew/_cota.json`, porcentagens de 0 a 100 nas duas fontes (o cabeçalho é multiplicado por 100):

```json
{
  "at": "2026-11-25T05:08:57Z",
  "fonte": "bridge",
  "host": "pc",
  "status": "allowed",
  "limitante": "seven_day",
  "janelas": {
    "5h": null,
    "7d": { "usado": 40, "reset": "2026-11-29T22:00:00Z", "status": "allowed" }
  },
  "extra": { "status": "rejected", "reset": null, "ligado": null, "gasto_usd": null, "limite_usd": null }
}
```

- `status` e `extra.status`: `allowed`, `allowed_warning` ou `rejected`, os valores do Claude Code.
- `limitante`: o `representative-claim`, a janela que manda agora.
- `extra.ligado`, `gasto_usd` e `limite_usd` só a leitura do quota-axi preenche; a do bridge deixa `null`.
- Regra para a frota: `allowed_warning` em qualquer janela é o aviso antes do limite; `rejected` com `extra.status` diferente de `allowed` é a parada "limite de uso" de D41, que espera o `reset` da janela `limitante`.

## Em aberto

- A VPS tem `~/.claude/.credentials.json` próprio. Não conferi se é a mesma conta do PC; se for, o arquivo da VPS e o do PC descrevem a mesma cota e o sync só precisa trazer o mais novo.
- O `utilization` do cabeçalho veio com uma casa (0.4); não está documentado se é sempre arredondado assim.
