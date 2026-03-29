# Changelog

## 0.2.20

- Fixed onboarding auth switching so only one form is visible at a time (`Přihlášení` or `Registrace`).
- Replaced addon branding asset with your provided `rp-home.svg` logo for header/auth screens and addon icon/logo files.

## 0.2.19

- Addon now starts with account onboarding screen only (`Přihlášení / Registrace`) like the client portal.
- After login, addon opens dashboard view with the same core info blocks as client dashboard (account status, devices, subdomain).
- Added fully functional top tabs and clickable KPI cards that switch real sections (`Moje zařízení`, `Subdoména`, `Účet`, `Fakturační údaje`).

## 0.2.18

- Updated addon UI text to Czech with proper diacritics (navigation, section labels, action buttons, and status messages).
- Updated success/error toast messages to Czech with diacritics as well.

## 0.2.17

- Fixed top navigation to be truly functional in the addon UI (clickable section navigation and active tab state).
- Clicking `Subdomena`, `Ucet`, or `Fakturacni udaje` now opens the settings section automatically.
- Minor visual tuning of nav chips/spacing for closer dashboard parity.

## 0.2.16

- Tuned addon dashboard visual parity with the client portal (header scale, nav chip sizing, greeting and section proportions).
- Moved tunnel/account controls into a collapsed section so the default addon view matches the client dashboard layout more closely.

## 0.2.15

- Rebuilt add-on page layout directly from the RichPear client dashboard structure (greeting block, KPI cards, dashboard proportions).
- Added full top navigation parity including `Fakturacni udaje` item and kept logged-in user + logout action in header.
- Preserved add-on specific tunnel/account controls in a dedicated panel below the dashboard cards.

## 0.2.14

- Reworked addon UI to mirror the RichPear web dashboard structure much more closely: sticky top bar, dashboard card composition, and matching hierarchy.
- Added direct logout action in addon UI so account behavior matches portal expectations.
- Kept HA theme sync, while preserving clear dark/light fallback styling.

## 0.2.13

- Redesigned add-on onboarding UI to match RichPear client dashboard style more closely (top bar, KPI cards, panel hierarchy, spacing).
- Improved theme behavior with stronger light/dark fallbacks while still syncing Home Assistant theme variables from parent ingress context.
- Kept onboarding flow simple: one auth block (Prihlaseni/Registrace tabs) plus direct subdomain/tunnel actions.

## 0.2.12

- Fixed add-on header branding: replaced unintended Home Assistant icon with RichPear logo asset.

## 0.2.11

- Improved visual parity with client portal: matching fonts (Inter/Space Grotesk), logo usage, and cleaner dashboard-like cards.
- Add-on now serves the same rp-home.svg logo internally and uses it in onboarding header.

## 0.2.10

- Fixed persistent login: add-on startup no longer overwrites onboarding_state.json and removes access_token during legacy auto-connect path.
- Existing state keys are now preserved on restart (token, plan_status, etc.).

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
