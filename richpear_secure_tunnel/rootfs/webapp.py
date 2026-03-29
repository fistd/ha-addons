#!/usr/bin/env python3
import json
import os
import subprocess
import urllib.error
import urllib.request
import urllib.parse
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
      --bg-main: var(--primary-background-color, #0a1020);
      --bg-elev: var(--secondary-background-color, #111827);
      --card: var(--card-background-color, #141c2f);
      --line: var(--divider-color, #2a3450);
      --text: var(--primary-text-color, #e8edf7);
      --muted: var(--secondary-text-color, #a8b4cd);
      --primary: var(--primary-color, #19c37d);
      --primary-ink: var(--text-primary-color, #03130d);
      --ok: var(--success-color, #24c881);
      --err: var(--error-color, #ef5350);
      --focus: color-mix(in srgb, var(--primary) 35%, transparent);
      --chip: color-mix(in srgb, var(--card) 78%, var(--bg-elev) 22%);
      --shadow: 0 20px 45px rgba(2, 7, 20, 0.36);
    }

    @media (prefers-color-scheme: light) {
      :root {
        --bg-main: var(--primary-background-color, #f3f6fb);
        --bg-elev: var(--secondary-background-color, #ebf0f8);
        --card: var(--card-background-color, #ffffff);
        --line: var(--divider-color, #d8e1ee);
        --text: var(--primary-text-color, #101829);
        --muted: var(--secondary-text-color, #5b6b85);
        --primary: var(--primary-color, #0f8b5f);
        --primary-ink: var(--text-primary-color, #ffffff);
        --chip: color-mix(in srgb, var(--card) 55%, var(--bg-elev) 45%);
        --shadow: 0 18px 35px rgba(15, 32, 66, 0.12);
      }
    }

    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 12% -10%, color-mix(in srgb, var(--primary) 13%, transparent), transparent 38%),
        radial-gradient(circle at 90% 105%, color-mix(in srgb, var(--primary) 10%, transparent), transparent 35%),
        linear-gradient(180deg, var(--bg-main), color-mix(in srgb, var(--bg-main) 76%, #000000 24%));
      padding: 20px 14px 28px;
    }

    .shell {
      max-width: 1080px;
      margin: 0 auto;
    }

    .topbar {
      border: 1px solid var(--line);
      border-radius: 14px;
      background: color-mix(in srgb, var(--card) 94%, var(--bg-elev) 6%);
      box-shadow: var(--shadow);
      padding: 12px 16px;
      display: flex;
      gap: 14px;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }

    .brand {
      display: inline-flex;
      gap: 10px;
      align-items: center;
      font-weight: 700;
      letter-spacing: 0.2px;
    }

    .brand-logo {
      width: 28px;
      height: 28px;
      object-fit: contain;
      flex: 0 0 auto;
    }

    .nav {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .nav-item {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      color: var(--muted);
      background: var(--chip);
    }

    .hero {
      margin-bottom: 12px;
    }

    .hero h1 {
      margin: 0;
      font-size: clamp(24px, 3.5vw, 34px);
      line-height: 1.1;
      letter-spacing: -0.02em;
    }

    .hero p {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 14px;
    }

    .grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(12, minmax(0, 1fr));
    }

    .card {
      background: color-mix(in srgb, var(--card) 96%, var(--bg-elev) 4%);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: var(--shadow);
      padding: 16px;
    }

    .kpi { grid-column: span 4; min-height: 118px; }
    .panel { grid-column: 1 / -1; }

    .label {
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 10px;
      display: block;
    }

    .value {
      font-size: 33px;
      line-height: 1;
      font-weight: 700;
      letter-spacing: -0.02em;
    }

    .value-sm {
      font-size: 20px;
      line-height: 1.2;
      font-weight: 700;
      word-break: break-word;
    }

    .sub {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid transparent;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
    }

    .up {
      color: color-mix(in srgb, var(--ok) 92%, #ffffff 8%);
      background: color-mix(in srgb, var(--ok) 20%, transparent);
      border-color: color-mix(in srgb, var(--ok) 40%, var(--line) 60%);
    }

    .down {
      color: color-mix(in srgb, var(--err) 92%, #ffffff 8%);
      background: color-mix(in srgb, var(--err) 16%, transparent);
      border-color: color-mix(in srgb, var(--err) 34%, var(--line) 66%);
    }

    .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }

    .flash {
      margin-bottom: 12px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      font-size: 14px;
      box-shadow: var(--shadow);
    }

    .flash.ok {
      color: color-mix(in srgb, var(--ok) 85%, var(--text) 15%);
      background: color-mix(in srgb, var(--ok) 18%, var(--card) 82%);
      border-color: color-mix(in srgb, var(--ok) 34%, var(--line) 66%);
    }

    .flash.err {
      color: color-mix(in srgb, var(--err) 88%, var(--text) 12%);
      background: color-mix(in srgb, var(--err) 14%, var(--card) 86%);
      border-color: color-mix(in srgb, var(--err) 34%, var(--line) 66%);
    }

    .stack { display: flex; flex-direction: column; gap: 10px; }

    .auth-tabs {
      display: inline-flex;
      gap: 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px;
      background: var(--chip);
      margin-bottom: 10px;
    }

    .auth-tab {
      border: 0;
      background: transparent;
      color: var(--muted);
      border-radius: 999px;
      padding: 7px 12px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }

    .auth-tab.active {
      color: var(--text);
      background: color-mix(in srgb, var(--card) 90%, var(--bg-elev) 10%);
      border: 1px solid var(--line);
    }

    .auth-form { display: none; }
    .auth-form.active { display: block; }

    .field {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: color-mix(in srgb, var(--card) 74%, var(--bg-elev) 26%);
      color: var(--text);
      padding: 11px 12px;
      font-size: 14px;
      outline: none;
      transition: border-color .15s ease, box-shadow .15s ease;
    }

    .field::placeholder { color: color-mix(in srgb, var(--muted) 78%, transparent); }

    .field:focus {
      border-color: color-mix(in srgb, var(--primary) 70%, var(--line) 30%);
      box-shadow: 0 0 0 3px var(--focus);
    }

    .btn {
      border: 1px solid transparent;
      border-radius: 10px;
      padding: 10px 14px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      transition: filter .15s ease, transform .05s ease;
    }

    .btn:active { transform: translateY(1px); }
    .btn:hover { filter: brightness(1.05); }
    .btn:disabled { opacity: .6; cursor: not-allowed; }

    .btn.primary {
      background: var(--primary);
      color: var(--primary-ink);
      border-color: color-mix(in srgb, var(--primary) 75%, #000000 25%);
    }

    .btn.ghost {
      background: var(--chip);
      color: var(--text);
      border-color: var(--line);
    }

    .domain-wrap {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .domain {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      color: var(--primary);
      font-weight: 700;
      background: var(--chip);
      white-space: nowrap;
    }

    .two-col {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .device-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      background: color-mix(in srgb, var(--card) 92%, var(--bg-elev) 8%);
    }

    .muted { color: var(--muted); font-size: 13px; }

    .section-title {
      margin: 0 0 12px;
      font-size: 28px;
      line-height: 1.1;
      letter-spacing: -0.02em;
    }

    .panel-title {
      margin: 0 0 12px;
      font-size: 24px;
      line-height: 1.1;
      letter-spacing: -0.02em;
    }

    @media (max-width: 980px) {
      .kpi { grid-column: span 6; }
      .two-col { grid-template-columns: 1fr; }
    }

    @media (max-width: 700px) {
      body { padding: 14px 10px 18px; }
      .kpi { grid-column: 1 / -1; }
      .section-title { font-size: 24px; }
      .panel-title { font-size: 22px; }
      .domain-wrap { flex-direction: column; align-items: stretch; }
      .domain { text-align: center; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <img src="rp-home.svg" alt="RichPear logo" class="brand-logo" />
        <span>RichPear Home</span>
      </div>
      <nav class="nav">
        <span class="nav-item">Prehled</span>
        <span class="nav-item">Moje zarizeni</span>
        <span class="nav-item">Subdomena</span>
        <span class="nav-item">Ucet</span>
      </nav>
    </header>

    <section class="hero">
      <h1 class="section-title">RichPear Secure Tunnel</h1>
      <p>Nastaveni pristupu z Home Assistanta do internetu.</p>
    </section>

    {% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}
    {% if flash_err %}<div class="flash err">{{ flash_err }}</div>{% endif %}

    <section class="grid">
      <article class="card kpi">
        <span class="label">Stav uctu</span>
        <div class="value-sm">{% if is_logged %}{{ state.get("plan_status", "active") }}{% else %}neprihlasen{% endif %}</div>
        <div class="sub">{% if state.get("email") %}{{ state.get("email") }}{% else %}-{% endif %}</div>
      </article>
      <article class="card kpi">
        <span class="label">Zarizeni</span>
        <div class="value">1</div>
        <div class="sub">Home Assistant</div>
      </article>
      <article class="card kpi">
        <span class="label">Subdomena</span>
        <div class="value-sm">{% if state.get("subdomain") %}{{ state.get("subdomain") }}{% else %}-{% endif %}</div>
        <div class="sub">{% if state.get("full_domain") %}https://{{ state.get("full_domain") }}{% else %}Nenastavena{% endif %}</div>
      </article>

      <article class="card panel">
        <h2 class="panel-title">Moje zarizeni</h2>
        <div class="device-row">
          <div>
            <strong>{{ device_id }}</strong>
            <div class="muted">Control plane: {{ control_plane_url }}</div>
          </div>
          {% if frpc_up %}<span class="status-pill up"><span class="dot"></span>Online</span>{% else %}<span class="status-pill down"><span class="dot"></span>Offline</span>{% endif %}
        </div>
      </article>

      <article class="card panel">
        <h2 class="panel-title">Nastaveni uctu a tunelu</h2>
        <div class="two-col">
          <section class="stack">
            <span class="label">Ucet zakaznika</span>
            {% if is_logged %}
            <div class="flash ok">Prihlaseno jako <strong>{{ state.get("email") }}</strong> (plan: {{ state.get("plan_status","-") }})</div>
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
                <input class="field" style="flex:1; min-width:180px;" name="subdomain" type="text" placeholder="napr. rphome" value="{{ state.get('subdomain','') }}" required {% if not is_logged %}disabled{% endif %} />
                <span class="domain">.cz.richpear.cz</span>
              </div>
              <button type="submit" class="btn primary" {% if not is_logged %}disabled{% endif %}>Pripojit tunel</button>
              {% if not is_logged %}<span class="muted">Nejdriv se registruj nebo prihlas.</span>{% endif %}
            </form>
            <form method="post" action="restart" style="margin-top:6px;">
              <button type="submit" class="btn ghost">Restart tunelu</button>
            </form>
          </section>
        </div>
      </article>
    </section>
  </div>

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
        var candidates = [
          doc.querySelector('home-assistant'),
          doc.documentElement,
          doc.body
        ];
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
          // Keep local light/dark fallbacks when parent styles are inaccessible.
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
