import Link from "next/link";
import Script from "next/script";

const siteUrl = "https://usedarwin.xyz";

export const metadata = {
  title: "Join Starter Cohort",
  description:
    "Prepare a public-safe DRW starter-cohort row and route that wallet into the canonical tiny-swap path.",
  alternates: {
    canonical: "/join/",
  },
};

const joinScriptVersion = "20260407-join1";

export default function JoinPage() {
  return (
    <>
      <Script src={`../lane.js?v=${joinScriptVersion}`} strategy="afterInteractive" />
      <Script src={`../join.js?v=${joinScriptVersion}`} strategy="afterInteractive" />

      <div className="background">
        <div className="orb orb-a"></div>
        <div className="orb orb-b"></div>
        <div className="grid"></div>
      </div>

      <div className="page-shell">
        <header className="hero card">
          <div className="hero-copy">
            <h2 className="section-title">
              Join the <span>starter cohort</span>.
            </h2>
            <p className="lede">
              This page does not submit a wallet anywhere. It prepares a clean cohort row that you
              can hand to the Darwin operator, then routes that wallet into the canonical tiny-swap
              path once the cohort is funded.
            </p>
            <div id="joinLaneSwitcher" className="lane-switcher"></div>
            <div className="hero-actions">
              <button id="joinUseConnectedWalletButton" className="button button-primary">
                Use connected wallet
              </button>
              <Link id="joinTradeLink" className="button button-secondary" href="/trade/?preset=tiny-sell">
                Tiny swap path
              </Link>
              <Link id="joinEpochLink" className="button button-secondary" href="/epoch/">
                Current epoch
              </Link>
              <Link id="joinActivityLink" className="button button-secondary" href="/activity/">
                Public proof
              </Link>
            </div>
          </div>

          <aside className="hero-panel">
            <div className="hero-stat">
              <span className="label">Lane</span>
              <span id="joinLaneBadge" className="badge">
                loading
              </span>
            </div>
            <div className="hero-stat">
              <span className="label">Starter amount</span>
              <strong id="joinStarterAmount">-</strong>
            </div>
            <div className="hero-stat">
              <span className="label">Outside wallets</span>
              <strong id="joinExternalWallets">-</strong>
            </div>
            <div className="hero-stat">
              <span className="label">Outside swaps</span>
              <strong id="joinExternalSwaps">-</strong>
            </div>
          </aside>
        </header>

        <main className="layout">
          <section className="card panel">
            <div className="section-heading">
              <h2>Wallet intake</h2>
              <span className="badge">public-safe</span>
            </div>
            <label className="field">
              <span>Wallet address</span>
              <input id="joinWalletAddress" type="text" placeholder="0x..." />
            </label>
            <div className="inline-fields">
              <label className="field">
                <span>Handle or label</span>
                <input id="joinWalletLabel" type="text" placeholder="@you or cohort note" />
              </label>
              <label className="field">
                <span>Source</span>
                <input id="joinWalletSource" type="text" value="starter-cohort" />
              </label>
            </div>
            <label className="field">
              <span>Notes</span>
              <input id="joinWalletNotes" type="text" placeholder="optional public-safe note" />
            </label>
            <p className="caption">
              The exported row uses raw DRW units and the current Darwin lane slug so it can go
              straight into the starter-cohort ops flow.
            </p>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Export row</h2>
              <span id="joinRowStatus" className="badge">
                waiting
              </span>
            </div>
            <label className="field">
              <span>CSV row</span>
              <textarea id="joinCsvRow" rows="4" readOnly></textarea>
            </label>
            <label className="field">
              <span>JSON row</span>
              <textarea id="joinJsonRow" rows="7" readOnly></textarea>
            </label>
            <div className="hero-actions">
              <button id="joinCopyCsvButton" className="button button-secondary">
                Copy CSV row
              </button>
              <button id="joinCopyJsonButton" className="button button-secondary">
                Copy JSON row
              </button>
              <button id="joinDownloadCsvButton" className="button button-secondary">
                Download one-row CSV
              </button>
              <button id="joinCopyInviteButton" className="button button-secondary">
                Copy invite packet
              </button>
            </div>
            <p id="joinExportHint" className="tiny-hint">
              Enter a valid wallet to prepare a starter-cohort row.
            </p>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Next move</h2>
              <span className="badge">honest flow</span>
            </div>
            <ol className="step-list">
              <li>Prepare one clean wallet row from this page.</li>
              <li>Send that row to the Darwin operator or add it to the starter cohort CSV.</li>
              <li>After the cohort is funded, claim DRW or receive the cohort allocation.</li>
              <li>Use the canonical tiny-swap path for the first public action.</li>
            </ol>
            <p className="caption">
              The goal is real outside participation. This page is for opt-in wallets, not recycled
              project addresses and not exchange deposit addresses.
            </p>
            <div className="link-row">
              <a
                href="https://github.com/darwin-protocol/darwin/blob/main/docs/STARTER_COHORT.md"
                target="_blank"
                rel="noreferrer"
              >
                Starter cohort runbook
              </a>
              <a
                href="https://github.com/darwin-protocol/darwin/blob/main/docs/COMMUNITY_BOOTSTRAP.md"
                target="_blank"
                rel="noreferrer"
              >
                Community bootstrap
              </a>
              <a href={siteUrl} target="_blank" rel="noreferrer">
                Public portal
              </a>
            </div>
          </section>
        </main>
      </div>
    </>
  );
}
