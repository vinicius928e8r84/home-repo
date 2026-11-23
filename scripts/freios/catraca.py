from scripts.freios.contexto import Achado, Configuracao, Contexto, Selecao
from scripts.freios.git import entradas_da_ref, leitor_do_indice, ponto_de_comparacao


def chave_do_achado(achado):
    return achado.grupo or achado.arquivo


def agrupar(achados):
    grupos = {}
    for achado in achados:
        item = grupos.setdefault(chave_do_achado(achado), {"medida": 0, "achados": []})
        item["medida"] += achado.medida
        item["achados"].append(achado)
    return grupos


def contexto_da_base(ctx, ponto, arquivos):
    universo = entradas_da_ref(ctx.raiz, ponto)
    alvos = [e for e in universo if e.caminho in arquivos]
    configuracao = Configuracao(ctx.limites, ctx.excecoes, ctx.base, ctx.execucao)
    return Contexto(ctx.raiz, Selecao(universo, alvos), leitor_do_indice(ctx.raiz), configuracao)


def medidas_da_base(ctx, verificacao, achados):
    ponto = ponto_de_comparacao(ctx.raiz, ctx.base)
    if ponto is None:
        ctx.avisos.append(f"{ctx.base} não existe aqui: sem teto da main, todo achado reprova")
        return {}
    arquivos = {a.arquivo for a in achados if a.arquivo}
    base = contexto_da_base(ctx, ponto, arquivos)
    return {chave: item["medida"] for chave, item in agrupar(verificacao.verificar(base)).items()}


def julgar(item, teto, ponto):
    if teto is None:
        return item["achados"]
    if item["medida"] > teto:
        primeiro = item["achados"][0]
        detalhe = f"piorou: {item['medida']} contra {teto} na main ({ponto}); o teto do arquivo é a medida dele na main"
        return [Achado(primeiro.verificacao, primeiro.arquivo, detalhe, grupo=primeiro.grupo)]
    return []


def aplicar(ctx, verificacao, achados):
    soltos = [a for a in achados if not chave_do_achado(a)]
    grupos = agrupar(a for a in achados if chave_do_achado(a))
    if not grupos:
        return soltos, 0
    tetos = medidas_da_base(ctx, verificacao, achados)
    ponto = (ponto_de_comparacao(ctx.raiz, ctx.base) or "")[:7]
    falhas = list(soltos)
    divida = 0
    for chave, item in sorted(grupos.items()):
        achou = julgar(item, tetos.get(chave), ponto)
        falhas += achou
        divida += 0 if achou else len(item["achados"])
    return falhas, divida
