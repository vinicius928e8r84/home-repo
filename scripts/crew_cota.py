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
ULTIMA_TENTATIVA = {}


def arquivo():
    return os.path.join(crew.STATE, "_cota.json")


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
        return json.loads(feito.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        raise Fail("cota", "o quota-axi não respondeu: %s" % e) from e


def usado(janela):
    if "percentUsed" in janela:
        return round(janela["percentUsed"])
    return round(100 - janela["percentRemaining"])


def reset(janela):
    momento = instante(janela.get("resetsAt"))
    if momento is None:
        return None
    arredondado = momento.replace(microsecond=0) + datetime.timedelta(seconds=momento.microsecond // 500000)
    return texto_da_hora(arredondado.astimezone(datetime.timezone.utc))


def extra_de(janela):
    if janela is None:
        return dict(status="rejected", reset=None, ligado=False, gasto_usd=None, limite_usd=None)
    return dict(status="rejected" if usado(janela) >= 100 else "allowed", reset=None, ligado=True,
                gasto_usd=janela.get("spentUsd"), limite_usd=janela.get("limitUsd"))


def da_leitura(saida):
    claude = next((p for p in saida.get("providers", []) if p.get("provider") == "claude"), {})
    achadas = {j["id"]: j for j in claude.get("windows", [])}
    if not any(nome in achadas for nome in JANELAS):
        raise Fail("cota", "o quota-axi não trouxe a janela semanal nem a de 5 h da conta Claude")
    usos = {nome: usado(achadas[nome]) for nome in JANELAS if nome in achadas}
    status = "rejected" if max(usos.values()) >= 100 else "allowed"
    janelas = {curto: dict(usado=usos[nome], reset=reset(achadas[nome]), status=status) if nome in achadas else None
               for nome, curto in JANELAS.items()}
    return dict(at=texto_da_hora(agora_utc()), fonte="quota-axi", host=HOSTS.get(sys.platform, "vps"), status=status,
                limitante=max(usos, key=usos.get), janelas=janelas, extra=extra_de(achadas.get("extra_usage")))


def refresh():
    if not velha(ler_arquivo()):
        return
    agora = crew.time.time()
    if agora - ULTIMA_TENTATIVA.get("t", -ESPERA_APOS_FALHA) < ESPERA_APOS_FALHA:
        return
    ULTIMA_TENTATIVA["t"] = agora
    try:
        leitura = da_leitura(ler())
    except Fail as e:
        print(json.dumps(dict(ok=False, step=e.step, error=e.error), ensure_ascii=False), flush=True)
        return
    os.makedirs(crew.STATE, exist_ok=True)
    crew.write_text(arquivo(), json.dumps(leitura))
