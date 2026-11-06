"use strict";

// ---- state -------------------------------------------------------------
const MAX_LOGS = 500;
const state = {
  strings: {},
  theme: "system",
  status: "",
  drop: null,
  channels: [],
  inventory: [],
  login: { status: "", user_id: null, waiting: false, code: null },
  websockets: null,
  settings: null,
  game_options: null,
  auth_invalidatable: false,
  logs: [],
  screen: "mining",
};

// ---- helpers -------------------------------------------------------------
function api() {
  return (window.pywebview && window.pywebview.api) || null;
}

function call(method, ...args) {
  const a = api();
  if (a && typeof a[method] === "function") return a[method](...args);
  return undefined;
}

// Builds DOM nodes. Text always goes through textContent - never innerHTML with data.
function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "style") node.setAttribute("style", value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function t(path, vars) {
  let value = state.strings;
  for (const key of path.split(".")) {
    value = value && typeof value === "object" ? value[key] : undefined;
  }
  if (typeof value !== "string") return path;
  return value.replace(/\{(\w+)\}/g, (m, name) => (vars && name in vars ? vars[name] : m));
}

function duration(minutes) {
  minutes = Math.max(0, Math.round(minutes));
  if (minutes < 60) return t("time.minutes", { n: minutes });
  if (minutes < 60 * 24) {
    const h = Math.floor(minutes / 60);
    const m = String(minutes % 60).padStart(2, "0");
    return t("time.hours", { h, m });
  }
  const days = Math.round(minutes / (60 * 24));
  return days === 1 ? t("time.day") : t("time.days", { n: days });
}

function minutesUntil(iso) {
  return (new Date(iso).getTime() - Date.now()) / 60000;
}

function bar(percent, extraClass) {
  const width = Math.max(0, Math.min(100, Number(percent) || 0));
  return el("div", { class: "bar" + (extraClass ? " " + extraClass : "") },
    el("i", { style: `width:${width}%` }));
}

function number(n) {
  return new Intl.NumberFormat().format(n);
}

// ---- icons (inline SVG, stroke = currentColor) ---------------------------
const ICON_PATHS = {
  mining: "M13 2 4 14h7l-1 8 9-12h-7z",
  inventory: "M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v8",
  channels: "M3 6h18v12H3zM8 21h8M12 18v3",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  log: "M4 17l6-5-6-5M12 19h8",
};

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", ICON_PATHS[name]);
  svg.append(path);
  return svg;
}

// ---- screens -------------------------------------------------------------
const screens = {};

function navigate(screen) {
  state.screen = screen;
  render();
}

function statusChip() {
  const kind = state.drop ? "ok" : (state.login.user_id ? "" : "warn");
  return el("span", { class: "chip " + kind, title: state.status }, state.status || "…");
}

function watchingChannel() {
  return (state.channels || []).find((c) => c.watching) || null;
}

