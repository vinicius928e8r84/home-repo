import concurrent.futures
import datetime
import json
import os
import re
import statistics
import subprocess
import sys

Fail = None
crew = None

MAQUINAS = ("pc", "vps", "mac")
NOMES = {"pc": "PC", "vps": "VPS", "mac": "Mac"}
SISTEMAS = {"pc": "windows", "vps": "linux", "mac": "macos"}
LOCAL = {"win32": "pc", "linux": "vps", "darwin": "mac"}
HOSPEDEIRO = {"vps": "vps", "mac": "fm-mac"}
LEITURAS_GUARDADAS = 3
MEMORIA_MINIMA_GB = (3, 4)
DISCO_MINIMO_GB = (10, 15)
CARGA_MAXIMA = (2.0, 1.5)
USO_MAXIMO = 90
PRESSAO_MAXIMA = 80
LIMITE_DA_LEITURA = 60
INTERVALO = 60
LEITURA_EM_CURSO = {}
TRAVA_E2E_NA_VPS = "~/crew-state/e2e.lock"
TRAVA_DO_MAC_NA_VPS = "~/crew-state/mac.lock"
TRAVA_DO_MAC_NO_MAC = "/tmp/fm-mac.lock"
TRAVAS_NA_VPS = (("e2e", TRAVA_E2E_NA_VPS), ("mac", TRAVA_DO_MAC_NA_VPS))
TRAVAS_DA_MAQUINA = {"pc": (), "vps": ("e2e",), "mac": ("mac",)}

SCRIPT_PC = r'''$ProgressPreference='SilentlyContinue'
$os=Get-CimInstance Win32_OperatingSystem -Property FreePhysicalMemory,TotalVisibleMemorySize
$p=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'" -Property PercentProcessorTime
$s=Get-CimInstance Win32_PerfFormattedData_PerfOS_System -Property ProcessorQueueLength
$d=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" -Property FreeSpace,Size
[pscustomobject]@{livre_mb=[int]($os.FreePhysicalMemory/1KB); total_mb=[int]($os.TotalVisibleMemorySize/1KB); cpu_pct=$p.PercentProcessorTime; fila=$s.ProcessorQueueLength; nucleos=[Environment]::ProcessorCount; disco_livre_gb=[math]::Round($d.FreeSpace/1GB,1); disco_total_gb=[math]::Round($d.Size/1GB,1)} | ConvertTo-Json -Compress
'''

SCRIPT_VPS = r'''echo '##meminfo'; grep -E '^(MemTotal|MemAvailable):' /proc/meminfo
echo '##loadavg'; cat /proc/loadavg
echo '##pressure'; cat /proc/pressure/cpu 2>/dev/null
echo '##nproc'; nproc
echo '##df'; df -B1 --output=avail,size /
T=$(lslocks -n -r -o PID,MODE,BLOCKER,PATH 2>/dev/null | grep -E '/crew-state/(e2e|mac)\.lock')
echo '##travas'; echo "$T"
echo '##procs'; echo "$T" | awk '{print $1}' | sort -u | while read p; do [ -n "$p" ] && echo "$p|$(readlink /proc/$p/cwd)|$(ps -o etimes= -p $p | tr -d ' ')"; done
true
'''

SCRIPT_MAC = '''echo '##ncpu'; sysctl -n hw.ncpu
echo '##memsize'; sysctl -n hw.memsize
echo '##loadavg'; sysctl -n vm.loadavg
echo '##pressure'; memory_pressure -Q
echo '##df'; df -k /
echo '##procs'; for p in $(lsof -t %s 2>/dev/null); do echo "$p|$(lsof -a -d cwd -p $p -Fn 2>/dev/null | sed -n 's/^n//p')|$(ps -o etime= -p $p | tr -d ' ')"; done
true
''' % TRAVA_DO_MAC_NO_MAC

SCRIPTS = {"pc": SCRIPT_PC, "vps": SCRIPT_VPS, "mac": SCRIPT_MAC}


def arquivo(maquina):
    return os.path.join(crew.STATE, "_recursos-%s.json" % maquina)


