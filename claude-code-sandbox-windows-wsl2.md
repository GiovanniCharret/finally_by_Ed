# Claude Code com `/sandbox` no Windows via WSL2

Guia prático para habilitar o **YOLO mode controlado** (`/sandbox` em Auto-allow) do Claude Code rodando no Windows, com VS Code conectado ao WSL2 e projetos no filesystem do Linux.

---

## Contexto e motivação

O comando `/sandbox` do Claude Code depende de primitivas de kernel que o Windows não possui — ele usa `bubblewrap` no Linux e `Seatbelt` no macOS. Por isso, ao executar `/sandbox` no Claude Code instalado nativamente no Windows (via PowerShell), aparece a mensagem:

> Sandboxing is currently only supported on macOS, Linux, and WSL2.

A solução é rodar o Claude Code **de dentro do WSL2**, e usar o VS Code do Windows como interface gráfica conectada remotamente ao Ubuntu via extensão WSL.

### Por que usar `/sandbox` em vez de `--dangerously-skip-permissions`

| | `--dangerously-skip-permissions` | `/sandbox` Auto-allow |
|---|---|---|
| Velocidade / UX | Roda sem pedir aprovação | Roda sem pedir aprovação |
| Acesso a filesystem | Total (mesmo do usuário) | Restrito ao CWD via kernel |
| Acesso a rede | Total | Allowlist via proxy local |
| Proteção contra prompt injection | Nenhuma | Bloqueio em nível de syscall |
| Proteção contra postinstall malicioso | Nenhuma | Subprocessos herdam restrições |

Os dois oferecem a mesma autonomia ao agente, mas o `/sandbox` adiciona uma camada de isolamento real do kernel. Se algo der errado (bug do modelo, prompt injection, dependência maliciosa), o sistema bloqueia automaticamente. **Hoje, com `/sandbox` disponível, ele é estritamente superior ao modo `--dangerously-skip-permissions`** para uso em máquina pessoal/de trabalho.

---

## Arquitetura final

```
┌──────────────────── Windows ────────────────────┐
│                                                  │
│   VS Code (interface gráfica)                    │
│        │                                         │
│        │ extensão WSL (conexão remota)           │
│        ▼                                         │
│   ┌──────────────── Ubuntu (WSL2) ───────────┐  │
│   │                                            │  │
│   │   ~/projetos/meu-app/  ← código aqui      │  │
│   │                                            │  │
│   │   Terminal integrado:                     │  │
│   │   $ claude → /sandbox (yolo mode)         │  │
│   │                                            │  │
│   └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## Passo a passo

### 1. Habilitar e atualizar o WSL2

Abra o **PowerShell como Administrador**:

```powershell
wsl --install
wsl --update
wsl --set-default-version 2
```

Reinicie o PC se for instalação nova.

Confira as distros instaladas:

```powershell
wsl -l -v
```

A coluna `VERSION` deve mostrar `2`.

### 2. Garantir que o Ubuntu é a distro padrão

Se você tem Docker Desktop instalado, é comum aparecer `docker-desktop` como padrão. Essa distro é minimalista (sem `sudo`, sem `apt` funcional) e não serve para nosso uso.

```powershell
wsl --set-default Ubuntu
```

> **Isso não quebra o Docker.** O Docker Desktop usa internamente as próprias distros (`docker-desktop`, `docker-desktop-data`) que ele gerencia sozinho. A "distro padrão" do WSL só afeta qual abre quando você digita `wsl` sem argumentos.

Se você ainda não tem Ubuntu instalado:

```powershell
wsl --install -d Ubuntu
```

Na primeira execução, ele pedirá um nome de usuário e senha do Linux (essa senha é a que o `sudo` vai pedir).

### 3. Entrar no Ubuntu e ir para a home

```powershell
wsl
```

> **Atenção ao prompt.** Se aparecer algo como `gioch@DESKTOP:/mnt/c/Users/gioch$`, você está no filesystem do Windows montado dentro do Linux — é lento (protocolo 9P, ~9x mais lento). Para ir à home do Linux:
>
> ```bash
> cd ~
> ```
>
> O prompt deve passar para `gioch@DESKTOP:~$` (com `~`).

Confirme:

```bash
whoami
pwd
sudo -v
```

Saídas esperadas: seu usuário Linux, `/home/seuusuario`, e a senha sendo aceita pelo `sudo`.

### 4. Atualizar o Ubuntu

```bash
sudo apt update && sudo apt upgrade -y
```

### 5. Instalar as dependências do `/sandbox`

```bash
sudo apt install -y bubblewrap socat ripgrep
```

Verifique a instalação:

```bash
which bwrap && which socat && which rg
```

Os três devem retornar caminhos (ex: `/usr/bin/socat`).

> **Cuidado com a flag de versão do socat.** O comando correto é `socat -V` (maiúsculo). Se você usar `socat -v` (minúsculo), ele retorna:
>
> ```
> socat[xxxx] E exactly 2 addresses required (there are 0)
> ```
>
> Isso **não é erro de instalação** — é só a flag errada (minúsculo é modo verbose, que espera dois endereços). O socat está instalado e funcional.

### 6. Instalar Node.js e Claude Code

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v && npm -v
```

Configure um diretório global para o npm (evita precisar de `sudo` em instalações globais):

