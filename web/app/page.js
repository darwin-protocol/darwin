import Link from "next/link";
import BrandMark from "../components/BrandMark";
import SiteHeader from "../components/SiteHeader";

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
        <SiteHeader />

        <section className="card home-hero">
          <div className="home-hero-copy">
            <div className="eyebrow-row">
              <p className="eyebrow">USE DARWIN</p>
              <span className="status-chip">LIVE ON BASE SEPOLIA</span>
            </div>
            <h1>
              A live market surface for <span>DRW</span>.
            </h1>
            <p className="lede">
              Darwin Protocol now has a branded public entry point: a live testnet token, public
              faucet, reference pool, and wallet-driven market portal. The next milestone is
              straightforward: move from DARWIN-controlled bootstrapping to real outside claims,
              swaps, and watchers.
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
            <div className="hero-stat-grid">
              <div className="metric">
                <span className="label">Canonical host</span>
                <strong>usedarwin.xyz</strong>
                <small>GitHub Pages custom domain</small>
              </div>
              <div className="metric">
                <span className="label">Market path</span>
                <strong>/trade</strong>
                <small>connect, claim, wrap, swap</small>
              </div>
              <div className="metric">
                <span className="label">Current pool</span>
                <strong>DRW / WETH</strong>
                <small>Base Sepolia reference liquidity</small>
              </div>
            </div>
          </div>

          <aside className="home-hero-panel">
            <div className="coin-panel">
              <BrandMark className="coin-mark" title="DRW coin mark" />
              <div className="coin-stack">
                <span className="coin-tag">TOKEN</span>
                <strong>DRW</strong>
                <span>Darwin is the wallet-visible token layer for the live DARWIN alpha.</span>
              </div>
            </div>
            <div className="hero-rail">
              <div className="rail-card">
                <span className="label">Faucet</span>
                <code>0x3DAa...bAe0</code>
              </div>
              <div className="rail-card">
                <span className="label">Reference pool</span>
                <code>0x9E1f...B891</code>
              </div>
              <div className="rail-card">
                <span className="label">Token contract</span>
                <code>0x9051...0FF2</code>
              </div>
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
              <h2>Why bots will notice it</h2>
              <span className="badge">but still alpha</span>
            </div>
            <ul className="truth-list">
              <li>The token, pool, faucet, and portal are all public and machine-readable.</li>
              <li>Wallets can import DRW directly from the portal using the token image and metadata.</li>
              <li>Reference liquidity exists, but it is still DARWIN-owned bootstrap liquidity.</li>
              <li>Real usage only starts counting once outside wallets claim and trade.</li>
            </ul>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>What still needs to happen</h2>
              <span className="badge">honest next steps</span>
            </div>
            <div className="status-ladder">
              <div className="ladder-step">
                <strong>Outside holders</strong>
                <span>Get claims from wallets that are not DARWIN-controlled.</span>
              </div>
              <div className="ladder-step">
                <strong>Outside trading</strong>
                <span>Replace internal demo trades with third-party swaps.</span>
              </div>
              <div className="ladder-step">
                <strong>Outside watchers</strong>
                <span>Run the canary with an external watcher and a real archive epoch.</span>
              </div>
              <div className="ladder-step">
                <strong>Review</strong>
                <span>Land the independent audit/review response and close any findings.</span>
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
