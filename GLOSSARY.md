# Glossário

A língua comum entre o Dono, o Chief e os Workers no Home Repo. Só linguagem: o que cada termo é, e quais palavras evitar.

## Pessoas e agentes

**Dono**:
A pessoa dona dos repos, o Vinicius. É quem responde as Decisões.
_Avoid_: usuário, captain, capitão
O código ainda usa `usuário` (no `AGENTS.md`); renomear aos poucos.

**Chief**:
O agente com quem o Dono fala. Distribui o trabalho aos Workers e leva ao Dono só Decisões e resultados.
_Avoid_: firstmate, orquestrador, chefe
O código ainda usa `orquestrador` (no brief do `crew.py`); renomear aos poucos.

**Worker**:
Agente que faz uma Tarefa num repo, numa cópia isolada, e nunca fala com o Dono.
_Avoid_: crewmate, subagente, tripulante

**Time**:
O Chief e os agentes que ele comanda: hoje os Workers, um dia também gerentes com os Workers deles. O Firstmate da VPS tem o seu próprio Time.
_Avoid_: frota, fleet, crew, tripulação
O código ainda usa `frota` e `fleet`; a troca vai numa PR própria.
O grupo de um gerente: o Dono falou em equipe do gerente; sem nome fixo até haver gerentes.

**Vigia**:
O que observa os Workers e avisa o Chief quando algo muda.
_Avoid_: watcher, monitor
O código ainda usa `watch`/`watcher`; renomear aos poucos.

## Trabalho

**Frente**:
Um trabalho grande com um destino, que pede mais de uma Tarefa e pode cruzar repos. Pode ter um mapa do wayfinder, e todo mapa é de uma Frente; uma Tarefa pertence a uma Frente ou a nenhuma.
_Avoid_: projeto, esforço, épico, iniciativa

**Tarefa**:
Um pedido com critério de pronto, entregue a um Worker. Termina em PR, Relatório ou nada.
_Avoid_: job, ticket (ticket é a issue do repo)

**Decisão**:
Pergunta que só o Dono responde. Fica registrada até ser respondida.
_Avoid_: pendência, hold

**Relatório**:
O texto que um Worker escreve ao fim da sua Tarefa: o que fez, o que achou e o que ficou em aberto. Só Worker escreve Relatório.
_Avoid_: report, resumo
O código ainda usa `report`; renomear aos poucos.

**Mesa**:
O que o Dono vê numa olhada: a cota da conta, as máquinas, cada Frente com o estado, o próximo passo e quem ela espera, os Workers parados com a causa, e as Decisões para responder ali mesmo.
_Avoid_: dashboard, painel, visão geral

**Quadro**:
Um recorte da Mesa, como o Quadro de uma Frente.
_Avoid_: board, bearings
O código ainda usa `board` para o texto do `crew.py board`, que mostra tudo de uma vez; o que ele vira fica para a spec.

**Rodada**:
Uma sessão de grilling numa página lavish: perguntas ao Dono, cada uma com a recomendação, respondidas de uma vez.
_Avoid_: formulário, questionário

**Repo de trabalho**:
O repo de que uma Tarefa trata. É lá que ficam spec, ADR, glossário e issues dela.
_Avoid_: projeto (quando se quer dizer o repo)
O código ainda usa `projeto` (no `board`); renomear aos poucos.

**Retomada**:
Reabrir um Chief ou Worker que parou, na mesma conversa, e dizer a ele por que parou.
_Avoid_: resume, restore, relaunch, revive, reabertura

## Memória e contexto

**Wiki**:
A memória pessoal do Dono: preferências, trabalho fora do código e o que cruza repos. O que é de um Repo de trabalho não entra.
_Avoid_: notas, memória do chief

**Smart zone**:
A faixa do contexto em que o modelo ainda raciocina bem, em geral até uns 150 mil tokens. O Chief trabalha para ficar nela.
_Avoid_: janela cheia, contexto grande

**Dumb zone**:
O contexto além da Smart zone, onde o raciocínio do modelo decai.
_Avoid_: contexto estourado
