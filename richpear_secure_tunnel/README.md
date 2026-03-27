# Richpear Secure Tunnel (Home Assistant Add-on)

Add-on pro bezpecne vystaveni Home Assistant pres Richpear gateway.

## Co dela

1. Zaregistruje zarizeni do Richpear control-plane.
2. Ziska FRP token.
3. Spusti outbound FRP tunnel bez potreby domaciho port-forwardu.

## Konfigurace

- `control_plane_url`: URL admin API (napr. `https://admin.cz.richpear.cz`)
- `email`: e-mail uzivatele
- `subdomain`: pozadovana subdomena
- `device_name`: jmeno zarizeni
- `ha_port`: lokalni port Home Assistant (`8123`)

## Poznamka

Add-on potrebuje odchozi pristup na internet (HTTPS + FRP port `7000`).
