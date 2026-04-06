import Link from "next/link";

export const metadata = {
  title: "Use Darwin",
  description:
    "Claim testnet DRW, wrap Base Sepolia ETH, and trade against the live DARWIN reference pool.",
  alternates: {
    canonical: "/",
  },
};

export default function HomePage() {
  return (
    <div className="background-shell">
      <div className="background">
        <div className="orb orb-a"></div>
        <div className="orb orb-b"></div>
        <div className="grid"></div>
      </div>

      <main className="home-shell">
        <section className="card home-hero">
          <div className="home-hero-copy">
            <p className="eyebrow">USE DARWIN</p>
            <h1>
              A live testnet market for <span>DRW</span>.
            </h1>
            <p className="lede">
              Darwin Protocol is a peer-to-peer market infrastructure project with a live Base
              Sepolia token, public faucet, and reference pool. The current milestone is not hype.
              It is getting real outside wallets to claim, trade, and observe the canary.
            </p>
            <div className="hero-actions">
              <Link className="button button-primary" href="/trade/">
                Open the market
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
                GitHub repo
              </a>
            </div>
          </div>

          <aside className="home-hero-panel">
            <div className="hero-stat">
              <span className="label">Chain</span>
              <span className="badge">Base Sepolia</span>
            </div>
            <div className="hero-stat">
              <span className="label">Token</span>
              <code>DRW</code>
            </div>
            <div className="hero-stat">
              <span className="label">Faucet</span>
              <code>0x3DAa...bAe0</code>
            </div>
            <div className="hero-stat">
              <span className="label">Pool</span>
              <code>0x9E1f...B891</code>
            </div>
          </aside>
        </section>

        <section className="home-grid">
          <article className="card home-panel">
            <div className="section-heading">
              <h2>What is live now</h2>
              <span className="badge">real testnet surface</span>
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
                <small>plus 0.00001 ETH drip</small>
              </div>
              <div className="metric">
                <span className="label">Reference pool</span>
                <strong>DRW / WETH</strong>
                <small>artifact-backed pool</small>
              </div>
              <div className="metric">
                <span className="label">Portal</span>
                <strong>Wallet-driven</strong>
                <small>claim, wrap, swap</small>
              </div>
            </div>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>How to use it</h2>
              <span className="badge">simple path</span>
            </div>
            <ol className="step-list">
              <li>Connect a browser wallet on Base Sepolia.</li>
              <li>Claim DRW from the public faucet.</li>
              <li>Wrap a small amount of ETH into WETH if you want to buy from the pool.</li>
              <li>Trade against the live DARWIN reference pool.</li>
              <li>Share the market with outside testers instead of generating fake activity.</li>
            </ol>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>Why this matters</h2>
              <span className="badge">honest alpha</span>
            </div>
            <ul className="truth-list">
              <li>The current market is live, but still mostly project-controlled.</li>
              <li>The public faucet exists to create real outside holders, not synthetic demand.</li>
              <li>The canary still needs outside watchers and outside archive flow.</li>
              <li>The meaningful next milestone is third-party claims and trades, not more internal churn.</li>
            </ul>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>Public surfaces</h2>
              <span className="badge">repo-backed</span>
            </div>
            <div className="link-row">
              <Link className="button button-secondary" href="/trade/">
                Trade and claim
              </Link>
              <a
                className="button button-secondary"
                href="https://github.com/darwin-protocol/darwin/blob/main/docs/MARKET_BOOTSTRAP.md"
                target="_blank"
                rel="noreferrer"
              >
                Market bootstrap
              </a>
              <a
                className="button button-secondary"
                href="https://github.com/darwin-protocol/darwin/blob/main/docs/OPERATOR_QUICKSTART.md"
                target="_blank"
                rel="noreferrer"
              >
                Operator quickstart
              </a>
              <a
                className="button button-secondary"
                href="https://github.com/darwin-protocol/darwin/blob/main/ops/deployments/base-sepolia.json"
                target="_blank"
                rel="noreferrer"
              >
                Deployment artifact
              </a>
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}
