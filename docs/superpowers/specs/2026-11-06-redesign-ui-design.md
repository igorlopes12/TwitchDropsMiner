# Redesign da interface — design

Data: 2026-11-06 · Branch: `redesign-ui` · Fork: `igorlopes12/TwitchDropsMiner`

## Intenção e porquê

A interface atual (Tkinter puro, `gui.py`) parece um programa antigo, não é bonita e não é intuitiva: tudo fica empilhado na mesma tela (status, 8 websockets, login, progresso, canais, log) e nada indica o que importa agora. O fork é distribuído para **outras pessoas no Windows, Linux e macOS** através da release automática do CI, então o redesign é para quem baixa o app, não só para o autor.

O que o usuário quer saber ao abrir o app: **o progresso do drop atual e quanto falta**. E quer um visual moderno e caprichado.

Também há um problema real de primeiro uso: o padrão atual é `priority_mode = PRIORITY_ONLY` com a lista `priority` vazia, então um usuário novo faz login, as campanhas carregam e o app não minera nada, sem explicar por quê.

## Objetivos

- Tela principal centrada no drop atual: tempo restante em destaque, porcentagem e barra.
- Visual minimalista (direção "C"), com tema claro e escuro.
- Passo a passo na primeira abertura que termina com jogos escolhidos (fim da lista de prioridade vazia).
- Funcionar e ser empacotado nas três plataformas que o CI já gera: Windows (.exe), macOS (.app zip), Linux (PyInstaller x86_64/aarch64 e AppImage x86_64/aarch64).

## Não-objetivos

- Não mudar a lógica de mineração, a seleção de canais, o websocket, o GQL ou o login pelo navegador (zendriver). O redesign troca só a camada de interface.
- Não adicionar funcionalidades novas além do passo a passo e do tema que segue o sistema.

## Anti-objetivos (seria fracasso mesmo funcionando)

- Quebrar o build de qualquer plataforma ou deixar a release com uma plataforma sem app utilizável.
- Perder opções que existem hoje (proxy, qualidade de conexão, badges/emotes, checagem de drops disponíveis, iniciar na bandeja, notificações, idioma, exclusões, modos de prioridade).
- Perder as traduções: o app tem 21 idiomas em `lang/*.json`.
- Um usuário novo terminar o primeiro uso sem minerar nada.

## Decisões tomadas

### Tecnologia (decisão do Claude, aceita pelo usuário: "escolhe você, quero o visual mais bonito")
- Interface em **HTML/CSS/JS** dentro de uma janela nativa com **`pywebview`** (Windows: Edge WebView2; macOS: WKWebView; Linux: WebKitGTK).
- O núcleo continua em Python/asyncio. Hoje o núcleo fala com a interface por cerca de 30 pontos (`gui.status.update`, `gui.display_drop`, `gui.clear_drop`, `gui.inv.add_campaign`, `gui.inv.update_drop`, `gui.inv.clear`, `gui.channels.*`, `gui.websockets.*`, `gui.login`, `gui.tray.*`, `gui.print`, `gui.progress.*`, `gui.set_games`, `gui.save`, `gui.start/stop/close*`, `gui.prevent_close`, `gui.grab_attention`, `gui.coro_unless_closed`, `gui.wait_until_closed`, `gui.help._invalidate_button`). A nova interface implementa essa mesma superfície; `twitch.py` e os demais módulos não devem precisar de mudanças além do mínimo.
- Ícone na bandeja continua com `pystray`.
- **Linux é testado primeiro**, antes de construir as telas: janela pywebview abrindo a partir do binário PyInstaller e do AppImage, em x86_64 e aarch64, no CI.

### Visual
- Direção **C · limpo e minimalista**: fundo claro `#f6f6f8`, painéis brancos com borda fina, números grandes de peso leve, barras finas, roxo da Twitch só como cor de destaque. Referências: `2026-11-06-redesign-ui-mockups/c-light-dark.html`.
- **Tema**: segue o sistema por padrão; nas Configurações, escolha entre Sistema / Claro / Escuro. Substitui a configuração atual `dark_mode: bool` (migrar: `true` → Escuro, `false` → Sistema).

### Telas
Navegação por barra lateral de ícones: Mineração, Inventário, Canais, Configurações; no rodapé da barra, um ícone discreto para Log e Ajuda.

1. **Mineração (principal)** — indicador de status no topo (ativo / ocioso / erro com texto curto); painel do drop atual com jogo, nome do drop, **tempo restante grande**, porcentagem e barra; painel da campanha ("0 de 5 drops · 3h35") com barra; linha do canal assistido com espectadores. Quando não há nada para minerar, a tela explica o motivo e oferece o caminho para resolver (por exemplo, "Nenhum jogo escolhido → Escolher jogos").
2. **Inventário** — uma linha por campanha; drops como quadradinhos (preenchido = ganho, anel = em progresso, vazio = pendente); filtros Ativas / Em breve / Concluídas; campanhas de jogos não escolhidos aparecem esmaecidas. Mockup: `other-screens.html`.
3. **Canais** — lista de canais ao vivo com drops (ponto verde/cinza, nome, espectadores); o assistido fica destacado; clicar num canal troca para ele (substitui o botão "Switch").
4. **Configurações** — lista de jogos reordenável arrastando, com "Só os escolhidos" / "Todos"; tema; iniciar com o sistema; avisos de drop; idioma; conta (nome + sair). As opções restantes de hoje ficam numa seção **"Avançado"** recolhida.
5. **Log e Ajuda** — o log de texto que hoje ocupa a tela principal; o status dos websockets também vai para cá. A Ajuda mantém o conteúdo e os botões da aba atual.

