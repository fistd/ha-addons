#!/usr/bin/env python3
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, redirect, render_template_string, request, send_file


APP = Flask(__name__)

CONTROL_PLANE_URL = os.environ.get("RP_CONTROL_PLANE_URL", "https://admin.cz.richpear.cz").rstrip("/")
FRPC_BIN = os.environ.get("RP_FRPC_BIN", "/usr/local/bin/frpc")
FRPC_CONFIG = os.environ.get("RP_FRPC_CONFIG", "/data/frpc.toml")
FRPC_LOG = os.environ.get("RP_FRPC_LOG", "/data/frpc.log")
DEVICE_ID_FILE = os.environ.get("RP_DEVICE_ID_FILE", "/data/device_id")
PUBLIC_KEY_FILE = os.environ.get("RP_PUBLIC_KEY_FILE", "/data/device_pub.pem")
STATE_FILE = os.environ.get("RP_STATE_FILE", "/data/onboarding_state.json")
LOCAL_PROXY_PORT = int(os.environ.get("RP_LOCAL_PROXY_PORT", "18123"))
UPSTREAM_HOST_HEADER = os.environ.get("RP_UPSTREAM_HOST_HEADER", "localhost")


def load_state() -> dict:
    p = Path(STATE_FILE)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    Path(STATE_FILE).write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def load_device_id() -> str:
    return Path(DEVICE_ID_FILE).read_text(encoding="utf-8").strip()


def load_public_key() -> str:
    return Path(PUBLIC_KEY_FILE).read_text(encoding="utf-8").strip()


def api_post(path: str, payload: dict, bearer_token: str | None = None) -> tuple[int, dict]:
    url = f"{CONTROL_PLANE_URL}{path}"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return resp.getcode(), json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        try:
            return e.code, json.loads(body) if body else {}
        except Exception:
            return e.code, {"detail": body or f"HTTP {e.code}"}
    except Exception as e:
        return 0, {"detail": str(e)}


def write_frpc_config(subdomain: str, frp_server: str, frp_port: int, frp_token: str) -> None:
    content = f"""serverAddr = \"{frp_server}\"
serverPort = {frp_port}
user = \"{subdomain}\"
metadatas.token = \"{frp_token}\"

[[proxies]]
name = \"{subdomain}-ha\"
type = \"http\"
localIP = \"127.0.0.1\"
localPort = {LOCAL_PROXY_PORT}
subdomain = \"{subdomain}\"
hostHeaderRewrite = \"{UPSTREAM_HOST_HEADER}\"
"""
    Path(FRPC_CONFIG).write_text(content, encoding="utf-8")


def restart_frpc() -> None:
    subprocess.run(["pkill", "-f", f"{FRPC_BIN} -c {FRPC_CONFIG}"], check=False)
    logf = open(FRPC_LOG, "a", encoding="utf-8")
    subprocess.Popen([FRPC_BIN, "-c", FRPC_CONFIG], stdout=logf, stderr=subprocess.STDOUT)


def frpc_running() -> bool:
    result = subprocess.run(["pgrep", "-f", f"{FRPC_BIN} -c {FRPC_CONFIG}"], check=False, capture_output=True, text=True)
    return result.returncode == 0 and bool(result.stdout.strip())


def ingress_path() -> str:
    base = request.headers.get("X-Ingress-Path", "").strip()
    if not base:
        return ""
    if not base.startswith("/"):
        base = f"/{base}"
    return base.rstrip("/")


def ingress_redirect(ok: str = "", err: str = ""):
    base = ingress_path()
    query = ""
    if ok:
        query = "?ok=" + urllib.parse.quote_plus(ok)
    elif err:
        query = "?err=" + urllib.parse.quote_plus(err)
    return redirect(f"{base}/{query}" if base else f"/{query}")


@APP.get("/rp-home.svg")
def addon_logo():
    return send_file("/opt/richpear/rp-home.svg", mimetype="image/svg+xml")


