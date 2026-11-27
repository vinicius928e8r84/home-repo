import html
import json
import os
import re
import shutil
import subprocess
import sys
import types

Fail = None
crew = None

PORTA = "4388"
POLL_MS = "1000"
LIMITE_DO_COMANDO = 90
RECIBO = "Recebido."
CAUSAS_DO_DONO = ("crédito", "credencial")
ANTIGAS = ("mesa.html", "geral.html", "d34-limite-de-linhas.html")
ENCERRADA = ("ended", "user-ended")
ESCAPES = {"n": "\n", "r": "\r", "t": "\t"}
JANELAS = (("5h", "5 horas"), ("7d", "semana"))
SITUACAO = {"allowed": "dentro do limite", "allowed_warning": "perto do limite", "rejected": "no limite"}
ULTIMO_ERRO = {}

ESTILO = """body{margin:0;background:#f6f7f9;color:#1b1f24;font:16px/1.45 system-ui,sans-serif}
main{max-width:56rem;margin:0 auto;padding:1rem}
section{background:#fff;border:1px solid #d9dde3;border-radius:8px;margin:0 0 1rem;padding:.25rem 1rem .75rem}
h1,h2{margin:.75rem 0 .5rem}h2{font-size:1.05rem}
ul{margin:0;padding-left:1.1rem}li{margin:.3rem 0;overflow-wrap:anywhere}
.alerta{border-color:#c0392b}.alerta h2{color:#c0392b}
form{margin:.4rem 0 1rem}textarea{width:100%;box-sizing:border-box;min-height:3.5rem;font:inherit}
button{font:inherit;padding:.3rem .8rem;margin:.2rem .3rem .2rem 0}button[aria-selected=true]{font-weight:700}
.vazio{color:#667}small{color:#556}"""
TABS = """document.querySelectorAll('[role=tab]').forEach(function (aba) {
  aba.addEventListener('click', function () {
    document.querySelectorAll('[role=tab]').forEach(function (outra) { outra.setAttribute('aria-selected', outra === aba); });
    document.querySelectorAll('[role=tabpanel]').forEach(function (painel) { painel.hidden = painel.id !== aba.getAttribute('aria-controls'); });
  });
});"""
ENVIAR = ("event.preventDefault(); const resposta = event.currentTarget.elements.resposta.value.trim(); if (resposta) { "
          "window.lavish.queuePrompt(resposta, { tag: 'decisao', text: '%s', element: event.currentTarget }); window.lavish.sendQueuedPrompts(); }")


def pasta():
    return os.path.join(crew.STATE, "_mesa")


def pagina():
    return os.path.join(pasta(), "mesa.html")


def diario():
    return os.path.join(pasta(), "respostas.jsonl")


def ambiente():
    return dict(os.environ, LAVISH_AXI_PORT=PORTA, LAVISH_AXI_STATE_DIR=os.path.join(pasta(), "lavish"), LAVISH_AXI_IDLE_TIMEOUT_MS="off",
                LAVISH_AXI_DISCONNECT_GRACE_MS="off", LAVISH_AXI_NO_OPEN="1", LAVISH_AXI_TELEMETRY="0")


def executar(argv, env):
    comando = [shutil.which(argv[0]) or argv[0]] + argv[1:]
    try:
        feito = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=LIMITE_DO_COMANDO)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Fail("mesa", "o lavish-axi falhou: %s" % e) from e
    return feito.stdout


def lavish(*args, env=None):
    return executar(["lavish-axi"] + list(args), env or ambiente())


def campos(linha):
    achados, atual, entre_aspas, escapado = [], [], False, False
    for letra in linha:
        if escapado:
            atual.append(ESCAPES.get(letra, letra))
            escapado = False
        elif letra == "\\" and entre_aspas:
            escapado = True
        elif letra == '"':
            entre_aspas = not entre_aspas
        elif letra == "," and not entre_aspas:
            achados.append("".join(atual))
            atual = []
        else:
            atual.append(letra)
    return achados + ["".join(atual)]


def ler_toon(texto):
    situacao = re.search(r"^\s*status: (\S+)", texto, re.M)
    codigo = re.search(r"^code: (\S+)", texto, re.M)
    tabela = re.search(r"^prompts\[(\d+)\]\{([^}]*)\}:\n", texto, re.M)
    prompts = []
    if tabela:
        nomes = tabela.group(2).split(",")
        prompts = [dict(zip(nomes, campos(linha.strip()))) for linha in texto[tabela.end():].splitlines()[:int(tabela.group(1))]]
    encerrada = bool(re.search(r"^\s*session_ended: true", texto, re.M)) or (situacao is not None and situacao.group(1) in ENCERRADA)
    return dict(codigo=codigo.group(1) if codigo else None, encerrada=encerrada, prompts=prompts)


def entradas():
    juntas = {}
    for linha in crew.file_text(diario()).splitlines():
        try:
            item = json.loads(linha)
        except ValueError:
            continue
        juntas.setdefault(item["n"], {}).update(item)
    return juntas


