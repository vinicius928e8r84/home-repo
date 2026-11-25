# Como o Pi e o Herdr reabrem um worker com a mesma conversa

Pesquisa do ticket [Como o Pi e o Herdr reabrem um worker com a mesma conversa](https://github.com/vinicius928e8r84/home-repo/issues/29), do mapa [Frota e painel do home-repo](https://github.com/vinicius928e8r84/home-repo/issues/26). Feita em 25/11/2026 contra:

- PC: Pi 1.6.0 (`%APPDATA%/npm/node_modules/@earendil-works/pi-coding-agent`), Herdr 0.9.5, integração pi do Herdr v9 (`~/.pi/agent/extensions/herdr-agent-state.ts`).
- VPS: Pi 1.5.2, Herdr 0.9.1, integração pi do Herdr **não instalada** (`herdr integration status`).
- Código do Herdr na tag [`v0.9.5`](https://github.com/herdrdev/herdr/tree/v0.9.5) e a doc dessa versão ([índice](https://herdr.dev/llms.txt)).

Os testes rodaram numa sessão Herdr à parte (`herdr --session crewtest server`, apagada no fim), numa pasta vazia, sem tocar na sessão padrão nem na frota.

## Resposta curta

- **O Pi já abre com id fixo.** `pi --session-id <id>` abre a sessão com esse id da pasta atual ou a cria se não existe. O modelo e o nível de raciocínio voltam da própria sessão. Extensões (`-e`), `--approve` e as variáveis de ambiente não ficam na sessão: quem reabre tem de passá-las de novo.
- **O restore do Herdr reabre o worker pela metade.** Ele digita `pi --session '<caminho>'` no shell do painel, na mesma pasta e com o mesmo id de painel. Não passa `-e` nem `--approve` e não refaz as variáveis do `--env` (`CREW_STATE_FILE`, `CREW_AGENT_NAME`), que o `session.json` não guarda.
- **O report do crew não prevalece.** Enquanto a integração `herdr:pi` é dona da sessão do painel, o Herdr descarta os reports com `--source crew`. Mandar um comando de retomada por eles dá `resume_not_accepted`. Só um report com a fonte `herdr:pi` consegue gravar o comando, e a doc reserva esse prefixo ao próprio Herdr.
- **Recomendação:** desligar `resume_agents_on_restore` no PC e deixar o crew reabrir (D40), sempre com o mesmo comando do spawn mais `--session-id <nome>`. Para um `pi` rodado dentro do painel não gravar no estado do pai, o `crew-state.ts` só grava quando o id da sessão é o `CREW_AGENT_NAME`.

## 1. O Pi: id fixo, o que volta e o que não volta

### `--session-id`

Fonte: `docs/cli.md` (*Sessions*) e `dist/main.js` do Pi 1.6.0.

- `--session-id <id>`: "Opens the current directory's existing session with the ID, or creates it otherwise." O id aceita letras, números, `.`, `_` e `-` e tem de começar e terminar com letra ou número. Nomes como `home-pi-sessao-retomada` servem.
- No código (`main.js`, perto da linha 383), o Pi procura o id só entre as sessões da pasta atual (`SessionManager.findById(cwd, …)`). Se acha, abre; se não, avisa `No project session found with id '<id>'; creating a new session with that id.` e cria.
- Não combina com `--session`, `--continue` nem `--resume`.
- A VPS tem o mesmo flag: o `pi --help` do 1.5.2 lista `--session-id <id>  Use the current directory's existing session with the ID, creating it otherwise`.
- O arquivo fica em `~/.pi/agent/sessions/<pasta>/<data>_<id>.jsonl`. O Pi só o grava depois da primeira mensagem. Reabrir antes disso cria outra sessão vazia com o mesmo id, e isso não estraga nada.

**Testado.** Em `crewtest-cwd`, `pi -p --session-id crewtest-c --model claude-bridge/claude-haiku-5-5:low "Guarde a palavra girassol. Responda apenas: ok"` respondeu `ok`. Depois, `pi -p --session-id crewtest-c "Qual palavra pedi para guardar?"`, **sem `--model`**, respondeu `girassol`, sem o aviso de sessão nova. As duas rodadas foram para o mesmo `.jsonl` e as duas respostas saíram de `claude-bridge/claude-haiku-5-5` com raciocínio `low`.

### O que volta da sessão

- **Modelo e raciocínio voltam.** "A session records model and thinking-level changes. Resuming the session restores them" (`docs/models.md`). No código, `core/sdk.js` linhas 87–99: sem `--model`, o Pi usa o modelo da sessão (`restoredModel`). Com `--model`, o da linha de comando ganha. Repetir o `--model` do spawn na retomada desfaz uma troca de modelo feita no meio do trabalho.
- **A pasta volta.** `--session` e `--resume` rodam na pasta gravada na sessão. `--session-id` procura na pasta atual, então o crew precisa abrir o painel no worktree (`docs/sessions.md`).

### O que não volta

- **Extensões.** O `-e <arquivo>` vale só para o processo. Na retomada, o Pi carrega as extensões globais (`~/.pi/agent/extensions`) e as do projeto (`.pi/extensions`, se a pasta for confiável), e não o `crew-state.ts` do home-repo, que entra por `-e` nos outros repos.
- **`--approve`.** "Trusts project-local configuration and resources for this process" (`docs/cli.md`). Sem ele, o Pi segue o `~/.pi/agent/trust.json` (`docs/security.md`, *How Pi chooses a trust decision*):
  - No PC, `C:\Users\sadvi\worktrees` está confiável, e a decisão da pasta-mãe vale para as filhas. Por isso a falta do `--approve` não trava o worker lá.
  - Na VPS, o `trust.json` não tem `~/worktrees`. Sem `--approve`, o Pi pergunta (no modo TUI) e o worker fica parado na pergunta.
- **Variáveis de ambiente.** São do processo, e o Pi não as grava na sessão.

## 2. O Herdr: o que o restore faz hoje

Fontes: [Session state and restore](https://raw.githubusercontent.com/herdrdev/herdr/v0.9.5/docs/next/website/src/content/docs/session-state.mdx), [Add Herdr support to your agent](https://raw.githubusercontent.com/herdrdev/herdr/v0.9.5/docs/next/website/src/content/docs/add-herdr-support.mdx), [Socket API → Agent state reporting](https://raw.githubusercontent.com/herdrdev/herdr/v0.9.5/docs/next/website/src/content/docs/socket-api.mdx) e o código citado abaixo.

### O comando que ele digita

- `resume_agents_on_restore` vem ligado por padrão, e o `config.toml` do PC o liga explicitamente (`[session] resume_agents_on_restore = true`).
- Para o pi, o comando vem de [`agent_resume.rs` linha 234](https://github.com/herdrdev/herdr/blob/v0.9.5/src/agent_resume.rs#L234): `("herdr:pi", "pi", Path | Id) => ["pi", "--session", <valor>]`. O valor é o caminho do `.jsonl` que a integração reportou (`herdr-agent-state.ts`, `reportSession` com `agent_session_path`).
- O Herdr digita esse comando no shell do painel restaurado. **Testado:** depois de `herdr session stop crewtest` e de subir o servidor de novo, o painel mostrou `PS C:\…\crewtest-cwd> pi --session 'C:\Users\sadvi\.pi\agent\sessions\…\…_crewtest-a.jsonl'`. O shell do painel no Windows é o PowerShell.
- A resposta não depende de um cliente conectado. O servidor sem interface (`herdr server`) também reabriu o pi.

### O que ele guarda e o que perde

- Ficam no `session.json` só `cwd`, `agent_name`, `agent_session` (`source`, `agent`, `kind`, `value`) e, quando houver, `agent_resume`. Isso vale para as 13 abas da sessão padrão e também se conferiu na sessão de teste.
- **O `--env` da aba não fica.** Uma aba criada com `--env CREW_STATE_FILE=…` voltou só com `cwd`. É por isso que o worker volta sem `CREW_STATE_FILE`.
- **O `crew-state.ts` também não volta.** O comando restaurado não tem `-e`. Num worktree do home-repo, o `crew-state.ts` ainda carrega como extensão do projeto, mas sem `CREW_STATE_FILE` ele cai no ramo do chief (`pane && isHomeRepo(cwd)`): grava em `state/crew/_chief/<painel>.json` e renomeia o painel para `chief`.
- **O id do painel continua o mesmo.** O `session.json` guarda `public_pane_numbers` e o id da área de trabalho. No teste, `w1:p1` e `w1:p2` voltaram com os mesmos ids. O `meta["pane"]` do crew continua valendo.
- **Uma referência velha cai.** Uma referência que não existe mais volta como shell comum ("Unsupported, missing, invalid, duplicated, or stale session references restore as normal shells").

### Por que o worker às vezes volta como `not_pi`

Não houve como reproduzir aqui. O código e a doc dão duas causas prováveis, a conferir à mão:

- A referência da sessão não vale mais: o `.jsonl` foi apagado, ou o worker caiu antes da primeira mensagem e o arquivo nunca existiu. O painel volta como shell.
- O Herdr apaga o agente do painel quando "the pane is back at its idle shell prompt" (`add-herdr-support.mdx`, *Release on exit*). Entre o shell voltar e o pi subir, `herdr pane get` não diz `pi`.

O vigia lê o `agent` do painel (`worker_view` em `scripts/crew.py`) e marca `not_pi` quando ele vem diferente de `pi`.

### O report do crew prevalece sobre o da integração?

**Não.** Testado no painel `w1:p1` com o pi aberto pela integração:

```
$ herdr --session crewtest pane report-agent w1:p1 --source crew --agent pi --state idle --seq <agora> -- pi --session-id crewtest-a --approve
{"error":{"code":"resume_not_accepted","message":"resume_argv requires the reporter to hold the pane; report its state with pane.report_agent first"}}
```

O motivo está no código:

- [`terminal/state.rs` linha 1330](https://github.com/herdrdev/herdr/blob/v0.9.5/src/terminal/state.rs#L1330), `current_session_owner_conflicts`: a dona da sessão do painel é a fonte que reportou a referência, aqui `herdr:pi`.
- Em `set_hook_authority_at` ([linha 743](https://github.com/herdrdev/herdr/blob/v0.9.5/src/terminal/state.rs#L743)), um report de outra fonte só toma o painel se `agent_resume::plan(source, …)` existir para ela. Esse plano só existe para as fontes oficiais `herdr:*` (`agent_resume.rs`, `plan`, primeira linha). Para `crew`, o report é ignorado.
- `can_record_reported_resume` ([linha 1933](https://github.com/herdrdev/herdr/blob/v0.9.5/src/terminal/state.rs#L1933)) só aceita um comando da fonte que segura o painel.

Consequência para hoje: os `report-agent` e `release-agent` com `--source crew` que o `crew-state.ts` manda não fazem nada nos painéis em que a integração pi roda. O estado na barra lateral vem da integração. O `herdr agent rename` funciona, porque roda no retorno do report, dê o report certo ou não.

**O que prevalece, testado:** um `report-agent-session` com `--source herdr:pi --agent pi`, o caminho da sessão atual e `-- pi --session-id crewtest-a --approve`.

- O Herdr gravou `"agent_resume": {"source": "herdr:pi", "agent": "pi", "argv": ["pi", "--session-id", "crewtest-a", "--approve"]}` no `session.json`. No restore seguinte, digitou `pi --session-id crewtest-a --approve`.
- O comando sobreviveu aos reports seguintes da integração, que não trazem comando, porque a fonte é a mesma (`reconcile_reported_resume`, [linha 1996](https://github.com/herdrdev/herdr/blob/v0.9.5/src/terminal/state.rs#L1996)).
- Mesmo assim, não serve como caminho:
  - A doc manda não usar o prefixo `herdr:` ("Don't start it with `herdr:`, because Herdr's own integrations use that prefix"), então qualquer versão nova pode quebrá-lo.
  - O comando tem de começar por um nome simples, sem caminho, sem apóstrofo, com no máximo 64 argumentos (`validate_resume_argv`, `agent_resume.rs` linha 58). Não dá para pôr `CREW_STATE_FILE=… pi …` nem `env …` no PowerShell.
  - Na VPS, o Herdr 0.9.1 ignora comandos de retomada, que pedem o 0.9.2 ("Resume commands need Herdr 0.9.2 or later").

### `resume_agents_on_restore = false`

Com ele desligado, o Herdr ainda restaura áreas de trabalho, abas, painéis, pastas e ids. Só não reabre agente nenhum, e o painel volta como shell na pasta do worktree. Na VPS isso já acontece hoje, porque não há integração pi instalada lá. A chave vale para o servidor inteiro, então o painel do chief também volta como shell, e a volta do chief passa a ser trabalho do crew (o boot da D42).

## 3. Um `pi` dentro do painel gravando no estado do pai

- Todo processo filho herda o ambiente do painel. Num shell do worker (o `bash` do próprio Pi), estão `CREW_STATE_FILE`, `CREW_AGENT_NAME`, `HERDR_ENV=1` e `HERDR_PANE_ID`: conferido com `env` neste painel.
- O Pi só troca as variáveis da sessão: a ferramenta `bash` apaga e regrava `PI_SESSION_ID`, `PI_SESSION_FILE`, `PI_PROVIDER`, `PI_MODEL` e `PI_REASONING_LEVEL` (`dist/core/tools/bash.js` linha 161). As do crew passam intactas.
- O `crew-state.ts` lê `process.env.CREW_STATE_FILE` no `session_start`. Um `pi -p` rodado de dentro do worker grava `idle` e depois `gone` no `state.json` do worker, e o vigia o vê fechado.
- `PI_CODING_AGENT` não serve de sinal: o Pi o põe em `true` no próprio processo ao subir (`dist/cli/setup.js` linha 5), seja ele filho ou não.
- A integração do Herdr já se protege: ela só reporta no modo TUI (`if (ctx?.mode !== "tui") return;` em `herdr-agent-state.ts`), e um `pi -p` filho não é TUI.

**Conserto que o código sustenta:**

- **Worker:** gravar só quando `ctx.sessionManager.getSessionId() === process.env.CREW_AGENT_NAME`. Exige que o crew abra o worker com `--session-id <nome>`. Um `pi` filho tem outro id e fica de fora.
- **Chief, que não tem `CREW_AGENT_NAME`:** não gravar quando `process.env.PI_SESSION_ID` já existe ao carregar. O Pi só põe essa variável no ambiente dos filhos (`bash.js` linhas 161–171), nunca no próprio processo. Ela só aparece num `pi` aberto de dentro de outro.

## 4. Comando de retomada recomendado

O spawn passa a abrir com o id fixo, e a retomada usa o mesmo comando:

```
# no worktree do worker, num painel com --env CREW_STATE_FILE=… --env CREW_AGENT_NAME=<nome>
pi --session-id <nome> --approve -e "<home-repo>/.pi/extensions/crew-state.ts" --model <modelo>:<nível>
```

- **Na retomada, sem `--model`.** O modelo e o raciocínio voltam da sessão (seção 1), e assim uma troca feita no meio do trabalho não se perde.
- **Painel.** Se o painel restaurado ainda existe (mesmo id, shell no worktree), o crew não consegue lhe devolver o `--env`. Feche-o e abra uma aba nova com `--env`, como no spawn, e atualize `meta["pane"]`. A alternativa é o `crew-state.ts` deduzir o arquivo de estado do id da sessão, sem variável.
- **Sem reenviar o brief.** A conversa já o tem. Mande só um aviso curto de que o worker voltou.
- **VPS.** O mesmo comando, com o `PATH`/`pi` de `crew_remote.py`. Lá o `--approve` é obrigatório (seção 1).
- **Herdr do PC.** `[session] resume_agents_on_restore = false`, para que só o crew reabra e não haja dois donos.
- **Nome que se repete.** `--session-id` reabre qualquer sessão antiga com o mesmo id na mesma pasta. Se uma tarefa for refeita com o mesmo nome e o mesmo caminho de worktree, o spawn tem de checar antes que não existe sessão com esse id, ou apagá-la no `close`.

## 5. O que falta testar à mão

1. **Reinício da sessão padrão do Herdr no PC com `resume_agents_on_restore = false`.** Só se testou numa sessão separada. Falta confirmar que as abas do `crew` voltam com os mesmos ids e como shell, e que o crew reabre cada worker no ponto em que estava.
2. **Queda no meio de uma ferramenta.** Matar o pi enquanto um `bash` roda, reabrir com `--session-id` e ver se a conversa segue: a chamada pela metade, o que o modelo faz com ela, e se basta um "continue".
3. **Reinício do PC.** Pelo caminho da D42 (tarefa do Agendador no logon), com o crew reabrindo chief e workers.
4. **VPS.** `--session-id` no Pi 1.5.2 e retomada depois de reiniciar o `crew-herdr.service`. Lá não há integração pi nem comando de retomada no Herdr 0.9.1.
5. **`not_pi` depois do restore.** Reproduzir para ver qual das duas causas da seção 2 acontece, ou se é outra.
6. **Os dois guardas do `crew-state.ts` da seção 3.** Um `pi -p` dentro de um worker não pode mexer no `state.json` dele, e o chief tem de continuar gravando.
