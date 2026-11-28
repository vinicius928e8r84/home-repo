import os
import shutil

Fail = None
crew = None


def achar(nome):
    achado = shutil.which(nome)
    if achado or os.name != "nt":
        return achado
    for pasta in os.environ.get("PATH", "").split(os.pathsep):
        achado = shutil.which(nome, path=alvo_do_junction(pasta))
        if achado:
            return achado
    return None


def alvo_do_junction(pasta):
    try:
        return os.readlink(pasta).removeprefix("\\\\?\\")
    except (OSError, ValueError):
        return ""
