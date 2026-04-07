import Link from "next/link";
import Script from "next/script";

const siteUrl = "https://usedarwin.xyz";
const activityUrl = `${siteUrl}/activity/`;
const miniAppEmbed = JSON.stringify({
  version: "1",
  imageUrl: `${siteUrl}/og-card.png`,
  button: {
    title: "View DARWIN",
    action: {
      type: "launch_miniapp",
      url: activityUrl,
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
    title: "View DARWIN",
    action: {
      type: "launch_frame",
      name: "Use Darwin",
      url: activityUrl,
      splashImageUrl: `${siteUrl}/icon.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});

export const metadata = {
  title: "DARWIN Activity",
  description:
    "Recent DARWIN onchain activity on Base Sepolia: swaps, faucet claims, and community distribution claims.",
  alternates: {
    canonical: "/activity/",
  },
  other: {
    "fc:miniapp": miniAppEmbed,
    "fc:frame": frameEmbed,
  },
};

const activityScriptVersion = "20260407-activity4";

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
              <Link className="button button-secondary" href="/epoch/">
                Open epoch
              </Link>
              <Link className="button button-secondary" href="/trade/">
                Open market
              </Link>
              <button id="copyTinySwapButton" className="button button-secondary">
                Copy tiny-swap link
              </button>
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
              <h2>Outside activity</h2>
              <span id="communityStatusBadge" className="badge">
                loading
              </span>
            </div>
            <div className="stat-grid">
              <article className="metric">
                <span className="label">External events</span>
                <strong id="externalEventCount">-</strong>
                <small>outside-vs-project classified locally</small>
              </article>
              <article className="metric">
                <span className="label">External wallets</span>
                <strong id="externalWalletCount">-</strong>
                <small>outside actors in the current window</small>
              </article>
              <article className="metric">
                <span className="label">External swaps</span>
                <strong id="externalSwapCount">-</strong>
                <small>non-project swap activity</small>
              </article>
              <article className="metric">
                <span className="label">External claims</span>
                <strong id="externalClaimCount">-</strong>
                <small>faucet + distributor claims</small>
              </article>
            </div>
            <p id="communityUpdatedAt" className="tiny-hint">
              Waiting for the public activity snapshot.
            </p>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Current epoch</h2>
              <span id="epochBadge" className="badge">
                loading
              </span>
            </div>
            <strong id="epochTitle">Loading epoch.</strong>
            <p id="epochSummary" className="caption">
              Waiting for the live Darwin campaign surface.
            </p>
            <p id="epochFocus" className="tiny-hint">
              Public onboarding should stay small, visible, and easy to repeat.
            </p>
            <ul id="epochGoals" className="truth-list">
              <li>Loading epoch goals.</li>
            </ul>
            <div className="tiny-actions">
              <a id="epochCtaLink" className="button button-primary tiny-button" href="/trade/?preset=tiny-sell">
                Start epoch
              </a>
              <a id="epochActivityLink" className="button button-secondary tiny-button" href="/activity/">
                Public proof
              </a>
              <button id="copyEpochLinkButton" className="button button-secondary tiny-button">
                Copy epoch link
              </button>
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

          <section className="card panel activity-panel">
            <div className="section-heading">
              <h2>Contract surface</h2>
              <span className="badge">public addresses</span>
            </div>
            <div id="activityContracts" className="contract-grid">
              <p className="caption">Loading contract addresses.</p>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Share and links</h2>
              <span className="badge">public</span>
            </div>
            <div className="tiny-actions">
              <button id="copyActivityLinkButton" className="button button-secondary tiny-button">
                Copy activity link
              </button>
              <button id="shareActivityButton" className="button button-secondary tiny-button">
                Share activity
              </button>
              <button id="copyTinySwapLinkButton" className="button button-secondary tiny-button">
                Copy tiny-swap link
              </button>
              <button id="copyEpochShareButton" className="button button-secondary tiny-button">
                Copy epoch link
              </button>
            </div>
            <div className="link-row">
              <a id="activityMarketDocLink" href="#" target="_blank" rel="noreferrer">
                Market runbook
              </a>
              <a id="activityCommunityDocLink" href="#" target="_blank" rel="noreferrer">
                Community bootstrap
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

          <section className="card panel">
            <div className="section-heading">
              <h2>Explorer lookup</h2>
              <span className="badge">quick jump</span>
            </div>
            <label className="field">
              <span>Address or transaction hash</span>
              <input
                id="explorerLookupInput"
                type="text"
                placeholder="0x wallet or 0x transaction hash"
              />
            </label>
            <div className="tiny-actions">
              <button id="openExplorerLookupButton" className="button button-secondary tiny-button">
                Open in explorer
              </button>
            </div>
            <p id="explorerLookupStatus" className="tiny-hint">
              Paste any Darwin-related address or transaction hash to open the Base Sepolia explorer.
            </p>
          </section>
        </main>
      </div>
    </>
  );
}
