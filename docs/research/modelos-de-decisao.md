# Modelos de decisão (Jev, da TypeSafe) no Time

Pesquisa pedida pelo Dono em 25/11/2026: onde "JEV e modelos de decisão como o da TypeSafe" ajudam o Time a ganhar qualidade, tempo ou velocidade. Lido em 25/11/2026: a documentação e o blog da TypeSafe (Jev 1.14), o artigo arXiv 2610.21412v1 e o repositório do JevAgentHarness; do nosso lado, a `main` em `2e90121` e os arquivos `decisions.jsonl` e `events.jsonl` de `state/crew/` (23 a 25/11).

## Resposta curta

- "JEV" é o **Jev**, o modelo da **TypeSafe AI** lançado em setembro de 2026. Só achei essa leitura. Ele não escreve texto: recebe um estado e perguntas fechadas e devolve a resposta com a probabilidade, em cerca de 100 ms, por US$ 0,042 o milhão de tokens.
- Ele não substitui o modelo de um Worker. Serve dentro do código do Time (`crew.py`, Vigia, checks), nos pontos em que hoje um regex, o Chief ou o Dono fazem um julgamento pequeno e repetido.
- O que mais vale é o método, que não pede o Jev: o código decide, o modelo só responde perguntas pequenas e tipadas, e a probabilidade diz se o código age, confirma ou sobe. Duas das três primeiras oportunidades usam só o método.
- O Jev entra primeiro em sombra, medido contra o nosso histórico. Ele pede conta, chave e texto nosso indo a um terceiro: decisões do Dono.
- Quatro dos oito atritos de hoje são defeito de código e se consertam sem modelo.

## 1. O que é

### Jev

| | |
|---|---|
| O que faz | Avalia perguntas tipadas contra um `state` (texto, JSON ou imagem) numa chamada só. Cada pergunta é respondida em paralelo e isolada das outras. [Introdução][intro] |
| Tipos | `Choice` (uma opção de uma lista), `Score` (um nível numa escala descrita), `Noul` (sim ou não: devolve a probabilidade do sim) e `Box` (uma caixa numa imagem). Choice e Score trazem `probabilities` e `confidence`. [Introdução][intro] |
| Garantia | A resposta sempre cabe no esquema pedido, sem opção inventada. Não gera texto nem explica o motivo. [Anúncio][post], [System One][s1] |
| Preço e tempo | US$ 0,042 por milhão de tokens de entrada, saída grátis; 70 a 500 ms por chamada, segundo a TypeSafe. [Models][models], [Anúncio][post] |
| Contexto | 64 mil tokens por chamada e 32 mil por pergunta; 262 mil com um cabeçalho "danger zone", mais lento e menos preciso. [Models][models] |
| Acesso | `POST /v1/systemone` com chave do console, SDK em Python e JS; também no OpenRouter (`typesafe/jev-1.14`, mesmo preço). [Models][models], [OpenRouter][or] |
| Dados | Não treina com as chamadas; guarda "as long as reasonably necessary"; retenção zero só no plano enterprise. [Models][models], [Privacy Policy][priv] |
| Versão | `jev-latest` troca de modelo a cada lançamento; limiar ajustado pede a versão fixa (`jev-1.14.0`). [Models][models] |

Não é modelo para agente de código: "There is no `model: "jev-latest"` setting that turns your coding agent into a Jev-powered agent" ([Jev with coding agents][agents]).

Limites que a própria TypeSafe lista em [Model jaggedness][jag] e em [Companion Noul][cnoul]:

- lê ao pé da letra;
- não conta, não faz conta e não compara datas;
- piora com estado grande e cheio de coisa irrelevante;
- texto dentro do estado pode puxar a resposta (injeção);
- a ordem das opções de um Choice pesa;
- um Choice sempre escolhe algo, mesmo quando nada serve.

Um pedido tem `state`, `model` e `questions` ([Choice][choice]). O exemplo abaixo mostra o formato com um caso nosso; não foi rodado:

```json
{
  "model": "jev-1.14.0",
  "state": {"pedido": "Posso trocar a assinatura da função e os 4 chamadores?", "recomendo": "Trocar: cabe no pedido."},
  "questions": {
    "quem": {"type": "choice", "instructions": "Quem responde este pedido?",
      "criteria": {"chief": "Dúvida técnica, desfaz-se com um commit", "dono": "Escopo, gasto ou algo que não se desfaz"}},
    "irreversivel": {"type": "noul", "instructions": "O pedido envolve algo que não se desfaz?"}
  }
}
```

A resposta traz `choice`, `probabilities` e `confidence` de `quem` e um número de 0 a 1 em `irreversivel`. O código manda ao Chief só se `probabilities.chief` passar do limiar e `irreversivel` ficar abaixo de 0,3; o resto vai ao Dono.