screens.mining = function () {
  const drop = state.drop;
  const head = el("div", { class: "head" },
    el("h1", {}, t("mining.title")),
    el("div", { class: "end" }, statusChip()));

  if (!state.login.user_id && !drop) {
    return [head, el("div", { class: "panel empty" },
      el("h2", {}, t("mining.logged_out")),
      el("p", { class: "muted" }, state.login.status || ""),
      el("button", {
        class: "btn", disabled: !state.login.waiting, onclick: () => call("login_press"),
      }, t("mining.login")))];
  }

  if (!drop) {
    const settings = state.settings;
    const noGames = settings && settings.mode === "only" && settings.priority.length === 0;
    return [head, el("div", { class: "panel empty" },
      el("h2", {}, noGames ? t("mining.no_games") : t("mining.no_campaigns")),
      el("p", { class: "muted" }, noGames ? t("mining.no_games_text") : t("mining.no_campaigns_text")),
      noGames && el("button", { class: "btn", onclick: () => navigate("settings") },
        t("mining.choose_games")))];
  }

  const channel = watchingChannel();
  return [
    head,
    el("div", { class: "panel" },
      el("div", { class: "drop-head" },
        drop.image && el("img", { src: drop.image, alt: "" }),
        el("div", {},
          el("div", { class: "muted" }, drop.game),
          el("div", { class: "strong", style: "font-size:17px" }, drop.name))),
      el("div", { class: "row", style: "align-items:baseline;margin-top:18px" },
        el("span", { class: "big" }, duration(drop.remaining_minutes)),
        el("span", { class: "muted" }, `${t("mining.remaining")} · ${Math.floor(drop.percent)}%`)),
      el("div", { style: "margin-top:14px" }, bar(drop.percent))),
    el("div", { class: "panel" },
      el("div", { class: "row" },
        el("span", {}, t("mining.campaign", { claimed: drop.campaign_claimed, total: drop.campaign_total })),
        el("span", { class: "muted end" }, duration(drop.campaign_remaining_minutes))),
      el("div", { class: "muted", style: "margin-top:2px" }, drop.campaign),
      el("div", { style: "margin-top:10px" }, bar(drop.campaign_percent, "accent"))),
    channel && el("div", { class: "panel row", style: "padding:12px 20px" },
      el("span", { class: "dot" }),
      el("span", { class: "strong" }, channel.name),
      el("span", { class: "muted" }, t("mining.watching")),
      el("span", { class: "muted end" },
        channel.viewers != null ? t("mining.viewers", { n: number(channel.viewers) }) : "")),
  ];
};

// ---- inventory ---------------------------------------------------------
state.inventoryFilter = "active";

function dropTile(drop) {
  const pct = Math.floor(drop.percent);
  return el("div", { class: "tile " + drop.state, title: `${drop.name} · ${pct}%` },
    el("div", { class: "thumb" },
      drop.image
        ? el("img", { src: drop.image, alt: "", loading: "lazy" })
        : el("span", { class: "initial" }, (drop.name || "?").trim().charAt(0).toUpperCase()),
      drop.state === "claimed" && el("span", { class: "check", "aria-hidden": "true" }, "✓")),
    el("div", { class: "tile-name" }, drop.name),
    el("div", { class: "tile-meta" },
      drop.state === "claimed" ? "100%" : drop.state === "progress" ? `${pct}%` : "—"),
    bar(drop.state === "claimed" ? 100 : drop.percent, drop.state === "progress" ? "accent" : ""));
}

screens.inventory = function () {
  const filters = ["active", "upcoming", "finished"];
  const head = el("div", { class: "head" },
    el("h1", {}, t("inventory.title")),
    el("div", { class: "end" },
      filters.map((f) => el("button", {
        class: "tab" + (state.inventoryFilter === f ? " on" : ""),
        onclick: () => { state.inventoryFilter = f; render(); },
      }, t("inventory." + f))),
      el("button", {
        class: "btn ghost small", title: t("inventory.refresh"), onclick: () => call("refresh_inventory"),
      }, "↻")));
  const campaigns = (state.inventory || [])
    .filter((c) => c.status === state.inventoryFilter)
    .sort((a, b) => (b.wanted - a.wanted) || a.ends_at.localeCompare(b.ends_at));
  if (campaigns.length === 0) {
    return [head, el("div", { class: "panel empty" }, el("p", { class: "muted" }, t("inventory.empty")))];
  }
  return [head, campaigns.map((c) => {
    const claimed = c.drops.filter((d) => d.state === "claimed").length;
    let when;
    if (c.status === "upcoming") when = t("inventory.starts_in", { time: duration(minutesUntil(c.starts_at)) });
    else if (c.status === "finished") when = t("inventory.ended");
    else when = t("inventory.ends_in", { time: duration(minutesUntil(c.ends_at)) });
    return el("div", { class: "panel campaign" + (c.wanted ? "" : " dim") },
      el("div", { class: "row" },
        c.game_image && el("img", { class: "cover", src: c.game_image, alt: "" }),
        el("div", { style: "min-width:0" },
          el("div", { class: "strong ellipsis" }, c.game),
          el("div", { class: "muted ellipsis" },
            `${c.name} · ${t("inventory.drops", { claimed, total: c.drops.length })}`)),
        el("span", { class: "muted end nowrap" }, c.wanted ? when : t("inventory.not_selected"))),
      el("div", { class: "drops" }, c.drops.map(dropTile)));
  })];
};