@APP.get("/")
def index():
    state = load_state()
    is_logged = bool(state.get("access_token"))
    return render_template_string(
        """
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RichPear Home</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: var(--primary-background-color, #0b101a);
      --card: var(--card-background-color, #151b28);
      --line: var(--divider-color, #2b3344);
      --text: var(--primary-text-color, #edf2ff);
      --muted: var(--secondary-text-color, #98a3b8);
      --primary: var(--primary-color, #19b46f);
      --primary-ink: var(--text-primary-color, #07160f);
      --ok: var(--success-color, #2abb67);
      --err: var(--error-color, #df4b4b);
      --chip: color-mix(in srgb, var(--card) 78%, #0f1420 22%);
      --input: color-mix(in srgb, var(--card) 90%, #0f1420 10%);
      --focus: color-mix(in srgb, var(--primary) 35%, transparent);
    }

    @media (prefers-color-scheme: light) {
      :root {
        --bg: var(--primary-background-color, #f3f6fb);
        --card: var(--card-background-color, #ffffff);
        --line: var(--divider-color, #d8e0ef);
        --text: var(--primary-text-color, #0f172a);
        --muted: var(--secondary-text-color, #607088);
        --primary: var(--primary-color, #128b5d);
        --primary-ink: var(--text-primary-color, #ffffff);
        --chip: color-mix(in srgb, var(--card) 52%, #ecf1f8 48%);
        --input: color-mix(in srgb, var(--card) 90%, #eef4fb 10%);
      }
    }

    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 14% -6%, color-mix(in srgb, var(--primary) 13%, transparent), transparent 35%),
        linear-gradient(180deg, var(--bg), color-mix(in srgb, var(--bg) 80%, #060b12 20%));
    }

    .container {
      width: min(1120px, calc(100% - 24px));
      margin: 0 auto;
    }

    .top {
      position: sticky;
      top: 0;
      z-index: 15;
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(8px);
      background: color-mix(in srgb, var(--card) 92%, transparent);
    }

    .top-inner {
      min-height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      padding: 8px 0;
    }

    .brand {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      font-size: 15px;
      letter-spacing: -0.01em;
    }

    .brand img {
      width: 30px;
      height: 30px;
      object-fit: contain;
      border-radius: 6px;
      display: block;
    }

    .nav {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }

    .nav-item {
      border: 1px solid var(--line);
      background: var(--chip);
      color: var(--muted);
      border-radius: 999px;
      padding: 6px 11px;
      font-size: 13px;
      line-height: 1;
      white-space: nowrap;
    }

    .nav-item.active {
      background: color-mix(in srgb, var(--primary) 18%, var(--card) 82%);
      border-color: color-mix(in srgb, var(--primary) 40%, var(--line) 60%);
      color: var(--primary);
      font-weight: 700;
    }

    .user {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 14px;
    }

    .logout {
      border: 1px solid var(--line);
      background: transparent;
      color: var(--text);
      border-radius: 10px;
      padding: 6px 10px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }

    .main { padding: 20px 0 28px; }

    .greet {
      margin-bottom: 14px;
    }

    .greet h1 {
      margin: 0;
      font-size: 42px;
      line-height: 1.08;
      letter-spacing: -0.02em;
    }

    .greet p {
      margin: 5px 0 0;
      color: var(--muted);
      font-size: 14px;
    }

    .flash {
      margin-bottom: 10px;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 14px;
    }

    .flash.ok {
      color: color-mix(in srgb, var(--ok) 83%, var(--text) 17%);
      background: color-mix(in srgb, var(--ok) 18%, var(--card) 82%);
      border-color: color-mix(in srgb, var(--ok) 35%, var(--line) 65%);
    }

    .flash.err {
      color: color-mix(in srgb, var(--err) 86%, var(--text) 14%);
      background: color-mix(in srgb, var(--err) 14%, var(--card) 86%);
      border-color: color-mix(in srgb, var(--err) 36%, var(--line) 64%);
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 12px;
    }

    .kpi {
      grid-column: span 4;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--card);
      padding: 16px;
      min-height: 126px;
    }

    .kpi-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    }

    .kpi-title {
      font-size: 14px;
      color: var(--muted);
    }

    .kpi-icon {
      width: 24px;
      height: 24px;
      border-radius: 8px;
      background: color-mix(in srgb, var(--primary) 16%, transparent);
      color: var(--primary);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      font-weight: 700;
    }

    .kpi-value {
      margin: 0;
      font-size: 38px;
      line-height: 1;
      letter-spacing: -0.03em;
      font-weight: 800;
    }

    .kpi-sub {
      margin-top: 7px;
      color: var(--muted);
      font-size: 13px;
      word-break: break-word;
    }

    .panel {
      grid-column: 1 / -1;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--card);
    }

    .panel-h {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      font-size: 16px;
      line-height: 1;
      font-weight: 700;
      letter-spacing: 0;
      margin: 0;
    }

    .panel-b {
      padding: 14px 16px;
    }

    .device-row {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }

    .device-id {
      font-size: 18px;
      font-weight: 700;
      margin: 0;
      letter-spacing: -0.01em;
      word-break: break-word;
    }

    .device-sub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
      word-break: break-word;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 5px 10px;
      border: 1px solid transparent;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .status.up {
      color: color-mix(in srgb, var(--ok) 88%, #ffffff 12%);
      background: color-mix(in srgb, var(--ok) 18%, transparent);
      border-color: color-mix(in srgb, var(--ok) 35%, var(--line) 65%);
    }

    .status.down {
      color: color-mix(in srgb, var(--err) 88%, #ffffff 12%);
      background: color-mix(in srgb, var(--err) 14%, transparent);
      border-color: color-mix(in srgb, var(--err) 35%, var(--line) 65%);
    }

    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: currentColor;
    }

    .settings-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .settings-wrap {
      grid-column: 1 / -1;
    }

    .settings-details {
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--card);
      overflow: hidden;
    }

    .settings-summary {
      list-style: none;
      cursor: pointer;
      padding: 12px 14px;
      font-size: 13px;
      font-weight: 700;
      color: var(--muted);
      border-bottom: 1px solid transparent;
      user-select: none;
    }

    .settings-summary::-webkit-details-marker { display: none; }

    .settings-details[open] .settings-summary {
      color: var(--text);
      border-bottom-color: var(--line);
    }

    .sub-title {
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 14px;
      font-weight: 600;
    }

    .stack { display: flex; flex-direction: column; gap: 10px; }

    .auth-tabs {
      display: inline-flex;
      gap: 5px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--chip);
      padding: 4px;
    }

    .auth-tab {
      border: 0;
      background: transparent;
      color: var(--muted);
      border-radius: 999px;
      padding: 7px 11px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }

    .auth-tab.active {
      background: color-mix(in srgb, var(--card) 90%, #000000 10%);
      color: var(--text);
      border: 1px solid var(--line);
    }

    .auth-form { display: none; }
    .auth-form.active { display: flex; }

    .field {
      width: 100%;
      border: 1px solid var(--line);
      background: var(--input);
      color: var(--text);
      border-radius: 10px;
      padding: 11px 12px;
      font-size: 14px;
      outline: none;
      transition: border-color .15s ease, box-shadow .15s ease;
    }

    .field:focus {
      border-color: color-mix(in srgb, var(--primary) 68%, var(--line) 32%);
      box-shadow: 0 0 0 3px var(--focus);
    }

    .domain {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
    }

    .suffix {
      border: 1px solid var(--line);
      background: var(--chip);
      color: var(--primary);
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 14px;
      font-weight: 700;
    }

    .btn {
      border-radius: 10px;
      border: 1px solid transparent;
      padding: 10px 14px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
    }

    .btn.primary {
      background: var(--primary);
      color: var(--primary-ink);
      border-color: color-mix(in srgb, var(--primary) 68%, #000000 32%);
    }

    .btn.ghost {
      background: transparent;
      color: var(--text);
      border-color: var(--line);
    }

    .btn:disabled { opacity: .6; cursor: not-allowed; }

    .muted { color: var(--muted); font-size: 13px; }

    @media (max-width: 980px) {
      .kpi { grid-column: span 6; }
      .settings-grid { grid-template-columns: 1fr; }
      .brand { font-size: 15px; }
    }

    @media (max-width: 720px) {
      .container { width: min(1120px, calc(100% - 14px)); }
      .top-inner { min-height: 54px; }
      .brand { font-size: 14px; }
      .brand img { width: 26px; height: 26px; }
      .kpi { grid-column: 1 / -1; }
      .panel-h { font-size: 16px; }
      .greet h1 { font-size: 34px; }
      .domain { grid-template-columns: 1fr; }
      .user { width: 100%; justify-content: flex-end; }
    }
  </style>
</head>
<body>
  <header class="top">
    <div class="container top-inner">
      <div class="brand"><img src="rp-home.svg" alt="RichPear logo" />RichPear Home</div>
      <nav class="nav">
        <span class="nav-item active">Prehled</span>
        <span class="nav-item">Moje zarizeni</span>
        <span class="nav-item">Subdomena</span>
        <span class="nav-item">Ucet</span>
        <span class="nav-item">Fakturacni udaje</span>
      </nav>
      {% if is_logged %}
      <div class="user">
        <span>{{ state.get("email", "") }}</span>
        <form method="post" action="logout" style="margin:0;"><button class="logout" type="submit">Odhlasit</button></form>
      </div>
      {% endif %}
    </div>
  </header>

  <main class="container main">
    <section class="greet">
      <h1>Ahoj, {% if state.get("email") %}{{ state.get("email").split("@")[0] }}{% else %}uzivateli{% endif %} 👋</h1>
      <p>Prehled vaseho uctu a zarizeni.</p>
    </section>

    {% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}
    {% if flash_err %}<div class="flash err">{{ flash_err }}</div>{% endif %}

    <section class="grid">
      <article class="kpi">
        <div class="kpi-head"><span class="kpi-title">Stav uctu</span><span class="kpi-icon">◻</span></div>
        <p class="kpi-value">{% if is_logged %}{{ state.get("plan_status", "active") }}{% else %}guest{% endif %}</p>
        <div class="kpi-sub">{% if state.get("email") %}{{ state.get("email") }}{% else %}—{% endif %}</div>
      </article>
      <article class="kpi">
        <div class="kpi-head"><span class="kpi-title">Zarizeni</span><span class="kpi-icon">⌂</span></div>
        <p class="kpi-value">1</p>
        <div class="kpi-sub">{% if frpc_up %}+1 1 online{% else %}0 online{% endif %}</div>
      </article>
      <article class="kpi">
        <div class="kpi-head"><span class="kpi-title">Subdomena</span><span class="kpi-icon">◎</span></div>
        <p class="kpi-value">{% if state.get("subdomain") %}{{ state.get("subdomain") }}{% else %}—{% endif %}</p>
        <div class="kpi-sub">{% if state.get("full_domain") %}{{ state.get("full_domain") }}{% else %}Nenastavena{% endif %}</div>
      </article>

      <article class="panel">
        <h2 class="panel-h">Moje zarizeni</h2>
        <div class="panel-b">
          <div class="device-row">
            <div>
              <p class="device-id">{{ device_id }}</p>
              <div class="device-sub">Control plane: {{ control_plane_url }}</div>
            </div>
            {% if frpc_up %}<span class="status up"><span class="status-dot"></span>Online</span>{% else %}<span class="status down"><span class="status-dot"></span>Offline</span>{% endif %}
          </div>
        </div>
      </article>

      <article class="settings-wrap">
        <details class="settings-details">
          <summary class="settings-summary">Nastaveni uctu a tunelu</summary>
          <div class="panel-b settings-grid">
            <section class="stack">
              <h3 class="sub-title">Ucet zakaznika</h3>
              {% if is_logged %}
                <div class="flash ok" style="margin:0;">Prihlaseno jako <strong>{{ state.get("email") }}</strong> (plan: {{ state.get("plan_status", "-") }})</div>
              {% else %}
                <div class="auth-tabs">
                  <button type="button" class="auth-tab active" data-auth-tab="login">Prihlaseni</button>
                  <button type="button" class="auth-tab" data-auth-tab="signup">Registrace</button>
                </div>
                <form method="post" action="login" class="auth-form active stack" data-auth-form="login">
                  <input class="field" name="email" type="email" placeholder="E-mail" required />
                  <input class="field" name="password" type="password" placeholder="Heslo" required />
                  <button type="submit" class="btn primary">Prihlasit</button>
                </form>
                <form method="post" action="signup" class="auth-form stack" data-auth-form="signup">
                  <input class="field" name="email" type="email" placeholder="E-mail" required />
                  <input class="field" name="password" type="password" placeholder="Heslo (min 10, pismena + cisla)" required />
                  <button type="submit" class="btn primary">Registrovat</button>
                </form>
              {% endif %}
            </section>

            <section class="stack">
              <h3 class="sub-title">Subdomena a pripojeni</h3>
              <form method="post" action="connect" class="stack">
                <div class="domain">
                  <input class="field" name="subdomain" type="text" placeholder="napr. rphome" value="{{ state.get('subdomain','') }}" required {% if not is_logged %}disabled{% endif %} />
                  <span class="suffix">.cz.richpear.cz</span>
                </div>
                <button type="submit" class="btn primary" {% if not is_logged %}disabled{% endif %}>Pripojit tunel</button>
                {% if not is_logged %}<span class="muted">Nejdriv se registruj nebo prihlas.</span>{% endif %}
              </form>
              <form method="post" action="restart" style="margin-top:8px;"><button type="submit" class="btn ghost">Restart tunelu</button></form>
            </section>
          </div>
        </details>
      </article>
    </section>
  </main>

  <script>
    (function () {
      var tabs = document.querySelectorAll('[data-auth-tab]');
      var forms = document.querySelectorAll('[data-auth-form]');
      function setMode(mode) {
        tabs.forEach(function (tab) { tab.classList.toggle('active', tab.getAttribute('data-auth-tab') === mode); });
        forms.forEach(function (form) { form.classList.toggle('active', form.getAttribute('data-auth-form') === mode); });
      }
      tabs.forEach(function (tab) { tab.addEventListener('click', function () { setMode(tab.getAttribute('data-auth-tab')); }); });

      var THEME_VARS = [
        '--primary-background-color', '--secondary-background-color', '--card-background-color',
        '--divider-color', '--primary-text-color', '--secondary-text-color', '--primary-color',
        '--text-primary-color', '--success-color', '--error-color'
      ];

      function firstNonEmptyVar(el, name) {
        if (!el) return '';
        var v = getComputedStyle(el).getPropertyValue(name);
        return (v || '').trim();
      }

      function resolveThemeSource(doc) {
        if (!doc) return null;
        var candidates = [doc.querySelector('home-assistant'), doc.documentElement, doc.body];
        for (var i = 0; i < candidates.length; i++) {
          var el = candidates[i];
          if (!el) continue;
          if (firstNonEmptyVar(el, '--primary-background-color')) return el;
        }
        return doc.documentElement || null;
      }

      function syncThemeFromParent() {
        try {
          var pdoc = window.parent && window.parent.document ? window.parent.document : document;
          var src = resolveThemeSource(pdoc);
          if (!src) return;
          THEME_VARS.forEach(function (name) {
            var val = firstNonEmptyVar(src, name);
            if (val) document.documentElement.style.setProperty(name, val);
          });
        } catch (e) {
          // Keep local fallback palette when parent theme cannot be accessed.
        }
      }

      syncThemeFromParent();
      setInterval(syncThemeFromParent, 1200);
    })();
  </script>
</body>
</html>
        """,
        state=state,
        control_plane_url=CONTROL_PLANE_URL,
        device_id=load_device_id(),
        frpc_up=frpc_running(),
        is_logged=is_logged,
        flash_ok=request.args.get("ok", ""),
        flash_err=request.args.get("err", ""),
    )


