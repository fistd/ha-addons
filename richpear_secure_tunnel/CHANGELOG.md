# Changelog

## 0.2.9

- Fixed HA theme sync in ingress iframe: addon now actively reads Home Assistant theme variables from parent and updates live.
- Light/Dark mode now follows HA theme toggle even when browser/OS theme differs.

## 0.2.8

- Fixed theme switching to follow Home Assistant Light/Dark mode directly (uses HA CSS theme variables instead of OS color scheme).
- Add-on colors now react immediately when HA theme is changed.

## 0.2.7

- Improved dark mode readability: dark input fields, dark input borders and softer focus glow in HA dark theme.
- Reduced harsh contrast in dark mode background gradients.

## 0.2.6

- Fixed add-on UI theming to respect Home Assistant light/dark mode (automatic dark palette via prefers-color-scheme).
- Unified cards, text and status colors for both modes.

## 0.2.5

- Aligned add-on colors to the same green palette used in the current RichPear client/admin frontend.
- Preserved clean single auth panel (Prihlaseni/Registrace tabs) and unified card styling.

## 0.2.4

- Refined add-on UI to better match the Client Portal visual language (lighter dashboard cards, blue primary accents, cleaner spacing).
- Kept single auth panel with Prihlaseni/Registrace tabs and one visible form at a time.
- Improved overall readability and consistency of status cards and subdomain row.

## 0.2.3

- Redesigned onboarding auth section to a single clean panel with tabs (Prihlaseni/Registrace).
- Removed side-by-side login/signup forms for a clearer client-dashboard-like flow.
- Minor visual polish for section headings and spacing.

## 0.2.2

- Unified add-on onboarding UI with the new RichPear admin visual style (cards, typography, forms, status badges).
- Improved tunnel setup panel clarity and mobile responsiveness.
- Kept onboarding flow and API behavior unchanged for compatibility.

## 0.2.1

- Fixed Home Assistant ingress 404 after signup/login/connect (ingress-aware redirects and relative form actions).
- Improved onboarding flow to explicit 2 steps: account (signup/login) then subdomain connect.
- Improved UI clarity and status visibility.

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