```bash
mkdir -p ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

Instale o Claude Code:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

> O `/sandbox` requer Claude Code **v2.1.0 ou superior**.

### 7. Instalar a extensão WSL no VS Code

No **VS Code do Windows** (não instale outra cópia no Linux), vá em **Extensions** (`Ctrl+Shift+X`) e instale:

- **WSL** (publisher: Microsoft)

### 8. Habilitar o comando `code` dentro do WSL

Se ao rodar `code .` no Ubuntu aparecer:

```
Command 'code' not found, but can be installed with:
sudo snap install code
```

> **NÃO instale via snap.** Isso instalaria um VS Code separado dentro do Linux, sem integração com o do Windows.

A solução correta é fazer o VS Code do Windows plantar o comando `code` no PATH do Ubuntu. Para isso:

1. Abra o VS Code no Windows
2. `Ctrl+Shift+P` → digite `WSL: Connect to WSL` → Enter
3. Aguarde 10-30s — uma nova janela abre com o indicador azul **WSL: Ubuntu** no canto inferior esquerdo. Nesse momento, o "VS Code Server" é instalado no Ubuntu e o comando `code` é registrado no PATH.

Volte ao terminal Ubuntu e teste:

```bash
which code
code .
```

Se o `which code` retornar vazio, recarregue o shell:

```bash
exec bash
```

Ou reinicie o WSL (no PowerShell):

```powershell
wsl --shutdown
wsl
```

### 9. Mover projetos para o filesystem do Linux

**Por que mover.** O Linux **enxerga** seus projetos em `/mnt/c/...`, mas cada operação de arquivo passa pelo protocolo 9P e fica ~9x mais lenta. Para projetos com builds, testes, `npm install`, ou uso intensivo do Claude Code, isso vira gargalo sério.

| Operação | `~/projeto/` | `/mnt/c/projeto/` |
|----------|-------------|-------------------|
| `npm install` | 30s | 4-5 min |
| `git status` em repo grande | instantâneo | 5-10s |
| Build / `ripgrep` / lint | rápido | engasga |

**Como mover.** Crie a pasta de projetos:

```bash
mkdir -p ~/projetos
cd ~/projetos
```

Se o projeto está num repositório Git (ideal):

```bash
git clone https://github.com/seuuser/seurepo.git
cd seurepo
```

Se está em uma pasta do Windows, copie:

```bash
cp -r /mnt/c/Users/seuuser/caminho/do/projeto ~/projetos/
```

**Acesso pelo Windows Explorer.** Os arquivos do Linux ficam acessíveis pelo Windows via:

```
\\wsl$\Ubuntu\home\seuusuario\projetos
```

Útil para arrastar/copiar entre os dois mundos.

### 10. Abrir o projeto no VS Code conectado ao WSL

Dentro do Ubuntu, na pasta do projeto:

```bash
cd ~/projetos/seu-projeto
code .
```

Confirme o indicador azul **WSL: Ubuntu** no canto inferior esquerdo da janela. É esse selo que garante que o VS Code está editando arquivos do Linux com terminal e extensões rodando no WSL.

### 11. Iniciar o Claude Code e ativar o `/sandbox`

No terminal integrado do VS Code (`Ctrl+'`), que já abre no bash do Ubuntu:

```bash
claude
```

Na primeira vez, autentique-se com sua conta Anthropic via URL.

Quando ele perguntar "Do you trust the files in this folder?", responda **Yes**.

Dentro do Claude Code:

```
/sandbox
```

Escolha **Auto-allow mode** — comandos rodam sem pedir aprovação, mas dentro do isolamento do kernel.

Confirme com:

```
/status
```

---

## Fluxo de trabalho diário

A partir daqui, seu fluxo é:

1. Abrir o **VS Code no Windows**
2. `Ctrl+Shift+P` → `WSL: Open Recent` → escolher o projeto
3. Terminal integrado já está no Ubuntu, na pasta certa
4. `claude` → `/sandbox` → Auto-allow
5. Trabalhar

Não precisa mais abrir PowerShell separado, nem digitar `wsl`, nem se preocupar com onde os arquivos estão.

---

## Resumo dos problemas encontrados nesta jornada

| Problema | Causa | Solução |
|----------|-------|---------|
| `/sandbox` no PowerShell retorna "only supported on macOS, Linux, and WSL2" | Claude Code nativo do Windows não tem suporte a sandbox | Rodar Claude Code dentro do WSL2 |
| `sudo: not found` em `/mnt/host/c/Users/gioch#` | Estava na distro `docker-desktop`, não no Ubuntu | `wsl --set-default Ubuntu` e reentrar |
| Lista do WSL com Ubuntu como `Stopped` e docker-desktop como padrão | Docker Desktop adiciona suas próprias distros e pode virar padrão | `wsl --set-default Ubuntu` (não quebra o Docker) |
| `socat -v` retornou erro `exactly 2 addresses required` | Flag minúscula é modo verbose, não versão | Usar `socat -V` (maiúsculo) ou `which socat` |
| Prompt em `~/projetos/` mas o caminho real era `/mnt/c/...` | WSL respeita o CWD do PowerShell ao entrar | `cd ~` para ir à home do Linux |
| `code .` retornou "Command 'code' not found, but can be installed with: sudo snap install code" | Comando `code` não estava no PATH do Linux ainda | NÃO usar snap; abrir VS Code no Windows e rodar `WSL: Connect to WSL` para plantar o `code` automaticamente |

---

## Referências oficiais

- [Claude Code Sandboxing — docs oficial](https://code.claude.com/docs/en/sandboxing)
- [Claude Code Setup — docs oficial](https://code.claude.com/docs/en/setup)
- [WSL Microsoft Docs](https://learn.microsoft.com/en-us/windows/wsl/)