@APP.post("/signup")
def signup():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    code, data = api_post("/api/v2/public/signup", {"email": email, "password": password})
    if code != 200:
        return ingress_redirect(err=data.get("detail", f"Signup failed ({code})"))
    state = load_state()
    state["email"] = data.get("email", email)
    state["access_token"] = data.get("access_token", "")
    state["plan_status"] = data.get("plan_status", "trial")
    save_state(state)
    return ingress_redirect(ok="Ucet vytvoren a prihlasen")


@APP.post("/login")
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    code, data = api_post("/api/v2/public/login", {"email": email, "password": password})
    if code != 200:
        return ingress_redirect(err=data.get("detail", f"Login failed ({code})"))
    state = load_state()
    state["email"] = data.get("email", email)
    state["access_token"] = data.get("access_token", "")
    state["plan_status"] = data.get("plan_status", "trial")
    save_state(state)
    return ingress_redirect(ok="Prihlaseni probehlo uspesne")


@APP.post("/logout")
def logout():
    state = load_state()
    state.pop("access_token", None)
    state.pop("plan_status", None)
    save_state(state)
    return ingress_redirect(ok="Odhlaseni probehlo uspesne")


@APP.post("/connect")
def connect():
    subdomain = request.form.get("subdomain", "").strip().lower()
    state = load_state()
    token = state.get("access_token", "")
    if not token:
        return ingress_redirect(err="Nejdriv se prihlas nebo zaregistruj")
    payload = {
        "device_id": load_device_id(),
        "subdomain": subdomain,
        "public_key": load_public_key(),
    }
    code, data = api_post("/api/v2/public/devices/claim", payload, bearer_token=token)
    if code != 200:
        return ingress_redirect(err=data.get("detail", f"Connect failed ({code})"))

    write_frpc_config(
        subdomain=subdomain,
        frp_server=str(data.get("frp_server", "")),
        frp_port=int(data.get("frp_port", 7000)),
        frp_token=str(data.get("frp_token", "")),
    )
    restart_frpc()
    state["subdomain"] = subdomain
    state["full_domain"] = data.get("full_domain", "")
    save_state(state)
    return ingress_redirect(ok=f"Tunel aktivni: {state.get('full_domain','')}")


@APP.post("/restart")
def restart():
    if Path(FRPC_CONFIG).exists():
        restart_frpc()
        return ingress_redirect(ok="Tunel restartovan")
    return ingress_redirect(err="Konfigurace tunelu zatim neexistuje")


if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=8099)
