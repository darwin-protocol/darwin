import Link from "next/link";
import Script from "next/script";

const siteUrl = "https://usedarwin.xyz";
const epochUrl = `${siteUrl}/epoch/`;
const socialImage = `${siteUrl}/og-epoch-alpha.png`;
const miniAppEmbed = JSON.stringify({
  version: "1",
  imageUrl: socialImage,
  button: {
    title: "Start epoch",
    action: {
      type: "launch_miniapp",
      url: epochUrl,
      name: "Use Darwin",
      splashImageUrl: `${siteUrl}/icon.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});
const frameEmbed = JSON.stringify({
  version: "next",
  imageUrl: socialImage,
  button: {
    title: "Start epoch",
    action: {
      type: "launch_frame",
      name: "Use Darwin",
      url: epochUrl,
      splashImageUrl: `${siteUrl}/icon.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});

export const metadata = {
  title: "DARWIN Epoch",
  description:
    "Claim DRW, make one tiny swap, and share the public Darwin activity surface.",
  alternates: {
    canonical: "/epoch/",
  },
  openGraph: {
    images: [{ url: "/og-epoch-alpha.png", width: 1200, height: 630, alt: "DARWIN Epoch Alpha" }],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/og-epoch-alpha.png"],
  },
  other: {
    "fc:miniapp": miniAppEmbed,
    "fc:frame": frameEmbed,
  },
};

export default function EpochPage() {
  return (
    <div className="background-shell">
      <Script src="../lane.js?v=20260408-epoch2" strategy="afterInteractive" />
      <Script src="../epoch.js?v=20260408-epoch2" strategy="afterInteractive" />
      <div className="background">
        <div className="orb orb-a"></div>
        <div className="orb orb-b"></div>
        <div className="grid"></div>
      </div>

      <main className="home-shell">
        <section className="card status-banner compact-banner">
          <div>
            <p className="eyebrow">DARWIN EPOCH</p>
            <h1 className="plain-title">Epoch Alpha: claim, tiny swap, share.</h1>
            <p id="epochSummaryLine" className="plain-note">
              The first outside Darwin actions should be small, public, and easy to repeat.
            </p>
          </div>
          <div className="status-banner-meta">
            <span className="badge">live</span>
            <span className="badge">tiny-swap path</span>
            <span className="badge">public proof</span>
          </div>
        </section>

        <section className="card home-hero simple-hero">
          <div className="home-hero-copy">
            <h2 className="section-title">Start with one visible action.</h2>
            <p className="lede">
              Darwin should not ask for blind conviction. It should offer a tiny, legible first
              move: claim DRW, use a tiny preset, and see the result on the public activity feed.
            </p>
            <div id="epochLaneSwitcher" className="lane-switcher"></div>
            <div className="hero-actions">
              <Link id="epochTinySellLink" className="button button-primary" href="/trade/?preset=tiny-sell">
                Start tiny sell
              </Link>
              <Link id="epochTinyBuyLink" className="button button-secondary" href="/trade/?preset=tiny-buy">
                Start tiny buy
              </Link>
              <Link id="epochActivityLink" className="button button-secondary" href="/activity/">
                View public activity
              </Link>
            </div>
          </div>

          <aside className="home-hero-panel simple-panel">
            <div className="rail-card">
              <span className="label">Step 1</span>
              <small>Claim 100 DRW from the public faucet.</small>
            </div>
            <div className="rail-card">
              <span className="label">Step 2</span>
              <small>Use a tiny preset to make one first market action.</small>
            </div>
            <div className="rail-card">
              <span className="label">Step 3</span>
              <small>Share the activity page so the next wallet can follow.</small>
            </div>
          </aside>
        </section>

        <section className="home-grid">
          <article className="card home-panel">
            <div className="section-heading">
              <h2>Epoch progress</h2>
              <span id="epochProgressBadge" className="badge">
                loading
              </span>
            </div>
            <div className="stat-grid">
              <article className="metric">
                <span className="label">Wallet goal</span>
                <strong id="epochWalletProgress">-</strong>
                <small id="epochWalletProgressDetail">Waiting for wallet progress.</small>
              </article>
              <article className="metric">
                <span className="label">Swap goal</span>
                <strong id="epochSwapProgress">-</strong>
                <small id="epochSwapProgressDetail">Waiting for swap progress.</small>
              </article>
            </div>
            <p id="epochProgressNote" className="tiny-hint">
              Canonical traction should be earned by real outside wallets, not internal churn.
            </p>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>Reward pilot</h2>
              <span id="epochRewardWindow" className="badge">
                loading
              </span>
            </div>
            <ul id="epochRewardRules" className="truth-list">
              <li>Loading reward rules.</li>
            </ul>
          </article>
        </section>

        <section className="card home-panel activity-panel">
          <div className="section-heading">
            <h2>Outside leaderboard</h2>
            <span id="epochLeaderboardBadge" className="badge">
              loading
            </span>
          </div>
          <div id="epochLeaderboardList" className="leaderboard-list">
            <p className="caption">Loading outside-wallet leaderboard.</p>
          </div>
        </section>

        <section className="home-grid">
          <article className="card home-panel">
            <div className="section-heading">
              <h2>Why this epoch</h2>
              <span className="badge">Darwin ethos</span>
            </div>
            <div className="status-ladder">
              <div className="ladder-step">
                <strong>Small first action</strong>
                <span>Outside wallets should not need to commit large size or guess at opaque mechanics.</span>
              </div>
              <div className="ladder-step">
                <strong>Visible proof</strong>
                <span>Claims and swaps should show up on the public activity page quickly.</span>
              </div>
              <div className="ladder-step">
                <strong>Evolving campaign</strong>
                <span>The social incentive can change by epoch without mutating the token unpredictably.</span>
              </div>
            </div>
          </article>

          <article className="card home-panel">
            <div className="section-heading">
              <h2>Public surfaces</h2>
              <span className="badge">shareable</span>
            </div>
            <div className="link-row">
              <Link className="button button-secondary" href="/trade/?preset=tiny-sell">
                Tiny sell
              </Link>
              <Link className="button button-secondary" href="/trade/?preset=tiny-buy">
                Tiny buy
              </Link>
              <Link className="button button-secondary" href="/activity/">
                Activity portal
              </Link>
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}
