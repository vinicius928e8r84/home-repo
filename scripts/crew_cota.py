import datetime
import json
import os
import shutil
import subprocess
import sys

Fail = None
crew = None

VELHA_MINUTOS = 15
ESPERA_APOS_FALHA = 60
LIMITE_DA_LEITURA = 60
JANELAS = {"five_hour": "5h", "seven_day": "7d"}
HOSTS = {"win32": "pc", "darwin": "mac"}


def arquivo():
    return os.path.join(crew.STATE, "_cota.json")


def arquivo_da_tentativa():
    return os.path.join(crew.STATE, "cota-tentativa.json")


def agora_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def texto_da_hora(momento):
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


def instante(texto):
    try:
        momento = datetime.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=datetime.timezone.utc)


def velha(leitura):
    feita = instante(leitura.get("at"))
    return feita is None or agora_utc() - feita > datetime.timedelta(minutes=VELHA_MINUTOS)


def ler_arquivo():
    try:
        with open(arquivo(), encoding="utf-8") as f:
            leitura = json.load(f)
    except (OSError, ValueError):
        return {}
    return leitura if isinstance(leitura, dict) else {}


def ler():
    comando = shutil.which("quota-axi")
    if not comando:
        raise Fail("cota", "o quota-axi não está instalado")
    try:
        feito = subprocess.run([comando, "--provider", "claude", "--json"], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=LIMITE_DA_LEITURA)
        saida = json.loads(feito.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        raise Fail("cota", "o quota-axi não respondeu: %s" % e) from e
    if not isinstance(saida, dict):
        raise Fail("cota", "o quota-axi respondeu fora do formato")
    return saida


def usado(janela):
    if isinstance(janela.get("percentUsed"), (int, float)):
        return round(janela["percentUsed"])
    if isinstance(janela.get("percentRemaining"), (int, float)):
        return round(100 - janela["percentRemaining"])
    return None


def reset(janela):
    momento = instante(janela.get("resetsAt"))
    if momento is None:
        return None
    arredondado = momento.replace(microsecond=0) + datetime.timedelta(seconds=momento.microsecond // 500000)
    return texto_da_hora(arredondado.astimezone(datetime.timezone.utc))


def extra_de(janela):
    if janela is None:
        return dict(status="rejected", reset=None, ligado=False, gasto_usd=None, limite_usd=None)
    return dict(status="rejected" if (usado(janela) or 0) >= 100 else "allowed", reset=None, ligado=True,
                gasto_usd=janela.get("spentUsd"), limite_usd=janela.get("limitUsd"))


def da_leitura(saida):
    claude = next((p for p in saida.get("providers", []) if p.get("provider") == "claude"), {})
    achadas = {j.get("id"): j for j in claude.get("windows", [])}
    usos = {nome: usado(achadas[nome]) for nome in JANELAS if nome in achadas and usado(achadas[nome]) is not None}
    if not usos:
        motivo = (claude.get("state") or {}).get("error")
        raise Fail("cota", "o quota-axi não trouxe a janela semanal nem a de 5 h da conta Claude" + (" (%s)" % motivo if motivo else ""))
    status = "rejected" if max(usos.values()) >= 100 else "allowed"
    janelas = {curto: dict(usado=usos[nome], reset=reset(achadas[nome]), status=status) if nome in usos else None
               for nome, curto in JANELAS.items()}
    return dict(at=texto_da_hora(agora_utc()), fonte="quota-axi", host=HOSTS.get(sys.platform, "vps"), status=status,
                limitante=max(usos, key=usos.get), janelas=janelas, extra=extra_de(achadas.get("extra_usage")))


def gravar(caminho, dados):
    os.makedirs(crew.STATE, exist_ok=True)
    crew.write_text(caminho, json.dumps(dados, ensure_ascii=False))


def refresh():
    if not velha(ler_arquivo()):
        return
    agora = crew.time.time()
    anterior = crew.file_state(arquivo_da_tentativa())
    if agora - anterior.get("t", -ESPERA_APOS_FALHA) < ESPERA_APOS_FALHA:
        return
    try:
        leitura, erro = da_leitura(ler()), None
    except Fail as e:
        leitura, erro = None, e.error
    gravar(arquivo_da_tentativa(), dict(t=agora, at=crew.now(), erro=erro))
    if leitura:
        gravar(arquivo(), leitura)
