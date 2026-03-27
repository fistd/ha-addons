#!/usr/bin/env python3
import json
import os
import subprocess
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path

from flask import Flask, redirect, render_template_string, request, url_for


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
    content = f"""serverAddr = "{frp_server}"
serverPort = {frp_port}
user = "{subdomain}"
metadatas.token = "{frp_token}"

[[proxies]]
name = "{subdomain}-ha"
type = "http"
localIP = "127.0.0.1"
localPort = {LOCAL_PROXY_PORT}
subdomain = "{subdomain}"
hostHeaderRewrite = "{UPSTREAM_HOST_HEADER}"
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
  <title>RichPear Tunnel Setup</title>
  <style>
    :root {
      --bg-main: #f5f9f1;
      --bg-soft: #eef6e8;
      --card: #ffffff;
      --line: #d6e5cd;
      --text: #17301c;
      --muted: #51695a;
      --primary: #1f6fff;
      --primary-ink: #ffffff;
      --ok: #198754;
      --ok-bg: #e9f7ef;
      --ok-line: #bfe7cf;
      --warn: #9f1239;
      --warn-bg: #fdecef;
      --warn-line: #f3c7d2;
      --radius: 14px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Noto Sans", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 8% 10%, rgba(87, 177, 110, 0.10), transparent 36%),
        radial-gradient(circle at 88% 88%, rgba(31, 111, 255, 0.08), transparent 32%),
        linear-gradient(165deg, var(--bg-main), var(--bg-soft));
      min-height: 100vh;
    }
    .page {
      max-width: 860px;
      margin: 26px auto;
      padding: 0 14px;
    }
    .hero {
      background: linear-gradient(125deg, #173d20, #245f31);
      color: #f3fff0;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.18);
      box-shadow: 0 20px 44px rgba(22, 57, 33, 0.22);
      padding: 20px;
      margin-bottom: 14px;
    }
    .brand {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      border-radius: 9px;
      background: #ffffff;
      color: #12351b;
      font-weight: 800;
      margin-right: 10px;
      font-size: 13px;
    }
    .hero h1 { margin: 0 0 6px; font-size: 26px; line-height: 1.2; }
    .hero p { margin: 0; color: rgba(243,255,240,0.84); font-size: 14px; }
    .meta {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }
    .meta-item {
      background: rgba(255,255,255,0.1);
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 13px;
    }
    .meta-label { color: rgba(243,255,240,0.76); display: block; margin-bottom: 4px; }
    .meta-value { font-weight: 700; word-break: break-word; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid transparent;
    }
    .up { background: #e9f7ef; color: #146c43; border-color: #bfe7cf; }
    .down { background: #fdecef; color: #9f1239; border-color: #f3c7d2; }
    .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

    .flash { margin: 10px 0; padding: 10px 12px; border-radius: 10px; font-size: 14px; }
    .flash.ok { background: var(--ok-bg); border: 1px solid var(--ok-line); color: #0f5831; }
    .flash.err { background: var(--warn-bg); border: 1px solid var(--warn-line); color: #7f1d1d; }

    .panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 14px 36px rgba(20, 51, 27, 0.10);
      padding: 16px;
      margin-top: 14px;
    }
    .panel h3 {
      margin: 0 0 10px;
      font-size: 17px;
      line-height: 1.25;
    }
    .muted { color: var(--muted); font-size: 13px; }
    .auth-wrap {
      max-width: 520px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fbfdf9;
      padding: 14px;
    }
    .auth-tabs {
      display: inline-flex;
      gap: 6px;
      background: #edf3e9;
      border: 1px solid #d8e5cf;
      border-radius: 999px;
      padding: 4px;
      margin-bottom: 10px;
    }
    .auth-tab {
      border: 0;
      background: transparent;
      color: #425f4d;
      font-size: 13px;
      font-weight: 700;
      border-radius: 999px;
      padding: 7px 12px;
      cursor: pointer;
    }
    .auth-tab.active {
      background: #ffffff;
      color: #1f6fff;
      box-shadow: 0 2px 8px rgba(20, 40, 27, 0.10);
    }
    .auth-form { display: none; }
    .auth-form.active { display: block; }
    .auth-title { margin: 0 0 8px; font-size: 14px; color: #234032; font-weight: 700; }
    .row { margin-bottom: 10px; }
    input {
      width: 100%;
      border: 1px solid #c8d8be;
      border-radius: 10px;
      padding: 11px 12px;
      font-size: 14px;
      outline: none;
      transition: border-color .15s ease, box-shadow .15s ease;
      background: #ffffff;
      color: var(--text);
    }
    input:focus {
      border-color: #6ea6ff;
      box-shadow: 0 0 0 4px rgba(31,111,255,.13);
    }
    .btn {
      border: 0;
      border-radius: 10px;
      padding: 10px 14px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      color: var(--primary-ink);
      background: var(--primary);
      transition: transform .05s ease, filter .15s ease;
    }
    .btn:hover { filter: brightness(1.05); }
    .btn:active { transform: translateY(1px); }
    .btn.secondary { background: #5f6c84; }
    .btn.ok { background: var(--ok); }
    .btn:disabled {
      cursor: not-allowed;
      filter: grayscale(.45);
      opacity: .6;
    }
    .row-inline { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .domain {
      color: #245f31;
      font-weight: 700;
      background: #eff8ea;
      border: 1px solid #d5e9c8;
      border-radius: 8px;
      padding: 4px 8px;
    }
    @media (max-width: 520px) { .meta { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div style="display:flex; align-items:center; margin-bottom:8px;">
        <span class="brand">RP</span>
        <div>
          <h1>RichPear Secure Tunnel</h1>
          <p>Nastaveni pristupu z Home Assistanta do internetu.</p>
        </div>
      </div>
      <div class="meta">
        <div class="meta-item">
          <span class="meta-label">Device ID</span>
          <span class="meta-value">{{ device_id }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Control plane</span>
          <span class="meta-value">{{ control_plane_url }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Stav tunelu</span>
          {% if frpc_up %}<span class="status-pill up"><span class="dot"></span>Running</span>{% else %}<span class="status-pill down"><span class="dot"></span>Stopped</span>{% endif %}
        </div>
        <div class="meta-item">
          <span class="meta-label">Aktivni domena</span>
          <span class="meta-value">{% if state.get("full_domain") %}https://{{ state.get("full_domain") }}{% else %}-{% endif %}</span>
        </div>
      </div>
    </section>

    {% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}
    {% if flash_err %}<div class="flash err">{{ flash_err }}</div>{% endif %}

    <section class="panel">
      <h3>Ucet zakaznika</h3>
      {% if is_logged %}
      <div class="flash ok">Prihlaseno jako <strong>{{ state.get("email") }}</strong> (plan: {{ state.get("plan_status","-") }})</div>
      {% else %}
      <div class="auth-wrap">
        <div class="auth-tabs">
          <button type="button" class="auth-tab active" data-auth-tab="login">Prihlaseni</button>
          <button type="button" class="auth-tab" data-auth-tab="signup">Registrace</button>
        </div>
        <form method="post" action="login" class="auth-form active" data-auth-form="login">
          <p class="auth-title">Prihlas se do existujiciho uctu</p>
          <div class="row"><input name="email" type="email" placeholder="E-mail" required /></div>
          <div class="row"><input name="password" type="password" placeholder="Heslo" required /></div>
          <button type="submit" class="btn">Prihlasit</button>
        </form>
        <form method="post" action="signup" class="auth-form" data-auth-form="signup">
          <p class="auth-title">Vytvor novy ucet</p>
          <div class="row"><input name="email" type="email" placeholder="E-mail" required /></div>
          <div class="row"><input name="password" type="password" placeholder="Heslo (min 10, pismena + cisla)" required /></div>
          <button type="submit" class="btn">Registrovat</button>
        </form>
      </div>
      {% endif %}
    </section>

    <section class="panel">
      <h3>Subdomena a pripojeni</h3>
      <form method="post" action="connect">
        <div class="row-inline" style="margin-bottom:10px;">
          <input style="flex:1; min-width:220px;" name="subdomain" type="text" placeholder="napr. rphome" value="{{ state.get('subdomain','') }}" required {% if not is_logged %}disabled{% endif %} />
          <span class="domain">.cz.richpear.cz</span>
        </div>
        <button type="submit" class="btn ok" {% if not is_logged %}disabled{% endif %}>Pripojit tunel</button>
      </form>
      {% if not is_logged %}
      <p class="muted">Nejdriv se registruj nebo prihlas.</p>
      {% endif %}
      <form method="post" action="restart" style="margin-top:10px;">
        <button type="submit" class="btn secondary">Restart tunelu</button>
      </form>
    </section>
  </div>
  <script>
    (function () {
      var tabs = document.querySelectorAll('[data-auth-tab]');
      var forms = document.querySelectorAll('[data-auth-form]');
      if (!tabs.length || !forms.length) return;
      function setMode(mode) {
        tabs.forEach(function (t) {
          t.classList.toggle('active', t.getAttribute('data-auth-tab') === mode);
        });
        forms.forEach(function (f) {
          f.classList.toggle('active', f.getAttribute('data-auth-form') === mode);
        });
      }
      tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
          setMode(tab.getAttribute('data-auth-tab'));
        });
      });
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