// ---- channels ------------------------------------------------------------
const STATUS_ORDER = { online: 0, pending: 1, offline: 2 };

screens.channels = function () {
  const head = el("div", { class: "head" },
    el("h1", {}, t("channels.title")),
    el("div", { class: "end muted" }, t("channels.auto")));
  const channels = [...(state.channels || [])].sort((a, b) =>
    (STATUS_ORDER[a.status] - STATUS_ORDER[b.status]) || ((b.viewers || 0) - (a.viewers || 0)));
  if (channels.length === 0) {
    return [head, el("div", { class: "panel empty" }, el("p", { class: "muted" }, t("channels.empty")))];
  }
  return [
    head,
    el("div", { class: "list" }, channels.map((c) => el("button", {
      class: "panel row channel" + (c.watching ? " watching" : ""),
      disabled: c.status !== "online",
      onclick: () => call("switch_channel", c.id),
    },
    el("span", { class: "dot" + (c.status === "online" ? "" : c.status === "pending" ? " pending" : " off") }),
    el("span", { class: c.watching ? "strong" : "" }, c.name),
    c.watching && el("span", { class: "muted" }, t("mining.watching")),
    c.status !== "online" && el("span", { class: "muted" }, t("channels." + c.status)),
    el("span", { class: "muted end" }, c.viewers != null ? number(c.viewers) : "")))),
    el("div", { class: "muted", style: "margin-top:4px" }, t("channels.hint")),
  ];
};

// ---- log & help ----------------------------------------------------------
function link(href, text) {
  return el("a", { href, target: "_blank", rel: "noopener" }, text);
}

screens.log = function () {
  const ws = state.websockets;
  const logBox = el("pre", { class: "log" }, state.logs.join("\n"));
  requestAnimationFrame(() => { logBox.scrollTop = logBox.scrollHeight; });
  return [
    el("div", { class: "head" }, el("h1", {}, t("log.title"))),
    ws && el("div", { class: "panel" },
      el("div", { class: "strong", style: "margin-bottom:8px" }, t("log.websockets")),
      el("div", { class: "ws" }, ws.items.map((w) => el("div", { class: "row" },
        el("span", { class: "dot" + (/connect/i.test(w.status) && !/dis/i.test(w.status) ? "" : " off") }),
        el("span", {}, `#${w.idx + 1}`),
        el("span", { class: "muted" }, w.status),
        el("span", { class: "muted end" }, `${w.topics}/${ws.limit}`))))),
    el("div", { class: "panel", style: "padding:0;overflow:hidden" }, logBox),
    el("div", { class: "panel" },
      el("div", { class: "strong", style: "margin-bottom:6px" }, t("help.how_it_works")),
      el("p", { class: "muted pre", style: "margin:0" }, t("help.how_it_works_text"))),
    el("div", { class: "panel row wrap" },
      link("https://www.twitch.tv/drops/inventory", t("help.links.inventory")),
      link("https://www.twitch.tv/drops/campaigns", t("help.links.campaigns")),
      link("https://github.com/igorlopes12/TwitchDropsMiner", "GitHub"),
      el("span", { class: "muted end" }, "Twitch Drops Miner · DevilXD")),
    el("div", { class: "panel row" },
      el("span", {}, t("help.invalidate.text")),
      el("button", {
        class: "btn small end", disabled: !state.auth_invalidatable, onclick: () => call("invalidate_auth"),
      }, t("help.invalidate.button"))),
  ];
};

// ---- settings ------------------------------------------------------------
function toggle(on, onchange, label) {
  return el("button", {
    class: "switch" + (on ? " on" : ""), role: "switch", "aria-checked": on ? "true" : "false",
    "aria-label": label, onclick: () => onchange(!on),
  });
}

