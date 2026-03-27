#!/usr/bin/env sh
set -eu

CONFIG_PATH="/data/options.json"
if [ ! -f "$CONFIG_PATH" ]; then
  echo "options.json not found, exiting"
  exit 1
fi

CONTROL_PLANE_URL=$(jq -r '.control_plane_url // "https://admin.cz.richpear.cz"' "$CONFIG_PATH")
EMAIL=$(jq -r '.email // ""' "$CONFIG_PATH")
SUBDOMAIN=$(jq -r '.subdomain // ""' "$CONFIG_PATH")
HA_PORT=$(jq -r '.ha_port // 8123' "$CONFIG_PATH")
UPSTREAM_HOST_HEADER=$(jq -r '.upstream_host_header // "localhost"' "$CONFIG_PATH")
LOCAL_PROXY_PORT=18123

DEVICE_ID_FILE="/data/device_id"
KEY_FILE="/data/device_key.pem"
PUB_FILE="/data/device_pub.pem"
STATE_FILE="/data/onboarding_state.json"
FRPC_CONFIG="/data/frpc.toml"
FRPC_LOG="/data/frpc.log"

[ -f "$DEVICE_ID_FILE" ] || cat /proc/sys/kernel/random/uuid > "$DEVICE_ID_FILE"
DEVICE_ID=$(cat "$DEVICE_ID_FILE")

if [ ! -f "$KEY_FILE" ]; then
  openssl genpkey -algorithm ed25519 -out "$KEY_FILE"
  openssl pkey -in "$KEY_FILE" -pubout -out "$PUB_FILE"
fi

PUB_KEY=$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' "$PUB_FILE")

ARCH=$(uname -m)
case "$ARCH" in
  x86_64) FRP_ARCH="amd64" ;;
  aarch64) FRP_ARCH="arm64" ;;
  armv7l) FRP_ARCH="arm" ;;
  *) FRP_ARCH="amd64" ;;
esac

FRP_VERSION="0.62.1"
FRP_BIN="/usr/local/bin/frpc"
if [ ! -x "$FRP_BIN" ]; then
  echo "Downloading frpc ${FRP_VERSION} for ${FRP_ARCH}"
  URL="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_${FRP_ARCH}.tar.gz"
  curl -fsSL "$URL" -o /tmp/frp.tgz
  tar -xzf /tmp/frp.tgz -C /tmp
  cp "/tmp/frp_${FRP_VERSION}_linux_${FRP_ARCH}/frpc" "$FRP_BIN"
  chmod +x "$FRP_BIN"
fi

# Local reverse proxy normalizes headers to keep HA happy without manual customer config.
CADDYFILE="/tmp/Caddyfile"
cat > "$CADDYFILE" <<EOF
:${LOCAL_PROXY_PORT} {
  reverse_proxy 127.0.0.1:${HA_PORT} {
    header_up Host ${UPSTREAM_HOST_HEADER}
    header_up -X-Forwarded-For
    header_up -X-Forwarded-Host
    header_up -X-Forwarded-Proto
    header_up -Forwarded
  }
}
EOF

echo "Starting local proxy on :${LOCAL_PROXY_PORT} -> 127.0.0.1:${HA_PORT}"
caddy run --config "$CADDYFILE" --adapter caddyfile >/tmp/caddy.log 2>&1 &

start_legacy_tunnel_if_configured() {
  if [ -z "$EMAIL" ] || [ -z "$SUBDOMAIN" ]; then
    return 0
  fi

  PAYLOAD=$(jq -n \
    --arg device_id "$DEVICE_ID" \
    --arg email "$EMAIL" \
    --arg subdomain "$SUBDOMAIN" \
    --arg public_key "$PUB_KEY" \
    '{device_id:$device_id,email:$email,subdomain:$subdomain,public_key:$public_key}')

  echo "Legacy auto-connect: registering $DEVICE_ID ($SUBDOMAIN) with $CONTROL_PLANE_URL"
  HTTP_CODE=$(curl -sS -o /tmp/register.json -w '%{http_code}' \
    -X POST "$CONTROL_PLANE_URL/api/v2/devices/register" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

  if [ "$HTTP_CODE" != "200" ]; then
    echo "Legacy register failed: HTTP $HTTP_CODE"
    cat /tmp/register.json || true
    return 0
  fi

  FRP_SERVER=$(jq -r '.frp_server' /tmp/register.json)
  FRP_PORT=$(jq -r '.frp_port' /tmp/register.json)
  FRP_TOKEN=$(jq -r '.frp_token' /tmp/register.json)
  FULL_DOMAIN=$(jq -r '.full_domain' /tmp/register.json)

  cat > "$FRPC_CONFIG" <<EOF
serverAddr = "${FRP_SERVER}"
serverPort = ${FRP_PORT}
user = "${SUBDOMAIN}"
metadatas.token = "${FRP_TOKEN}"

[[proxies]]
name = "${SUBDOMAIN}-ha"
type = "http"
localIP = "127.0.0.1"
localPort = ${LOCAL_PROXY_PORT}
subdomain = "${SUBDOMAIN}"
hostHeaderRewrite = "${UPSTREAM_HOST_HEADER}"
EOF

  echo "Starting legacy frpc tunnel for ${FULL_DOMAIN}"
  "$FRP_BIN" -c "$FRPC_CONFIG" >>"$FRPC_LOG" 2>&1 &

  # Preserve existing onboarding state (access_token, plan_status, etc.)
  # and only update legacy connection fields.
  if [ -f "$STATE_FILE" ]; then
    jq \
      --arg email "$EMAIL" \
      --arg subdomain "$SUBDOMAIN" \
      --arg full_domain "$FULL_DOMAIN" \
      '.email=$email | .subdomain=$subdomain | .full_domain=$full_domain | .legacy_mode=true' \
      "$STATE_FILE" > "${STATE_FILE}.tmp" && mv "${STATE_FILE}.tmp" "$STATE_FILE"
  else
    cat > "$STATE_FILE" <<EOF
{
  "email": "${EMAIL}",
  "subdomain": "${SUBDOMAIN}",
  "full_domain": "${FULL_DOMAIN}",
  "legacy_mode": true
}
EOF
  fi
}

start_legacy_tunnel_if_configured

export RP_CONTROL_PLANE_URL="$CONTROL_PLANE_URL"
export RP_FRPC_BIN="$FRP_BIN"
export RP_FRPC_CONFIG="$FRPC_CONFIG"
export RP_FRPC_LOG="$FRPC_LOG"
export RP_DEVICE_ID_FILE="$DEVICE_ID_FILE"
export RP_PUBLIC_KEY_FILE="$PUB_FILE"
export RP_STATE_FILE="$STATE_FILE"
export RP_LOCAL_PROXY_PORT="$LOCAL_PROXY_PORT"
export RP_UPSTREAM_HOST_HEADER="$UPSTREAM_HOST_HEADER"

echo "Starting onboarding web UI on :8099"
exec python3 /opt/richpear/webapp.py