### Primeira abertura (passo a passo)
Mockup: `onboarding.html`. Aparece quando não há login salvo ou a lista de jogos está vazia.
1. **Entrar** — explica em uma frase o que o app faz; botão abre o login da Twitch no navegador (fluxo zendriver atual).
2. **Escolher jogos** — grade com as capas (`boxArtURL`) dos jogos que têm campanhas ativas, com número de drops e tempo restante; a ordem dos cliques vira a prioridade; "Minerar todos" pula a escolha.
3. **Pronto** — confirma os jogos e avisa que o app continua na bandeja.

O passo 2 grava na mesma lista `priority` / `priority_mode` que existe hoje.

### Padrões adotados pelo Claude (o usuário delegou: "ok, me avisa quando terminar")
- **Compatibilidade com o upstream (DevilXD)**: o fork continua puxando atualizações do upstream. A interface nova vive num pacote novo (`webgui/`) com um `GUIManager` que expõe a mesma superfície de chamadas usada pelo núcleo; o `gui.py` antigo fica intocado (merges do upstream nele não conflitam) e o núcleo só troca a linha de import. Isso preserva a intenção "poucos conflitos" melhor do que reescrever o `gui.py`. Mudanças fora da interface (`twitch.py`, `main.py`, `utils.py`) ficam no mínimo indispensável.
- **Portão do Linux**: se a janela pywebview não funcionar nos builds de Linux (PyInstaller e AppImage, x86_64 e aarch64), o trabalho **para** e volta ao usuário antes de construir as telas. Nenhuma alternativa (Tk só no Linux, ou Tk modernizado em tudo) é escolhida sem ele.

### Decisões do Claude após a revisão (o usuário pode contestar)
- **Mapeamento dos modos de jogo**: "Só os escolhidos" = `PRIORITY_ONLY`; "Todos" = `ENDING_SOONEST`; `LOW_AVBL_FIRST` vai para "Avançado". "Minerar todos" no passo a passo grava `ENDING_SOONEST`.
- **Quando mostrar o passo a passo**: nova configuração `onboarding_done: bool` (padrão `false`; usuários que já têm `settings.json` com `priority` não vazia ou modo diferente de `PRIORITY_ONLY` migram como `true`). Não depende da lista estar vazia, para quem escolhe "Minerar todos" não ver o passo a passo de novo.
- **Passo a passo × núcleo**: o núcleo não espera; segue o fluxo atual (com a lista vazia não minera nada). Ao concluir o passo 2, a interface grava as configurações e dispara a mesma recarga que a mudança de prioridade já dispara hoje (estado `GAMES_UPDATE`). Sem mudança de fluxo no `twitch.py`.
- **WebKitGTK no Linux**: o AppImage leva o WebKitGTK embutido (é a opção "funciona em qualquer distro"); o build PyInstaller do Linux exige WebKitGTK instalado no sistema, documentado em `manual.txt`, e mostra uma mensagem clara se faltar — no mesmo espírito do commit atual "mensagem amigável se nenhum navegador for encontrado".

## Restrições

- Python do CI: 3.10 (`PYTHON_VERSION` em `.github/workflows/ci.yml`); o código precisa rodar nele.
- Sem servidor HTTP exposto: a página é carregada localmente pelo pywebview, e a comunicação passa pela ponte JS↔Python do pywebview.
- Assets do front-end (HTML/CSS/JS, fontes) vão dentro do pacote; nada carregado de CDN em tempo de execução. Capas e imagens de drops vêm das URLs da Twitch.
- Todo texto visível usa as traduções de `lang/`; textos novos entram em `English.json` (os outros idiomas caem no inglês até serem traduzidos).
- O workflow de release só roda no `master`; a branch `redesign-ui` não publica release.

## Deixado para quem for construir

- Como rodar o loop do pywebview junto com o loop asyncio (no macOS o pywebview exige a thread principal; hoje o Tk é "bombeado" de dentro do asyncio em `GUIManager._poll`) e como o `pystray` convive com isso em cada plataforma.
- Se a interface usa JS puro ou uma biblioteca leve, e como empacotá-la.
- Detecção do tema do sistema no Linux, se o `prefers-color-scheme` do WebKitGTK não refletir o tema do GTK.
- O que fazer se o WebView2 não estiver instalado no Windows (raro no 10/11).
- Detalhes visuais finos, ícones e animações, dentro da direção C.
- Se o `gui.py` antigo é removido ou mantido temporariamente como alternativa.
