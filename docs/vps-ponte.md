# Máquina "VPS crew" do Herdr do PC: só se liga ao servidor da unidade

Issue #23. Quem sobe um servidor Herdr na VPS quando o PC abre a máquina é o `remote-client-bridge`, rodado pelo binário que o cliente achou na VPS com `command -v herdr`: `~/.local/bin/herdr`, que é a 0.9.1. Se nenhum servidor responde, esse binário sobe o próprio, e o servidor vira filho da conexão do PC (some quando ela cai, leva os panes junto e deixa a `crew-herdr.service` perdendo a corrida).

## O que muda

`scripts/vps-ponte.sh` instala `~/.local/share/crew/ponte/herdr` na VPS. A ponte só difere do binário do crew nos comandos `remote-client-bridge` e `remote-api-bridge`:

- se há servidor respondendo na sessão, segue para o binário do crew (0.9.5) e a conexão se liga a ele;
- se não há, pede `systemctl --user start crew-herdr.service` (`crew-herdr-<sessão>.service` nas outras sessões) e espera até 30 s;
- se ainda não há, sai com erro e não sobe servidor nenhum.

Os demais comandos vão direto ao binário do crew. O script também põe uma linha no `~/.bashrc` da VPS, antes do `case $- in`, que só põe a ponte no `PATH` quando o ssh traz `LC_CREW_PONTE`. Assim `ssh vps` e as outras máquinas ficam como estavam.

## Instalar

Na VPS: `ssh vps bash -s < scripts/vps-ponte.sh` (idempotente). O `scripts/vps-setup.sh` também roda, depois de buscar os repos, o `vps-ponte.sh` da `origin/main` do clone `~/home-repo`.

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

O spawn abre o Worker com `pi --session-id <nome do Worker>`, então a Retomada acha a mesma conversa pelo nome. O `crew-state.ts` não registra mais no Herdr o comando que reabre o pane: o caminho para reabrir é um só, o comando do spawn.

Para o Herdr não reabrir os panes por conta própria (e perder o contexto, como em 23/11), o Herdr do PC fica com o restore de agentes desligado, no `config.toml` dele:

```toml
[session]
resume_agents_on_restore = false
```

Para conferir: `herdr config check` deve responder `config: ok` (uma chave errada aparece como `unknown config key`), e a linha acima tem de estar no arquivo. Um Herdr já aberto só lê a mudança depois de `herdr server reload-config` ou de reiniciar.

Workers abertos antes desta mudança carregaram a extensão antiga e ainda registram o comando de retomada no Herdr, e a conversa deles tem outro nome (o id é um UUID): só os abertos depois dela têm a conversa de nome fixo.
