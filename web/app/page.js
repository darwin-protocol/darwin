import Link from "next/link";

export const metadata = {
  title: "Use Darwin",
  description:
    "Claim testnet DRW, wrap Base Sepolia ETH, and trade against the live DARWIN reference pool.",
  alternates: {
    canonical: "/",
  },
};

const structuredData = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Use Darwin",
  url: "https://usedarwin.xyz",
  description:
    "Claim testnet DRW, wrap Base Sepolia ETH, and trade against the live DARWIN reference pool.",
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
              portal, and deployment artifact. The important next step is outside users, not more
              internal churn.
            </p>
            <div className="hero-actions">
              <Link className="button button-primary" href="/trade/">
                Open market
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
                <span className="label">Faucet</span>
                <strong>100 DRW</strong>
                <small>plus native ETH drip</small>
              </div>
              <div className="metric">
                <span className="label">Pool</span>
                <strong>DRW / WETH</strong>
                <small>reference liquidity</small>
              </div>
              <div className="metric">
                <span className="label">Portal</span>
                <strong>/trade</strong>
                <small>wallet connect + swap</small>
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
              <li>Wrap ETH into WETH if you want to buy from the pool.</li>
              <li>Use the QR request flow for direct peer-to-peer sends.</li>
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
