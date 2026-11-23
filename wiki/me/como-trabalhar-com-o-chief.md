# Como o dono quer trabalhar com o chief

Preferências do dono, ditas em 2026-11-23.

- O dono não fala com workers. O chief é o intermediário e leva ao dono só as decisões, no chat ou num lavish. "Poupar minha atenção."
- Os workers ficam fora da vista do dono, mas o chief continua falando com eles.
- As rodadas de grilling vão para uma página lavish.
- Merge (2026-11-23): no PerpetualMiner o chief mescla sozinho PR de atenção baixa ou média, com CI todo verde e revisada pelo /code-review de outro agente (autorrevisão não conta); o resto o dono mescla. No home-repo as PRs só entram depois de definidas as lint rules.
- O que entra no home-repo pesa no contexto de toda sessão. Antes de mexer nele, revise as decisões e cheque três coisas: o assunto é de outro repo ou do GitHub? Já existe numa fonte que basta apontar? Vai envelhecer? Se alguma resposta for sim, não entra.
- A wiki guarda só o que é pessoal do dono, as tarefas fora do código e o que cruza repos. O que é de um projeto vai para o repo dele, de preferência em issues e não em `.md` novo. Na wiki entra, no máximo, um ponteiro.
- Toda página lavish vai com o link no chat também, porque às vezes ela não abre sozinha.
- O alvo é um firstmate nosso, só que mínimo: proteger a janela de contexto e trabalhar na smart zone. Do firstmate (github.com/kunchenguid/firstmate) vale trazer a guarda de fim de turno, o roteiro para worker travado e o brief que não alarga o pedido; o `/stow` já é coberto pela wiki do chief. Secondmates talvez depois, quando houver mais repos.
- O glossário do home-repo (`GLOSSARY.md`) é definido aos poucos, na conversa, para que o dono e o chief fiquem cada vez mais alinhados.
- O chief só orquestra: toda tarefa, inclusive página lavish, wayfinder e sessão de grill, vai para um worker, e o chief atualiza o dono no chat quando ela termina (2026-11-23).
- Do sf-kit (github.com/fullstacksushil/sf-kit) o dono quer: teto de tamanho por arquivo, freios antes de aceleradores e revisor que é outro agente. Rotinas e automações virão; o dono quer saber organizá-las e ver se deram certo ou falharam.
- Nenhuma decisão do dono pode se perder no chat. Toda decisão pendente (merge, lavish sem resposta, regra a definir) vira registro com `crew.py ask`, e toda mensagem do chief termina com o mesmo bloco "Suas decisões", tirado do quadro, com link e recomendação em cada uma. Assim o dono lê só a última mensagem e sai respondendo (2026-11-23).
- Ordem de preocupação do dono (2026-11-23): 1) a codebase; 2) lint rules; 3) checks automáticos; 4) skills e `.md`. Sempre que der para fazer algo de forma determinística, faz-se com script; a LLM fica só com o que não é determinístico. Isso barateia, dá constância ao fluxo e mantém qualidade e previsibilidade.