### O método, que vale com qualquer motor

Da documentação ([How to build][build], [Confidence][conf], [Patterns][pat]) e do texto [Don't Call It a Decision Model][dcidm], que resume: "Jev makes judgments, code makes decisions".

1. **Código primeiro.** O que o código calcula exato fica no código.
2. **Perguntas atômicas.** Cada pergunta é um julgamento de poucos segundos; o código junta as respostas.
3. **Estado mínimo.** Vai só o que a pergunta precisa.
4. **Limiar pelo risco.** Três faixas: a alta age, a média confirma, a baixa sobe para uma pessoa ou um modelo maior. Ação mais arriscada pede probabilidade maior. Para Noul, começar em 0,7 e 0,3.
5. **Peneira.** Um Noul barato antes do passo caro, seja ele um modelo grande ou uma pessoa.
6. **"Nenhuma serve".** Um Noul ao lado do Choice diz quando nenhuma opção cabe.
7. **Um arquivo só** para as perguntas e os limiares, porque é isso que a pessoa revisa ([Agent skill][skill]).

### Parentes

- **Adaptador para LLM** (`system-one-adapter`, MIT, da TypeSafe): a mesma interface respondida por OpenAI, Anthropic ou Gemini pela API paga, feito para comparar ([README][adapter]). No Time, o equivalente sem conta nova é `pi -p --model claude-bridge/claude-haiku-5-5` pedindo JSON: gasta cota, é mais lento e a probabilidade não é calibrada.
- **Pesos abertos** citados no [artigo][arxiv]: Laya, OpenJev, Intern-Decision, StartLux-Decision e o AgentDecision-4B, que respondeu em 31 ms numa GPU L4. Não testei nenhum, nem sem GPU.
- **JevAgentHarness** (MIT, alfa): um proxy compatível com a API da OpenAI que manda cada passo do agente a um modelo forte ou a um rápido ([README][jah]).
- **Jev Router** no OpenRouter: um roteador de LLM feito sobre o Jev ([lista de modelos][orapi]).

### Evidência de fora da TypeSafe

O artigo [JevAgentHarness][arxiv] (Zhu et al., 15/10/2026) testou modelos de decisão dentro de agentes:

- Deixar o Jev escolher toda ferramenta, sem limiar ajustado, derrubou o sucesso em 19,0 pontos. Com o limiar ajustado nas trajetórias do próprio agente, só passou resposta quase certa (1,00 e 0,99).
- As 34 tarefas que o Jev perdeu começaram com uma escolha irreversível errada, em geral cancelar quando devia perguntar.
- Guarda que ainda chama o LLM economiza pouco. A guarda de parada aceitou 40,7% dos "terminei" errados de um LLM barato: "a decision-model guard should never be the only control on an irreversible action".
- Em agente de código, onde a ação é texto livre, o modelo de decisão só escolhe qual LLM escreve o passo: 7,0 a 10,5% de economia. O [README][jah] mostra 31% a menos no `pi` com um par de preços bem distante, numa rodada só e com intervalo largo.
- Tudo em inglês. Injeção não foi testada, e os adaptadores "should not be used as security boundaries".

A [Thoughtworks][tw], fonte secundária, data o lançamento em meados de setembro de 2026 e resume: nada de arquitetura nova, e bom como "confidence gate" no lugar do LLM juiz.

## 2. Como o Time decide hoje, medido

De `decisions.jsonl` e `events.jsonl`, de 23/11 06:47 a 25/11 05:30:

- 110 pedidos de Workers: 93 Decisões (D) e 17 Perguntas ao Chief (P). 137 Workers abertos.
- Das 88 respostas a Decisões, 40 começam com "Chief": ele respondeu o que estava registrado para o Dono, com mediana de 1,7 min. As outras 48 levaram 13 min de mediana e 95 min no percentil 90.
- A primeira Pergunta ao Chief é de 24/11 22:43 (commit `f92b8bd`). Depois dela ainda entraram 20 Decisões; das 16 já respondidas, 15 respostas começam com "Chief".
- 10 pedidos são só um link de Rodada para repassar. 14 respostas dizem "como recomendado" ou equivalente. D81, D82 e D83 receberam a mesma resposta.
- 29 alarmes de "parado" em 19 Workers; 6 Workers repetiram, um deles 5 vezes. A regra é um regex sobre 40 linhas da tela (`ESPERA` em `scripts/crew_alarmes.py`).
- Já é decisão tipada e funciona: `Veredito`, `Risco`, `Head` e `Atenção` no Registro da PR, `decidir()` em `scripts/crew_prs.py` e o tipo da Tarefa em `model_routing.json`.

## 3. Onde encaixa em cada fase

| Fase | Julgamento pequeno e repetido | Encaixe |
|---|---|---|
| Planejamento | A pergunta da Rodada já foi respondida por uma Decisão ou pela wiki? | Peneira: o código busca as candidatas e um Noul confere cada uma. O Worker vê a Decisão achada em vez de perguntar de novo. |
| Implementação | Qual modelo escreve este passo? | Fraco hoje: o Time roda na assinatura pelo `claude-bridge`, que não passa pelo proxy, e o ganho medido em agente de código é pequeno. |
| Revisão | O corpo tem evidência real? O diff faz mais do que o pedido? | Peneira antes de gastar um revisor Opus, devolvendo ao autor na hora. O CLEAN continua do revisor. |
| Prova | Que recurso a prova pede? A seção descreve algo rodado? | Campo tipado que o autor escreve e o código agrupa. Um Noul sobre a seção serve só de aviso ao revisor. |
| Mesclagem | Nenhum | Já é regra de código: CLEAN no head exato, checks verdes e Prova real. É o passo irreversível, e fica sem modelo. |
| Rebase | O head novo muda o que foi revisado? | Código primeiro (`git range-diff`); um Choice só para dizer o tamanho da nova revisão. |
| Orquestração | Quem decide isto? Este Worker está parado ou esperando? | O melhor encaixe: muitos casos, e o erro custa um aviso a mais. |

## 4. Oportunidades

Ordenadas pela relação entre o ganho e o custo somado ao risco. Motor: **C** é só código; **T** é pergunta tipada respondida por quem já tem o contexto; **J** é o Jev ou outro modelo de decisão.

| # | Oportunidade | Motor | Ganho | Custo | Risco |
|---|---|---|---|---|---|
| 1 | `ask` tipado e tabela de quem decide | T e C | Tempo e atenção do Dono: perto da metade das Decisões foi respondida pelo Chief | Uma PR pequena | Baixo: o Chief ainda sobe o que for do Dono |
| 2 | Prova real em lote por recurso | T e C | Tempo: uma sessão de Anki, Mac ou iPhone para várias PRs ALTA | Uma PR pequena | Baixo |
| 3 | Bancada do Jev em sombra sobre o histórico | J | Qualidade: um número nosso antes de ligar qualquer coisa | Conta, chave, centavos e um script | Baixo, tirados os segredos do texto |
| 4 | Tela do Worker lida por perguntas tipadas (parado, esperando, terminou, pede confirmação) | J | Tempo: menos alarme falso ou repetido e menos turnos do Chief | Médio; espera a 3 | Médio: a tela pode ter segredo; o regex fica de reserva |
| 5 | Pergunta já respondida | J | Tempo: menos Decisões repetidas | Médio; espera a 3 | Médio: casar errado esconde pergunta nova |
| 6 | Revisão só do delta depois do CLEAN | C e J | Velocidade: rebase puro deixa de pedir revisão inteira | Médio: muda o Registro (ALTA) | Médio: afrouxa um freio, decisão do Dono |
| 7 | Peneira antes do revisor | J | Tempo e cota: menos idas e voltas | Médio | Médio: diff grande passa dos 32 mil tokens |
| 8 | Roteamento de passos por modelo | J | Cota: 7 a 31% nos testes de fora | Alto: sair da assinatura ou escrever o roteador no bridge | Alto |

## 5. As três primeiras, como issues

### Issue 1: `ask` tipado: o Worker classifica o pedido e o código escolhe quem responde

**Problema.** O Worker escolhe o destinatário lendo o brief. De 23 a 25/11, 40 das 88 respostas a Decisões vieram do Chief, e 10 pedidos eram só um link.

**Pronto quando**

- [ ] `crew.py ask` exige `--tipo` com um valor de uma lista fechada (`escopo`, `gasto`, `irreversivel`, `acesso`, `tecnica`, `link`) e falha dizendo os válidos.
- [ ] Uma tabela, num arquivo só, liga cada tipo ao destinatário: `tecnica` e `link` vão ao Chief e os outros ao Dono. O brief deixa de pedir `--para`.
- [ ] O Chief sobe uma Pergunta ao Dono com um comando, levando o texto e a recomendação.
- [ ] O brief explica cada tipo em uma linha, com um exemplo.

**Teste.** Um caso por tipo confere o destinatário e a letra do id (D ou P); tipo fora da lista falha com os válidos.

### Issue 2: Prova real em lote: a PR diz o recurso e o Quadro agrupa

**Problema.** Juntar as provas das PRs ALTA numa sessão (D6) depende de o Chief lembrar. A vez do Anki da porta 8766 foi combinada por Pergunta (P12).

**Pronto quando**

- [ ] O brief pede, em PR de Atenção ALTA, uma linha `Prova em:` com um valor de uma lista fechada, num arquivo só: `anki-windows`, `mac`, `iphone`, `navegador`, `github`, `vps`.
- [ ] `scripts/crew_prs.py` lê a linha nas PRs abertas dos três repos, e o Quadro mostra, por recurso, as PRs ALTA que esperam prova.
- [ ] Com duas ou mais no mesmo recurso, o Vigia avisa o Chief uma vez: "lote pronto".
- [ ] PR ALTA sem a linha aparece como "recurso não dito".

**Teste.** PRs de exemplo com e sem a linha: o agrupamento e o aviso único saem como esperado.

### Issue 3: Bancada: o Jev em sombra contra as Decisões já respondidas

**Pergunta.** O Jev acerta, em português, quem devia responder cada pedido, melhor ou mais barato que a tabela da issue 1 e que o Haiku?

**Antes, do Dono.** Criar a conta e a chave (TypeSafe ou OpenRouter) e aceitar que o texto dos pedidos vá à TypeSafe. São cerca de 20 mil tokens, menos de US$ 0,01.

**Pronto quando**

- [ ] Um script, fora do que roda, lê `decisions.jsonl`, tira segredos, IPs e e-mails e pergunta ao `jev-1.14.0`, por pedido: um Choice (o Worker segue a própria recomendação, Chief ou Dono) e Nouls atômicos (é irreversível? gasta dinheiro? muda o escopo? é só um link?).
- [ ] Os mesmos pedidos passam pelo Haiku (`pi -p`) e pela tabela da issue 1.
- [ ] O Relatório traz, por motor: acerto contra quem respondeu de verdade, acerto só acima de 0,9, tempo e custo por pedido, e quantas respostas mudam ao inverter a ordem das opções.
- [ ] O Relatório recomenda ligar ou não as oportunidades 4 e 5, e com que limiar.

A bancada só mede: nenhuma resposta dela chega a um Worker.

## Os oito atritos de hoje

"Código primeiro" resolve quatro deles sem modelo.

| Atrito | Onde cai |
|---|---|
| Registro da PR vermelho até o rerun | Código: falta o gatilho ([#47](https://github.com/vinicius928e8r84/home-repo/issues/47)). |
| IDs de Decisão repetidos | Código: `next_id` em `scripts/crew_conversa.py` soma 1 à quantidade de ids distintos; um número pulado faz a conta cair num id já usado, que sai de novo a cada pedido (D87 saiu 4 vezes). |
| Teto de agentes | Código: fila e leitura de recursos ([#49](https://github.com/vinicius928e8r84/home-repo/issues/49)). |
| Avisos do Vigia atrasados ou repetidos | Código na entrega; o "parado" repetido é a oportunidade 4. |
| Quem decide: Dono, Chief ou Worker | Oportunidade 1; a 3 mede se um modelo faz melhor. |
| Prova real por PR em vez de em lote | Oportunidade 2. |
| Autor que muda o head depois do CLEAN | Oportunidade 6. |
| Cota semanal acabando | Oportunidades 4 e 7 (menos turnos de Opus) e 8. |

## Em aberto

- Não chamei o Jev: não há chave nesta máquina. Preço, tempo e precisão são os que a TypeSafe e o artigo publicam.
- Português: a 1.14 anuncia "better multilingual support" no [changelog][changelog], sem número, e o artigo é todo em inglês.
- Cobrança mínima, créditos e limites de taxa ficam atrás do login do console.
- A ordem das oportunidades 4 a 8 é estimativa; só a 1 e a 2 têm número nosso.

[intro]: https://docs.typesafe.ai/introduction
[s1]: https://docs.typesafe.ai/concepts/system-one
[models]: https://docs.typesafe.ai/models
[agents]: https://docs.typesafe.ai/introduction/coding-agents
[jag]: https://docs.typesafe.ai/model-jaggedness
[cnoul]: https://docs.typesafe.ai/patterns/companion-noul
[choice]: https://docs.typesafe.ai/primitives/choice
[build]: https://docs.typesafe.ai/concepts/how-to-build-with-system-one
[conf]: https://docs.typesafe.ai/confidence
[pat]: https://docs.typesafe.ai/patterns
[skill]: https://docs.typesafe.ai/agent-skill
[changelog]: https://docs.typesafe.ai/changelog
[post]: https://typesafe.ai/blog/introducing-system-one-models-and-jev
[dcidm]: https://typesafe.ai/blog/dont-call-it-a-decision-model
[priv]: https://typesafe.ai/legal/privacy-policy
[adapter]: https://github.com/typesafe-ai/system-one-adapter-python
[or]: https://openrouter.ai/typesafe/jev-1.14
[orapi]: https://openrouter.ai/api/v1/models
[arxiv]: https://arxiv.org/abs/2610.21412
[jah]: https://github.com/JevAgentHarness/JevAgentHarness
[tw]: https://www.thoughtworks.com/insights/blog/generative-ai/jev-decision-models-what-need-know-why
