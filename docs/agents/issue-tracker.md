# Issue tracker: GitHub

Os planos, specs e tickets do home-repo são issues no GitHub (`vinicius928e8r84/home-repo`), mexidas com o `gh`. Nada disso mora em arquivo no repo: o que já foi feito fica no histórico do git, e o que falta fica numa issue.

## Convenções

- **Criar**: `gh issue create --title "..." --body-file <arquivo>` (o corpo num arquivo temporário, apagado depois).
- **Ler**: `gh issue view <n> --comments`.
- **Listar**: `gh issue list --state open --json number,title,labels,assignees` com `--label` e `--state`.
- **Comentar**: `gh issue comment <n> --body "..."`.
- **Rótulos**: `gh issue edit <n> --add-label "..."` / `--remove-label "..."`.
- **Fechar**: `gh issue close <n> --comment "..."`.

O GitHub usa a mesma numeração para issues e PRs: um `#42` solto pode ser qualquer um dos dois (`gh pr view 42`, e se falhar `gh issue view 42`).

## Quando um skill diz "publique no issue tracker"

Crie uma issue no GitHub.

## Quando um skill diz "busque o ticket"

Rode `gh issue view <n> --comments`.

## Operações do wayfinder (Wayfinding operations)

Usadas pelo skill `wayfinder`. O **mapa** é uma issue só, com as **issues filhas** como tickets.

- **Mapa**: issue com o rótulo `wayfinder:map`, com Destination, Notes, Decisions so far, Not yet specified e Out of scope no corpo.
- **Ticket**: issue filha ligada ao mapa como sub-issue do GitHub (`gh api --method POST repos/vinicius928e8r84/home-repo/issues/<mapa>/sub_issues -F sub_issue_id=<id do ticket>`), com o rótulo `wayfinder:<tipo>` (`research`, `prototype`, `grilling` ou `task`) e `Pai: #<mapa>` no topo do corpo.
- **Bloqueio**: a dependência nativa do GitHub, `gh api --method POST repos/vinicius928e8r84/home-repo/issues/<ticket>/dependencies/blocked_by -F issue_id=<id do bloqueador>`. O `id` é o número do banco (`gh api repos/vinicius928e8r84/home-repo/issues/<n> --jq .id`), não o `#número` nem o `node_id`. O corpo repete a lista em "Bloqueado por", para quem lê.
- **Fronteira**: as filhas abertas do mapa (`gh api repos/vinicius928e8r84/home-repo/issues/<mapa>/sub_issues`), sem bloqueador aberto (`issue_dependencies_summary.blocked_by` igual a 0) e sem responsável; vale a primeira na ordem do mapa.
- **Pegar**: `gh issue edit <n> --add-assignee @me`, a primeira escrita da sessão.
- **Resolver**: `gh issue comment <n> --body "<resposta>"`, `gh issue close <n>` e uma linha com o resumo e o link em Decisions so far do mapa.
