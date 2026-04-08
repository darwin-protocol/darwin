import Link from "next/link";
import Script from "next/script";

const siteUrl = "https://usedarwin.xyz";
const searchUrl = `${siteUrl}/search/`;
const miniAppEmbed = JSON.stringify({
  version: "1",
  imageUrl: `${siteUrl}/og-card.png`,
  button: {
    title: "Search DARWIN",
    action: {
      type: "launch_miniapp",
      url: searchUrl,
      name: "Use Darwin",
      splashImageUrl: `${siteUrl}/drw-logo.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});
const frameEmbed = JSON.stringify({
  version: "next",
  imageUrl: `${siteUrl}/og-card.png`,
  button: {
    title: "Search DARWIN",
    action: {
      type: "launch_frame",
      name: "Use Darwin",
      url: searchUrl,
      splashImageUrl: `${siteUrl}/drw-logo.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});

export const metadata = {
  title: "Search DARWIN",
  description:
    "Search DRW transactions, wallets, pools, claims, and governance surfaces across the public Darwin lanes.",
  alternates: {
    canonical: "/search/",
  },
  other: {
    "fc:miniapp": miniAppEmbed,
    "fc:frame": frameEmbed,
  },
};

const searchScriptVersion = "20260408-search1";

export default function SearchPage() {
  return (
    <>
      <Script src={`../lane.js?v=${searchScriptVersion}`} strategy="afterInteractive" />
      <Script
        src="https://cdn.jsdelivr.net/npm/ethers@6.14.3/dist/ethers.umd.min.js"
        strategy="afterInteractive"
      />
      <Script src={`../search.js?v=${searchScriptVersion}`} strategy="afterInteractive" />

      <div className="background">
        <div className="orb orb-a"></div>
        <div className="orb orb-b"></div>
        <div className="grid"></div>
      </div>

      <div className="page-shell">
        <header className="hero card">
          <div className="hero-copy">
            <h2 className="section-title">
              Search <span>DARWIN</span>.
            </h2>
            <p className="lede">
              This is the Darwin-native search surface for the current lane. Look up a transaction,
              wallet, token, pool, faucet, distributor, or timelock from the live public RPC and
              see the parts that matter for DRW.
            </p>
            <p className="hero-status-line">
              <span id="searchRuntimeStatus">
                <code>usedarwin.xyz</code> is live over HTTPS.
              </span>
            </p>
            <div id="searchLaneSwitcher" className="lane-switcher"></div>
            <div className="hero-actions">
              <Link id="searchOpenMarketLink" className="button button-primary" href="/trade/">
                Open market
              </Link>
              <Link id="searchOpenActivityLink" className="button button-secondary" href="/activity/">
                Live activity
              </Link>
              <Link id="searchOpenTinySwapLink" className="button button-secondary" href="/trade/?preset=tiny-sell">
                Tiny swap
              </Link>
              <button id="copySearchLinkButton" className="button button-secondary">
                Copy search link
              </button>
            </div>
          </div>

          <aside className="hero-panel">
            <div className="hero-stat">
              <span className="label">Current lane</span>
              <span id="searchChainBadge" className="badge">
                loading
              </span>
            </div>
            <div className="hero-stat">
              <span className="label">Search scope</span>
              <span className="badge">tx + address</span>
            </div>
            <div className="hero-stat">
              <span className="label">Explorer</span>
              <span id="searchExplorerBadge" className="badge">
                live RPC
              </span>
            </div>
            <div className="hero-stat">
              <span className="label">Attribution</span>
              <span id="searchAttributionBadge" className="badge">
                checking
              </span>
            </div>
          </aside>
        </header>

        <main className="layout">
          <section className="card panel activity-panel">
            <div className="section-heading">
              <h2>Lookup</h2>
              <span id="searchStatusBadge" className="badge">
                idle
              </span>
            </div>
            <label className="field">
              <span>Transaction hash, wallet, or Darwin alias</span>
              <input
                id="searchInput"
                type="text"
                placeholder="0x transaction, 0x wallet, drw, pool, faucet, distributor, timelock"
              />
            </label>
            <div className="tiny-actions">
              <button id="runSearchButton" className="button button-primary tiny-button">
                Search
              </button>
              <button id="clearSearchButton" className="button button-secondary tiny-button">
                Clear
              </button>
              <button id="copySearchQueryLinkButton" className="button button-secondary tiny-button">
                Copy search link
              </button>
            </div>
            <div id="searchQuickActions" className="tiny-actions"></div>
            <p id="searchHint" className="tiny-hint">
              Try <code>drw</code>, <code>pool</code>, <code>faucet</code>, an address, or a
              transaction hash.
            </p>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Summary</h2>
              <span id="searchKindBadge" className="badge">
                waiting
              </span>
            </div>
            <div id="searchSummaryGrid" className="stat-grid">
              <article className="metric">
                <span className="label">Type</span>
                <strong>-</strong>
                <small>transaction or address</small>
              </article>
              <article className="metric">
                <span className="label">Resolved</span>
                <strong>-</strong>
                <small>known Darwin label if matched</small>
              </article>
              <article className="metric">
                <span className="label">Builder Code</span>
                <strong>-</strong>
                <small>suffix detection when relevant</small>
              </article>
              <article className="metric">
                <span className="label">Explorer</span>
                <strong>-</strong>
                <small>current Darwin lane</small>
              </article>
            </div>
            <div className="tiny-actions">
              <a
                id="searchExplorerLink"
                className="button button-secondary tiny-button"
                href="#"
                target="_blank"
                rel="noreferrer"
              >
                Open in explorer
              </a>
              <button id="copyResolvedValueButton" className="button button-secondary tiny-button">
                Copy resolved value
              </button>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Resolved details</h2>
              <span id="searchResolvedBadge" className="badge">
                none
              </span>
            </div>
            <div id="searchDetails" className="detail-grid">
              <p className="caption">
                Run a Darwin search to inspect a transaction, wallet, token, pool, or governance
                surface.
              </p>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>DARWIN state</h2>
              <span id="searchStateBadge" className="badge">
                idle
              </span>
            </div>
            <div id="searchStateGrid" className="stat-grid">
              <article className="metric">
                <span className="label">Native ETH</span>
                <strong>-</strong>
                <small>search a wallet or contract</small>
              </article>
              <article className="metric">
                <span className="label">DRW</span>
                <strong>-</strong>
                <small>current lane token balance</small>
              </article>
              <article className="metric">
                <span className="label">Quote asset</span>
                <strong>-</strong>
                <small>current lane quote token balance</small>
              </article>
              <article className="metric">
                <span className="label">Recent Darwin matches</span>
                <strong>-</strong>
                <small>within the current lookback</small>
              </article>
            </div>
            <p id="searchStateHint" className="tiny-hint">
              Search a wallet or contract to load DRW balances, quote-token balances, pool
              reserves, or recent Darwin activity.
            </p>
          </section>

          <section className="card panel activity-panel">
            <div className="section-heading">
              <h2>Recent Darwin matches</h2>
              <span id="searchMatchesBadge" className="badge">
                idle
              </span>
            </div>
            <div id="searchActivityList" className="activity-list">
              <p className="caption">
                Search a wallet or contract to load matching Darwin events from the current lane.
              </p>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Search notes</h2>
              <span className="badge">Darwin native</span>
            </div>
            <ul className="truth-list">
              <li>This search is lane-aware and reads the live public RPC for the selected lane.</li>
              <li>It decodes Darwin transaction methods and checks Builder Code suffixes when present.</li>
              <li>It is a Darwin-native search surface, not a full generic block explorer clone.</li>
            </ul>
          </section>
        </main>
      </div>
    </>
  );
}
