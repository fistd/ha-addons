ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.20
FROM ${BUILD_FROM}

RUN apk add --no-cache curl jq openssl tar caddy python3 py3-flask
COPY rootfs/run.sh /run.sh
COPY rootfs/webapp.py /opt/richpear/webapp.py
COPY rootfs/rp-home.svg /opt/richpear/rp-home.svg
RUN chmod +x /run.sh
CMD ["/run.sh"]
