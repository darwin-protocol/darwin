# Pi Tunnel Hosting

This is the deterministic fallback path for `usedarwin.xyz` if GitHub Pages keeps stalling on TLS.

## When To Use It

Use this path if any of these are true:

- GitHub Pages custom-domain HTTPS is still not issuing in a reasonable window
- you want direct control over TLS cutover timing
- you want the public site to stop depending on GitHub Pages
- you want the Raspberry Pi origin hidden behind an outbound-only tunnel

## Why This Is Smart

For the current DARWIN site, a Raspberry Pi plus Cloudflare Tunnel is a reasonable fallback:

- no inbound router port forwards
- outbound-only tunnel from the Pi
- Cloudflare edge terminates TLS
- origin IP is not exposed in public DNS
- the site is already a static Next.js export, so the Pi only has to serve files

The tradeoff is operational, not technical:

- home internet and power now matter
- Cloudflare is part of the trust boundary
- domain ownership is still not anonymous

## Recommended Layout

- domain and DNS: Cloudflare
- origin: Raspberry Pi
- public edge: Cloudflare Tunnel
- local origin server: Caddy on `site:8080`
- site content: `web/out/` synced to `/srv/usedarwin/site/current`

Keep the GitHub Pages URL as a backup path, not the canonical public host.

## Required External Steps

1. Add `usedarwin.xyz` to Cloudflare.
2. Change nameservers at IONOS to Cloudflare.
3. In Cloudflare Zero Trust, create a tunnel.
4. Route the tunnel hostnames in Cloudflare DNS to that tunnel.
5. Copy the tunnel credentials JSON onto the Pi.
6. Render the local tunnel config with the tunnel id and public hostnames.
The local config should point `usedarwin.xyz` and `www.usedarwin.xyz` at `http://site:8080`.

## Pi Setup

On the Raspberry Pi:

```bash
cd /path/to/darwin
./ops/pi/install_public_site_stack.sh
sudo nano /opt/darwin-public-site/.env
sudo nano /opt/darwin-public-site/cloudflared-config.yml
sudo docker compose -f /opt/darwin-public-site/docker-compose.yml up -d
```

Then publish the current static export from the workstation:

```bash
cd /path/to/darwin
./ops/pi/publish_static_site.sh <pi-host> <pi-user>
```

That script now:

- regenerates `market-config.json`
- regenerates `runtime-status.json` in Cloudflare-tunnel mode
- builds the site for the canonical custom domain instead of the GitHub Pages `/darwin` base path
- syncs the finished static export to the Pi

## What The Pi Runs

- `darwin-site`: Caddy serving static files from `/srv/usedarwin/site/current`
- `darwin-cloudflared`: Cloudflare Tunnel agent using a local ingress config plus tunnel credentials file

For host-local verification only, the stack binds:

- `127.0.0.1:8080 -> darwin-site`
- `127.0.0.1:21123 -> cloudflared metrics`

The Caddy config lives in [ops/pi/Caddyfile](../ops/pi/Caddyfile).

The compose stack lives in [ops/pi/docker-compose.public-site.yml](../ops/pi/docker-compose.public-site.yml).

## Security Notes

- do not expose port `8080` to the public internet
- keep SSH limited to your admin path
- keep the tunnel credentials JSON only on the Pi
- use Cloudflare access controls later if you add private admin subdomains

## Operational Notes

- if you want `www.usedarwin.xyz`, add another public hostname in the same tunnel
- if you want the spare `usedarwin.*` domains to keep forwarding, leave them at IONOS or re-create redirects elsewhere
- if you later add dynamic services, put them on separate hostnames such as `ops.usedarwin.xyz`

## Recommendation

Right now the cleanest move is:

1. keep `darwin-protocol.github.io/darwin/` as a backup
2. cut `usedarwin.xyz` to Cloudflare + tunnel if GitHub Pages TLS keeps failing
3. use the Pi only as a static origin and operator surface, not as an all-purpose app server
