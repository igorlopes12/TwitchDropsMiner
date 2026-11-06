"""Writes webgui/web/dev.html: the web GUI with fake data, for checking the look in a browser."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.argv[0] = str(ROOT / "main.py")
sys.path.insert(0, str(ROOT))
from translate import _  # noqa: E402

lang = sys.argv[1] if len(sys.argv) > 1 else "Português"
_.set_language(lang)
strings = json.dumps({**_._translation["gui"]["web"], "help": _._translation["gui"]["help"]}, ensure_ascii=False).replace("</", "<\\/")

DEV = r"""<!doctype html>
<html lang="en" data-theme="system">
<head><meta charset="utf-8"><title>TDM dev</title><link rel="stylesheet" href="app.css">
<style>#devbar{position:fixed;right:10px;bottom:10px;z-index:9;display:flex;gap:6px}
#devbar button{font:12px sans-serif;padding:4px 8px}</style></head>
<body><div id="app"></div>
<div id="devbar">
  <button onclick="tdm.on('theme','light')">light</button>
  <button onclick="tdm.on('theme','dark')">dark</button>
  <button onclick="tdm.on('theme','system')">system</button>
  <button onclick="tdm.on('drop',null)">no drop</button>
  <button onclick="tdm.onboarding()">onboarding</button>
</div>
<script src="app.js"></script>
<script>
const calls = [];
window.pywebview = {api: new Proxy({}, {get: (_, name) => (...args) => {
  calls.push([name, ...args]); console.log("api", name, args);
  if (name === "get_snapshot") return Promise.resolve(null);
}})};
const S = __STRINGS__;
const future = (h) => new Date(Date.now() + h * 3600e3).toISOString();
const box = (id) => `https://static-cdn.jtvnw.net/ttv-boxart/${id}.jpg`;
tdm.on("strings", S);
tdm.on("login", {status: "Logged in", user_id: 144802444, waiting: false, code: null});
tdm.on("status", "Assistindo: huntshowdown");
tdm.on("settings", {priority: ["Hunt: Showdown 1896", "Marvel Rivals"], exclude: [], mode: "only",
  theme: "system", onboarding_done: true, tray_notifications: true, autostart_tray: false,
  enable_badges_emotes: false, available_drops_check: false, connection_quality: 1,
  language: "Português", languages: ["English", "Português", "Deutsch"], proxy: ""});
tdm.on("drop", {id: "d1", name: "Supply Crate", game: "Hunt: Showdown 1896",
  campaign: "Hunt 1896 (Week 2, Pt. 3)", image: null, percent: 80, remaining_minutes: 5,
  campaign_claimed: 0, campaign_total: 5, campaign_remaining_minutes: 215, campaign_percent: 32.7});
tdm.on("channels", [
  {id: 1, name: "huntshowdown", status: "online", viewers: 2431, game: "Hunt: Showdown 1896", watching: true},
  {id: 2, name: "gunsmith_hunt", status: "online", viewers: 812, game: "Hunt: Showdown 1896", watching: false},
  {id: 3, name: "bayou_streams", status: "pending", viewers: null, game: null, watching: false},
  {id: 4, name: "crowbait_tv", status: "offline", viewers: null, game: null, watching: false}]);
const HUNT = ["Supply Crate", "Random Avatar", "Legendary Hunter: Bloodline", "Weapon Charm", "Spitfire Skin"];
const drops = (states) => states.map((s, i) => ({id: "x" + i, name: HUNT[i % HUNT.length], image: null,
  state: s, percent: s === "progress" ? 80 : (s === "claimed" ? 100 : 0)}));
tdm.on("inventory", [
  {id: "c1", name: "Hunt 1896 (Week 2, Pt. 3)", game: "Hunt: Showdown 1896", game_image: box("1597497"),
   starts_at: future(-48), ends_at: future(3.6), status: "active", wanted: true,
   drops: drops(["progress", "pending", "pending", "pending", "pending"])},
  {id: "c2", name: "Season 5", game: "Marvel Rivals", game_image: box("1264310518"),
   starts_at: future(-24), ends_at: future(50), status: "active", wanted: true,
   drops: drops(["claimed", "pending", "pending"])},
  {id: "c3", name: "Twitch Drops Round 42", game: "Rust", game_image: box("263490"),
   starts_at: future(-10), ends_at: future(150), status: "active", wanted: false,
   drops: drops(["pending", "pending", "pending", "pending"])},
  {id: "c4", name: "Next season", game: "Destiny 2", game_image: box("497057"),
   starts_at: future(30), ends_at: future(200), status: "upcoming", wanted: false, drops: drops(["pending"])}]);
tdm.on("game_options", [
  {name: "Hunt: Showdown 1896", image: box("1597497"), drops: 5, ends_at: future(3.6)},
  {name: "Rust", image: box("263490"), drops: 8, ends_at: future(150)},
  {name: "Marvel Rivals", image: box("1264310518"), drops: 3, ends_at: future(50)},
  {name: "PUBG: BATTLEGROUNDS", image: box("493057"), drops: 4, ends_at: future(120)},
  {name: "VALORANT", image: box("516575"), drops: 2, ends_at: future(24)},
  {name: "Destiny 2", image: box("497057"), drops: 6, ends_at: future(216)}]);
tdm.on("websockets", {limit: 50, max: 8, items: [{idx: 0, status: "Connected", topics: 42}]});
tdm.on("auth_invalidatable", true);
if (location.hash.startsWith("#theme=")) tdm.on("theme", location.hash.slice(7).split("&")[0]);
const screenArg = (location.hash.match(/screen=(\w+)/) || [])[1];
if (screenArg) tdm.navigate(screenArg);
const obArg = (location.hash.match(/ob=(\d)/) || [])[1];
if (obArg) {
  if (obArg === "1") tdm.on("login", {status: "Logged out", user_id: null, waiting: true, code: null});
  tdm.onboarding();
  if (obArg === "3") { tdm.state.ob.step = 3; tdm.state.ob.picks = ["Hunt: Showdown 1896", "Marvel Rivals"]; }
  if (obArg === "2") tdm.state.ob.picks = ["Hunt: Showdown 1896", "Marvel Rivals"];
  tdm.render();
}
for (let i = 0; i < 30; i++) tdm.on("log", `17:2${i % 10}:0${i % 10}: INFO: example log line ${i}`);
</script></body></html>
"""

out = ROOT / "webgui" / "web" / "dev.html"
out.write_text(DEV.replace("__STRINGS__", strings), encoding="utf8")
print(out)
