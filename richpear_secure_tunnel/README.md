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
- `upstream_host_header`: host hlavicka posilana do Home Assistantu (`localhost`, doporucene)

## Poznamka

Add-on potrebuje odchozi pristup na internet (HTTPS + FRP port `7000`).

## Troubleshooting 400

Pokud domena vraci `400: Bad Request`, vetsinou Home Assistant odmita puvodni externi `Host` hlavicku.
Nechte `upstream_host_header=localhost` (vychozi), pripadne v HA povolte reverzni proxy:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 127.0.0.1
```
