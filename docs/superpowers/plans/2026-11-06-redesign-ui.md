# Redesign da interface (pywebview) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a interface Tkinter por uma interface HTML/CSS/JS em janela `pywebview`, no estilo minimalista "C" com tema claro/escuro, passo a passo de primeira abertura, e builds funcionando em Windows, macOS e Linux.

**Architecture:** Novo pacote `webgui/` com um `GUIManager` que implementa exatamente a superfície que o núcleo (`twitch.py`, `inventory.py`, `channel.py`, `websocket.py`, `main.py`, `cache.py`) já chama no `gui.GUIManager`. O núcleo asyncio roda numa thread de fundo iniciada por `webview.start(func)`; a thread principal pertence ao pywebview (exigência do macOS). Python → JS por eventos (`window.evaluate_js("tdm.on(evt, payload)")`); JS → Python por `js_api`, que repassa ao loop asyncio com `loop.call_soon_threadsafe`. O `gui.py` antigo fica intocado; o núcleo troca só a linha de import.

**Tech Stack:** Python 3.10+, asyncio, `pywebview` (WebView2 / WKWebView / WebKitGTK), `pystray` (bandeja, como hoje), HTML/CSS/JS puro sem build step, PyInstaller, appimage-builder, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-06-redesign-ui-design.md` (mockups em `docs/superpowers/specs/2026-11-06-redesign-ui-mockups/`)

## Global Constraints

- Código roda em Python 3.10 (`PYTHON_VERSION: "3.10"` no CI).
- Lógica de mineração, canais, websocket, GQL e login zendriver **não mudam**. Fora de `webgui/`, só são permitidas: troca de import `gui` → `webgui`, os pontos de `twitch.py` que tocam Tk diretamente (`gui.help._invalidate_button.config`) se o shim não bastar, `main.py` (threading de inicialização), `settings.py` e `translate.py` (chaves novas), `build.spec`, `appimage/AppImageBuilder.yml`, `.github/workflows/ci.yml`, `requirements.txt`, `manual.txt`.
- `gui.py` não é editado.
- Nenhum asset carregado de CDN em tempo de execução; HTML/CSS/JS/fontes vão no pacote. Imagens (capas `boxArtURL`, drops `imageAssetURL`) vêm das URLs da Twitch.
- Todo texto visível vem de `_()` (`translate.py`); textos novos ficam em `translation["gui"]["web"]` no dicionário padrão de `translate.py` e em `lang/English.json`.
- Visual direção C: claro `#f6f6f8` / painel `#fff` / borda `#e5e5ea` / texto `#18181b`; escuro `#0f0f12` / `#16161a` / `#26262c` / `#ededf0`; destaque roxo `#9147ff` (escuro `#a970ff`); número principal 40px peso 300; barras de 4px.
- Tema: `"system" | "light" | "dark"`, padrão `"system"`.
- O release só roda no `master`; esta branch (`redesign-ui`) publica nada.

## Review Focus

1. **Fechar a janela no meio de um login ou de uma requisição** — o app deve encerrar limpo (sem thread asyncio órfã travando o processo). Teste no Task 4 (`test_close_from_js_sets_close_requested`) e verificação manual no Task 5.
2. **Chamadas do núcleo antes da página carregar** (o núcleo começa a imprimir log e atualizar status antes do `loaded` do webview) — eventos devem ser enfileirados e entregues quando a página ficar pronta, não perdidos. Teste no Task 4 (`test_events_before_ready_are_flushed`).
3. **Texto vindo da Twitch com aspas, `</script>` ou emoji em nomes de jogo/canal/drop** — não pode quebrar o JS nem injetar HTML. Teste no Task 4 (`test_payload_is_json_escaped`) e regra no Task 6 (renderizar só com `textContent`).
4. **`settings.json` antigo** (com `dark_mode`, `priority` cheia, sem `onboarding_done`) — usuários atuais não podem ver o passo a passo de novo nem perder o tema. Testes no Task 2.
5. **Sistema sem WebView utilizável** (Linux sem WebKitGTK no build PyInstaller; Windows sem WebView2) — mensagem clara e saída com código ≠ 0, não crash mudo. Task 9.

---

### Task 1: Portão do Linux — pywebview abre nos builds de CI

**Este task é um portão. Se qualquer job de Linux falhar após tentativas razoáveis (deps, includes do AppImage), PARE, não siga para o Task 2, e reporte ao usuário com os logs.** (Spec: "Portão do Linux".)

