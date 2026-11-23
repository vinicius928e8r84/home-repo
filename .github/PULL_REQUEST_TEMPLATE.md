## Summary

## Evidence

## Merge Danger

**Door:**

**Blast Radius:**

**Atenção:**

Closes https://github.com/vinicius928e8r84/home-repo/issues/N

<!--
O check "Registro da PR" (.github/workflows/registro-da-pr.yml, scripts/freios/registro_da_pr.py) confere, no head exato da PR.
O que está em comentário de HTML, em bloco de código ou em citação (>) não conta.

1. Atenção: uma linha "Atenção: BAIXA", "Atenção: MÉDIA" ou "Atenção: ALTA" (o valor sozinho na linha).
   ALTA é obrigatória se a PR mexe em scripts/freios/, .github/, scripts/crew.py, .pi/, model_routing.json, repos.json,
   AGENTS.md, CLAUDE.md ou .agents/skills/ (CAMINHOS_SENSIVEIS em scripts/freios/registro_da_pr.py), e exige a seção "Prova real" (item 4).

2. Issue: uma linha "Closes <URL completa da issue>" por issue (https://github.com/vinicius928e8r84/home-repo/issues/<N>;
   o número solto não fecha nada), ou "Sem issue" sozinho na linha. Troque a linha Closes de cima por uma dessas.

3. Revisão independente: um comentário de revisão da PR, de quem pode escrever no repositório, com as linhas

   Veredito: CLEAN
   Head: <SHA inteiro do head, 40 caracteres: git rev-parse HEAD>
   Autor: <quem escreveu a mudança>
   Revisor: <quem revisou; não é o autor nem quem abriu a PR>
   Risco: <BAIXA, MÉDIA ou ALTA: o risco que o revisor viu>

   Vale o registro mais recente com o head exato. Um commit novo muda o head: revise de novo. Se o revisor registrar
   Risco: ALTA, a PR conta como ALTA mesmo com o corpo dizendo BAIXA ou MÉDIA. Um registro publicado como comentário
   simples não roda o check de novo; publique como revisão:
   python scripts/freios/registrar_na_pr.py revisao --pr <número> --head <SHA> --autor <quem> --revisor <quem> --risco baixa|media|alta --publicar

4. Prova real, com atenção ALTA: a seção abaixo, com uma única linha Head: com o SHA inteiro e uma explicação de pelo menos
   40 caracteres do que foi rodado de verdade e do que apareceu. NÃO COBERTO e BLOQUEADA invalidam a seção.

   ## Prova real

   PROVADO 100% REAL
   Head: <SHA inteiro do head>

   <o que você rodou e o que apareceu>

   python scripts/freios/registrar_na_pr.py prova --pr <número> --head <SHA> --cobertura total --nota <arquivo> --publicar
   escreve a seção com o head lido no GitHub.

O check confere o artefato e o SHA, não que a revisão ou a prova aconteceram.
-->
