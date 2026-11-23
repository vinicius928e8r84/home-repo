import json
from pathlib import Path

from scripts.freios.contexto import Achado
from scripts.freios.git import conteudo_na_ref

ARQUIVO = "scripts/freios/linha-de-base.json"
SUFIXO_DAS_LINHAS = "#linhas"
ATUALIZAR = "python scripts/freios/freios.py --tudo --atualizar-linha-de-base"


def arquivo_do_grupo(chave):
    return chave.removesuffix(SUFIXO_DAS_LINHAS)


def agrupar(achados):
    grupos = {}
    for achado in achados:
        item = grupos.setdefault(achado.grupo or achado.arquivo, {"medida": 0, "achados": []})
        item["medida"] += achado.medida
        item["achados"].append(achado)
    return grupos


def ler_linha_de_base(texto, origem):
    try:
        dados = json.loads(texto)
    except ValueError as erro:
        raise ValueError(f"{origem} não é um JSON válido ({erro})") from erro
    ok = isinstance(dados, dict) and all(isinstance(v, dict) for v in dados.values())
    ok = ok and all(isinstance(n, int) and n >= 1 for v in dados.values() for n in v.values())
    if not ok:
        raise ValueError(f"{origem} precisa ser {{verificação: {{arquivo: inteiro a partir de 1}}}}")
    return dados


def carregar(ctx):
    entrada = ctx.arquivos.get(ARQUIVO)
    texto = ctx.texto(entrada) if entrada else None
    atual = ler_linha_de_base(texto, ARQUIVO) if texto else {}
    if ctx.execucao != "tudo":
        return atual, None
    antiga = conteudo_na_ref(ctx.raiz, ctx.base, ARQUIVO)
    if antiga is None:
        ctx.avisos.append(f"{ctx.base} ainda não tem {ARQUIVO}: esta é a primeira linha de base, nada a comparar")
        return atual, None
    return atual, ler_linha_de_base(antiga, f"{ctx.base}:{ARQUIVO}")


def _julgar(verificacao, chave, item, antes):
    arquivo = arquivo_do_grupo(chave)
    medida = item["medida"]
    if antes is None:
        return item["achados"]
    if medida > antes:
        detalhe = f"piorou: {medida} contra {antes} na linha de base, que só encolhe; conserte o que entrou de novo"
        return [Achado(verificacao, arquivo, detalhe, grupo=chave)]
    if medida < antes:
        detalhe = f"melhorou de {antes} para {medida}: rode `{ATUALIZAR}` e versione {ARQUIVO}"
        return [Achado(verificacao, arquivo, detalhe, grupo=chave)]
    return []


def _sumidos(verificacao, base, grupos, foco):
    sumidos = [c for c in sorted(base) if c not in grupos and (foco is None or arquivo_do_grupo(c) in foco)]
    detalhe = f"não tem mais achados: rode `{ATUALIZAR}` para tirá-lo da linha de base"
    return [Achado(verificacao, arquivo_do_grupo(c), detalhe, grupo=c) for c in sumidos]


def _crescimento(verificacao, base, teto):
    achados = []
    for chave, valor in sorted(base.items()):
        antes = teto.get(chave)
        if antes is not None and valor <= antes:
            continue
        motivo = "entrou na linha de base, que só encolhe: conserte em vez de listar"
        if antes is not None:
            motivo = f"a linha de base subiu de {antes} para {valor}: ela só encolhe"
        achados.append(Achado(verificacao, ARQUIVO, f"{chave}: {motivo}"))
    return achados


def aplicar(ctx, verificacao, achados, linha_de_base):
    atual, teto = linha_de_base
    base = atual.get(verificacao, {})
    foco = {e.caminho for e in ctx.alvos} if ctx.execucao == "commit" else None
    soltos = [a for a in achados if not (a.grupo or a.arquivo)]
    grupos = agrupar(a for a in achados if a.grupo or a.arquivo)
    falhas = list(soltos)
    for chave, item in sorted(grupos.items()):
        falhas += _julgar(verificacao, chave, item, base.get(chave))
    falhas += _sumidos(verificacao, base, grupos, foco)
    if teto is not None:
        falhas += _crescimento(verificacao, base, teto.get(verificacao, {}))
    divida = sum(len(i["achados"]) for c, i in grupos.items() if base.get(c) == i["medida"])
    return falhas, divida


def _gravar(ctx, dados, ordem):
    ordenado = {v: dict(sorted(dados[v].items())) for v in ordem if v in dados}
    texto = json.dumps(ordenado, ensure_ascii=False, indent=2) + "\n"
    destino = Path(ctx.raiz) / ARQUIVO
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(texto.encode("utf-8"))


def _medidas(achados):
    return {chave: item["medida"] for chave, item in agrupar(achados).items()}


def criar(ctx, resultados):
    atual, _ = carregar(ctx)
    faltam = [v for v in resultados if v not in atual]
    if not faltam:
        return 1, [f"{ARQUIVO} já tem a linha de base de {', '.join(resultados)}; ela só encolhe ({ATUALIZAR})"]
    for verificacao in faltam:
        atual[verificacao] = _medidas(resultados[verificacao])
    _gravar(ctx, atual, ctx.limites["linha_de_base"]["verificacoes"])
    return 0, [f"linha de base de {v} criada com {len(atual[v])} arquivo(s)" for v in faltam]


def _atualizar_uma(verificacao, achados, antes):
    nova, erros = {}, []
    for chave, medida in _medidas(achados).items():
        if chave not in antes or medida > antes[chave]:
            erros.append(f"{verificacao} {chave}: {medida}, acima da linha de base ({antes.get(chave, 'ausente')}); conserte")
        else:
            nova[chave] = medida
    return nova, erros


def atualizar(ctx, resultados):
    atual, _ = carregar(ctx)
    if not atual:
        return 1, [f"{ARQUIVO} não existe; crie-a com --criar-linha-de-base"]
    novos, erros = dict(atual), []
    for verificacao, achados in resultados.items():
        if verificacao in atual:
            novos[verificacao], falhas = _atualizar_uma(verificacao, achados, atual[verificacao])
            erros += falhas
    if erros:
        return 1, [*erros, "nada foi atualizado: a linha de base só encolhe"]
    _gravar(ctx, novos, ctx.limites["linha_de_base"]["verificacoes"])
    return 0, [f"linha de base de {v} atualizada: {len(novos[v])} arquivo(s)" for v in resultados if v in atual]