**Files:**
- Modify: `requirements.txt` (adicionar `pywebview>=5.3`; no Linux `pywebview[gtk]` vem do PyGObject já listado)
- Create: `webgui/__init__.py` (vazio por enquanto)
- Create: `webgui/smoke.py`
- Modify: `main.py` (flag `--webview-smoke`)
- Modify: `build.spec` (incluir `webgui/` e hiddenimports do pywebview por plataforma)
- Modify: `appimage/AppImageBuilder.yml` (pacotes WebKitGTK: `gir1.2-webkit2-4.1`, `libwebkit2gtk-4.1-0`, e os helpers `WebKitNetworkProcess`/`WebKitWebProcess` em `usr/lib/*/webkit2gtk-4.1/`)
- Modify: `.github/workflows/ci.yml` (apt: `libwebkit2gtk-4.1-dev gir1.2-webkit2-4.1 xvfb`; um passo por job que roda o artefato com `--webview-smoke`)

**Interfaces:**
- Produces: `webgui.smoke.run_smoke() -> int` — abre uma janela 200×100, executa `evaluate_js("1+1")`, imprime `WEBVIEW_OK 2` no stdout e retorna 0; retorna 3 e imprime `WEBVIEW_FAIL <erro>` se algo falhar; fecha sozinho em ≤10 s.

- [ ] **Step 1:** Implementar `run_smoke()` em `webgui/smoke.py` (usar `webview.create_window(..., hidden=False)` + `webview.start(func, window)` onde `func` avalia o JS, imprime e chama `window.destroy()`).
- [ ] **Step 2:** Em `main.py`, logo após `parser.parse_args`, se `args.webview_smoke`: `sys.exit(run_smoke())`.
- [ ] **Step 3:** Rodar local: `env/bin/pip install pywebview && env/bin/python main.py --webview-smoke` → stdout contém `WEBVIEW_OK 2`, exit 0.
- [ ] **Step 4:** CI: após "Create portable executable"/"Create AppImage" em cada job (windows, macos, linux-pyinstaller ×2, linux-appimage ×2), rodar o artefato com `--webview-smoke` (Linux sob `xvfb-run -a`). Passo falha se a saída não contiver `WEBVIEW_OK 2`.
- [ ] **Step 5:** Commit e push da branch; `gh run watch` até concluir. Esperado: os 6 jobs de build verdes, cada um com `WEBVIEW_OK 2` no log.

```bash
git add requirements.txt webgui main.py build.spec appimage/AppImageBuilder.yml .github/workflows/ci.yml
git commit -m "Add pywebview smoke test to all platform builds"
git push -u origin redesign-ui
```

- [ ] **Step 6: GATE.** Todos verdes → seguir. Algum Linux vermelho sem solução → parar e reportar.

---

### Task 2: Configurações `theme` e `onboarding_done` com migração

**Files:**
- Modify: `settings.py`
- Create: `tests/test_settings_migration.py`
- Create: `requirements-dev.txt` (`pytest`)

**Interfaces:**
- Produces: `Settings.theme: Literal["system", "light", "dark"]`, `Settings.onboarding_done: bool`; função pura `settings.migrate(raw: dict) -> dict` aplicada ao JSON carregado antes de virar `Settings`. `dark_mode` continua no arquivo (o `gui.py` antigo lê) mas a interface nova usa só `theme`.

- [ ] **Step 1: Write the failing tests**

```python
from settings import migrate
from constants import PriorityMode

def test_dark_mode_true_becomes_dark():
    assert migrate({"dark_mode": True})["theme"] == "dark"

def test_dark_mode_false_becomes_system():
    assert migrate({"dark_mode": False})["theme"] == "system"

def test_existing_theme_kept():
    assert migrate({"dark_mode": True, "theme": "light"})["theme"] == "light"

def test_fresh_install_needs_onboarding():
    assert migrate({})["onboarding_done"] is False

def test_user_with_priority_skips_onboarding():
    assert migrate({"priority": ["Rust"], "priority_mode": PriorityMode.PRIORITY_ONLY})["onboarding_done"] is True

def test_user_with_non_priority_mode_skips_onboarding():
    assert migrate({"priority": [], "priority_mode": PriorityMode.ENDING_SOONEST})["onboarding_done"] is True

def test_empty_priority_only_needs_onboarding():
    assert migrate({"priority": [], "priority_mode": PriorityMode.PRIORITY_ONLY})["onboarding_done"] is False

def test_explicit_onboarding_flag_kept():
    assert migrate({"onboarding_done": False, "priority": ["Rust"]})["onboarding_done"] is False
```

