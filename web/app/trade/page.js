import Link from "next/link";
import Script from "next/script";

const siteUrl = "https://usedarwin.xyz";
const tradeUrl = `${siteUrl}/trade/?preset=tiny-sell`;
const miniAppEmbed = JSON.stringify({
  version: "1",
  imageUrl: `${siteUrl}/og-card.png`,
  button: {
    title: "Tiny swap",
    action: {
      type: "launch_miniapp",
      url: tradeUrl,
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
    title: "Tiny swap",
    action: {
      type: "launch_frame",
      name: "Use Darwin",
      url: tradeUrl,
      splashImageUrl: `${siteUrl}/icon.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});

export const metadata = {
  title: "Trade DRW",
  description:
    "Connect a wallet, claim DRW from the live Darwin faucet, and start with a tiny DRW swap against the current DARWIN reference pool.",
  alternates: {
    canonical: "/trade/",
  },
  other: {
    "fc:miniapp": miniAppEmbed,
    "fc:frame": frameEmbed,
  },
};

const tradeScriptVersion = "20260407-portal10";

export default function TradePage() {
  return (
    <>
      <Script src={`../lane.js?v=${tradeScriptVersion}`} strategy="afterInteractive" />
      <Script
        src="https://cdn.jsdelivr.net/npm/ethers@6.14.3/dist/ethers.umd.min.js"
        strategy="afterInteractive"
      />
      <Script
        src={`../vendor/qrcode.min.js?v=${tradeScriptVersion}`}
        strategy="afterInteractive"
      />
      <Script src={`../trade.js?v=${tradeScriptVersion}`} strategy="afterInteractive" />

      <div className="background">
        <div className="orb orb-a"></div>
        <div className="orb orb-b"></div>
        <div className="grid"></div>
      </div>

      <div className="page-shell">
        <header className="hero card">
          <div className="hero-copy">
            <h2 className="section-title">
              Trade <span>DRW</span>.
            </h2>
            <p className="lede">
              Claim testnet DRW, acquire quote assets where supported, swap against the live pool,
              or open a direct peer-to-peer transfer request. The easiest public first move is a
              tiny DRW sell through the canonical pool after claiming from the faucet.
            </p>
            <p className="hero-status-line">
              <span id="runtimeHostStatus">
                <code>usedarwin.xyz</code> is live over HTTPS.
              </span>
            </p>
            <div id="tradeLaneSwitcher" className="lane-switcher"></div>
            <div className="hero-actions">
              <button id="connectButton" className="button button-primary">
                Connect wallet
              </button>
              <button id="networkButton" className="button button-secondary">
                Switch network
              </button>
              <button id="watchAssetButton" className="button button-secondary">
                Add DRW to wallet
              </button>
              <Link id="tradeViewActivityLink" className="button button-secondary" href="/activity/">
                View activity
              </Link>
              <Link id="tradeViewEpochLink" className="button button-secondary" href="/epoch/">
                View epoch
              </Link>
              <Link id="tradeJoinCohortLink" className="button button-secondary" href="/join/">
                Join cohort
              </Link>
            </div>
          </div>

          <aside className="hero-panel">
            <div className="status-ladder compact">
              <div className="ladder-step">
                <strong>Claim</strong>
                <span>Pull DRW from the public faucet.</span>
              </div>
              <div className="ladder-step">
                <strong>Wrap</strong>
                <span>Convert a little native ETH into WETH.</span>
              </div>
              <div className="ladder-step">
                <strong>Swap</strong>
                <span>Start with a tiny DRW swap against the live pool.</span>
              </div>
            </div>
            <div className="hero-stat">
              <span className="label">Pool</span>
              <a id="poolLink" className="mono" href="#" target="_blank" rel="noreferrer"></a>
            </div>
            <div className="hero-stat">
              <span className="label">Token</span>
              <a id="tokenLink" className="mono" href="#" target="_blank" rel="noreferrer"></a>
            </div>
            <div className="hero-stat">
              <span className="label">Chain</span>
              <span id="chainBadge" className="badge">
                loading
              </span>
            </div>
            <div className="hero-stat">
              <span className="label">Fee</span>
              <span id="feeBadge" className="badge">
                30 bps
              </span>
            </div>
          </aside>
        </header>

        <main className="layout">
          <section className="card panel">
            <div className="section-heading">
              <h2>Live market</h2>
              <button id="refreshButton" className="button button-tertiary">
                Refresh
              </button>
            </div>
            <div className="stat-grid">
              <article className="metric">
                <span className="label">Pool reserve</span>
                <strong id="poolBaseReserve">-</strong>
                <small>DRW</small>
              </article>
              <article className="metric">
                <span className="label">Pool reserve</span>
                <strong id="poolQuoteReserve">-</strong>
                <small>WETH</small>
              </article>
              <article className="metric">
                <span className="label">Token supply</span>
                <strong id="tokenSupply">-</strong>
                <small>current Darwin lane</small>
              </article>
              <article className="metric">
                <span className="label">Portal state</span>
                <strong id="portalState">Loading</strong>
                <small id="portalSubstate">Waiting for config</small>
              </article>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Pool routes</h2>
              <span id="poolStructureBadge" className="badge">
                loading
              </span>
            </div>
            <p id="poolStructureNote" className="caption">
              Loading the Darwin pool routing policy for this lane.
            </p>
            <div id="poolStructureGrid" className="route-grid">
              <p className="caption">Loading pool routes.</p>
            </div>
          </section>

          <section className="card panel swap-panel">
            <div className="section-heading">
              <h2>Swap</h2>
              <div className="segmented">
                <button className="segment is-active" data-mode="buy">
                  Buy DRW
                </button>
                <button className="segment" data-mode="sell">
                  Sell DRW
                </button>
              </div>
            </div>

            <div className="tiny-strip">
              <div className="tiny-strip-copy">
                <span className="label">Community start</span>
                <strong>Tiny swap path</strong>
                <p className="caption">
                  Claim 100 DRW, then use <code>tiny sell</code> for a first public swap. If you
                  already hold the lane quote asset, <code>tiny buy</code> uses a minimal input.
                </p>
                <p id="tinyAttributionHint" className="tiny-hint">
                  Loading transaction attribution and smart-start support for this lane.
                </p>
              </div>
              <div className="tiny-actions">
                <button className="button button-secondary tiny-button" data-tiny-preset="tiny-sell">
                  Tiny sell 10 DRW
                </button>
                <button className="button button-secondary tiny-button" data-tiny-preset="tiny-buy">
                  Tiny buy 0.00001 WETH
                </button>
                <button className="button button-secondary tiny-button" data-tiny-preset="tiny-wrap">
                  Tiny wrap 0.00002 ETH
                </button>
                <button id="copyTinySwapLinkButton" className="button button-secondary tiny-button">
                  Copy share link
                </button>
                <button id="smartStartButton" className="button button-primary tiny-button">
                  Smart start
                </button>
              </div>
              <p id="tinySwapHint" className="tiny-hint">
                Load a preset to prefill a small first action.
              </p>
            </div>

            <label className="field">
              <span>Input amount</span>
              <input id="swapAmount" type="number" min="0" step="any" placeholder="0.0" />
            </label>

            <div className="inline-fields">
              <label className="field">
                <span>Token in</span>
                <input id="tokenInDisplay" type="text" value="WETH" readOnly />
              </label>
              <label className="field">
                <span>Slippage bps</span>
                <input id="slippageBps" type="number" min="1" max="5000" step="1" defaultValue="100" />
              </label>
            </div>

            <div className="quote-box">
              <div>
                <span className="label">Quoted output</span>
                <strong id="quotedOutput">-</strong>
              </div>
              <div>
                <span className="label">Minimum output</span>
                <strong id="minOutput">-</strong>
              </div>
            </div>

            <button id="swapButton" className="button button-primary button-wide">
              Connect wallet to swap
            </button>
            <p className="caption">
              Swaps hit the live pool directly with `approve` and `swapExactInput`. This is a
              testnet alpha market and not a promise of mainnet liquidity.
            </p>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Community epoch</h2>
              <span id="tradeEpochBadge" className="badge">
                loading
              </span>
            </div>
            <strong id="tradeEpochTitle">Loading epoch.</strong>
            <p id="tradeEpochSummary" className="caption">
              Waiting for the live Darwin community loop.
            </p>
            <div className="stat-grid">
              <article className="metric">
                <span className="label">Outside wallets</span>
                <strong id="tradeExternalWalletCount">-</strong>
                <small>recent non-project participants</small>
              </article>
              <article className="metric">
                <span className="label">Outside swaps</span>
                <strong id="tradeExternalSwapCount">-</strong>
                <small>recent non-project swaps</small>
              </article>
            </div>
            <div className="tiny-actions">
              <a id="tradeEpochLink" className="button button-secondary tiny-button" href="/epoch/">
                Open epoch
              </a>
              <button id="shareEpochButton" className="button button-secondary tiny-button">
                Share epoch
              </button>
            </div>
            <p id="tradeCommunityHint" className="tiny-hint">
              The goal is real outside usage, not project-generated optics.
            </p>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Wrap ETH</h2>
              <span id="wrapBadge" className="badge">Quote asset</span>
            </div>
            <label className="field">
              <span>ETH to wrap</span>
              <input id="wrapAmount" type="number" min="0" step="any" defaultValue="0.0001" />
            </label>
            <button id="wrapButton" className="button button-secondary button-wide">
              Wrap into WETH
            </button>
            <p id="wrapCaption" className="caption">
              Buying `DRW` from this pool requires the quote asset, not native ETH. On lanes with
              native wrapping this action calls `deposit()` on the quote token.
            </p>
          </section>

          <section id="faucetPanel" className="card panel" hidden>
            <div className="section-heading">
              <h2>Claim DRW</h2>
              <span id="faucetBadge" className="badge">
                transparent faucet
              </span>
            </div>
            <div className="stat-grid">
              <article className="metric">
                <span className="label">Claim amount</span>
                <strong id="faucetClaimAmount">-</strong>
                <small>DRW</small>
              </article>
              <article className="metric">
                <span className="label">Native drip</span>
                <strong id="faucetNativeAmount">-</strong>
                <small>ETH</small>
              </article>
              <article className="metric">
                <span className="label">Cooldown</span>
                <strong id="faucetCooldown">-</strong>
                <small>between claims</small>
              </article>
              <article className="metric">
                <span className="label">Next claim</span>
                <strong id="faucetNextClaim">-</strong>
                <small>connected wallet</small>
              </article>
            </div>
            <button id="claimButton" className="button button-primary button-wide">
              Claim DRW
            </button>
            <p className="caption">
              This is a public testnet faucet for third-party onboarding. It is not organic
              distribution or price discovery.
            </p>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Connected wallet</h2>
              <span id="walletStatus" className="badge">
                Disconnected
              </span>
            </div>
            <div className="wallet-grid">
              <div>
                <span className="label">Address</span>
                <strong id="walletAddress" className="mono">
                  Not connected
                </strong>
              </div>
              <div>
                <span className="label">Native ETH</span>
                <strong id="walletEth">-</strong>
              </div>
              <div>
                <span className="label">DRW</span>
                <strong id="walletDrw">-</strong>
              </div>
              <div>
                <span id="walletQuoteLabel" className="label">WETH</span>
                <strong id="walletWeth">-</strong>
              </div>
            </div>
          </section>

          <section className="card panel qr-panel">
            <div className="section-heading">
              <h2>Peer-to-peer request</h2>
              <span className="badge">wallet QR</span>
            </div>
            <div className="qr-layout">
              <div className="qr-stage">
                <div id="qrCanvas" className="qr-render"></div>
              </div>
              <div className="qr-controls">
                <label className="field">
                  <span>Recipient</span>
                  <input id="qrRecipient" type="text" placeholder="0x..." />
                </label>
                <label className="field">
                  <span>DRW amount</span>
                  <input id="qrAmount" type="number" min="0" step="any" defaultValue="25" />
                </label>
                <div className="hero-actions qr-actions">
                  <button id="useConnectedWalletButton" className="button button-secondary">
                    Use connected wallet
                  </button>
                  <button id="copyQrUriButton" className="button button-secondary">
                    Copy request URI
                  </button>
                </div>
                <label className="field">
                  <span>Wallet request</span>
                  <textarea id="qrUri" rows="4" readOnly></textarea>
                </label>
                <p id="qrCaption" className="caption">
                  This QR encodes a DRW transfer request for the current Darwin lane. Scan it from
                  another wallet to open a direct token send.
                </p>
              </div>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Addresses</h2>
              <span className="badge">copy + inspect</span>
            </div>
            <div className="address-list">
              <button className="address-row" data-copy-target="poolAddress">
                <span>Reference pool</span>
                <code id="poolAddress"></code>
              </button>
              <button className="address-row" data-copy-target="drwAddress">
                <span>DRW token</span>
                <code id="drwAddress"></code>
              </button>
              <button className="address-row" data-copy-target="wethAddress">
                <span id="quoteAddressLabel">Quote token</span>
                <code id="wethAddress"></code>
              </button>
              <button id="faucetAddressRow" className="address-row" data-copy-target="faucetAddress" hidden>
                <span>DRW faucet</span>
                <code id="faucetAddress"></code>
              </button>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Context</h2>
              <span className="badge">alpha</span>
            </div>
            <ul className="truth-list">
              <li>The pool is live and the portal talks to it directly.</li>
              <li>This is public testnet alpha infrastructure on the selected Darwin lane.</li>
              <li>Liquidity is limited, so use small amounts.</li>
              <li>If the faucet is enabled, it is there for simple onboarding.</li>
              <li>The public milestone is straightforward usage: claim, trade, and then buy when the lane supports it.</li>
            </ul>
            <div className="link-row">
              <a id="liveStatusLink" href="#" target="_blank" rel="noreferrer">
                Live status
              </a>
              <a id="marketDocLink" href="#" target="_blank" rel="noreferrer">
                Market runbook
              </a>
              <a id="repoLink" href="#" target="_blank" rel="noreferrer">
                Repository
              </a>
            </div>
          </section>

          <section className="card panel message-panel">
            <div className="section-heading">
              <h2>Activity</h2>
              <span id="messageKind" className="badge">
                idle
              </span>
            </div>
            <p id="messageText">Portal booting.</p>
            <a id="messageLink" href="#" target="_blank" rel="noreferrer" hidden>
              View transaction
            </a>
            <div className="tiny-actions">
              <button id="shareActionButton" className="button button-secondary tiny-button" disabled>
                Share progress
              </button>
              <button id="copyActionLinkButton" className="button button-secondary tiny-button" disabled>
                Copy proof link
              </button>
            </div>
            <p id="sharePrompt" className="tiny-hint">
              Complete a claim, wrap, or swap to create a shareable Darwin proof link.
            </p>
          </section>
        </main>
      </div>
    </>
  );
}
