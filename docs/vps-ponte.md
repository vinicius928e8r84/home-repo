# Máquina "VPS crew" do Herdr do PC: só se liga ao servidor da unidade

Issue #23. Quem sobe um servidor Herdr na VPS quando o PC abre a máquina é o `remote-client-bridge`, rodado pelo binário que o cliente achou na VPS com `command -v herdr`: `~/.local/bin/herdr`, que é a 0.9.1. Se nenhum servidor responde, esse binário sobe o próprio, e o servidor vira filho da conexão do PC (some quando ela cai, leva os panes junto e deixa a `crew-herdr.service` perdendo a corrida).

## O que muda

`scripts/vps-ponte.sh` instala `~/.local/share/crew/ponte/herdr` na VPS. A ponte só difere do binário do crew nos comandos `remote-client-bridge` e `remote-api-bridge`:

- se há servidor respondendo na sessão, segue para o binário do crew (0.9.5) e a conexão se liga a ele;
- se não há, pede `systemctl --user start crew-herdr.service` (`crew-herdr-<sessão>.service` nas outras sessões) e espera até 30 s;
- se ainda não há, sai com erro e não sobe servidor nenhum.

Os demais comandos vão direto ao binário do crew. O script também põe uma linha no `~/.bashrc` da VPS, antes do `case $- in`, que só põe a ponte no `PATH` quando o ssh traz `LC_CREW_PONTE`. Assim `ssh vps` e as outras máquinas ficam como estavam.

## Instalar

Na VPS: `ssh vps bash -s < scripts/vps-ponte.sh` (idempotente).

No PC, em `~/.ssh/config`:

```
Host vps-crew
  HostName <o mesmo de vps>
  User factory
  IdentityFile ~/.ssh/id_ed25519_vps
  IdentitiesOnly yes
  SetEnv LC_CREW_PONTE=1
```

O `sshd` da VPS já aceita `LC_*` (`AcceptEnv LANG LC_*`).

## Trocar a máquina (hoje a "VPS crew" ainda aponta para `vps`)

Trocar derruba a conexão antiga. Faça quando nenhum worker estiver rodando, ou depois de a `crew-herdr.service` ter assumido a sessão `crew`:

```
herdr machine remove 15ae9b0a91b27ad78c350d3b8d025c34
herdr machine add vps-crew --label "VPS crew" --remote-session crew
```

Conferência, na VPS: `ps -eo pid,ppid,args | grep 'herdr.*server'` deve mostrar um só servidor `crew`, filho do `systemd --user`, em `~/.local/share/crew/bin/herdr`.

## Retomada dos panes

O `crew-state.ts` registra no Herdr, a cada mudança de estado, o comando que reabre o pane: `env` com `CREW_*`, `PI_CODING_AGENT_DIR`, `PI_CODING_AGENT_SESSION_DIR` e `PATH` do pane, seguido de `pi` com os mesmos argumentos (`-e`, `--model`) e `--session <arquivo da sessão>`. Sem isso o Herdr reabre com `pi --session <arquivo>` pelo `PATH` de login, sem a extensão, sem o modelo e sem o `CREW_STATE_FILE`. O registro usa `--seq` maior que o da integração `herdr:pi`; sem ele o Herdr ignora o comando e ainda responde sucesso.

Workers que já rodam carregaram a extensão antiga e não registram o comando: só os abertos depois desta mudança voltam completos.