def gravar_entrada(item):
    os.makedirs(pasta(), exist_ok=True)
    with open(diario(), "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def guardar(prompts, origem):
    n = len(entradas())
    for prompt in prompts:
        n += 1
        gravar_entrada(dict(n=n, at=crew.now(), origem=origem, texto=prompt.get("prompt", ""), marca=prompt.get("tag", ""), id=prompt.get("text", "")))


def responder(item):
    atual = crew.decisions().get(item["id"].upper())
    if atual and atual.get("status") == "answered" and atual.get("answer") == item["texto"]:
        return None
    try:
        return crew.cmd_answer(types.SimpleNamespace(id=item["id"], answer=item["texto"])).get("note")
    except Fail as e:
        return "a resposta não entrou: %s" % e.error


def texto_para_o_chief(item, nota):
    if item["origem"] != "mesa":
        return "[mesa] resposta do dono nunca entregue, da página %s: %s" % (item["origem"], item["texto"])
    if item["marca"] != "decisao":
        return "[mesa] o dono escreveu na Mesa: %s" % item["texto"]
    quem = crew.decisions().get(item["id"].upper(), {}).get("worker")
    texto = "[mesa] o dono respondeu %s%s na Mesa: %s" % (item["id"], " (%s)" % quem if quem else "", item["texto"])
    return texto + (" [%s]" % nota if nota else "")


def entregar(chief, item):
    nota = responder(item) if item["origem"] == "mesa" and item["marca"] == "decisao" else None
    crew.tell_chief(chief, texto_para_o_chief(item, nota))
    gravar_entrada(dict(n=item["n"], entregue=True))


def entregar_pendentes(chief):
    for item in sorted((e for e in entradas().values() if not e.get("entregue")), key=lambda e: e["n"]):
        entregar(chief, item)


def esc(texto):
    return html.escape(str(texto), quote=True)


def lista(itens):
    return "<ul>%s</ul>" % "".join("<li>%s</li>" % item for item in itens) if itens else '<p class="vazio">nada</p>'


def secao(titulo, corpo, classe=""):
    return '<section class="%s"><h2>%s</h2>%s</section>' % (classe, titulo, corpo)


def formulario(decisao):
    ident = esc(decisao["id"])
    recomendacao = "<br><small>recomendação do worker: %s</small>" % esc(decisao["recommend"]) if decisao.get("recommend") else ""
    return ('<b>%s</b> [%s · %s] %s%s<form data-lavish-question="%s" onsubmit="%s"><textarea name="resposta" aria-label="Resposta a %s"></textarea>'
            '<button type="submit">Responder</button></form>') % (ident, esc(decisao["repo"]), esc(decisao["worker"]), esc(decisao["question"]),
                                                                    recomendacao, ident, esc(ENVIAR % ident), ident)


def quando(texto):
    painel = crew_painel()
    momento = painel.instante(texto)
    return momento.strftime("%d/%m %H:%M") if momento else "?"


def crew_painel():
    pasta_dos_scripts = os.path.dirname(os.path.abspath(__file__))
    if pasta_dos_scripts not in sys.path:
        sys.path.insert(0, pasta_dos_scripts)
    import crew_painel as painel
    return painel


def do_dono(linha):
    return linha["estado"] in ["parou: %s" % causa for causa in CAUSAS_DO_DONO]


def bloco_do_dono(linhas):
    abertas = crew.module("crew_conversa").open_for_owner([d for d in crew.decisions().values() if d.get("status") == "open"])
    itens = [formulario(d) for d in sorted(abertas, key=lambda d: d["at"])]
    itens += ["<li><b>%s</b> %s: só você resolve. Depois, o Chief retoma o worker.</li>" % (esc(x["nome"]), esc(x["estado"])) for x in linhas if do_dono(x)]
    return secao("Decisões para você", lista(itens), "alerta" if itens else "")


def bloco_dos_parados(linhas):
    parados = [esc(x["texto"]) for x in linhas if x["marca"] == "!" and not do_dono(x)]
    return secao("Parados", lista(parados), "alerta" if parados else "")


def bloco_da_cota():
    cota = crew.module("crew_cota")
    leitura = cota.ler_arquivo()
    if not leitura:
        return secao("Cota", lista(["sem leitura da cota"]))
    itens = []
    for chave, nome in JANELAS:
        janela = (leitura.get("janelas") or {}).get(chave)
        if janela:
            itens.append("%s: %s%% usado, volta em %s" % (nome, janela.get("usado"), quando(janela.get("reset"))))
    itens.append("situação: %s" % SITUACAO.get(leitura.get("status"), leitura.get("status")))
    itens.append("lida às %s%s" % (quando(leitura.get("at")), " (leitura velha)" if cota.velha(leitura) else ""))
    return secao("Cota", lista(esc(i) for i in itens))


def dono_da_trava(quem):
    return "livre" if not quem else quem.get("worker") or quem.get("onde") or "pid %s" % quem.get("pid")


def trava_de(trava):
    texto = "trava %s: %s" % (trava["nome"], dono_da_trava(trava.get("com")))
    esperando = [dono_da_trava(e) for e in trava.get("esperando", [])]
    return texto + ("; esperam: %s" % ", ".join(esperando) if esperando else "")


def linha_da_maquina(maquina):
    recursos = crew.module("crew_recursos")
    nome, leitura = recursos.NOMES[maquina], crew.file_state(recursos.arquivo(maquina))
    if not leitura:
        return "%s: sem leitura" % nome
    if not leitura.get("alcancavel", True):
        return "%s: fora do ar (%s)" % (nome, leitura.get("erro"))
    memoria, disco = leitura.get("memoria", {}), leitura.get("disco", {})
    partes = ["com Folga" if leitura.get("folga") else "sem Folga (%s)" % leitura.get("motivo"),
              "memória %s de %s GB livres" % (recursos.decimal((memoria.get("livre_mb") or 0) / 1024), recursos.decimal((memoria.get("total_mb") or 0) / 1024)),
              "disco %s GB livres" % recursos.decimal(disco.get("livre_gb") or 0)] + [trava_de(t) for t in leitura.get("travas", [])]
    return "%s: %s" % (nome, " · ".join(partes))


def bloco_das_maquinas():
    return secao("Máquinas", lista(esc(linha_da_maquina(m)) for m in crew.module("crew_recursos").MAQUINAS))


def esteira_de_prs():
    prs = crew.file_state(crew.module("crew_prs").arquivo()).get("prs", {})
    return ["%s PR #%s «%s»: %s" % (repo, pr["number"], pr["title"], pr["estado"]) for repo, lista_do_repo in prs.items() for pr in lista_do_repo
            if pr.get("state") == "OPEN"]


def abas(linhas):
    corpo = [("aba-workers", "Workers", lista(esc(x["texto"]) for x in linhas)), ("aba-prs", "PRs", lista(esc(p) for p in esteira_de_prs()))]
    botoes = "".join('<button role="tab" aria-selected="%s" aria-controls="%s">%s</button>' % ("true" if i == 0 else "false", ident, nome)
                     for i, (ident, nome, _) in enumerate(corpo))
    paineis = "".join('<div role="tabpanel" id="%s"%s>%s</div>' % (ident, "" if i == 0 else " hidden", texto) for i, (ident, _, texto) in enumerate(corpo))
    return '<section><div role="tablist">%s</div>%s</section>' % (botoes, paineis)


def montar_pagina():
    linhas = crew_painel().linhas(crew.workers(True), crew.decisions(), crew.STATE)
    corpo = "<h1>Mesa</h1>" + bloco_do_dono(linhas) + bloco_dos_parados(linhas) + bloco_da_cota() + bloco_das_maquinas() + abas(linhas)
    return ('<!doctype html><html lang="pt-BR" data-lavish-annotate="off"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Mesa</title><style>%s</style></head>'
            "<body><main>%s</main><script>%s</script></body></html>") % (ESTILO, corpo, TABS)


def gravar_pagina():
    nova = montar_pagina()
    os.makedirs(pasta(), exist_ok=True)
    if crew.file_text(pagina()) != nova.strip():
        crew.write_text(pagina(), nova)


def ouvir(chief):
    resposta = ler_toon(lavish("poll", pagina(), "--timeout-ms", POLL_MS, "--owner", "vigia"))
    if resposta["codigo"] == "NOT_FOUND":
        lavish(pagina(), "--no-open")
        return None
    if resposta["codigo"]:
        return "o poll da Mesa deu %s" % resposta["codigo"]
    guardar(resposta["prompts"], "mesa")
    entregar_pendentes(chief)
    if resposta["encerrada"]:
        lavish(pagina(), "--reopen", "--no-open")
    if resposta["prompts"]:
        lavish("reply", pagina(), "--agent-reply", RECIBO)
    return None


def paginas_antigas():
    try:
        sessoes = json.loads(crew.module("crew_dono").ler_do_pc()).get("sessions", {}).values()
    except ValueError:
        return []
    return [s["file"] for s in sessoes if s.get("prompts") and os.path.basename(s["file"].replace("\\", "/")) in ANTIGAS]


def ouvir_antigas(chief):
    for arquivo in paginas_antigas():
        resposta = ler_toon(lavish("poll", arquivo, "--timeout-ms", POLL_MS, "--owner", "vigia", env=dict(os.environ)))
        guardar(resposta["prompts"], os.path.basename(arquivo.replace("\\", "/")))
    entregar_pendentes(chief)


def rodada(chief):
    try:
        entregar_pendentes(chief)
        gravar_pagina()
        erro = ouvir(chief)
        ouvir_antigas(chief)
    except (Fail, OSError) as e:
        erro = getattr(e, "error", None) or str(e)
    if erro == ULTIMO_ERRO.get("texto"):
        return None
    ULTIMO_ERRO["texto"] = erro
    return erro
