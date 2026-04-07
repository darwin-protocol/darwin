import Link from "next/link";
import Script from "next/script";

export const metadata = {
  title: "DARWIN Activity",
  description:
    "Recent DARWIN onchain activity on Base Sepolia: swaps, faucet claims, and community distribution claims.",
  alternates: {
    canonical: "/activity/",
  },
};

const activityScriptVersion = "20260407-activity1";

export default function ActivityPage() {
  return (
    <>
      <Script
        src="https://cdn.jsdelivr.net/npm/ethers@6.14.3/dist/ethers.umd.min.js"
        strategy="afterInteractive"
      />
      <Script src={`../activity.js?v=${activityScriptVersion}`} strategy="afterInteractive" />

      <div className="background">
        <div className="orb orb-a"></div>
        <div className="orb orb-b"></div>
        <div className="grid"></div>
      </div>

      <div className="page-shell">
        <header className="hero card">
          <div className="hero-copy">
            <h2 className="section-title">
              DARWIN <span>activity</span>.
            </h2>
            <p className="lede">
              This page shows recent DARWIN contract activity on Base Sepolia: public swaps, faucet
              claims, and Merkle distributor claims. It is a DARWIN activity feed, not a full chain
              explorer.
            </p>
            <p className="hero-status-line">
              <span id="activityRuntimeStatus">
                <code>usedarwin.xyz</code> is live over HTTPS.
              </span>
            </p>
            <div className="hero-actions">
              <Link className="button button-primary" href="/trade/?preset=tiny-sell">
                Open tiny swap
              </Link>
              <Link className="button button-secondary" href="/trade/">
                Open market
              </Link>
            </div>
          </div>

          <aside className="hero-panel">
            <div className="hero-stat">
              <span className="label">Scope</span>
              <span className="badge">DARWIN contracts only</span>
            </div>
            <div className="hero-stat">
              <span className="label">Network</span>
              <span id="activityChainBadge" className="badge">
                Base Sepolia
              </span>
            </div>
            <div className="hero-stat">
              <span className="label">Feed window</span>
              <span id="activityLookback" className="badge">
                loading
              </span>
            </div>
          </aside>
        </header>

        <main className="layout">
          <section className="card panel">
            <div className="section-heading">
              <h2>Recent counts</h2>
              <button id="activityRefreshButton" className="button button-tertiary">
                Refresh
              </button>
            </div>
            <div className="stat-grid">
              <article className="metric">
                <span className="label">Events</span>
                <strong id="activityCount">-</strong>
                <small>recent DARWIN events</small>
              </article>
              <article className="metric">
                <span className="label">Unique wallets</span>
                <strong id="activityWalletCount">-</strong>
                <small>recent participant addresses</small>
              </article>
              <article className="metric">
                <span className="label">Swaps</span>
                <strong id="activitySwapCount">-</strong>
                <small>reference pool</small>
              </article>
              <article className="metric">
                <span className="label">Claims</span>
                <strong id="activityClaimCount">-</strong>
                <small>faucet + distributor</small>
              </article>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Filters</h2>
              <span id="activityFeedStatus" className="badge">
                loading
              </span>
            </div>
            <div className="tiny-actions">
              <button className="button button-secondary tiny-button is-active" data-activity-filter="all">
                All
              </button>
              <button className="button button-secondary tiny-button" data-activity-filter="swap">
                Swaps
              </button>
              <button className="button button-secondary tiny-button" data-activity-filter="faucet">
                Faucet
              </button>
              <button className="button button-secondary tiny-button" data-activity-filter="distributor">
                Distributor
              </button>
            </div>
            <p id="activityUpdatedAt" className="tiny-hint">
              Waiting for live RPC data.
            </p>
          </section>

          <section className="card panel activity-panel">
            <div className="section-heading">
              <h2>Recent DARWIN activity</h2>
              <span className="badge">onchain</span>
            </div>
            <div id="activityList" className="activity-list">
              <p className="caption">Loading live DARWIN activity.</p>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Useful links</h2>
              <span className="badge">public</span>
            </div>
            <div className="link-row">
              <a id="activityMarketDocLink" href="#" target="_blank" rel="noreferrer">
                Market runbook
              </a>
              <a id="activityRepoLink" href="#" target="_blank" rel="noreferrer">
                Repository
              </a>
            </div>
            <ul className="truth-list">
              <li>This feed shows recent DARWIN-related contracts, not every Base Sepolia transaction.</li>
              <li>Project-controlled and third-party activity both appear here unless you filter off-site.</li>
              <li>For full raw traces, use the linked Base Sepolia explorer.</li>
            </ul>
          </section>
        </main>
      </div>
    </>
  );
}