Observação: o valor de `priority_mode` no JSON é o que `json_load` já produz hoje (verificar em `utils.json_load` se vem como enum ou int e ajustar os testes para o mesmo tipo).

- [ ] **Step 2:** `env/bin/pip install -r requirements-dev.txt && env/bin/python -m pytest tests/test_settings_migration.py -v` → FAIL (`migrate` não existe).
- [ ] **Step 3:** Implementar `migrate` e adicionar `theme: "system"` e `onboarding_done: False` a `default_settings`; chamar `migrate` em `Settings.__init__` antes do merge com os padrões (a migração só preenche chaves ausentes).
- [ ] **Step 4:** Rodar os testes → PASS. Rodar `env/bin/python main.py` uma vez com o `settings.json` atual e confirmar que o app antigo ainda abre.
- [ ] **Step 5: Commit** `git commit -m "Add theme and onboarding_done settings with migration"`

---

### Task 3: View-models — dados do núcleo → dicionários JSON

**Files:**
- Create: `webgui/views.py`
- Create: `tests/test_views.py`

**Interfaces:**
- Consumes: `inventory.TimedDrop`, `inventory.DropsCampaign`, `channel.Channel`, `inventory.Game` (atributos já existentes: `drop.name`, `drop.current_minutes`, `drop.required_minutes`, `drop.progress`, `drop.remaining_minutes`, `drop.is_claimed`, `drop.campaign`, `drop.image_url`/benefits; `campaign.name`, `campaign.game`, `campaign.ends_at`, `campaign.starts_at`, `campaign.drops`, `campaign.claimed_drops`, `campaign.total_drops`, `campaign.upcoming`, `campaign.finished`, `campaign.image_url`; `channel.id`, `channel.name`, `channel.online`, `channel.pending_online`, `channel.viewers`, `channel.game`). O implementador confirma os nomes exatos em `inventory.py`/`channel.py` e ajusta.
- Produces:
  - `drop_view(drop: TimedDrop) -> dict` com chaves `id, name, game, campaign, image, percent (0–100 float), remaining_minutes (int), campaign_claimed (int), campaign_total (int), campaign_remaining_minutes (int)`
  - `campaign_view(campaign: DropsCampaign, wanted: bool) -> dict` com `id, name, game, game_image, ends_at (ISO str), starts_at (ISO str), status ("active"|"upcoming"|"finished"), wanted, drops: [{id, name, image, state ("claimed"|"progress"|"pending"), percent}]`
  - `channel_view(channel: Channel, watching: bool) -> dict` com `id, name, status ("online"|"pending"|"offline"), viewers (int|None), game (str|None), watching`
  - `game_option(game: Game, campaigns: list[DropsCampaign]) -> dict` com `name, image, drops (int), ends_at (ISO do que termina primeiro)` — usado no passo a passo.

- [ ] **Step 1: Write the failing tests** com objetos falsos simples (`types.SimpleNamespace`) que imitam os atributos. Casos mínimos:

```python
def test_drop_view_values(): ...  # percent == 80.0, remaining_minutes == 5, campaign_claimed == 0, campaign_total == 5
def test_campaign_status_upcoming(): ...  # upcoming=True -> status == "upcoming"
def test_campaign_drop_states(): ...  # claimed / progress (current_minutes>0) / pending
def test_channel_viewers_none_when_offline(): ...  # offline -> viewers is None, status == "offline"
def test_views_are_json_serializable(): ...  # json.dumps(view) não levanta, incluindo nome com '"</script>😀'
```

- [ ] **Step 2:** `env/bin/python -m pytest tests/test_views.py -v` → FAIL.
- [ ] **Step 3:** Implementar as quatro funções em `webgui/views.py` (só leitura de atributos e formatação; datas com `.isoformat()`).
- [ ] **Step 4:** Testes → PASS.
- [ ] **Step 5: Commit** `git commit -m "Add web GUI view-models"`

---

### Task 4: Ponte Python ↔ JS

**Files:**
- Create: `webgui/bridge.py`
- Create: `tests/test_bridge.py`

