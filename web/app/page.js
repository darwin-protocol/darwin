import Link from "next/link";
import Script from "next/script";

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
      splashImageUrl: `${siteUrl}/drw-logo.svg`,
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
      splashImageUrl: `${siteUrl}/drw-logo.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});

export const metadata = {
  title: "Use Darwin",
  description:
    "Claim DRW, make a tiny first swap, and track live Darwin market activity across the public Base and Arbitrum testnet lanes.",
  alternates: {
    canonical: "/",
  },
  other: {
    "fc:miniapp": miniAppEmbed,
    "fc:frame": frameEmbed,
  },
};

const homeScriptVersion = "20260408-home5";

const structuredData = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Use Darwin",
  url: "https://usedarwin.xyz",
  description:
    "Claim DRW, make a tiny first swap, and track live Darwin market activity across the public Base and Arbitrum testnet lanes.",
};

export default function HomePage() {
  return (
    <div className="background-shell">
      <Script src={`./lane.js?v=${homeScriptVersion}`} strategy="afterInteractive" />
      <Script src={`./home.js?v=${homeScriptVersion}`} strategy="afterInteractive" />

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
          <div className="brand-row">
            <img className="brand-mark" src="/drw-logo.svg" alt="DRW coin logo" width="72" height="72" />
            <div>
              <p className="eyebrow">USE DARWIN</p>
              <h1 className="plain-title">Live DRW market lanes.</h1>
              <p id="homeHeroStatusLine" className="plain-note">
                Public host: <code>usedarwin.xyz</code>. Base recovery is live now, and the Arbitrum
                Sepolia lane is ready in the same portal.
              </p>
            </div>
          </div>
          <div className="status-banner-meta">
            <span id="homePrimaryLaneBadge" className="badge">Base Sepolia</span>
            <span className="badge">Arbitrum Sepolia</span>
            <span className="badge">DRW live</span>
            <span className="badge">Testnet alpha</span>
          </div>
        </section>

        <section className="card home-hero simple-hero">
          <div className="home-hero-copy">
            <h2 className="section-title">Claim, wrap, and trade.</h2>
            <p className="lede">
              DARWIN is live as a public testnet surface: token, faucet, reference pool, wallet
              portal, and deployment artifact. The first outside action should stay small and
              obvious: claim DRW, then use the canonical tiny swap on the current lane.
            </p>
            <div id="homeLaneSwitcher" className="lane-switcher"></div>
            <div className="hero-actions">
              <Link id="homeOpenMarketLink" className="button button-primary" href="/trade/">
                Open market
              </Link>
              <Link id="homeHeroTinySwapLink" className="button button-secondary" href="/trade/?preset=tiny-sell">
                Try tiny swap
              </Link>
              <Link id="homeHeroEpochLink" className="button button-secondary" href="/epoch/">
                Current epoch
              </Link>
              <Link id="homeHeroJoinLink" className="button button-secondary" href="/join/">
                Join cohort
              </Link>
              <Link id="homeHeroActivityLink" className="button button-secondary" href="/activity/">
                Live activity
              </Link>
              <Link id="homeHeroSearchLink" className="button button-secondary" href="/search/">
                Search Darwin
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
              <small>public testnet market lanes</small>
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
              <h2>Current epoch</h2>
              <span id="homeEpochBadge" className="badge">
                loading
              </span>
            </div>
            <strong id="homeEpochTitle">Loading epoch.</strong>
            <p id="homeEpochSummary" className="caption">
              Waiting for the live Darwin community loop.
            </p>
            <div className="stat-grid">
              <div className="metric">
                <span className="label">Outside wallets</span>
                <strong id="homeExternalWallets">-</strong>
                <small>recent non-project participants</small>
              </div>
              <div className="metric">
                <span className="label">Outside swaps</span>
                <strong id="homeExternalSwaps">-</strong>
                <small>recent non-project swaps</small>
              </div>
              <div className="metric">
                <span className="label">Total events</span>
                <strong id="homeTotalEvents">-</strong>
                <small>recent Darwin contract events</small>
              </div>
              <div className="metric">
                <span className="label">Community state</span>
                <strong id="homeCommunityStatus">loading</strong>
                <small id="homeCommunityUpdatedAt">Waiting for a live community snapshot.</small>
              </div>
            </div>
            <div className="hero-actions">
              <a id="homeEpochLink" className="button button-secondary" href="/epoch/">
                Epoch page
              </a>
              <a id="homeTinySwapLink" className="button button-secondary" href="/trade/?preset=tiny-sell">
                Tiny swap
              </a>
              <a id="homeActivityLink" className="button button-secondary" href="/activity/">
                Public proof
              </a>
              <a id="homeJoinLink" className="button button-secondary" href="/join/">
                Join cohort
              </a>
              <a id="homeSearchLink" className="button button-secondary" href="/search/">
                Search Darwin
              </a>
              <button id="copyInviteButton" className="button button-secondary">
                Copy invite text
              </button>
              <button id="copyTinySwapHomeButton" className="button button-secondary">
                Copy tiny-swap link
              </button>
              <button id="copyActivityHomeButton" className="button button-secondary">
                Copy activity link
              </button>
            </div>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>Pool structure</h2>
              <span id="homePoolStrategyBadge" className="badge">
                loading
              </span>
            </div>
            <p id="homePoolStrategyNote" className="caption">
              Loading the Darwin market-structure policy for this lane.
            </p>
            <div id="homePoolStrategyGrid" className="route-grid">
              <p className="caption">Loading pool routes.</p>
            </div>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>What is live</h2>
              <span className="badge">real surface</span>
            </div>
            <div className="stat-grid">
              <div className="metric">
                <span className="label">Token</span>
                <strong>1B DRW</strong>
                <small>live on Darwin testnet lanes</small>
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
              <li>Connect a wallet on the selected Darwin lane.</li>
              <li>Claim DRW from the faucet.</li>
              <li>Use the `tiny sell` preset for a first public swap.</li>
              <li>Share the epoch or activity link so the next wallet can follow.</li>
              <li>Acquire quote assets later if the lane supports buying from the pool.</li>
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
                <span>Everything here still runs on public testnets, not mainnet.</span>
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
              <Link id="homeMarketPageLink" className="button button-secondary" href="/trade/">
                Market page
              </Link>
              <Link id="homeActivityPageLink" className="button button-secondary" href="/activity/">
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
