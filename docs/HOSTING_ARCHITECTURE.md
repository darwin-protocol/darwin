# Hosting Architecture

## Recommended Public Stack

DARWIN should keep the public website on static hosting and keep the Raspberry Pi out of the direct public path.

- Public site: GitHub Pages
- DNS / optional CDN: IONOS DNS now, optional Cloudflare later
- App path: static Next.js export
- Private services later: Raspberry Pi behind a tunnel on separate subdomains

This keeps the public site simple, cacheable, and easy to move, while avoiding a home-origin dependency for the main public surface.

## Why

- The current DARWIN web surface is static.
- Static hosting is enough for SEO if the site has crawlable HTML, metadata, sitemap, and robots.
- A Raspberry Pi origin adds uptime and origin-leak risk without helping the public portal.
- Domain ownership is not anonymous just because the site runs on a Pi; what matters is minimizing public origin exposure and unnecessary infrastructure.

## Recommended Domain Map

- apex domain: brand / landing page
- `www`: redirect to apex or vice versa
- `app`: optional future app alias if the public site splits from the landing page
- `docs`: optional docs alias if docs move off GitHub
- `ops` or `api`: only for future Pi-hosted dynamic services

## Current Best Path

1. Keep the public site on GitHub Pages.
2. Use the Next.js static export in `web/`.
3. Set a custom domain in GitHub Pages.
4. Point the bought domain at GitHub Pages from IONOS.
5. Only add Cloudflare if you want DNS control, CDN, or extra edge features.
6. Only add Raspberry Pi hosting for private or dynamic services later.

For the exact GitHub-side and registrar cutover sequence, see [CUSTOM_DOMAIN_SETUP.md](CUSTOM_DOMAIN_SETUP.md).

## Repo Settings

The Pages workflow now supports two repo variables:

- `DARWIN_SITE_DOMAIN`
- `DARWIN_SITE_BASE_PATH`

Recommended usage:

- with only the project Pages URL: leave `DARWIN_SITE_DOMAIN` unset and let the build fall back to `/darwin`
- with a real custom domain: set `DARWIN_SITE_DOMAIN` to the apex you want to serve and leave `DARWIN_SITE_BASE_PATH` empty

When `DARWIN_SITE_DOMAIN` is present, the workflow writes `web/public/CNAME` automatically during deploy.

## DNS Direction

Use the bought domain as the canonical public hostname.

Recommended public split:

- apex domain: landing page and protocol front door
- `www`: redirect to apex
- `app`: optional later alias if the market portal becomes distinct from the landing page
- `docs`: optional later docs alias

For the initial cut, keep it simple:

- point the apex at GitHub Pages
- point `www` at GitHub Pages or redirect it to the apex
- keep the Raspberry Pi off the public web path

## Optional Cloudflare

Cloudflare is optional, not required.

Use it if you want:

- edge caching
- easy DNS management
- later origin shielding for non-static Pi-hosted services

Do not use it as the first step if the immediate goal is just getting the custom domain live on the static site.

## Pi Hosting Later

If DARWIN later needs a private dashboard, indexer, or operator-only service on the Raspberry Pi:

- keep the public site on Pages
- publish the Pi service on a separate subdomain
- use a tunnel or reverse-proxy layer
- do not expose the Pi directly on the public internet unless you are intentionally operating and hardening it as an origin

## Self-Hosted Tunnel Candidates

If you want a Cloudflare Tunnel alternative later, evaluate:

- Pangolin
- boringproxy
- frp

These are phase-two infrastructure options, not blockers for the public DARWIN website.