**Interfaces:**
- Produces:
  - `class Bridge` (`__init__(self, loop: asyncio.AbstractEventLoop)`):
    - `attach(window) -> None` — guarda a janela pywebview; não entrega nada até `mark_ready()`.
    - `mark_ready() -> None` — chamado pelo evento `window.events.loaded`; entrega a fila pendente em ordem.
    - `emit(event: str, payload: Any) -> None` — thread-safe; serializa com `json.dumps(payload, ensure_ascii=False)` e chama `window.evaluate_js(f"window.tdm.on({json.dumps(event)}, {payload_json})")`; antes do `ready`, enfileira. Para `event == "log"` mantém só as últimas 500 linhas na fila.
    - `snapshot` (dict mutável) — último estado de cada evento "de estado" (`status`, `drop`, `channels`, `inventory`, `login`, `websockets`, `settings`, `theme`), devolvido a JS em `get_snapshot()` ao recarregar a página.
  - `class Api` (objeto passado como `js_api`; cada método roda numa thread do pywebview e agenda no loop com `loop.call_soon_threadsafe`): `get_snapshot() -> dict`, `login_press() -> None`, `submit_code(code: str) -> None`, `switch_channel(channel_id: int) -> None`, `set_games(names: list[str], mode: Literal["only","all"]) -> None`, `finish_onboarding(names: list[str], mode: Literal["only","all"]) -> None`, `set_setting(key: str, value: Any) -> None`, `refresh_inventory() -> None`, `invalidate_auth() -> None`, `close() -> None`. Os callbacks concretos são injetados pelo `GUIManager` (Task 5) via `Api(bridge, handlers: dict[str, Callable])`.

- [ ] **Step 1: Write the failing tests** (janela falsa com `evaluate_js` que grava as strings):

```python
def test_events_before_ready_are_flushed():   # emit 2x antes, mark_ready -> 2 chamadas na ordem
def test_payload_is_json_escaped():           # nome '"); alert(1); ("</script>' chega como string JSON válida (json.loads do argumento extraído == original)
def test_emit_from_other_thread():            # emit de threading.Thread não levanta e é entregue
def test_snapshot_keeps_last_state():         # emit("status", "a"); emit("status", "b") -> snapshot["status"] == "b"
def test_log_queue_capped():                  # 600 logs antes do ready -> 500 entregues
def test_close_from_js_sets_close_requested():# Api.close() roda o handler "close" no loop
```

- [ ] **Step 2:** `env/bin/python -m pytest tests/test_bridge.py -v` → FAIL.
- [ ] **Step 3:** Implementar `Bridge` e `Api` (lock simples em torno da fila e do flag `ready`).
- [ ] **Step 4:** Testes → PASS.
- [ ] **Step 5: Commit** `git commit -m "Add Python<->JS bridge for web GUI"`

---

### Task 5: `webgui.GUIManager` com a mesma superfície do `gui.GUIManager` + inicialização

**Files:**
- Create: `webgui/manager.py` (e reexportar `GUIManager`, `LoginForm`, `ChannelList`, `WebsocketStatus` em `webgui/__init__.py` para os imports de tipagem)
- Modify: `twitch.py:20,61`, `cache.py:18`, `channel.py:21`, `websocket.py:30` (só `from gui import` → `from webgui import`)
- Modify: `main.py` (inicialização: `webview.create_window(...)` na thread principal; `webview.start(func=run_core)` onde `run_core` faz `asyncio.run(main())`; fechar a janela quando `main()` termina)
- Create: `webgui/web/index.html` mínimo (só `<script>window.tdm={on(e,p){console.log(e,p)}}</script>`) — o front real vem no Task 6
- Create: `tests/test_manager_surface.py`

