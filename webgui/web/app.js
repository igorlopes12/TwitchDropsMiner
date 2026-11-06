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
  for (const child of children.flat()) {
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

// ---- render ------------------------------------------------------------
const NAV = ["mining", "inventory", "channels", "settings"];
let renderQueued = false;

function render() {
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
  document.getElementById("app").replaceChildren(el("div", { class: "app" }, nav, main));
  main.scrollTop = top;
}

// ---- events from Python --------------------------------------------------
window.tdm = {
  on(event, payload) {
    if (event === "log") {
      state.logs.push(payload);
      if (state.logs.length > MAX_LOGS) state.logs.splice(0, state.logs.length - MAX_LOGS);
    } else {
      state[event] = payload;
    }
    render();
  },
  t, el, navigate, duration, state, screens, render,
};

window.addEventListener("pywebviewready", async () => {
  const snapshot = await call("get_snapshot");
  if (snapshot) Object.assign(state, snapshot);
  render();
});

// time-based labels ("ends in ...") drift; refresh them every minute
setInterval(render, 60000);
render();