function segmented(options, current, onpick) {
  return el("div", { class: "seg", role: "radiogroup" }, options.map(([value, label]) => el("button", {
    class: value === current ? "on" : "", role: "radio", "aria-checked": value === current ? "true" : "false",
    onclick: () => value !== current && onpick(value),
  }, label)));
}

function settingRow(label, control) {
  return el("div", { class: "row setting" }, el("span", {}, label), el("div", { class: "end" }, control));
}

function gameChoices(exclude) {
  const taken = new Set(exclude);
  const names = new Set((state.game_options || []).map((g) => g.name));
  (state.inventory || []).forEach((c) => names.add(c.game));
  return [...names].filter((n) => !taken.has(n)).sort((a, b) => a.localeCompare(b));
}

function addSelect(placeholder, choices, onpick) {
  return el("select", {
    class: "add", onchange: (e) => { if (e.target.value) onpick(e.target.value); },
  }, el("option", { value: "" }, placeholder), choices.map((n) => el("option", { value: n }, n)));
}

let dragFrom = null;

function priorityList(s) {
  const mode = s.mode === "low" ? "low" : s.mode;
  const save = (list) => call("set_games", list, mode);
  if (s.priority.length === 0) {
    return el("div", { class: "muted", style: "padding:8px 0" }, t("settings.no_games"));
  }
  return el("ol", { class: "games" }, s.priority.map((name, i) => el("li", {
    draggable: "true",
    ondragstart: (e) => { dragFrom = i; e.dataTransfer.effectAllowed = "move"; },
    ondragover: (e) => { e.preventDefault(); e.currentTarget.classList.add("over"); },
    ondragleave: (e) => e.currentTarget.classList.remove("over"),
    ondrop: (e) => {
      e.preventDefault();
      if (dragFrom === null || dragFrom === i) return;
      const list = [...s.priority];
      const [moved] = list.splice(dragFrom, 1);
      list.splice(i, 0, moved);
      dragFrom = null;
      save(list);
    },
  },
  el("span", { class: "grip", "aria-hidden": "true" }, "⋮⋮"),
  el("span", { class: "num" }, `${i + 1}.`),
  el("span", { class: "ellipsis" }, name),
  el("button", {
    class: "x end", title: t("settings.remove"), "aria-label": t("settings.remove"),
    onclick: () => save(s.priority.filter((n) => n !== name)),
  }, "×"))));
}