**Interfaces:**
- Consumes: `Bridge`, `Api` (Task 4); `drop_view`, `campaign_view`, `channel_view`, `game_option` (Task 3); `TrayIcon` reaproveitado de `gui.py` só se não puxar Tk — caso puxe, criar `webgui/tray.py` com a mesma API (`change_icon(state)`, `notify(message, title)`, `update_title(drop)`, `minimize()`, `restore()`, `stop()`) usando `pystray` como hoje, inclusive pulando a bandeja no macOS como o código atual faz.
- Produces — exatamente estes nomes, porque o núcleo os chama (lista extraída do código):
  - `GUIManager(twitch)`; propriedades `running`, `close_requested`; métodos `start()`, `stop()`, `close(*args) -> int`, `close_window()`, `prevent_close()`, `wait_until_closed()`, `coro_unless_closed(coro)`, `save(*, force=False)`, `grab_attention(*, sound=True)`, `set_games(games)`, `display_drop(drop, *, countdown=True, subone=False)`, `clear_drop()`, `print(message)`.
  - `gui.status.update(text)` → evento `status`.
  - `gui.websockets.update(idx, status=None, topics=None)`, `gui.websockets.remove(idx)` → evento `websockets`.
  - `gui.login`: `update(status, user_id)`, `clear(login=False, password=False, token=False)`, `wait_for_login_press()`, `ask_login()`, `ask_enter_code(uri, code)` → evento `login`; `wait_for_login_press` resolve quando `Api.login_press()` é chamado.
  - `gui.progress.stop_timer()`, `gui.progress.minute_almost_done() -> bool` (mesma semântica do `CampaignProgress` atual: timer local de 60 s reiniciado em `display_drop`).
  - `gui.channels`: `display(channel, *, add=False)`, `remove(channel)`, `clear()`, `set_watching(channel)`, `clear_watching()`, `get_selection() -> Channel | None` (seleção vem de `Api.switch_channel`, que também chama `twitch.change_state(State.CHANNEL_SWITCH)` como o botão "Switch" faz hoje).
  - `gui.inv`: `clear()`, `async add_campaign(campaign)`, `update_drop(drop)`.
  - `gui.tray`: `change_icon(state)`, `notify(message, title)`.
  - `gui.help._invalidate_button.config(state=...)` → shim que emite `auth_invalidatable` true/false.
  - Logging: handler que chama `print` (mesmo formatter `OUTPUT_FORMATTER`).
  - `Api.set_games/finish_onboarding` gravam `settings.priority` (na ordem recebida), `settings.priority_mode` (`"only"` → `PRIORITY_ONLY`, `"all"` → `ENDING_SOONEST`), `settings.onboarding_done = True` (no `finish_onboarding`), `settings.alter()`/save como o `SettingsPanel` atual faz, e chamam `twitch.change_state(State.INVENTORY_FETCH)` (mesma recarga que o botão "Refresh" do inventário dispara hoje).

- [ ] **Step 1: Write the failing test** — contrato da superfície:

```python
import ast, pathlib
CORE = ["twitch.py", "inventory.py", "channel.py", "websocket.py", "main.py", "cache.py"]

def test_every_core_gui_call_exists_on_webgui():
    # coleta todos os atributos encadeados a partir de `.gui.` nos arquivos do núcleo
    # (ex.: ("status","update"), ("help","_invalidate_button","config"))
    # e verifica com getattr em um webgui.GUIManager criado com twitch falso e Bridge com janela falsa
```

- [ ] **Step 2:** `env/bin/python -m pytest tests/test_manager_surface.py -v` → FAIL.
- [ ] **Step 3:** Implementar `webgui/manager.py`, trocar os imports, ajustar `main.py`.
- [ ] **Step 4:** Teste → PASS; rodar todos: `env/bin/python -m pytest -v` → PASS.
- [ ] **Step 5: Verificação manual:** `env/bin/python main.py -vv --log` → abre janela; `log.txt` mostra `Login successful` (sessão salva) e `Websocket[0] connected.`; fechar a janela pelo X → processo termina em ≤5 s (`pgrep -f main.py` vazio). Repetir fechando durante "Opening the browser...".
- [ ] **Step 6: Commit** `git commit -m "Add webgui GUIManager and run core under pywebview"`

---

### Task 6: Front-end — casca, tema, i18n e tela de Mineração

**Files:**
- Create: `webgui/web/index.html`, `webgui/web/app.css`, `webgui/web/app.js`
- Create: `webgui/web/dev.html` (carrega `app.js` com um `window.pywebview.api` falso e dados de exemplo — Hunt: Showdown 1896 / Supply Crate / 80% / 5 min / campanha 0 de 5 / 3h35 / huntshowdown 2.431)
- Modify: `translate.py` + `lang/English.json` (chaves `gui.web.*` usadas nesta e nas próximas telas)
- Modify: `webgui/manager.py` (emitir `theme` e `strings` no snapshot)

