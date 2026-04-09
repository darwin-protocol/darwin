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
    "Claim DRW, make a tiny testnet trade, and confirm it on the live Darwin activity feed.",
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
    "Claim DRW, make a tiny testnet trade, and confirm it on the live Darwin activity feed.",
};

export default function HomePage() {
  return (
    <div className="background-shell">
      <Script src="./lane.js?v=20260409-home8" strategy="afterInteractive" />
      <Script src="./home.js?v=20260409-home8" strategy="afterInteractive" />

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
        <section className="card home-hero simple-hero">
          <div className="home-hero-copy">
            <p className="eyebrow">USE DARWIN</p>
            <div className="status-banner-meta">
              <span id="homePrimaryLaneBadge" className="badge">Base Sepolia</span>
              <span className="badge">Arbitrum Sepolia</span>
              <span className="badge">DRW testnet</span>
            </div>
            <h1 className="plain-title">Claim DRW. Start with one tiny trade.</h1>
            <p className="lede">
              Darwin is a live testnet market surface. Claim from the faucet, run the tiny sell
              through the reference pool, then confirm the result on the activity page.
            </p>
            <p id="homeHeroStatusLine" className="plain-note">
              Public host: <code>usedarwin.xyz</code>. Base and Arbitrum Sepolia are both available
              from the same portal.
            </p>
            <div id="homeLaneSwitcher" className="lane-switcher"></div>
            <div className="hero-actions">
              <Link id="homeOpenMarketLink" className="button button-primary" href="/trade/">
                Open market
              </Link>
              <Link id="homeHeroTinySwapLink" className="button button-secondary" href="/trade/?preset=tiny-sell">
                Tiny sell preset
              </Link>
              <Link id="homeHeroActivityLink" className="button button-secondary" href="/activity/">
                Live activity
              </Link>
            </div>
            <div className="link-row">
              <a id="homeEpochLink" className="button button-secondary" href="/epoch/">
                Current epoch
              </a>
              <a id="homeJoinLink" className="button button-secondary" href="/join/">
                Join cohort
              </a>
              <Link id="homeHeroSearchLink" className="button button-secondary" href="/search/">
                Search Darwin
              </Link>
            </div>
          </div>

          <aside className="home-hero-panel simple-panel">
            <div className="section-heading">
              <h2>Start here</h2>
              <span id="homeEpochBadge" className="badge">
                loading
              </span>
            </div>
            <div className="status-ladder">
              <div className="ladder-step">
                <strong>1. Claim</strong>
                <span>Pull DRW from the faucet on the selected lane.</span>
              </div>
              <div className="ladder-step">
                <strong>2. Sell 10 DRW</strong>
                <span>Use the tiny sell preset through the canonical pool.</span>
              </div>
              <div className="ladder-step">
                <strong>3. Check the feed</strong>
                <span>Open activity and confirm the trade landed where you expect.</span>
              </div>
            </div>
            <p className="tiny-hint">
              This is the shortest honest Darwin loop. Nothing here requires mainnet funds.
            </p>
          </aside>
        </section>

        <section className="home-grid">
          <article className="card home-panel">
            <div className="section-heading">
              <h2>Current lane</h2>
              <span className="badge">live data</span>
            </div>
            <strong id="homeEpochTitle">Loading epoch.</strong>
            <p id="homeEpochSummary" className="caption">
              Waiting for the live Darwin community loop.
            </p>
            <div className="stat-grid">
              <div className="metric">
                <span className="label">Eligible wallets</span>
                <strong id="homeExternalWallets">-</strong>
                <small>swap-active outside participants</small>
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
            <div className="link-row">
              <button id="copyInviteButton" className="button button-secondary">
                Copy invite text
              </button>
              <Link id="homeActivityPageLink" className="button button-secondary" href="/activity/">
                Activity page
              </Link>
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

          <article className="card home-panel activity-panel">
            <div className="section-heading">
              <h2>Ground rules</h2>
              <span className="badge">read once</span>
            </div>
            <div className="status-ladder">
              <div className="ladder-step">
                <strong>Testnet only</strong>
                <span>Base Sepolia and Arbitrum Sepolia are live here. Nothing on this surface is mainnet.</span>
              </div>
              <div className="ladder-step">
                <strong>Start tiny</strong>
                <span>Liquidity is still thin. The right first trade is small enough to inspect, not to optimize.</span>
              </div>
              <div className="ladder-step">
                <strong>Only swaps count</strong>
                <span>Unlocks and leaderboard progress count swap-active wallets, not claim-only wallets.</span>
              </div>
            </div>
            <div className="link-row">
              <a
                className="button button-secondary"
                href="https://github.com/darwin-protocol/darwin/blob/main/docs/MARKET_BOOTSTRAP.md"
                target="_blank"
                rel="noreferrer"
              >
                Market runbook
              </a>
              <a
                className="button button-secondary"
                href="https://github.com/darwin-protocol/darwin/blob/main/docs/COMMUNITY_BOOTSTRAP.md"
                target="_blank"
                rel="noreferrer"
              >
                Community bootstrap
              </a>
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}