screens.settings = function () {
  const s = state.settings;
  if (!s) return [];
  const set = (key, value) => call("set_setting", key, value);
  const mode = s.mode === "only" ? "only" : "all";
  const choices = gameChoices(s.priority);
  return [
    el("div", { class: "head" }, el("h1", {}, t("settings.title"))),
    el("div", { class: "panel" },
      el("div", { class: "row" },
        el("span", { class: "strong" }, t("settings.games")),
        el("div", { class: "end" }, segmented(
          [["only", t("settings.mode_only")], ["all", t("settings.mode_all")]], mode,
          (value) => set("mode", value)))),
      priorityList(s),
      choices.length > 0 && addSelect(t("settings.add_game"), choices,
        (name) => call("set_games", [...s.priority, name], s.mode))),
    el("div", { class: "panel" },
      settingRow(t("settings.theme"), segmented([
        ["system", t("settings.theme_system")], ["light", t("settings.theme_light")],
        ["dark", t("settings.theme_dark")]], s.theme, (value) => set("theme", value))),
      settingRow(t("settings.autostart"), toggle(s.autostart, (v) => set("autostart", v), t("settings.autostart"))),
      settingRow(t("settings.notify"), toggle(s.tray_notifications, (v) => set("tray_notifications", v), t("settings.notify"))),
      settingRow(t("settings.language"), el("select", {
        onchange: (e) => set("language", e.target.value),
      }, s.languages.map((l) => el("option", { value: l, selected: l === s.language }, l)))),
      s.language !== state.startLanguage && state.startLanguage &&
        el("div", { class: "muted", style: "text-align:right" }, t("settings.language_restart"))),
    el("div", { class: "panel" },
      settingRow(t("settings.account"), el("div", { class: "row" },
        el("span", { class: "muted" }, state.login.user_id ? `ID ${state.login.user_id}` : "—"),
        el("button", {
          class: "btn ghost small", disabled: !state.auth_invalidatable, onclick: () => call("invalidate_auth"),
        }, t("settings.logout"))))),
    el("details", { class: "panel advanced", open: state.advancedOpen },
      el("summary", { onclick: (e) => { e.preventDefault(); state.advancedOpen = !state.advancedOpen; render(); } },
        t("settings.advanced")),
      settingRow(t("settings.start_in_tray"), toggle(s.autostart_tray, (v) => set("autostart_tray", v), t("settings.start_in_tray"))),
      settingRow(t("settings.low_availability"), toggle(s.mode === "low",
        (v) => set("mode", v ? "low" : "all"), t("settings.low_availability"))),
      settingRow(t("settings.badges_emotes"), toggle(s.enable_badges_emotes, (v) => set("enable_badges_emotes", v), t("settings.badges_emotes"))),
      settingRow(t("settings.available_drops_check"), toggle(s.available_drops_check, (v) => set("available_drops_check", v), t("settings.available_drops_check"))),
      settingRow(t("settings.connection_quality"), el("input", {
        type: "number", min: "1", max: "6", value: s.connection_quality, class: "num-input",
        onchange: (e) => set("connection_quality", Number(e.target.value)),
      })),
      settingRow(t("settings.proxy"), el("input", {
        type: "text", value: s.proxy, placeholder: t("settings.proxy_hint"), class: "text-input",
        onchange: (e) => set("proxy", e.target.value),
      })),
      el("div", { class: "setting" },
        el("div", { style: "margin-bottom:6px" }, t("settings.exclude")),
        el("div", { class: "chips" }, s.exclude.map((name) => el("span", { class: "chip" }, name, " ",
          el("button", {
            class: "x", "aria-label": t("settings.remove"),
            onclick: () => set("exclude", s.exclude.filter((n) => n !== name)),
          }, "×")))),
        addSelect(t("settings.add_game"), gameChoices(s.exclude), (name) => set("exclude", [...s.exclude, name])))),
  ];
};

// ---- onboarding ------------------------------------------------------------
state.ob = { step: 1, picks: [] };

function onboarding() {
  const ob = state.ob;
  if (ob.step === 1 && state.login.user_id) ob.step = 2;
  const steps = el("div", { class: "steps" }, [1, 2, 3].map((n) => el("i", { class: n <= ob.step ? "on" : "" })));
  let body;
  if (ob.step === 1) {
    body = [
      el("h2", {}, t("onboarding.welcome")),
      el("p", { class: "muted" }, t("onboarding.welcome_text")),
      el("div", { class: "ob-center" },
        el("div", { class: "logo" }, icon("mining")),
        el("p", { class: "muted" }, state.login.waiting ? t("onboarding.login_hint") : t("onboarding.logging_in"))),
      el("div", { class: "ob-actions" }, el("button", {
        class: "btn", disabled: !state.login.waiting, onclick: () => call("login_press"),
      }, t("onboarding.login_button"))),
    ];
  } else if (ob.step === 2) {
    const options = state.game_options;
    body = [
      el("h2", {}, t("onboarding.games")),
      el("p", { class: "muted" }, options ? t("onboarding.games_text", { n: options.length }) : t("onboarding.loading")),
      el("div", { class: "grid" }, (options || []).map((g) => {
        const index = ob.picks.indexOf(g.name);
        return el("button", {
          class: "game" + (index >= 0 ? " sel" : ""), "aria-pressed": index >= 0 ? "true" : "false",
          onclick: () => {
            if (index >= 0) ob.picks.splice(index, 1); else ob.picks.push(g.name);
            render();
          },
        },
        el("div", { class: "art" }, g.image && el("img", { src: g.image, alt: "" }),
          index >= 0 && el("span", { class: "badge" }, String(index + 1))),
        el("div", { class: "strong ellipsis" }, g.name),
        el("div", { class: "muted ellipsis" },
          `${g.drops} drops · ${duration(minutesUntil(g.ends_at))}`));
      })),
      el("div", { class: "ob-actions" },
        el("button", { class: "btn ghost", onclick: () => call("finish_onboarding", [], "all") }, t("onboarding.mine_all")),
        el("button", {
          class: "btn", disabled: ob.picks.length === 0, onclick: () => { ob.step = 3; render(); },
        }, t("onboarding.continue", { n: ob.picks.length }))),
    ];
  } else {
    body = [
      el("h2", {}, t("onboarding.done")),
      el("p", { class: "muted" }, t("onboarding.done_text")),
      el("div", { class: "ob-center" },
        el("div", { class: "big" }, t("onboarding.games_count", { n: ob.picks.length })),
        el("p", { class: "muted" }, ob.picks.join(" → "))),
      el("div", { class: "ob-actions" },
        el("button", { class: "btn ghost", onclick: () => { ob.step = 2; render(); } }, "‹"),
        el("button", { class: "btn", onclick: () => call("finish_onboarding", [...ob.picks], "only") },
          t("onboarding.start"))),
    ];
  }
  return el("div", { class: "onboarding" }, el("div", { class: "ob-card" }, steps, body));
}