def agora_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def aqui():
    return LOCAL.get(sys.platform)


def ler_aqui(maquina):
    argv = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "-"] if maquina == "pc" else ["sh", "-s"]
    try:
        feito = subprocess.run(argv, input=SCRIPTS[maquina], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=LIMITE_DA_LEITURA)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Fail("recursos", "a leitura do %s falhou: %s" % (NOMES[maquina], e)) from e
    if feito.returncode != 0:
        raise Fail("recursos", (feito.stderr or feito.stdout).strip() or "exit %d" % feito.returncode)
    return feito.stdout


def ler_por_ssh(maquina):
    if maquina == "pc":
        raise Fail("recursos", "o PC só é lido de dentro dele")
    pelo_vps = maquina == "mac" and aqui() != "vps"
    host = HOSPEDEIRO["vps"] if pelo_vps else HOSPEDEIRO[maquina]
    comando = "ssh -o BatchMode=yes -o ConnectTimeout=10 %s sh -s" % HOSPEDEIRO[maquina] if pelo_vps else "sh -s"
    return crew.module("crew_remote").ssh(host, comando, "recursos", stdin=SCRIPTS[maquina])


def ler(maquina):
    return ler_aqui(maquina) if aqui() == maquina else ler_por_ssh(maquina)


def secoes(texto):
    achadas, atual = {}, None
    for linha in texto.splitlines():
        if linha.startswith("##"):
            atual = achadas.setdefault(linha[2:].strip(), [])
        elif atual is not None and linha.strip():
            atual.append(linha)
    return achadas


def gb(bytes_):
    return round(bytes_ / 2 ** 30, 1)


def segundos(texto):
    if not texto:
        return None
    dias, _, resto = texto.rpartition("-")
    total = 0
    for parte in resto.split(":"):
        total = total * 60 + int(parte)
    return total + int(dias or 0) * 86400


def processos(linhas):
    achados = {}
    for linha in linhas:
        pid, cwd, tempo = linha.split("|")
        achados[int(pid)] = dict(cwd=cwd, ha_s=segundos(tempo))
    return achados


def quem(pid, procs):
    return dict(pid=pid, **procs.get(pid, dict(cwd="", ha_s=None)))


def travas_da_vps(achadas):
    procs = processos(achadas.get("procs", []))
    linhas = []
    for linha in achadas.get("travas", []):
        pid, modo, resto = linha.split(" ", 2)
        linhas.append((int(pid), modo.endswith("*"), resto.partition(" ")[2]))
    travas = []
    for nome, caminho in TRAVAS_NA_VPS:
        deles = [(pid, espera) for pid, espera, achado in linhas if achado.endswith(caminho[1:])]
        travas.append(dict(nome=nome, lugar="vps", caminho=caminho, com=next((quem(pid, procs) for pid, espera in deles if not espera), None),
                           esperando=[quem(pid, procs) for pid, espera in deles if espera]))
    return travas


def trava_do_mac(achadas):
    procs = processos(achadas.get("procs", []))
    dono = next(iter(procs), None)
    return [dict(nome="mac", lugar="mac", caminho=TRAVA_DO_MAC_NO_MAC, com=None if dono is None else quem(dono, procs), esperando=[])]


def identificar(com, workers):
    if com is None:
        return None
    cwd = com["cwd"]
    achado = next((w for w in workers if w.get("worktree") and (cwd == w["worktree"] or cwd.startswith(w["worktree"] + "/"))), None)
    onde = cwd.split("/worktrees/", 1)[1].split("/")[0] if "/worktrees/" in cwd else cwd
    return dict(pid=com["pid"], onde=onde, worker=achado["name"] if achado else None, ha_s=com["ha_s"])


def medir_pc(texto):
    lido = json.loads(texto)
    return dict(nucleos=lido["nucleos"], livre_mb=lido["livre_mb"], total_mb=lido.get("total_mb"), disco_livre_gb=lido["disco_livre_gb"],
                disco_total_gb=lido.get("disco_total_gb"), uso_pct=lido["cpu_pct"], fila=lido["fila"])


