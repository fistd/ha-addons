# Richpear Secure Tunnel (Home Assistant Add-on)

Add-on pro bezpecne vystaveni Home Assistant pres Richpear gateway s onboardovacim web UI.

## Co dela

1. Otevre vlastni web UI v Home Assistant Ingress.
2. Uzivatel se zaregistruje/prihlasi do Richpear uctu.
3. Vybere subdomenu, add-on priradi zarizeni k uctu.
4. Add-on sam nastavi a spusti outbound FRP tunnel bez port-forwardu.

## Konfigurace

- `control_plane_url`: URL admin API (napr. `https://admin.cz.richpear.cz`)
- `email`: volitelne pro legacy autostart
- `subdomain`: volitelne pro legacy autostart
- `device_name`: jmeno zarizeni
- `ha_port`: lokalni port Home Assistant (`8123`)
- `upstream_host_header`: host hlavicka posilana do Home Assistantu (`localhost`, doporucene)

## Poznamka

Add-on potrebuje odchozi pristup na internet (HTTPS + FRP port `7000`).
Add-on automaticky spousti lokalni reverzni proxy, ktera normalizuje hlavicky pro HA.
Primarni onboarding probiha pres Ingress web UI (verze `0.2.0+`).

## Troubleshooting 400

Pokud domena vraci `400: Bad Request`, zkontrolujte, ze bezi verze add-onu `0.1.2+`.
Tato verze problem resi automaticky bez nutnosti upravovat `configuration.yaml`.
