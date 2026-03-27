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
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Richpear Tunnel Onboarding</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:linear-gradient(180deg,#f2f6ff,#edf5f2); margin:0; }
    .wrap { max-width: 760px; margin: 22px auto; background:#fff; border-radius: 14px; padding: 22px; box-shadow:0 12px 30px rgba(16,30,70,.10);}
    h1 { margin-top: 0; }
    .row { margin-bottom: 14px; }
    input { width:100%; box-sizing: border-box; padding: 10px; border:1px solid #ccd3de; border-radius: 8px; }
    button { background:#145af2; color:#fff; border:0; border-radius: 8px; padding: 10px 14px; cursor:pointer; }
    button.secondary { background:#4b5565; }
    button.ok { background:#198754; }
    .hint { color:#58667a; font-size: 14px; }
    .ok { background:#e8f7ee; border:1px solid #b8e3c7; color:#114d27; padding:10px; border-radius:8px; }
    .err { background:#fdecec; border:1px solid #f5c2c2; color:#7f1d1d; padding:10px; border-radius:8px; }
    .grid { display:grid; grid-template-columns: 1fr 1fr; gap:16px; }
    .cardline { border:1px solid #dbe5f3; border-radius:10px; padding:14px; margin-top:14px; }
    .badge { display:inline-block; padding:4px 8px; border-radius:999px; font-size:12px; font-weight:600; }
    .b-ok { background:#e9f7ef; color:#146c43; border:1px solid #bfe7cf; }
    .b-off { background:#f8eaed; color:#9f1239; border:1px solid #f3c7d2; }
    .muted-small { color:#6b778d; font-size:13px; }
    @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Richpear Secure Tunnel</h1>
    <p class="hint">Device ID: {{ device_id }}</p>
    <p class="hint">Control plane: {{ control_plane_url }}</p>
    <p class="hint">Tunnel:
      {% if frpc_up %}<span class="badge b-ok">running</span>{% else %}<span class="badge b-off">stopped</span>{% endif %}
    </p>
    {% if state.get("full_domain") %}
    <p class="hint">Aktivni domena: <strong>https://{{ state.get("full_domain") }}</strong></p>
    {% endif %}
    {% if flash_ok %}<div class="ok">{{ flash_ok }}</div>{% endif %}
    {% if flash_err %}<div class="err">{{ flash_err }}</div>{% endif %}

    <div class="cardline">
      <h3 style="margin-top:0;">1) Ucet</h3>
      {% if is_logged %}
      <div class="ok">Prihlaseno jako <strong>{{ state.get("email") }}</strong> (plan: {{ state.get("plan_status","-") }})</div>
      {% else %}
      <div class="grid">
        <form method="post" action="signup">
          <div class="muted-small" style="margin-bottom:8px;">Nemam ucet</div>
          <div class="row"><input name="email" type="email" placeholder="E-mail" required /></div>
          <div class="row"><input name="password" type="password" placeholder="Heslo (min 8)" required /></div>
          <button type="submit">Registrovat</button>
        </form>
        <form method="post" action="login">
          <div class="muted-small" style="margin-bottom:8px;">Uz mam ucet</div>
          <div class="row"><input name="email" type="email" placeholder="E-mail" required /></div>
          <div class="row"><input name="password" type="password" placeholder="Heslo" required /></div>
          <button type="submit">Prihlasit</button>
        </form>
      </div>
      {% endif %}
    </div>

    <div class="cardline">
      <h3 style="margin-top:0;">2) Subdomena a pripojeni</h3>
      <form method="post" action="connect">
        <div class="row"><input name="subdomain" type="text" placeholder="napr. rphome" value="{{ state.get('subdomain','') }}" required {% if not is_logged %}disabled{% endif %} /></div>
        <button type="submit" class="ok" {% if not is_logged %}disabled{% endif %}>Pripojit tunel</button>
      </form>
      {% if not is_logged %}
      <p class="muted-small">Nejdriv se registruj nebo prihlas.</p>
      {% endif %}
      <form method="post" action="restart" style="margin-top:10px;">
        <button type="submit" class="secondary">Restart tunelu</button>
      </form>
    </div>
  </div>
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
