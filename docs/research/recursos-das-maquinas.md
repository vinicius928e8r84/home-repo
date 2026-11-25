# Como o chief lê os recursos do PC e da VPS para decidir

Pesquisa do ticket [Como o chief lê os recursos do PC e da VPS para decidir](https://github.com/vinicius928e8r84/home-repo/issues/49), do mapa [Frota e painel do home-repo](https://github.com/vinicius928e8r84/home-repo/issues/26). Feita em 25/11/2026, entre 07:30 e 08:00 UTC. As medições foram feitas de verdade, só com leituras: a VPS (`srv1835512`, onde este worker roda), o PC (`ssh windows-pc`, Windows 11 e PowerShell 5.1) e o Mac (`ssh fm-mac`, macOS 15.6.1).

## Resposta curta

- **Não existe nada pronto que leia os recursos.** O quota-axi só lê cota de provedores, não há `recurso-axi` nem nada parecido no npm, e o `psutil` não está instalado nem no PC nem na VPS. Os comandos do sistema bastam, e todos dão número ou JSON.
- **Formato:** um `crew.py recursos [--json]` em Python, só com a biblioteca padrão, como o resto do `crew.py`. Cada máquina grava a sua leitura em `state/crew/_recursos.json`, ao lado do `_cota.json`, e o chief lê o arquivo do PC e o da VPS. Um pacote axi novo não se paga para três máquinas que já sabemos ler.
- **Regra:** não abrir agente numa máquina com menos de 3 GB de memória livre, menos de 10 GB de disco ou o processador saturado (Linux: carga de 5 min acima de 2× os núcleos; Windows: média de 1 min acima de 90% ou fila acima de 2× os núcleos). Vale a mediana das três últimas leituras, e a máquina só volta a receber agentes com folga (4 GB, 15 GB de disco, 1,5×). O teto de D43 continua por cima.
- **Hoje a regra fecha as duas máquinas.** O PC estava com 2,4 a 3,0 GB livres, 4,7 GB no C: e fila de processador de 15 a 37 em 16 núcleos. A VPS estava com carga de 19,8 a 32,7 em 4 núcleos, o processador esperando 91% do tempo e a troca cheia. O que fazer quando nenhuma máquina tem folga é decisão do dono (ticket novo abaixo).

## 1. O que já existe

| Ferramenta | O que dá | Serve aqui? |
| --- | --- | --- |
| `quota-axi` 0.1.60 (VPS) | Janelas de cota de provedores, em TOON ou `--json` (`quota-axi --help`) | Não lê a máquina. É o modelo de como ler: uma leitura que vira um arquivo (pesquisa [cota-claude.md](cota-claude.md)). |
| `lslocks --json` (util-linux, VPS) | Cada trava com `command`, `pid`, `mode` e `blocker` ([lslocks(8)](https://man7.org/linux/man-pages/man8/lslocks.8.html)) | Sim, para a fila do `e2e.lock`. |
| `Get-CimInstance … \| ConvertTo-Json` (PC) | Qualquer classe WMI em JSON | Sim, para tudo no Windows. |
| `/proc/meminfo`, `/proc/loadavg`, `/proc/pressure/*` (VPS) | Texto com números, de leitura instantânea | Sim. |
| `sysctl`, `memory_pressure`, `df`, `lsof` (Mac) | Texto com números | Sim. |
| `psutil`, `glances`, `btm` | Ausentes nas máquinas | Não: instalar dependência para o que três leituras já fazem não compensa. |
| npm: `recurso-axi`, `resource-axi`, `system-axi`, `machine-axi`, `host-axi` | 404 em todos; os pacotes de kunchenguid são quota-axi, lavish-axi, gh-axi, tasks-axi e chrome-devtools-axi | Não existe. |

## 2. Como ler cada recurso

### Linux (VPS)

- **Memória livre:** `MemAvailable` em `/proc/meminfo`, a estimativa do kernel da memória que um programa novo consegue sem troca ([proc_meminfo(5)](https://man7.org/linux/man-pages/man5/proc_meminfo.5.html)). O campo `free` de `free` é baixo demais (377 MB hoje, contra 4,3 GB de `MemAvailable`). Ver também `SwapFree`, que estava em 4 kB de 2 GB.
- **Processador:** `/proc/loadavg` dá a carga de 1, 5 e 15 min ([proc_loadavg(5)](https://man7.org/linux/man-pages/man5/proc_loadavg.5.html)); dividir por `nproc`. `/proc/pressure/cpu` dá a fração do tempo com alguma tarefa esperando processador, `some avg10/avg60/avg300` ([PSI, docs do kernel](https://docs.kernel.org/accounting/psi.html)). Mede o aperto melhor do que a carga, que no Linux também conta quem espera disco.
- **Disco:** `df -B1 --output=avail,size /`.
- Custo: as quatro leituras juntas, com `lslocks`, levaram 0,10 s.

### Windows (PC)

- **Memória livre:** `Win32_OperatingSystem.FreePhysicalMemory`, em KB ([Win32_OperatingSystem](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-operatingsystem)). No PC, ele andou junto com o contador de memória disponível (`Win32_PerfFormattedData_PerfOS_Memory.AvailableBytes`: 2,75 GB contra 2,72 GB na mesma leitura), então serve como "disponível". **Oscila muito:** 1,19 GB, 0,26 GB, 2,75 GB, 2,99 GB, 2,47 GB e 2,39 GB em 20 minutos. Por isso a regra usa a mediana.
- **Processador:** o Windows não tem carga média. `Win32_PerfFormattedData_PerfOS_Processor` com `Name='_Total'` dá `PercentProcessorTime`, e `Win32_PerfFormattedData_PerfOS_System` dá `ProcessorQueueLength`, as threads prontas esperando ([PerfOS_System](https://learn.microsoft.com/en-us/previous-versions/aa394272(v=vs.85)); [WMI Tasks: Performance Monitoring](https://learn.microsoft.com/en-us/windows/win32/wmisdk/wmi-tasks--performance-monitoring)). Núcleos: `[Environment]::ProcessorCount` (16).
- **Não use `Get-Counter`:** os nomes dos contadores são traduzidos. `Get-Counter '\Processor(_Total)\% Processor Time'` falhou no PC com "O objeto especificado não foi encontrado no computador", porque o Windows está em português. As classes `Win32_PerfFormattedData_*` não dependem do idioma.
- **Disco:** `Win32_LogicalDisk` com `DeviceID='C:'`, `FreeSpace` e `Size` ([Win32_LogicalDisk](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-logicaldisk)).
- **Custo:** a leitura inteira levou de 4,1 a 7,7 s dentro do PowerShell, e de 6 a 15 s com o ssh. Não cabe na volta de 20 s do Vigia; tem que rodar à parte, a cada minuto. O PowerShell imprime progresso em CLIXML no stderr; `$ProgressPreference='SilentlyContinue'` evita isso.

```powershell
$ProgressPreference='SilentlyContinue'
$os=Get-CimInstance Win32_OperatingSystem -Property FreePhysicalMemory,TotalVisibleMemorySize
$p=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'" -Property PercentProcessorTime
$s=Get-CimInstance Win32_PerfFormattedData_PerfOS_System -Property ProcessorQueueLength
$d=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" -Property FreeSpace,Size
$a=@(Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue).Count
[pscustomobject]@{livre_mb=[int]($os.FreePhysicalMemory/1KB); cpu_pct=$p.PercentProcessorTime; fila=$s.ProcessorQueueLength;
  nucleos=[Environment]::ProcessorCount; disco_livre_gb=[math]::Round($d.FreeSpace/1GB,1); anki_8766=($a -gt 0)} | ConvertTo-Json -Compress
```

Saída real: `{"livre_mb":2473,"cpu_pct":65,"fila":37,"nucleos":16,"disco_livre_gb":4.7,"anki_8766":false}`.

### macOS (Mac)

`sysctl -n hw.ncpu vm.loadavg` dá núcleos e carga (8; `{ 1.35 2.09 1.88 }`). `memory_pressure -Q` dá a memória livre em porcentagem (41%). `df -k /` dá o disco (20 GB livres de 228 GB). `lsof -nP -iTCP:8766 -sTCP:LISTEN` mostra quem escuta na porta do Anki. Pelo ssh, levou 1,7 s.

## 3. A fila do e2e, a vez do Anki e o Mac

**`e2e.lock` (VPS).** Os briefs do PerpetualMiner mandam rodar todo e2e na VPS com `flock ~/crew-state/e2e.lock npx playwright test …`. O `flock(1)` deixa o segundo processo esperando enquanto o primeiro tem a trava ([flock(1)](https://man7.org/linux/man-pages/man1/flock.1.html)). Quem tem a trava e quem espera aparecem no `lslocks`: quem espera vem com `WRITE*` e o pid de quem bloqueia em `BLOCKER`. Testado com uma trava descartável (dois `flock` no mesmo arquivo): o segundo apareceu com `MODE WRITE*` e `BLOCKER` igual ao pid do primeiro. O `/proc/locks` mostra o mesmo com `->`. Para saber de qual Worker é cada processo, basta o `cwd` (`readlink /proc/<pid>/cwd`) e o tempo (`ps -o etimes=`). Leitura real às 07:40 UTC:

```
lslocks --json -o COMMAND,PID,MODE,BLOCKER,PATH  →  [{"command":"flock","pid":2288803,"mode":"WRITE","blocker":null,"path":"/home/factory/crew-state/e2e.lock"}]
readlink /proc/2288803/cwd  →  /home/factory/worktrees/PerpetualMiner-rev-t3/e2e   (havia 57 s; ninguém esperando)
```

**A vez do Anki (porta 8766).** A Conexão com o Anki escuta em `127.0.0.1:8766` ([README do PerpetualMiner](https://github.com/vinicius928e8r84/PerpetualMiner/blob/main/README.md)), e só um processo por máquina escuta nessa porta. Os testes e2e não usam a porta, porque o Chromium de teste a desvia para a Conexão de mentira (`verify-perpetualminer/SKILL.md` do PerpetualMiner). Só a prova real com o Anki de verdade, no Windows e no Mac, disputa a porta com o Anki do dono. Hoje não existe fila para isso. O que dá para saber é se a porta está ocupada e por quem: `Get-NetTCPConnection -LocalPort 8766 -State Listen` e o `OwningProcess` no PC ([Get-NetTCPConnection](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection)), e o `lsof` acima no Mac. Às 07:50 UTC, ninguém escutava na 8766, nem no PC nem no Mac.

**O Mac livre.** Também não há trava nem fila. Pelo ssh dá para ler a carga, a memória e os processos de teste. O Mac não tem `flock`, mas tem `lockf(1)` e `shlock` ([lockf(1)](https://man.freebsd.org/cgi/man.cgi?query=lockf&sektion=1)), que fazem a mesma fila. Achado: o Mac tem um Chrome for Testing sem cabeça (`/tmp/nova-p16-mPtU`) rodando há 4 dias, provavelmente sobra de uma prova do Nova-AI. Pelos processos, o Mac parece ocupado sem estar.

## 4. Formato proposto

`crew.py recursos` lê a máquina local (Linux por `/proc`, Windows pelo PowerShell acima, macOS por `sysctl`) e grava `state/crew/_recursos.json`. O Vigia de cada máquina o roda a cada minuto, fora da volta de 20 s. O da VPS também lê o Mac (o `fm-mac` está no ssh da VPS). O chief lê o arquivo local e, no `sync_remote`, traz o da VPS. Cada arquivo tem um só escritor, a própria máquina; a cota, que é da conta, continua num arquivo só.

```json
{
  "at": "2026-11-25T07:50:00Z",
  "host": "pc",
  "sistema": "windows",
  "nucleos": 16,
  "memoria": {"livre_mb": 2473, "total_mb": 16103, "mediana_mb": 2473},
  "cpu": {"uso_pct": 65, "fila": 37, "carga_5m": null, "pressao_60s": null},
  "disco": {"livre_gb": 4.7, "total_gb": 455},
  "anki_8766": {"ocupada": false, "processo": null},
  "e2e": null,
  "workers": 3,
  "folga": false,
  "motivo": "disco: 4,7 GB livres (mínimo 10)"
}
```

Na VPS, `cpu` traz `carga_5m` e `pressao_60s`, e `e2e` vem como `{"com": {"pid": 2288803, "worktree": "PerpetualMiner-rev-t3", "ha_s": 57}, "esperando": []}`. O Mac vem dentro do arquivo da VPS, em `"mac": {"alcancavel": true, "memoria_livre_pct": 41, "carga_1m": 1.35, "nucleos": 8, "disco_livre_gb": 20, "anki_8766": {"ocupada": false}, "testes": ["chrome-for-testing nova-p16 há 4 dias"]}`. `folga` e `motivo` são a regra já aplicada, para o `crew.py spawn` e a Mesa só lerem.

## 5. Regra de decisão para abrir agentes

Aplicada no `crew.py spawn`, antes de abrir o painel, sobre a mediana das três últimas leituras da máquina:

1. **Sem folga** se houver uma destas: memória livre abaixo de 3 GB; disco livre abaixo de 10 GB (disco cheio é uma das causas de parada de D41; ver [sinais-de-parada.md](sinais-de-parada.md)); processador saturado. No Linux, saturado é carga de 5 min acima de 2× os núcleos, ou pressão de processador `some avg60` acima de 80%. No Windows, é `PercentProcessorTime` médio acima de 90% ou fila acima de 2× os núcleos.
2. **Histerese:** a máquina que perdeu a folga só a recupera com 4 GB livres, 15 GB de disco e carga abaixo de 1,5× os núcleos. Sem isso, a máquina entra e sai a cada leitura.
3. **Onde abrir:** a VPS por padrão (D44). Se a VPS não tem folga e o PC tem, abrir no PC. Se nenhuma tem, o Worker vai para a fila de D43, e a Mesa o mostra como "esperando folga". O teto de 10 no PC e 6 na VPS vale por cima de tudo.
4. **Leitura velha** (mais de 5 min) conta como sem folga para a máquina remota, e o Vigia avisa. Na local, o `spawn` lê na hora.
5. **O e2e não trava o `spawn`**, porque a trava já é a fila. Um Worker de revisão ou de prova que vai rodar e2e só deve ser aberto quando a fila tem no máximo uma pessoa esperando.
6. **Anki e Mac não decidem o `spawn`.** Decidem a prova real: não rodar prova com Anki de verdade numa máquina com a 8766 ocupada (é o Anki do dono), nem no Mac com outra prova rodando.

**Aplicada às leituras de hoje:**

| Máquina | Memória livre | Disco livre | Processador | Folga? |
| --- | --- | --- | --- | --- |
| PC | 2,4 a 3,0 GB (mediana 2,5) | 4,7 GB | 53 a 97%, fila 15 a 37 em 16 | não (memória, disco e fila) |
| VPS | 4,3 GB, troca cheia | 56 GB | carga 19,8/15,9 e 32,7/22,9 em 4; pressão 91% | não (processador) |
| Mac | 41% de 8 GB | 20 GB | carga 1,35 em 8 | sim (não abre Workers; é para provas) |

O exemplo do ticket (3 GB, 2× os núcleos) fica como está; só se somam o disco e a histerese. Com esses números, hoje não se abre nenhum agente em lugar nenhum.

## Tickets que esta pesquisa abre

- **O que o chief faz quando nenhuma máquina tem folga** (grilling, dono): os limites estão certos? Enfileira tudo, abre mesmo assim os de revisão, ou fecha os ociosos primeiro? Bloqueia "A fila de PRs até o destino".
- **Como a frota reserva o Anki real e o Mac** (grilling, dono): hoje não há fila para a porta 8766 nem para o Mac. Uma trava como o `e2e.lock` (`lockf` no Mac), ou basta ver a porta e os processos? Bloqueia "A fila de PRs até o destino".
