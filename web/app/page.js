import Link from "next/link";
import Script from "next/script";
import { readFile } from "node:fs/promises";
import path from "node:path";
import {
  communityStateText,
  communityUpdatedText,
  laneHref,
  loadPublishedLaneData,
  shortAddress,
} from "./lib/publishedLaneData";

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

const PUBLIC_DIR = path.join(process.cwd(), "public");
const DEFAULT_NODE_FLEET = {
  availability: {
    public_total: 0,
    public_live: 0,
    public_parked: 0,
    public_staged: 0,
    public_summary: "node availability not published yet",
    note: "Aggregate availability only. Per-node operator state stays private.",
  },
};

async function readPublicJson(publicPath, fallback) {
  try {
    const filePath = path.join(PUBLIC_DIR, String(publicPath || "").replace(/^\/+/, ""));
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function renderPoolCard(pool, selection) {
  return (
    <article key={pool.id || pool.label} className={`route-card route-${pool.derivedStatus || pool.status || "locked"}`}>
      <div className="route-top">
        <strong>{pool.label || pool.id || "Pool"}</strong>
        <span className="badge">{pool.derivedStatus || pool.status || "locked"}</span>
      </div>
      <p className="caption">{pool.purpose || ""}</p>
      <p className="tiny-hint">
        {pool.isDefault
          ? `Default route. ${pool.reason || ""}`.trim()
          : `${pool.progressLabel}. ${pool.reason || ""}`.trim()}
      </p>
      {pool.pool_address ? (
        <span className="label">Pool {shortAddress(pool.pool_address)}</span>
      ) : null}
      {pool.enabled && pool.entry_path ? (
        <a className="button button-secondary tiny-button" href={laneHref(pool.entry_path, selection)}>
          {pool.entry_label || "Open route"}
        </a>
      ) : null}
    </article>
  );
}

export default async function HomePage() {
  const selection = await loadPublishedLaneData();
  const nodeFleet = await readPublicJson("/node-fleet.json", DEFAULT_NODE_FLEET);
  const current = selection.current || {};
  const config = current.config || {};
  const share = current.share || {};
  const stats = current.stats || {};
  const structure = current.structure || { defaultEntry: "canonical", summary: "", pools: [] };
  const currentNetworkName = config.network?.name || current.lane?.name || "Base Sepolia";
  const epoch = share.epoch || config.community?.epoch || {};
  const eligibleWallets = Number(stats.eligible_wallets ?? stats.external_wallets ?? 0);
  const eligibleSwaps = Number(stats.eligible_swaps ?? stats.external_swaps ?? 0);
  const totalEvents = Number(stats.total_events ?? 0);
  const marketHref = laneHref("/trade/", selection);
  const tinySwapHref = laneHref(config.community?.tiny_swap_path || "/trade/?preset=tiny-sell", selection);
  const activityHref = laneHref(config.community?.activity_path || "/activity/", selection);
  const epochHref = laneHref(config.community?.epoch_path || "/epoch/", selection);
  const joinHref = laneHref(config.community?.starter_cohort_path || "/join/", selection);
  const searchHref = laneHref("/search/", selection);
  const extraLanes = selection.lanes.filter((lane) => lane.slug !== selection.defaultLane.slug);
  const fleetAvailability = nodeFleet.availability || DEFAULT_NODE_FLEET.availability;

  return (
    <div className="background-shell">
      <Script src="./lane.js?v=20260409-home9" strategy="afterInteractive" />
      <Script src="./home.js?v=20260409-home9" strategy="afterInteractive" />

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
              <span id="homePrimaryLaneBadge" className="badge">{currentNetworkName}</span>
              {extraLanes.map((lane) => (
                <span key={lane.slug} className="badge">{lane.name || lane.network?.name || lane.slug}</span>
              ))}
              <span className="badge">DRW testnet</span>
            </div>
            <h1 className="plain-title">Claim DRW. Start with one tiny trade.</h1>
            <p className="lede">
              Darwin is a live testnet market surface. Claim from the faucet, run the tiny sell
              through the reference pool, then confirm the result on the activity page.
            </p>
            <p id="homeHeroStatusLine" className="plain-note">
              Public host: <code>usedarwin.xyz</code>. Current lane: <code>{currentNetworkName}</code>.
            </p>
            <div id="homeLaneSwitcher" className="lane-switcher">
              {selection.lanes.map((lane) => (
                <a
                  key={lane.slug}
                  className={`button button-secondary tiny-button${lane.slug === selection.defaultLane.slug ? " is-active" : ""}`}
                  href={laneHref("/", selection, lane)}
                >
                  {lane.name || lane.network?.name || lane.slug}
                </a>
              ))}
            </div>
            <div className="hero-actions">
              <Link id="homeOpenMarketLink" className="button button-primary" href={marketHref}>
                Open market
              </Link>
              <Link id="homeHeroTinySwapLink" className="button button-secondary" href={tinySwapHref}>
                Tiny sell preset
              </Link>
              <Link id="homeHeroActivityLink" className="button button-secondary" href={activityHref}>
                Live activity
              </Link>
            </div>
            <div className="link-row">
              <a id="homeEpochLink" className="button button-secondary" href={epochHref}>
                Current epoch
              </a>
              <a id="homeJoinLink" className="button button-secondary" href={joinHref}>
                Join cohort
              </a>
              <Link id="homeHeroSearchLink" className="button button-secondary" href={searchHref}>
                Search Darwin
              </Link>
            </div>
          </div>

          <aside className="home-hero-panel simple-panel">
            <div className="section-heading">
              <h2>Start here</h2>
              <span id="homeEpochBadge" className="badge">
                {epoch.status || "live"}
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
            <strong id="homeEpochTitle">{epoch.title || "Epoch Alpha"}</strong>
            <p id="homeEpochSummary" className="caption">
              {epoch.summary || "Claim DRW, make one tiny swap, and share the public proof surface."}
            </p>
            <div className="stat-grid">
              <div className="metric">
                <span className="label">Eligible wallets</span>
                <strong id="homeExternalWallets">{eligibleWallets}</strong>
                <small>swap-active outside participants</small>
              </div>
              <div className="metric">
                <span className="label">Outside swaps</span>
                <strong id="homeExternalSwaps">{eligibleSwaps}</strong>
                <small>recent non-project swaps</small>
              </div>
              <div className="metric">
                <span className="label">Total events</span>
                <strong id="homeTotalEvents">{totalEvents}</strong>
                <small>recent Darwin contract events</small>
              </div>
              <div className="metric">
                <span className="label">Community state</span>
                <strong id="homeCommunityStatus">{communityStateText(stats)}</strong>
                <small id="homeCommunityUpdatedAt">{communityUpdatedText(share)}</small>
              </div>
            </div>
            <div className="link-row">
              <button id="copyInviteButton" className="button button-secondary">
                Copy invite text
              </button>
              <Link id="homeActivityPageLink" className="button button-secondary" href={activityHref}>
                Activity page
              </Link>
            </div>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>Pool structure</h2>
              <span id="homePoolStrategyBadge" className="badge">
                {structure.defaultEntry || "canonical"}
              </span>
            </div>
            <p id="homePoolStrategyNote" className="caption">
              {structure.summary || "Keep one canonical pool live until outside usage is real, then unlock the next Darwin routes."}
            </p>
            <div id="homePoolStrategyGrid" className="route-grid">
              {structure.pools.map((pool) => renderPoolCard(pool, selection))}
            </div>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>Node availability</h2>
              <span className="badge">{fleetAvailability.public_summary || "aggregate only"}</span>
            </div>
            <p className="caption">
              This site only publishes aggregate Darwin availability. Per-node operator state stays
              private.
            </p>
            <div className="stat-grid">
              <div className="metric">
                <span className="label">Public lanes online</span>
                <strong>{Number(fleetAvailability.public_live ?? 0)}</strong>
                <small>aggregate only</small>
              </div>
              <div className="metric">
                <span className="label">Parked for capacity</span>
                <strong>{Number(fleetAvailability.public_parked ?? 0)}</strong>
                <small>hardware or storage constrained</small>
              </div>
              <div className="metric">
                <span className="label">Provisioned lanes</span>
                <strong>{Number(fleetAvailability.public_staged ?? 0)}</strong>
                <small>not currently online</small>
              </div>
              <div className="metric">
                <span className="label">Disclosure</span>
                <strong>Aggregate only</strong>
                <small>{fleetAvailability.note || "Per-node operator state stays private."}</small>
              </div>
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