def medir_vps(texto):
    achadas = secoes(texto)
    memoria = {linha.split(":")[0]: int(linha.split()[1]) for linha in achadas["meminfo"]}
    pressao = next((float(linha.split("avg60=")[1].split()[0]) for linha in achadas.get("pressure", []) if linha.startswith("some")), None)
    livre, total = (int(n) for n in achadas["df"][-1].split()[:2])
    return dict(nucleos=int(achadas["nproc"][0]), livre_mb=memoria["MemAvailable"] // 1024, total_mb=memoria["MemTotal"] // 1024,
                disco_livre_gb=gb(livre), disco_total_gb=gb(total), carga_5m=float(achadas["loadavg"][0].split()[1]), pressao_60s=pressao,
                travas=travas_da_vps(achadas))


def medir_mac(texto):
    achadas = secoes(texto)
    total_mb = int(achadas["memsize"][0]) // 2 ** 20
    livre_pct = int(re.search(r"free percentage: (\d+)%", " ".join(achadas["pressure"])).group(1))
    disco = achadas["df"][-1].split()
    return dict(nucleos=int(achadas["ncpu"][0]), livre_mb=total_mb * livre_pct // 100, total_mb=total_mb,
                disco_livre_gb=gb(int(disco[3]) * 1024), disco_total_gb=gb(int(disco[1]) * 1024),
                carga_5m=float(achadas["loadavg"][0].strip("{} ").split()[1]), travas=trava_do_mac(achadas))


MEDIDORES = {"pc": medir_pc, "vps": medir_vps, "mac": medir_mac}
CAMPOS_DA_LEITURA = ("livre_mb", "disco_livre_gb", "uso_pct", "fila", "carga_5m", "pressao_60s")


def mediana(historico, campo):
    valores = [h[campo] for h in historico if h.get(campo) is not None]
    return statistics.median(valores) if valores else None


def virgula(texto):
    return texto.replace(".", ",")


def decimal(valor):
    return virgula("%.1f" % valor)


def avaliar(nucleos, historico, tinha_folga):
    i = 0 if tinha_folga else 1
    volta = "" if tinha_folga else "para voltar, "
    acima = (lambda valor, teto: valor > teto) if tinha_folga else (lambda valor, teto: valor >= teto)
    razoes, processador = [], []
    memoria, disco = mediana(historico, "livre_mb") / 1024, mediana(historico, "disco_livre_gb")
    if memoria < MEMORIA_MINIMA_GB[i]:
        razoes.append("memória: %s GB livres (%smínimo %d)" % (decimal(memoria), volta, MEMORIA_MINIMA_GB[i]))
    if disco < DISCO_MINIMO_GB[i]:
        razoes.append("disco: %s GB livres (%smínimo %d)" % (decimal(disco), volta, DISCO_MINIMO_GB[i]))
    teto = CARGA_MAXIMA[i] * nucleos
    uso, fila, carga, pressao = (mediana(historico, c) for c in ("uso_pct", "fila", "carga_5m", "pressao_60s"))
    if uso is not None and uso > USO_MAXIMO:
        processador.append("uso %d%% (máximo %d)" % (uso, USO_MAXIMO))
    if fila is not None and acima(fila, teto):
        processador.append("fila %s em %d núcleos (%smáximo %s)" % (virgula("%g" % fila), nucleos, volta, decimal(teto)))
    if carga is not None and acima(carga, teto):
        processador.append("carga de 5 min %s em %d núcleos (%smáximo %s)" % (decimal(carga), nucleos, volta, decimal(teto)))
    if pressao is not None and pressao > PRESSAO_MAXIMA:
        processador.append("pressão %d%% (máximo %d)" % (pressao, PRESSAO_MAXIMA))
    if processador:
        razoes.append("processador: " + " e ".join(processador))
    return not razoes, "; ".join(razoes) or None


def ler_arquivo(maquina):
    antigo = crew.file_state(arquivo(maquina))
    return antigo if isinstance(antigo, dict) else {}


