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
    Path(STATE_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


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
    email = str(state.get("email", ""))
    username = email.split("@")[0] if "@" in email else "uživateli"
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
      z-index: 20;
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

    .main { padding: 20px 0 28px; }

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

    .auth-layout {
      min-height: calc(100vh - 120px);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 18px 0;
    }

    .auth-card {
      width: min(460px, 100%);
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--card);
      padding: 18px;
    }

    .auth-head {
      text-align: center;
      margin-bottom: 16px;
    }

    .auth-head img {
      width: 48px;
      height: 48px;
      object-fit: contain;
      margin-bottom: 8px;
    }

    .auth-head h1 {
      margin: 0;
      font-size: 24px;
      line-height: 1.1;
    }

    .auth-head p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
    }

    .auth-tabs {
      display: inline-flex;
      gap: 5px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--chip);
      padding: 4px;
      margin: 0 auto 14px;
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
    .auth-form.active { display: flex; flex-direction: column; gap: 10px; }

    .stack { display: flex; flex-direction: column; gap: 10px; }

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

    .help {
      color: var(--muted);
      font-size: 13px;
      text-align: center;
      margin-top: 10px;
    }

    .nav {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }

    .nav-item {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      background: var(--chip);
      color: var(--muted);
      border-radius: 999px;
      padding: 6px 11px;
      font-size: 13px;
      line-height: 1;
      white-space: nowrap;
      text-decoration: none;
      cursor: pointer;
      transition: background .15s ease, color .15s ease, border-color .15s ease;
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

    .greet {
      margin-bottom: 14px;
    }

    .greet h1 {
      margin: 0;
      font-size: 36px;
      line-height: 1.08;
      letter-spacing: -0.02em;
    }

    .greet p {
      margin: 5px 0 0;
      color: var(--muted);
      font-size: 14px;
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
      text-decoration: none;
      color: inherit;
    }

    .kpi:hover {
      border-color: color-mix(in srgb, var(--primary) 38%, var(--line) 62%);
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

    .section {
      grid-column: 1 / -1;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--card);
      display: none;
    }

    .section.active { display: block; }

    .section-h {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      font-size: 16px;
      line-height: 1;
      font-weight: 700;
      margin: 0;
    }

    .section-b {
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

    .sub-title {
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 14px;
      font-weight: 600;
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

    .muted {
      color: var(--muted);
      font-size: 13px;
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .meta-item {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      background: color-mix(in srgb, var(--card) 90%, transparent);
    }

    .meta-item strong {
      display: block;
      font-size: 14px;
      margin-bottom: 4px;
    }

    @media (max-width: 980px) {
      .kpi { grid-column: span 6; }
      .settings-grid, .meta-grid { grid-template-columns: 1fr; }
      .brand { font-size: 15px; }
    }

    @media (max-width: 720px) {
      .container { width: min(1120px, calc(100% - 14px)); }
      .top-inner { min-height: 54px; }
      .brand { font-size: 14px; }
      .brand img { width: 26px; height: 26px; }
      .kpi { grid-column: 1 / -1; }
      .greet h1 { font-size: 30px; }
      .domain { grid-template-columns: 1fr; }
      .user { width: 100%; justify-content: flex-end; }
    }
  </style>
</head>
<body>
  {% if not is_logged %}
  <header class="top">
    <div class="container top-inner">
      <div class="brand"><img src="rp-home.svg" alt="RichPear logo" />RichPear Home</div>
    </div>
  </header>

  <main class="container main">
    {% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}
    {% if flash_err %}<div class="flash err">{{ flash_err }}</div>{% endif %}

    <section class="auth-layout">
      <article class="auth-card">
        <div class="auth-head">
          <img src="rp-home.svg" alt="RichPear logo" />
          <h1>RichPear Home</h1>
          <p>Přihlaste se nebo si vytvořte účet.</p>
        </div>

        <div style="text-align:center;">
          <div class="auth-tabs">
            <button type="button" class="auth-tab active" data-auth-tab="login">Přihlášení</button>
            <button type="button" class="auth-tab" data-auth-tab="signup">Registrace</button>
          </div>
        </div>

        <form method="post" action="login" class="auth-form active" data-auth-form="login">
          <input class="field" name="email" type="email" placeholder="E-mail" required />
          <input class="field" name="password" type="password" placeholder="Heslo" required />
          <button type="submit" class="btn primary">Přihlásit se</button>
        </form>

        <form method="post" action="signup" class="auth-form" data-auth-form="signup">
          <input class="field" name="email" type="email" placeholder="E-mail" required />
          <input class="field" name="password" type="password" placeholder="Heslo (min. 10, písmena + čísla)" required />
          <button type="submit" class="btn primary">Registrovat se</button>
        </form>

        <p class="help">Po přihlášení se otevře klientský dashboard addonu.</p>
      </article>
    </section>
  </main>

  {% else %}
  <header class="top">
    <div class="container top-inner">
      <div class="brand"><img src="rp-home.svg" alt="RichPear logo" />RichPear Home</div>
      <nav class="nav">
        <a class="nav-item active" href="#" data-nav="overview">Přehled</a>
        <a class="nav-item" href="#" data-nav="devices">Moje zařízení</a>
        <a class="nav-item" href="#" data-nav="subdomain">Subdoména</a>
        <a class="nav-item" href="#" data-nav="account">Účet</a>
        <a class="nav-item" href="#" data-nav="billing">Fakturační údaje</a>
      </nav>
      <div class="user">
        <span>{{ state.get("email", "") }}</span>
        <form method="post" action="logout" style="margin:0;"><button class="logout" type="submit">Odhlásit</button></form>
      </div>
    </div>
  </header>

  <main class="container main">
    {% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}
    {% if flash_err %}<div class="flash err">{{ flash_err }}</div>{% endif %}

    <section class="greet">
      <h1>Ahoj, {{ username }} 👋</h1>
      <p>Přehled vašeho účtu a zařízení.</p>
    </section>

    <section class="grid" id="overview-section">
      <a class="kpi" href="#" data-goto="account">
        <div class="kpi-head"><span class="kpi-title">Stav účtu</span><span class="kpi-icon">◻</span></div>
        <p class="kpi-value">{{ state.get("plan_status", "active") }}</p>
        <div class="kpi-sub">{{ state.get("email", "—") }}</div>
      </a>

      <a class="kpi" href="#" data-goto="devices">
        <div class="kpi-head"><span class="kpi-title">Zařízení</span><span class="kpi-icon">⌂</span></div>
        <p class="kpi-value">1</p>
        <div class="kpi-sub">{% if frpc_up %}1 online{% else %}0 online{% endif %}</div>
      </a>

      <a class="kpi" href="#" data-goto="subdomain">
        <div class="kpi-head"><span class="kpi-title">Subdoména</span><span class="kpi-icon">◎</span></div>
        <p class="kpi-value">{% if state.get("subdomain") %}{{ state.get("subdomain") }}{% else %}—{% endif %}</p>
        <div class="kpi-sub">{% if state.get("full_domain") %}{{ state.get("full_domain") }}{% else %}Nenastavená{% endif %}</div>
      </a>

      <article class="section active" id="section-devices" data-section="devices">
        <h2 class="section-h">Moje zařízení</h2>
        <div class="section-b">
          <div class="device-row">
            <div>
              <p class="device-id">{{ device_id }}</p>
              <div class="device-sub">Control plane: {{ control_plane_url }}</div>
              <div class="device-sub">Poslední aktivita: {{ now }}</div>
            </div>
            {% if frpc_up %}<span class="status up"><span class="status-dot"></span>Online</span>{% else %}<span class="status down"><span class="status-dot"></span>Offline</span>{% endif %}
          </div>
        </div>
      </article>

      <article class="section" id="section-subdomain" data-section="subdomain">
        <h2 class="section-h">Subdoména</h2>
        <div class="section-b settings-grid">
          <section class="stack">
            <h3 class="sub-title">Subdoména a připojení</h3>
            <form method="post" action="connect" class="stack">
              <div class="domain">
                <input id="subdomain-input" class="field" name="subdomain" type="text" placeholder="např. rphome" value="{{ state.get('subdomain','') }}" required />
                <span class="suffix">.cz.richpear.cz</span>
              </div>
              <button type="submit" class="btn primary">Připojit tunel</button>
            </form>
            <form method="post" action="restart" style="margin-top:8px;"><button type="submit" class="btn ghost">Restart tunelu</button></form>
          </section>
          <section class="stack">
            <h3 class="sub-title">Aktuální stav</h3>
            <div class="meta-item"><strong>Plná doména</strong>{% if state.get("full_domain") %}{{ state.get("full_domain") }}{% else %}Nenastavená{% endif %}</div>
            <div class="meta-item"><strong>Proxy</strong>{% if frpc_up %}Běží{% else %}Neběží{% endif %}</div>
          </section>
        </div>
      </article>

      <article class="section" id="section-account" data-section="account">
        <h2 class="section-h">Účet</h2>
        <div class="section-b meta-grid">
          <div class="meta-item"><strong>E-mail</strong>{{ state.get("email", "—") }}</div>
          <div class="meta-item"><strong>Plán</strong>{{ state.get("plan_status", "active") }}</div>
          <div class="meta-item"><strong>Device ID</strong>{{ device_id }}</div>
          <div class="meta-item"><strong>Control plane</strong>{{ control_plane_url }}</div>
        </div>
      </article>

      <article class="section" id="section-billing" data-section="billing">
        <h2 class="section-h">Fakturační údaje</h2>
        <div class="section-b meta-grid">
          <div class="meta-item"><strong>Stav fakturace</strong>Manuální správa (zatím)</div>
          <div class="meta-item"><strong>Plán</strong>{{ state.get("plan_status", "active") }}</div>
          <div class="meta-item"><strong>Stripe</strong>Bude přidáno později</div>
          <div class="meta-item"><strong>Poznámka</strong>Údaje doplníme v klientském portálu</div>
        </div>
      </article>
    </section>
  </main>
  {% endif %}

  <script>
    (function () {
      var tabs = document.querySelectorAll('[data-auth-tab]');
      var forms = document.querySelectorAll('[data-auth-form]');
      function setMode(mode) {
        tabs.forEach(function (tab) { tab.classList.toggle('active', tab.getAttribute('data-auth-tab') === mode); });
        forms.forEach(function (form) { form.classList.toggle('active', form.getAttribute('data-auth-form') === mode); });
      }
      tabs.forEach(function (tab) { tab.addEventListener('click', function () { setMode(tab.getAttribute('data-auth-tab')); }); });

      var navItems = Array.prototype.slice.call(document.querySelectorAll('[data-nav]'));
      var sections = Array.prototype.slice.call(document.querySelectorAll('[data-section]'));
      var gotoCards = Array.prototype.slice.call(document.querySelectorAll('[data-goto]'));
      var subdomainInput = document.getElementById('subdomain-input');

      function showSection(name) {
        if (!sections.length || !navItems.length) return;
        sections.forEach(function (section) {
          section.classList.toggle('active', section.getAttribute('data-section') === name);
        });
        navItems.forEach(function (item) {
          item.classList.toggle('active', item.getAttribute('data-nav') === name || (name === 'devices' && item.getAttribute('data-nav') === 'overview'));
        });
        if (name === 'subdomain' && subdomainInput) {
          setTimeout(function () { subdomainInput.focus(); }, 120);
        }
      }

      navItems.forEach(function (item) {
        item.addEventListener('click', function (e) {
          e.preventDefault();
          var name = item.getAttribute('data-nav');
          if (name === 'overview') {
            showSection('devices');
            return;
          }
          showSection(name);
        });
      });

      gotoCards.forEach(function (card) {
        card.addEventListener('click', function (e) {
          e.preventDefault();
          var target = card.getAttribute('data-goto');
          showSection(target);
        });
      });

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
        is_logged=is_logged,
        control_plane_url=CONTROL_PLANE_URL,
        device_id=load_device_id(),
        frpc_up=frpc_running(),
        flash_ok=request.args.get("ok", ""),
        flash_err=request.args.get("err", ""),
        username=username,
        now=__import__("datetime").datetime.now().strftime("%d. %m. %Y %H:%M:%S"),
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
    return ingress_redirect(ok="Účet vytvořen a přihlášen")


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
    return ingress_redirect(ok="Přihlášení proběhlo úspěšně")


@APP.post("/logout")
def logout():
    state = load_state()
    state.pop("access_token", None)
    state.pop("plan_status", None)
    save_state(state)
    return ingress_redirect(ok="Odhlášení proběhlo úspěšně")


@APP.post("/connect")
def connect():
    subdomain = request.form.get("subdomain", "").strip().lower()
    state = load_state()
    token = state.get("access_token", "")
    if not token:
        return ingress_redirect(err="Nejdřív se přihlas nebo zaregistruj")
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
    return ingress_redirect(ok=f"Tunel aktivní: {state.get('full_domain','')}")


@APP.post("/restart")
def restart():
    if Path(FRPC_CONFIG).exists():
        restart_frpc()
        return ingress_redirect(ok="Tunel restartován")
    return ingress_redirect(err="Konfigurace tunelu zatím neexistuje")


if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=8099)