**Interfaces:**
- Consumes: eventos `status`, `drop`, `channels`, `login`, `theme`, `strings`; `Api.get_snapshot()`.
- Produces (JS, usado pelos Tasks 7–8): `window.tdm.on(event, payload)`; `tdm.t(path: string) -> string` (lê `strings`); `tdm.navigate(screen: "mining"|"inventory"|"channels"|"settings"|"log")`; `tdm.el(tag, attrs, ...children)` que cria elementos **sempre com `textContent`** (nunca `innerHTML` com dados).
- Regras visuais: tokens CSS em `:root` (valores das Global Constraints); escuro via `@media (prefers-color-scheme: dark)` quando `data-theme="system"` e forçado quando `data-theme="dark"`; barra lateral 56px com 4 ícones + ícone de log no rodapé (SVG inline); tela de Mineração conforme `c-light-dark.html`; tempo restante formatado `5 min` / `3h35` / `2 dias` via `tdm.t` com plural simples.
- Estado vazio da Mineração: sem drop e `onboarding_done` com lista vazia em `PRIORITY_ONLY` → texto "Nenhum jogo escolhido" + botão "Escolher jogos" (abre Configurações); sem campanhas ativas → "Nenhuma campanha ativa para os seus jogos agora".

- [ ] **Step 1:** Implementar casca + tema + i18n + tela de Mineração.
- [ ] **Step 2: Verificação visual:** abrir `webgui/web/dev.html` no Chrome, tirar screenshot nos temas claro e escuro (alternar `data-theme`), comparar com `c-light-dark.html`: mesma hierarquia (tempo grande, barra, campanha, canal).
- [ ] **Step 3: Verificação real:** `env/bin/python main.py -vv --log` com um jogo em mineração → a tela mostra o drop real e o tempo diminui a cada minuto; mudar o tema do sistema → a janela acompanha sem reiniciar (Windows/macOS).
- [ ] **Step 4:** Rodar o passo "Validate language files" do CI localmente (mesmo comando de `ci.yml`) → OK.
- [ ] **Step 5: Commit** `git commit -m "Add web GUI shell, theming and mining screen"`

---

### Task 7: Telas de Inventário, Canais, Log e Ajuda

**Files:**
- Modify: `webgui/web/app.js`, `webgui/web/app.css`, `webgui/web/dev.html` (dados de exemplo das três telas), `translate.py`, `lang/English.json`

**Interfaces:**
- Consumes: eventos `inventory` (lista de `campaign_view`), `channels` (lista de `channel_view`), `log` (string), `websockets`, `auth_invalidatable`; `Api.switch_channel`, `Api.refresh_inventory`, `Api.invalidate_auth`.
- Comportamento (mockup `other-screens.html`):
  - Inventário: filtros Ativas / Em breve / Concluídas (padrão Ativas); campanha com `wanted == false` com opacidade 0.55; drops como quadrados 30px (preenchido = `claimed`, anel cônico com `percent` = `progress`, vazio = `pending`).
  - Canais: ordenados por status (online primeiro) e espectadores desc; o `watching` com borda 2px; clique → `Api.switch_channel(id)`.
  - Log: últimas 500 linhas, rolagem automática se já estiver no fim; status dos websockets acima do log; Ajuda abaixo, com os links e o botão de invalidar sessão do `HelpTab` atual.

- [ ] **Step 1:** Implementar as três telas.
- [ ] **Step 2: Verificação visual** em `dev.html` (claro e escuro) contra `other-screens.html`.
- [ ] **Step 3: Verificação real:** com o app rodando, clicar num canal → `log.txt` mostra a troca e a tela de Mineração passa a mostrar o novo canal.
- [ ] **Step 4: Commit** `git commit -m "Add inventory, channels, log and help screens"`

---

### Task 8: Configurações e passo a passo da primeira abertura

**Files:**
- Modify: `webgui/web/app.js`, `webgui/web/app.css`, `webgui/web/dev.html`, `webgui/manager.py` (evento `settings` com o estado atual e `game_options`), `translate.py`, `lang/English.json`

