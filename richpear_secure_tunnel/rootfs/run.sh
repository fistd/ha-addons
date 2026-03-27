#!/usr/bin/env sh
set -eu

CONFIG_PATH="/data/options.json"
if [ ! -f "$CONFIG_PATH" ]; then
  echo "options.json not found, exiting"
  exit 1
fi

CONTROL_PLANE_URL=$(jq -r '.control_plane_url' "$CONFIG_PATH")
EMAIL=$(jq -r '.email' "$CONFIG_PATH")
SUBDOMAIN=$(jq -r '.subdomain' "$CONFIG_PATH")
DEVICE_NAME=$(jq -r '.device_name' "$CONFIG_PATH")
HA_PORT=$(jq -r '.ha_port // 8123' "$CONFIG_PATH")
UPSTREAM_HOST_HEADER=$(jq -r '.upstream_host_header // "localhost"' "$CONFIG_PATH")
LOCAL_PROXY_PORT=18123

DEVICE_ID_FILE="/data/device_id"
KEY_FILE="/data/device_key.pem"
PUB_FILE="/data/device_pub.pem"

[ -f "$DEVICE_ID_FILE" ] || cat /proc/sys/kernel/random/uuid > "$DEVICE_ID_FILE"
DEVICE_ID=$(cat "$DEVICE_ID_FILE")

if [ ! -f "$KEY_FILE" ]; then
  openssl genpkey -algorithm ed25519 -out "$KEY_FILE"
  openssl pkey -in "$KEY_FILE" -pubout -out "$PUB_FILE"
fi

PUB_KEY=$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' "$PUB_FILE")

PAYLOAD=$(jq -n \
  --arg device_id "$DEVICE_ID" \
  --arg email "$EMAIL" \
  --arg subdomain "$SUBDOMAIN" \
  --arg public_key "$PUB_KEY" \
  '{device_id:$device_id,email:$email,subdomain:$subdomain,public_key:$public_key}')

echo "Registering $DEVICE_NAME ($DEVICE_ID) with $CONTROL_PLANE_URL"
HTTP_CODE=$(curl -sS -o /tmp/register.json -w '%{http_code}' \
  -X POST "$CONTROL_PLANE_URL/api/v2/devices/register" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

if [ "$HTTP_CODE" != "200" ]; then
  echo "Registration failed: HTTP $HTTP_CODE"
  cat /tmp/register.json
  exit 1
fi

echo "Registration succeeded"
cat /tmp/register.json

FRP_SERVER=$(jq -r '.frp_server' /tmp/register.json)
FRP_PORT=$(jq -r '.frp_port' /tmp/register.json)
FRP_TOKEN=$(jq -r '.frp_token' /tmp/register.json)

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

# Start local reverse proxy to normalize headers for Home Assistant.
# This avoids requiring manual trusted_proxies configuration on customer HA.
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

echo "Starting local header-normalizing proxy on :${LOCAL_PROXY_PORT} -> 127.0.0.1:${HA_PORT}"
caddy run --config "$CADDYFILE" --adapter caddyfile >/tmp/caddy.log 2>&1 &

FRPC_CONFIG="/data/frpc.toml"
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

echo "Starting frpc tunnel for ${SUBDOMAIN}.${FRP_SERVER}"
exec "$FRP_BIN" -c "$FRPC_CONFIG"
