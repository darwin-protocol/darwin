# Custom Domain Setup

This is the cleanest setup for DARWIN today:

- keep the public site on GitHub Pages
- use the Next.js static export in [`web/`](../web/)
- use one primary domain as the canonical public hostname
- use any extra registrar-included domains as redirects, not parallel primaries

## Why

- the public site is static, so there is no reason to put the Raspberry Pi in front of it
- GitHub Pages gives HTTPS, cacheability, and no home-origin exposure for the public site
- a single canonical host is better for SEO and less confusing for users
- spare domains are more useful as `301` forwards than as split public entrypoints

## Recommended Domain Map

- apex domain: main landing page and public market entry
- `www`: alias to the apex
- spare domains: `301` forward to the apex
- Raspberry Pi later: separate subdomain only for dynamic or private services

## Best-Practice Flow

1. Pick one primary domain.
2. Verify that domain in GitHub if possible.
3. Run the GitHub-side helper:

```bash
./ops/configure_pages_domain.sh example.com
```

4. At the registrar, point the apex at GitHub Pages:

```text
A     @    185.199.108.153
A     @    185.199.109.153
A     @    185.199.110.153
A     @    185.199.111.153
AAAA  @    2606:50c0:8000::153
AAAA  @    2606:50c0:8001::153
AAAA  @    2606:50c0:8002::153
AAAA  @    2606:50c0:8003::153
CNAME www  darwin-protocol.github.io.
```

5. Forward any spare domains to the canonical host with a permanent `301` redirect.
6. Wait for GitHub Pages HTTPS to finish provisioning.
7. Confirm DNS health:

```bash
gh api repos/darwin-protocol/darwin/pages/health
```

## IONOS Guidance

If the bought domain is at IONOS:

- keep DNS there initially unless you specifically want Cloudflare features
- use IONOS forwarding for extra bundled domains
- do not use wildcard DNS for GitHub Pages

## What Not To Do

- do not split the same public site across multiple unrelated canonical domains
- do not move the main public site onto a Raspberry Pi just to say it is self-hosted
- do not put the Pi directly on the public internet for the static site

## Raspberry Pi Later

If the Raspberry Pi becomes useful later, keep it on a separate subdomain for:

- operator dashboards
- indexers
- admin tools
- private or semi-private services

That should be phase two, not the first public cut.
