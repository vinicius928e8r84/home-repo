# Como o dono quer trabalhar com o chief

## 2026-11-23

- O dono não fala com workers. O chief é o intermediário: ele lê os relatórios, responde aos prompts dos workers (inclusive as telas de confiança do Pi) e leva ao dono só as decisões, no chat ou num lavish. Objetivo, nas palavras dele: "poupar minha atenção".
- Os painéis dos workers que o `crew.py` abre como abas no workspace do chief chamaram a atenção do dono ("teve outro terminal aqui que foi spawnado"). Ele leu o fim do worker do inventário direto no painel.
- Decisões em rodadas de grilling vão para uma página lavish, e o dono responde marcando opções. Ele fecha a sessão pelo navegador, e a resposta chega de uma vez.
- Merge de PR que muda as regras do repo: o chief deixa a PR verde e revisada e avisa, e o dono mescla (resposta à Q18 do grilling do glossário).

## Problemas de ferramenta vistos em 2026-11-23

- O `crew.py spawn` parou na tela "Trust parent folder (C:\Users\sadvi\worktrees)" do Pi. O chief escolheu "Trust parent folder", então os próximos spawns em `~/worktrees` não devem mais vê-la. Se ela voltar, o `spawn` precisa tratá-la.
- `crew.py read` quebrava com `UnicodeEncodeError` no console cp1252. Corrigido no home-repo com `sys.stdout.reconfigure(encoding="utf-8")` em `main()`.