// ---- render ------------------------------------------------------------
const NAV = ["mining", "inventory", "channels", "settings"];
let renderQueued = false;

let renderDeferred = false;

function render() {
  // don't rebuild the page under the user's cursor while they type or pick
  const active = document.activeElement;
  if (active && active.matches && active.matches("input, select, textarea")) {
    renderDeferred = true;
    return;
  }
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(() => {
    renderQueued = false;
    draw();
  });
}

function draw() {
  document.documentElement.dataset.theme = state.theme || "system";
  const nav = el("nav", { class: "nav" },
    NAV.map((name) => el("button", {
      class: state.screen === name ? "on" : "", title: t("nav." + name),
      "aria-label": t("nav." + name), onclick: () => navigate(name),
    }, icon(name))),
    el("div", { class: "spacer" }),
    el("button", {
      class: state.screen === "log" ? "on" : "", title: t("nav.log"), "aria-label": t("nav.log"),
      onclick: () => navigate("log"),
    }, icon("log")));
  const screen = screens[state.screen] || screens.mining;
  const main = el("main", { class: "main" }, el("div", { class: "screen" }, screen()));
  const scroll = document.querySelector(".main");
  const top = scroll ? scroll.scrollTop : 0;
  const showOnboarding = state.settings && !state.settings.onboarding_done;
  document.getElementById("app").replaceChildren(
    el("div", { class: "app" }, nav, main), showOnboarding && onboarding());
  main.scrollTop = top;
}

// ---- events from Python --------------------------------------------------
window.tdm = {
  on(event, payload) {
    if (event === "log") {
      state.logs.push(payload);
      if (state.logs.length > MAX_LOGS) state.logs.splice(0, state.logs.length - MAX_LOGS);
      // log lines only matter on the log screen
      if (state.screen !== "log") return;
    } else {
      if (event === "settings" && payload && !state.startLanguage) state.startLanguage = payload.language;
      state[event] = payload;
    }
    render();
  },
  t, el, navigate, duration, state, screens, render,
  onboarding: () => { state.settings = Object.assign({}, state.settings, { onboarding_done: false }); state.ob = { step: 1, picks: [] }; render(); },
};

document.addEventListener("focusout", () => {
  if (!renderDeferred) return;
  renderDeferred = false;
  // focus moves after focusout; check on the next tick
  setTimeout(render, 0);
});

window.addEventListener("pywebviewready", async () => {
  const snapshot = await call("get_snapshot");
  if (snapshot) Object.assign(state, snapshot);
  render();
});

// time-based labels ("ends in ...") drift; refresh them every minute
setInterval(render, 60000);
render();
