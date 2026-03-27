# Changelog

## 0.2.0

- Added built-in onboarding web UI in add-on ingress (signup/login/connect subdomain).
- Added customer account and device-claim flow integration with control-plane public API.
- Kept backward-compatible legacy autostart from static `email/subdomain` options.

## 0.1.2

- Added internal local reverse proxy (Caddy) inside add-on to normalize headers before forwarding to Home Assistant.
- Removed dependency on manual `trusted_proxies` setup for common tunnel deployments.

## 0.1.1

- Added `upstream_host_header` option (default `localhost`) to avoid `400 Bad Request` in Home Assistant behind FRP tunnel.
- Added troubleshooting notes for Home Assistant reverse-proxy settings.

## 0.1.0

- Initial release
- Device registration to control-plane
- Automatic frpc download and tunnel startup