**Interfaces:**
- Consumes: `Api.set_games`, `Api.finish_onboarding`, `Api.set_setting`, `Api.login_press`, `Api.submit_code`; eventos `settings`, `game_options` (lista de `game_option`), `login`.
- Configurações (mockup `other-screens.html`): lista de jogos reordenável por arrastar (HTML5 drag-and-drop) + "+ adicionar jogo" (escolhe entre `game_options` ainda não listados); segmento "Só os escolhidos"/"Todos"; Tema Sistema/Claro/Escuro (`set_setting("theme", ...)`, aplicado na hora); Iniciar com o sistema (`autostart`); Avisar quando ganhar um drop (`tray_notifications`); Idioma (lista de `lang/`, aplica após reiniciar — mostrar aviso); Conta (nome + Sair = `invalidate_auth`). Seção **"Avançado"** recolhida com: proxy, `connection_quality`, `enable_badges_emotes`, `available_drops_check`, `autostart_tray`, lista de exclusão, modo "Menor disponibilidade primeiro" (`LOW_AVBL_FIRST`). Nenhuma opção do `SettingsPanel` atual pode faltar — conferir campo a campo com `gui.py:1572-2090`.
- Passo a passo (mockup `onboarding.html`), mostrado quando `settings.onboarding_done == false`, em tela cheia sobre a interface:
  1. Entrar: se já logado, pula para 2; botão → `Api.login_press()`; mostra o código se `login` pedir `ask_enter_code`.
  2. Escolher jogos: grade 3 colunas com `game_options` (capa, nº de drops, tempo restante); ordem dos cliques = ordem da prioridade (mostrar o número); "Minerar todos" → `finish_onboarding([], "all")`; "Continuar (N)" desabilitado com N = 0. Enquanto `game_options` não chegou, mostrar "Carregando campanhas…".
  3. Pronto: resume os jogos; "Começar a minerar" → `finish_onboarding(names, "only")`.

- [ ] **Step 1: Teste Python** em `tests/test_manager_surface.py`:

```python
def test_finish_onboarding_only():   # names ["Hunt: Showdown 1896","Marvel Rivals"], "only" -> priority na mesma ordem, PRIORITY_ONLY, onboarding_done True, change_state(INVENTORY_FETCH) chamado
def test_finish_onboarding_all():    # [], "all" -> priority [], ENDING_SOONEST, onboarding_done True
def test_set_theme_persists():       # set_setting("theme","dark") -> settings.theme == "dark" e evento "theme" emitido
```

- [ ] **Step 2:** Rodar → FAIL; implementar os handlers em `webgui/manager.py`; rodar → PASS.
- [ ] **Step 3:** Implementar as telas.
- [ ] **Step 4: Verificação real:** mover `settings.json` para backup, abrir o app → passo a passo aparece; escolher 1 jogo com campanha ativa → ao terminar, a Mineração começa a minerar esse jogo (log mostra o canal); reabrir o app → passo a passo **não** aparece. Restaurar o `settings.json`.
- [ ] **Step 5: Commit** `git commit -m "Add settings screen and first-run onboarding"`

---

### Task 9: Empacotamento final e mensagens de falta de WebView

**Files:**
- Modify: `build.spec` (incluir `webgui/web/*` em `datas`), `main.py` (mensagem de erro), `manual.txt`, `.github/workflows/ci.yml` (smoke do Task 1 passa a abrir a interface real: `--webview-smoke` carrega `webgui/web/index.html` e verifica `typeof window.tdm.on === "function"`)

**Interfaces:**
- Produces: em `main.py`, se `import webview` falhar ou o `webview.start` levantar por falta de backend (Linux sem WebKitGTK, Windows sem WebView2), imprimir e mostrar (via `tkinter.messagebox`, que já é usado ali) uma mensagem traduzível em `gui.web.no_webview` explicando o que instalar (Linux: `gir1.2-webkit2-4.1`; Windows: link do instalador do WebView2) e sair com código 5.

- [ ] **Step 1:** Implementar a mensagem e o empacotamento.
- [ ] **Step 2: Verificação local da falha:** rodar com `TDM_FORCE_NO_WEBVIEW=1 env/bin/python main.py` (variável lida só para teste, que simula o `ImportError`) → mensagem aparece e exit code 5.
- [ ] **Step 3:** Atualizar `manual.txt` (requisito de WebKitGTK para o build PyInstaller do Linux; AppImage já inclui).
- [ ] **Step 4:** Push da branch e `gh run watch` → todos os jobs verdes com `WEBVIEW_OK` no log; baixar o artefato de Windows/macOS/Linux AppImage do run e abrir em cada plataforma disponível (no mínimo macOS local).
- [ ] **Step 5: Commit** `git commit -m "Package web GUI assets and handle missing WebView"`