def montar(maquina, medida, antigo, travas):
    historico = (antigo.get("historico") or [])[-(LEITURAS_GUARDADAS - 1):] + [{c: medida.get(c) for c in CAMPOS_DA_LEITURA}]
    folga, motivo = avaliar(medida["nucleos"], historico, antigo.get("folga", True))
    return dict(at=agora_utc(), host=maquina, sistema=SISTEMAS[maquina], alcancavel=True, nucleos=medida["nucleos"],
                memoria=dict(livre_mb=medida["livre_mb"], total_mb=medida.get("total_mb"), mediana_mb=int(mediana(historico, "livre_mb"))),
                cpu=dict(uso_pct=medida.get("uso_pct"), fila=medida.get("fila"), carga_5m=medida.get("carga_5m"), pressao_60s=medida.get("pressao_60s")),
                disco=dict(livre_gb=medida["disco_livre_gb"], total_gb=medida.get("disco_total_gb")),
                travas=travas, folga=folga, motivo=motivo, historico=historico)


def fora(maquina, erro, travas):
    return dict(at=agora_utc(), host=maquina, sistema=SISTEMAS[maquina], alcancavel=False, erro=erro, travas=travas, folga=False,
                motivo="%s fora" % NOMES[maquina], historico=[])


def tentar_ler(maquina):
    try:
        return maquina, ler(maquina), None
    except (Fail, OSError) as e:
        return maquina, None, getattr(e, "error", str(e))


def resumo_de(maquina, leitura):
    return dict(alcancavel=leitura["alcancavel"], folga=leitura["folga"], motivo=leitura["motivo"], arquivo=crew.posix(arquivo(maquina)))


def medir(lidas):
    medidas, erros = {}, {}
    for maquina, texto, erro in lidas:
        try:
            if erro:
                erros[maquina] = erro
            else:
                medidas[maquina] = MEDIDORES[maquina](texto)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
            erros[maquina] = "a leitura do %s veio num formato que não entendo: %s" % (NOMES[maquina], e)
    return medidas, erros


def comando(a):
    with concurrent.futures.ThreadPoolExecutor(len(MAQUINAS)) as pool:
        lidas = list(pool.map(tentar_ler, MAQUINAS))
    medidas, erros = medir(lidas)
    workers = crew.workers()
    travas = [dict(t, com=identificar(t["com"], workers), esperando=[identificar(e, workers) for e in t["esperando"]])
              for medida in medidas.values() for t in medida.get("travas", [])]
    os.makedirs(crew.STATE, exist_ok=True)
    resultado = {}
    for maquina in MAQUINAS:
        minhas = [t for t in travas if t["nome"] in TRAVAS_DA_MAQUINA[maquina]]
        leitura = fora(maquina, erros[maquina], minhas) if maquina in erros else montar(maquina, medidas[maquina], ler_arquivo(maquina), minhas)
        crew.write_text(arquivo(maquina), json.dumps(leitura, ensure_ascii=False))
        resultado[maquina] = resumo_de(maquina, leitura)
    return dict(ok=True, maquinas=resultado)


def disparar():
    os.makedirs(crew.STATE, exist_ok=True)
    comando_do_crew = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "crew.py"), "recursos"]
    extra = dict(creationflags=0x08000000 | 0x00000200) if os.name == "nt" else dict(start_new_session=True)
    with open(os.path.join(crew.STATE, "recursos.log"), "w", encoding="utf-8") as log:
        return subprocess.Popen(comando_do_crew, cwd=crew.ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log, **extra)


def refresh():
    agora = crew.time.time()
    anterior = LEITURA_EM_CURSO.get("processo")
    if anterior is not None and anterior.poll() is None:
        return None
    if agora - LEITURA_EM_CURSO.get("t", agora - INTERVALO) < INTERVALO:
        return None
    try:
        LEITURA_EM_CURSO.update(processo=disparar(), t=agora)
    except OSError as e:
        LEITURA_EM_CURSO.update(processo=None, t=agora)
        return "não consegui abrir a leitura dos recursos: %s" % e
    return None
