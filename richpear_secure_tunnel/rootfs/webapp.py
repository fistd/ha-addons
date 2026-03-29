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
      --bg-main: var(--primary-background-color, #0c1017);
      --card: var(--card-background-color, #181b22);
      --line: var(--divider-color, #2a313d);
      --text: var(--primary-text-color, #f2f5fa);
      --muted: var(--secondary-text-color, #9ba4b4);
      --primary: var(--primary-color, #17a864);
      --primary-ink: var(--text-primary-color, #e7f7ee);
      --ok: var(--success-color, #2bbf67);
      --err: var(--error-color, #e24f4f);
      --chip-bg: color-mix(in srgb, var(--card) 80%, #111827 20%);
      --input-bg: color-mix(in srgb, var(--card) 90%, #0f131a 10%);
      --focus: color-mix(in srgb, var(--primary) 34%, transparent);
    }

    @media (prefers-color-scheme: light) {
      :root {
        --bg-main: var(--primary-background-color, #f3f6fb);
        --card: var(--card-background-color, #ffffff);
        --line: var(--divider-color, #d7deea);
        --text: var(--primary-text-color, #0f172a);
        --muted: var(--secondary-text-color, #5f6b7d);
        --primary: var(--primary-color, #138d5e);
        --primary-ink: var(--text-primary-color, #ffffff);
        --chip-bg: color-mix(in srgb, var(--card) 56%, #edf2f8 44%);
        --input-bg: color-mix(in srgb, var(--card) 88%, #edf3fb 12%);
      }
    }

    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 12% 0%, color-mix(in srgb, var(--primary) 12%, transparent), transparent 28%),
        linear-gradient(180deg, var(--bg-main), color-mix(in srgb, var(--bg-main) 80%, #070b12 20%));
    }

    .topbar {
      position: sticky;
      top: 0;
      z-index: 20;
      backdrop-filter: blur(8px);
      background: color-mix(in srgb, var(--card) 92%, transparent);
      border-bottom: 1px solid var(--line);
    }

    .container {
      width: min(1280px, calc(100% - 22px));
      margin: 0 auto;
    }

    .topbar-inner {
      min-height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
      padding: 10px 0;
    }

    .brand {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      text-decoration: none;
      color: var(--text);
      font-weight: 700;
      font-size: 18px;
    }

    .brand-logo {
      width: 30px;
      height: 30px;
      object-fit: contain;
      display: block;
      border-radius: 6px;
    }

    .nav {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .nav-item {
      padding: 7px 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--chip-bg);
      color: var(--muted);
      font-size: 14px;
      line-height: 1;
    }

    .nav-item.active {
      background: color-mix(in srgb, var(--primary) 20%, var(--card) 80%);
      border-color: color-mix(in srgb, var(--primary) 45%, var(--line) 55%);
      color: var(--primary);
      font-weight: 600;
    }

    .user-box {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 14px;
    }

    .logout-btn {
      border: 1px solid var(--line);
      background: transparent;
      color: var(--text);
      border-radius: 10px;
      padding: 7px 11px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }

    .page {
      padding: 24px 0 30px;
    }

    h1 {
      margin: 0;
      font-size: clamp(35px, 4.2vw, 56px);
      line-height: 1.03;
      letter-spacing: -0.03em;
      font-weight: 800;
    }

    .subtitle {
      margin: 8px 0 18px;
      color: var(--muted);
      font-size: 34px;
      line-height: 1.08;
      letter-spacing: -0.02em;
      font-weight: 700;
    }

    .grid {
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(12, minmax(0, 1fr));
    }

    .card {
      grid-column: span 4;
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 18px;
      padding: 20px;
      min-height: 150px;
    }

    .label {
      color: var(--muted);
      font-size: 34px;
      line-height: 1.05;
      font-weight: 650;
      letter-spacing: -0.02em;
      margin-bottom: 14px;
      display: block;
    }

    .kpi {
      font-size: 52px;
      line-height: 1;
      letter-spacing: -0.035em;
      font-weight: 800;
      margin: 0;
    }

    .kpi-sm {
      font-size: 44px;
      line-height: 1;
      letter-spacing: -0.03em;
      font-weight: 800;
      margin: 0;
      word-break: break-word;
    }

    .sub {
      color: var(--muted);
      font-size: 28px;
      line-height: 1.12;
      margin-top: 10px;
      word-break: break-word;
    }

    .panel {
      grid-column: 1 / -1;
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 18px;
      padding: 20px;
    }

    .panel-title {
      margin: 0 0 14px;
      font-size: 50px;
      line-height: 1;
      letter-spacing: -0.03em;
      font-weight: 800;
    }

    .device-row {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 86px;
    }

    .device-id {
      font-size: 36px;
      line-height: 1.06;
      font-weight: 780;
      letter-spacing: -0.02em;
      margin: 0;
      word-break: break-word;
    }

    .device-sub {
      color: var(--muted);
      font-size: 29px;
      line-height: 1.1;
      margin-top: 6px;
      word-break: break-word;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      border: 1px solid transparent;
      font-size: 30px;
      line-height: 1;
      font-weight: 700;
      padding: 10px 18px;
      white-space: nowrap;
    }

    .status-pill.up {
      background: color-mix(in srgb, var(--ok) 18%, transparent);
      border-color: color-mix(in srgb, var(--ok) 40%, var(--line) 60%);
      color: color-mix(in srgb, var(--ok) 88%, #ffffff 12%);
    }

    .status-pill.down {
      background: color-mix(in srgb, var(--err) 16%, transparent);
      border-color: color-mix(in srgb, var(--err) 36%, var(--line) 64%);
      color: color-mix(in srgb, var(--err) 90%, #ffffff 10%);
    }

    .dot {
      width: 14px;
      height: 14px;
      border-radius: 999px;
      background: currentColor;
    }

    .flash {
      border-radius: 12px;
      border: 1px solid var(--line);
      padding: 14px 16px;
      font-size: 31px;
      line-height: 1.08;
      margin-bottom: 14px;
    }

    .flash.ok {
      color: color-mix(in srgb, var(--ok) 82%, var(--text) 18%);
      background: color-mix(in srgb, var(--ok) 18%, var(--card) 82%);
      border-color: color-mix(in srgb, var(--ok) 35%, var(--line) 65%);
    }

    .flash.err {
      color: color-mix(in srgb, var(--err) 84%, var(--text) 16%);
      background: color-mix(in srgb, var(--err) 14%, var(--card) 86%);
      border-color: color-mix(in srgb, var(--err) 34%, var(--line) 66%);
    }

    .setting-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .stack {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .auth-tabs {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--chip-bg);
      padding: 5px;
      margin-bottom: 8px;
    }

    .auth-tab {
      border: 0;
      background: transparent;
      color: var(--muted);
      font-size: 26px;
      line-height: 1;
      border-radius: 999px;
      padding: 8px 14px;
      font-weight: 650;
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
      background: var(--input-bg);
      color: var(--text);
      border-radius: 12px;
      padding: 12px 14px;
      font-size: 30px;
      line-height: 1.1;
      outline: none;
      transition: border-color .15s ease, box-shadow .15s ease;
    }

    .field::placeholder { color: color-mix(in srgb, var(--muted) 88%, transparent); }

    .field:focus {
      border-color: color-mix(in srgb, var(--primary) 70%, var(--line) 30%);
      box-shadow: 0 0 0 4px var(--focus);
    }

    .domain-wrap {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
    }

    .domain-suffix {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 11px 14px;
      background: var(--chip-bg);
      color: var(--primary);
      font-size: 31px;
      line-height: 1;
      font-weight: 700;
      white-space: nowrap;
    }

    .btn {
      border: 1px solid transparent;
      border-radius: 12px;
      padding: 13px 16px;
      font-size: 34px;
      line-height: 1;
      font-weight: 750;
      cursor: pointer;
      transition: filter .15s ease;
    }

    .btn:hover { filter: brightness(1.05); }
    .btn:disabled { opacity: 0.6; cursor: not-allowed; }

    .btn.primary {
      background: var(--primary);
      color: var(--primary-ink);
      border-color: color-mix(in srgb, var(--primary) 70%, #000000 30%);
    }

    .btn.secondary {
      background: transparent;
      color: var(--text);
      border-color: var(--line);
    }

    .muted {
      color: var(--muted);
      font-size: 26px;
      line-height: 1.1;
    }

    @media (max-width: 1300px) {
      .label { font-size: 20px; }
      .kpi { font-size: 34px; }
      .kpi-sm { font-size: 32px; }
      .sub { font-size: 18px; }
      .panel-title { font-size: 42px; }
      .device-id { font-size: 30px; }
      .device-sub { font-size: 18px; }
      .status-pill { font-size: 20px; }
      .flash { font-size: 18px; }
      .auth-tab { font-size: 16px; }
      .field { font-size: 18px; }
      .btn { font-size: 24px; }
      .domain-suffix { font-size: 19px; }
      .muted { font-size: 15px; }
      .subtitle { font-size: 26px; }
    }

    @media (max-width: 980px) {
      .card { grid-column: span 6; }
      .setting-grid { grid-template-columns: 1fr; }
      .panel-title { font-size: 34px; }
    }

    @media (max-width: 700px) {
      .container { width: min(1280px, calc(100% - 12px)); }
      .topbar-inner { min-height: 56px; }
      .brand { font-size: 15px; }
      .brand-logo { width: 24px; height: 24px; }
      .nav-item { font-size: 12px; padding: 6px 10px; }
      h1 { font-size: clamp(26px, 10vw, 44px); }
      .subtitle { font-size: 18px; }
      .card, .panel { padding: 14px; border-radius: 14px; }
      .card { grid-column: 1 / -1; min-height: 120px; }
      .label { font-size: 18px; margin-bottom: 8px; }
      .kpi { font-size: 30px; }
      .kpi-sm { font-size: 28px; }
      .sub { font-size: 16px; }
      .panel-title { font-size: 30px; }
      .device-id { font-size: 22px; }
      .device-sub { font-size: 15px; }
      .status-pill { font-size: 16px; padding: 8px 12px; }
      .dot { width: 10px; height: 10px; }
      .flash { font-size: 16px; }
      .field { font-size: 16px; padding: 10px 12px; }
      .btn { font-size: 20px; }
      .domain-suffix { font-size: 15px; }
      .domain-wrap { grid-template-columns: 1fr; }
      .muted { font-size: 14px; }
      .user-box { width: 100%; justify-content: flex-end; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="container topbar-inner">
      <div class="brand">
        <img src="rp-home.svg" alt="RichPear logo" class="brand-logo" />
        <span>RichPear Home</span>
      </div>
      <nav class="nav">
        <span class="nav-item active">Prehled</span>
        <span class="nav-item">Moje zarizeni</span>
        <span class="nav-item">Subdomena</span>
        <span class="nav-item">Ucet</span>
      </nav>
      {% if is_logged %}
      <div class="user-box">
        <span>{{ state.get("email", "") }}</span>
        <form method="post" action="logout" style="margin:0;">
          <button type="submit" class="logout-btn">Odhlasit</button>
        </form>
      </div>
      {% endif %}
    </div>
  </header>

  <main class="container page">
    <h1>RichPear Secure Tunnel</h1>
    <p class="subtitle">Nastaveni pristupu z Home Assistanta do internetu.</p>

    {% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}
    {% if flash_err %}<div class="flash err">{{ flash_err }}</div>{% endif %}

    <section class="grid">
      <article class="card">
        <span class="label">Stav uctu</span>
        <p class="kpi-sm">{% if is_logged %}{{ state.get("plan_status", "active") }}{% else %}neprihlasen{% endif %}</p>
        <div class="sub">{% if state.get("email") %}{{ state.get("email") }}{% else %}-{% endif %}</div>
      </article>
      <article class="card">
        <span class="label">Zarizeni</span>
        <p class="kpi">1</p>
        <div class="sub">Home Assistant</div>
      </article>
      <article class="card">
        <span class="label">Subdomena</span>
        <p class="kpi-sm">{% if state.get("subdomain") %}{{ state.get("subdomain") }}{% else %}-{% endif %}</p>
        <div class="sub">{% if state.get("full_domain") %}https://{{ state.get("full_domain") }}{% else %}Nenastavena{% endif %}</div>
      </article>

      <article class="panel">
        <h2 class="panel-title">Moje zarizeni</h2>
        <div class="device-row">
          <div>
            <p class="device-id">{{ device_id }}</p>
            <div class="device-sub">Control plane: {{ control_plane_url }}</div>
          </div>
          {% if frpc_up %}
            <span class="status-pill up"><span class="dot"></span>Online</span>
          {% else %}
            <span class="status-pill down"><span class="dot"></span>Offline</span>
          {% endif %}
        </div>
      </article>

      <article class="panel">
        <h2 class="panel-title">Nastaveni uctu a tunelu</h2>
        <div class="setting-grid">
          <section class="stack">
            <span class="label">Ucet zakaznika</span>
            {% if is_logged %}
              <div class="flash ok">Prihlaseno jako <strong>{{ state.get("email") }}</strong> (plan: {{ state.get("plan_status", "-") }})</div>
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
            <span class="label">Subdomena a pripojeni</span>
            <form method="post" action="connect" class="stack">
              <div class="domain-wrap">
                <input class="field" name="subdomain" type="text" placeholder="napr. rphome" value="{{ state.get('subdomain','') }}" required {% if not is_logged %}disabled{% endif %} />
                <span class="domain-suffix">.cz.richpear.cz</span>
              </div>
              <button type="submit" class="btn primary" {% if not is_logged %}disabled{% endif %}>Pripojit tunel</button>
              {% if not is_logged %}<span class="muted">Nejdriv se registruj nebo prihlas.</span>{% endif %}
            </form>
            <form method="post" action="restart" style="margin-top:8px;">
              <button type="submit" class="btn secondary">Restart tunelu</button>
            </form>
          </section>
        </div>
      </article>
    </section>
  </main>

  <script>
    (function () {
      var tabs = document.querySelectorAll('[data-auth-tab]');
      var forms = document.querySelectorAll('[data-auth-form]');

      function setMode(mode) {
        tabs.forEach(function (tab) {
          tab.classList.toggle('active', tab.getAttribute('data-auth-tab') === mode);
        });
        forms.forEach(function (form) {
          form.classList.toggle('active', form.getAttribute('data-auth-form') === mode);
        });
      }

      tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
          setMode(tab.getAttribute('data-auth-tab'));
        });
      });

      var THEME_VARS = [
        '--primary-background-color',
        '--secondary-background-color',
        '--card-background-color',
        '--divider-color',
        '--primary-text-color',
        '--secondary-text-color',
        '--primary-color',
        '--text-primary-color',
        '--success-color',
        '--error-color'
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
