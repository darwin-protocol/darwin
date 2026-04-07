import Link from "next/link";

const siteUrl = "https://usedarwin.xyz";
const miniAppEmbed = JSON.stringify({
  version: "1",
  imageUrl: `${siteUrl}/og-card.png`,
  button: {
    title: "Open DARWIN",
    action: {
      type: "launch_miniapp",
      url: siteUrl,
      name: "Use Darwin",
      splashImageUrl: `${siteUrl}/icon.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});
const frameEmbed = JSON.stringify({
  version: "next",
  imageUrl: `${siteUrl}/og-card.png`,
  button: {
    title: "Open DARWIN",
    action: {
      type: "launch_frame",
      name: "Use Darwin",
      url: siteUrl,
      splashImageUrl: `${siteUrl}/icon.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});

export const metadata = {
  title: "Use Darwin",
  description:
    "Claim testnet DRW and use a tiny first swap on the live Base Sepolia DARWIN reference pool.",
  alternates: {
    canonical: "/",
  },
  other: {
    "fc:miniapp": miniAppEmbed,
    "fc:frame": frameEmbed,
  },
};

const structuredData = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Use Darwin",
  url: "https://usedarwin.xyz",
  description:
    "Claim testnet DRW and use a tiny first swap on the live Base Sepolia DARWIN reference pool.",
};

export default function HomePage() {
  return (
    <div className="background-shell">
      <div className="background">
        <div className="orb orb-a"></div>
        <div className="orb orb-b"></div>
        <div className="grid"></div>
      </div>

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />

      <main className="home-shell">
        <section className="card status-banner">
          <div>
            <p className="eyebrow">USE DARWIN</p>
            <h1 className="plain-title">Live Base Sepolia DRW market.</h1>
            <p className="plain-note">
              Public host: <code>usedarwin.xyz</code>. The public testnet market, faucet, and trade
              portal are live.
            </p>
          </div>
          <div className="status-banner-meta">
            <span className="badge">Base Sepolia</span>
            <span className="badge">DRW live</span>
            <span className="badge">Testnet alpha</span>
          </div>
        </section>

        <section className="card home-hero simple-hero">
          <div className="home-hero-copy">
            <h2 className="section-title">Claim, wrap, and trade.</h2>
            <p className="lede">
              DARWIN is live as a public testnet surface: token, faucet, reference pool, wallet
              portal, and deployment artifact. The first outside action should be small and
              obvious: claim DRW, then use a tiny swap.
            </p>
            <div className="hero-actions">
              <Link className="button button-primary" href="/trade/">
                Open market
              </Link>
              <Link className="button button-secondary" href="/trade/?preset=tiny-sell">
                Try tiny swap
              </Link>
              <Link className="button button-secondary" href="/epoch/">
                Current epoch
              </Link>
              <Link className="button button-secondary" href="/activity/">
                Live activity
              </Link>
              <a
                className="button button-secondary"
                href="https://github.com/darwin-protocol/darwin/blob/main/LIVE_STATUS.md"
                target="_blank"
                rel="noreferrer"
              >
                Live status
              </a>
              <a
                className="button button-secondary"
                href="https://github.com/darwin-protocol/darwin"
                target="_blank"
                rel="noreferrer"
              >
                GitHub
              </a>
            </div>
          </div>

          <aside className="home-hero-panel simple-panel">
            <div className="rail-card">
              <span className="label">Token</span>
              <strong>DRW</strong>
              <small>Base Sepolia live surface</small>
            </div>
            <div className="rail-card">
              <span className="label">Faucet</span>
              <small>Public claim path in the market portal</small>
            </div>
            <div className="rail-card">
              <span className="label">Reference pool</span>
              <small>Live DRW / WETH pair in the market portal</small>
            </div>
          </aside>
        </section>

        <section className="home-grid">
          <article className="card home-panel">
            <div className="section-heading">
              <h2>What is live</h2>
              <span className="badge">real surface</span>
            </div>
            <div className="stat-grid">
              <div className="metric">
                <span className="label">Token</span>
                <strong>1B DRW</strong>
                <small>live on Base Sepolia</small>
              </div>
              <div className="metric">
                <span className="label">Faucet claim</span>
                <strong>100 DRW</strong>
                <small>plus native ETH drip</small>
              </div>
              <div className="metric">
                <span className="label">Pool</span>
                <strong>DRW / WETH</strong>
                <small>reference liquidity</small>
              </div>
              <div className="metric">
                <span className="label">First action</span>
                <strong>Tiny swap</strong>
                <small>claim then sell 10 DRW</small>
              </div>
            </div>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>What to do</h2>
              <span className="badge">simple path</span>
            </div>
            <ol className="step-list">
              <li>Open the market page.</li>
              <li>Connect a wallet on Base Sepolia.</li>
              <li>Claim DRW from the faucet.</li>
              <li>Use the `tiny sell` preset for a first public swap.</li>
              <li>Share the epoch or activity link so the next wallet can follow.</li>
              <li>Wrap ETH later if you want to buy from the pool.</li>
            </ol>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>What is still missing</h2>
              <span className="badge">real blockers</span>
            </div>
            <div className="status-ladder">
              <div className="ladder-step">
                <strong>Testnet only</strong>
                <span>Everything here runs on Base Sepolia, not mainnet.</span>
              </div>
              <div className="ladder-step">
                <strong>Reference liquidity</strong>
                <span>The pool is live, but liquidity is still thin and experimental.</span>
              </div>
              <div className="ladder-step">
                <strong>Small amounts</strong>
                <span>Use the faucet and trade conservatively.</span>
              </div>
            </div>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>Public surfaces</h2>
              <span className="badge">repo-backed</span>
            </div>
            <div className="link-row">
              <Link className="button button-secondary" href="/trade/">
                Market page
              </Link>
              <Link className="button button-secondary" href="/activity/">
                Activity page
              </Link>
              <a
                className="button button-secondary"
                href="https://github.com/darwin-protocol/darwin/blob/main/docs/MARKET_BOOTSTRAP.md"
                target="_blank"
                rel="noreferrer"
              >
                Market runbook
              </a>
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}
