import Link from "next/link";
import Script from "next/script";
import {
  buildMarketStructure,
  explorerAddressHref,
  formatDuration,
  formatUnits,
  laneHref,
  loadPublishedLaneData,
  shortAddress,
} from "../lib/publishedLaneData";

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
      splashImageUrl: `${siteUrl}/drw-logo.svg`,
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
      splashImageUrl: `${siteUrl}/drw-logo.svg`,
      splashBackgroundColor: "#f4efe5",
    },
  },
});

export const metadata = {
  title: "Trade DRW",
  description:
    "Connect a wallet, claim DRW, sell 10 DRW, and confirm the tiny testnet trade on Darwin's live activity feed.",
  alternates: {
    canonical: "/trade/",
  },
  other: {
    "fc:miniapp": miniAppEmbed,
    "fc:frame": frameEmbed,
  },
};

const tradeScriptVersion = "20260409-portal14";

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

export default async function TradePage() {
  const selection = await loadPublishedLaneData();
  const current = selection.current || {};
  const config = current.config || {};
  const stats = current.stats || {};
  const structure = current.structure || buildMarketStructure(config, stats);
  const networkName = config.network?.name || current.lane?.name || "Base Sepolia";
  const tokenSymbol = config.token?.symbol || "DRW";
  const quoteSymbol = config.quote_token?.symbol || "WETH";
  const faucetEnabled = Boolean(config.faucet?.enabled && config.faucet?.address);
  const smartStartEnabled = Boolean(config.attribution?.smart_start_enabled && faucetEnabled);
  const wrapEnabled = Boolean(config.quote_token?.wrap_enabled);
  const activityHref = laneHref(config.community?.activity_path || "/activity/", selection);
  const epochHref = laneHref(config.community?.epoch_path || "/epoch/", selection);
  const joinHref = laneHref(config.community?.starter_cohort_path || "/join/", selection);
  const searchHref = laneHref("/search/", selection);
  const tinySwapHref = laneHref(config.community?.tiny_swap_path || "/trade/?preset=tiny-sell", selection);
  const epoch = config.community?.epoch || {};
  const rewardPolicy = epoch.reward_policy || null;
  const rewardRules = Array.isArray(rewardPolicy?.rules) && rewardPolicy.rules.length
    ? rewardPolicy.rules.map((rule) => {
        const amount = Number(rule.amount || 0);
        if (!amount) {
          return `${rule.label || "Reward"}: ${rule.detail || "Locked for a later phase."}`;
        }
        return `${rule.label || "Reward"}: ${amount} ${rewardPolicy.currency_symbol || tokenSymbol}. ${rule.detail || ""}`.trim();
      })
    : ["The current Darwin lane is live without a public reward pilot."];
  const tradeProgress = rewardPolicy
    ? `${rewardPolicy.window_label || "Current window"}: ${Number(stats.eligible_wallets ?? stats.external_wallets ?? 0)}/${epoch.milestones?.external_wallets_target ?? 25} swap-active wallets, ${Number(stats.eligible_swaps ?? stats.external_swaps ?? 0)}/${epoch.milestones?.external_swaps_target ?? 40} swaps. Incentivized routes stay locked until the canonical traction gate is real.`
    : "No public reward pilot configured yet.";

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
            <p className="eyebrow">DARWIN MARKET</p>
            <h1 className="section-title">Claim DRW. Sell 10 DRW. Verify it.</h1>
            <p className="lede">
              The first Darwin trade should be obvious. Connect a wallet, claim the faucet,
              use the tiny sell preset on the reference pool, then confirm the result on the live
              activity page.
            </p>
            <p className="hero-status-line">
              <span id="runtimeHostStatus">
                <code>usedarwin.xyz</code> is live. Current lane: <code>{networkName}</code>.
              </span>
            </p>
            <div id="tradeLaneSwitcher" className="lane-switcher">
              {selection.lanes.map((lane) => (
                <a
                  key={lane.slug}
                  className={`button button-secondary tiny-button${lane.slug === selection.defaultLane.slug ? " is-active" : ""}`}
                  href={laneHref("/trade/", selection, lane)}
                >
                  {lane.name || lane.network?.name || lane.slug}
                </a>
              ))}
            </div>
            <div className="hero-actions">
              <Link id="tradeViewActivityLink" className="button button-primary" href={activityHref}>
                Live activity
              </Link>
              <Link id="tradeViewEpochLink" className="button button-secondary" href={epochHref}>
                Current epoch
              </Link>
              <Link id="tradeSearchLink" className="button button-secondary" href={searchHref}>
                Search Darwin
              </Link>
            </div>
            <div className="link-row">
              <Link id="tradeJoinCohortLink" className="button button-secondary" href={joinHref}>
                Join cohort
              </Link>
            </div>
          </div>

          <aside className="hero-panel">
            <div className="hero-stat">
              <span className="label">Chain</span>
              <span id="chainBadge" className="badge">
                {networkName}
              </span>
            </div>
            <div className="hero-stat">
              <span className="label">Pool</span>
              <a id="poolLink" className="mono" href={explorerAddressHref(config, config.pool?.address)} target="_blank" rel="noreferrer">
                {shortAddress(config.pool?.address || "")}
              </a>
            </div>
            <div className="hero-stat">
              <span className="label">Token</span>
              <a id="tokenLink" className="mono" href={explorerAddressHref(config, config.token?.address)} target="_blank" rel="noreferrer">
                {shortAddress(config.token?.address || "")}
              </a>
            </div>
            <div className="hero-stat">
              <span className="label">Fee</span>
              <span id="feeBadge" className="badge">
                {config.pool?.fee_bps || 30} bps
              </span>
            </div>
          </aside>
        </header>

        <main className="layout">
          <section className="card panel trade-primary-panel activity-panel">
            <div className="section-heading">
              <h2>First trade path</h2>
              <span className="badge">connect - claim - tiny sell - verify</span>
            </div>
            <p className="caption">
              Keep the first Darwin action small and legible. Everything below is oriented around
              the single reference path, not around feature sprawl.
            </p>

            <div className="trade-workbench">
              <div className="trade-column">
                <article className="trade-step">
                  <div className="trade-step-header">
                    <h3>1. Connect</h3>
                    <span className="badge">{networkName}</span>
                  </div>
                  <p className="trade-step-copy">
                    Use a browser wallet on the selected lane. The first Darwin pass is designed
                    for a tiny testnet balance, not a big position.
                  </p>
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
                  </div>
                </article>

                <section id="faucetPanel" className="trade-step">
                  <div className="trade-step-header">
                    <h3>2. Claim DRW</h3>
                    <span id="faucetBadge" className="badge">
                      {config.faucet?.funded ? "funded faucet" : "unfunded faucet"}
                    </span>
                  </div>
                  <div className="stat-grid compact-stat-grid">
                    <article className="metric">
                      <span className="label">Claim amount</span>
                      <strong id="faucetClaimAmount">
                        {faucetEnabled ? formatUnits(config.faucet?.claim_amount || 0, config.token?.decimals || 18, 3) : "-"}
                      </strong>
                      <small>{tokenSymbol}</small>
                    </article>
                    <article className="metric">
                      <span className="label">Native drip</span>
                      <strong id="faucetNativeAmount">
                        {faucetEnabled ? formatUnits(config.faucet?.native_drip_amount || 0, 18, 6) : "-"}
                      </strong>
                      <small>{config.network?.native_symbol || "ETH"}</small>
                    </article>
                    <article className="metric">
                      <span className="label">Cooldown</span>
                      <strong id="faucetCooldown">
                        {faucetEnabled ? formatDuration(config.faucet?.claim_cooldown || 0) : "-"}
                      </strong>
                      <small>between claims</small>
                    </article>
                    <article className="metric">
                      <span className="label">Next claim</span>
                      <strong id="faucetNextClaim">connect wallet</strong>
                      <small>connected wallet</small>
                    </article>
                  </div>
                  <div className="hero-actions">
                    <button id="claimButton" className="button button-primary">
                      Claim DRW
                    </button>
                    <button id="smartStartButton" className="button button-secondary" disabled={!smartStartEnabled}>
                      Smart start
                    </button>
                  </div>
                  <p className="trade-inline-note">
                    This is a public testnet faucet for outside onboarding. It is not organic
                    distribution or price discovery.
                  </p>
                </section>
              </div>

              <div className="trade-column trade-column-wide">
                <article className="trade-step">
                  <div className="trade-step-header">
                    <h3>3. Tiny sell</h3>
                    <div className="segmented">
                      <button className="segment" data-mode="buy">
                        Buy DRW
                      </button>
                      <button className="segment is-active" data-mode="sell">
                        Sell DRW
                      </button>
                    </div>
                  </div>

                  <div className="tiny-strip">
                    <div className="tiny-strip-copy">
                      <span className="label">Recommended path</span>
                      <strong>Tiny sell 10 DRW</strong>
                      <p className="caption">
                        Claim 100 DRW, then use tiny sell for the first public market action. Tiny
                        buy and tiny wrap remain available as secondary routes.
                      </p>
                      <p id="tinyAttributionHint" className="tiny-hint">
                        Builder Code and smart-start support load for the current lane after the wallet surface boots.
                      </p>
                    </div>
                    <div className="tiny-actions">
                      <button className="button button-primary tiny-button is-active" data-tiny-preset="tiny-sell">
                        Tiny sell 10 DRW
                      </button>
                      <button className="button button-secondary tiny-button" data-tiny-preset="tiny-buy">
                        Tiny buy 0.00001 WETH
                      </button>
                      <button className="button button-secondary tiny-button" data-tiny-preset="tiny-wrap">
                        Tiny wrap 0.00002 ETH
                      </button>
                      <button id="copyTinySwapLinkButton" className="button button-secondary tiny-button">
                        Copy tiny-sell link
                      </button>
                    </div>
                  </div>

                  <label className="field">
                    <span>Input amount</span>
                    <input id="swapAmount" type="number" min="0" step="any" defaultValue="10" placeholder="0.0" />
                  </label>

                  <div className="inline-fields">
                    <label className="field">
                      <span>Token in</span>
                      <input id="tokenInDisplay" type="text" value={tokenSymbol} readOnly />
                    </label>
                    <label className="field">
                      <span>Slippage bps</span>
                      <input id="slippageBps" type="number" min="1" max="5000" step="1" defaultValue="150" />
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
                    Sell DRW
                  </button>
                  <p id="tinySwapHint" className="tiny-hint">
                    Tiny sell is preloaded because it is the clearest first Darwin trade.
                  </p>
                </article>

                <article className="trade-step">
                  <div className="trade-step-header">
                    <h3>4. Verify</h3>
                    <span id="messageKind" className="badge">
                      ready
                    </span>
                  </div>
                  <p id="messageText">
                    Portal ready. Connect a wallet, claim DRW, then use tiny sell.
                  </p>
                  <a id="messageLink" href="#" target="_blank" rel="noreferrer" hidden>
                    View transaction
                  </a>
                  <div className="hero-actions">
                    <Link className="button button-secondary" href={activityHref}>
                      Open activity
                    </Link>
                    <button id="shareActionButton" className="button button-secondary" disabled>
                      Share progress
                    </button>
                    <button id="copyActionLinkButton" className="button button-secondary" disabled>
                      Copy proof link
                    </button>
                  </div>
                  <p id="sharePrompt" className="tiny-hint">
                    Complete a claim or swap to create a shareable Darwin proof link.
                  </p>
                </article>
              </div>
            </div>
          </section>

          <section className="card panel">
            <div className="section-heading">
              <h2>Current market</h2>
              <button id="refreshButton" className="button button-tertiary">
                Refresh
              </button>
            </div>
            <div className="stat-grid">
              <article className="metric">
                <span className="label">Pool reserve</span>
                <strong id="poolBaseReserve">-</strong>
                <small>{tokenSymbol}</small>
              </article>
              <article className="metric">
                <span className="label">Pool reserve</span>
                <strong id="poolQuoteReserve">-</strong>
                <small>{quoteSymbol}</small>
              </article>
              <article className="metric">
                <span className="label">Token supply</span>
                <strong id="tokenSupply">
                  {formatUnits(config.token?.total_supply || 0, config.token?.decimals || 18, 3)}
                </strong>
                <small>current Darwin lane</small>
              </article>
              <article className="metric">
                <span className="label">Portal state</span>
                <strong id="portalState">Refreshing</strong>
                <small id="portalSubstate">Checking live pool state on load.</small>
              </article>
            </div>
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
                <span id="walletQuoteLabel" className="label">{quoteSymbol}</span>
                <strong id="walletWeth">-</strong>
              </div>
            </div>
          </section>

          <details className="card trade-more activity-panel">
            <summary>
              <span>More tools</span>
              <span>Wrap, pool routes, epoch context, QR, addresses</span>
            </summary>

            <div className="trade-more-body">
              <div className="trade-advanced-grid">
                <section className="card panel">
                  <div className="section-heading">
                    <h2>Community epoch</h2>
                    <span id="tradeEpochBadge" className="badge">
                      {epoch.status || "live"}
                    </span>
                  </div>
                  <strong id="tradeEpochTitle">{epoch.title || "Epoch Alpha"}</strong>
                  <p id="tradeEpochSummary" className="caption">
                    {epoch.summary || "Claim DRW, make one tiny swap, and share the public proof surface."}
                  </p>
                  <div className="stat-grid">
                    <article className="metric">
                      <span className="label">Eligible wallets</span>
                      <strong id="tradeExternalWalletCount">{Number(stats.eligible_wallets ?? stats.external_wallets ?? 0)}</strong>
                      <small>swap-active outside participants</small>
                    </article>
                    <article className="metric">
                      <span className="label">Outside swaps</span>
                      <strong id="tradeExternalSwapCount">{Number(stats.eligible_swaps ?? stats.external_swaps ?? 0)}</strong>
                      <small>recent non-project swaps</small>
                    </article>
                  </div>
                  <p id="tradeEpochProgress" className="tiny-hint">
                    {tradeProgress}
                  </p>
                  <ul id="tradeRewardRules" className="truth-list">
                    {rewardRules.map((rule) => (
                      <li key={rule}>{rule}</li>
                    ))}
                  </ul>
                  <div className="tiny-actions">
                    <a id="tradeEpochLink" className="button button-secondary tiny-button" href={epochHref}>
                      Open epoch
                    </a>
                    <button id="shareEpochButton" className="button button-secondary tiny-button">
                      Share epoch
                    </button>
                  </div>
                  <p id="tradeCommunityHint" className="tiny-hint">
                    {epoch.focus || "The goal is real outside usage, not project-generated optics."}
                  </p>
                </section>

                <section className="card panel">
                  <div className="section-heading">
                    <h2>Pool routes</h2>
                    <span id="poolStructureBadge" className="badge">
                      {structure.defaultEntry || "canonical"}
                    </span>
                  </div>
                  <p id="poolStructureNote" className="caption">
                    {structure.summary || "Keep one canonical pool live until outside usage is real, then unlock the next Darwin routes."}
                  </p>
                  <div id="poolStructureGrid" className="route-grid">
                    {structure.pools.map((pool) => renderPoolCard(pool, selection))}
                  </div>
                </section>

                <section className="card panel">
                  <div className="section-heading">
                    <h2>Wrap ETH</h2>
                    <span id="wrapBadge" className="badge">
                      {wrapEnabled ? `${networkName} ${quoteSymbol}` : `${quoteSymbol} is preseeded`}
                    </span>
                  </div>
                  <label className="field">
                    <span>ETH to wrap</span>
                    <input id="wrapAmount" type="number" min="0" step="any" defaultValue="0.00002" />
                  </label>
                  <button id="wrapButton" className="button button-secondary button-wide" disabled={!wrapEnabled}>
                    Wrap into {quoteSymbol}
                  </button>
                  <p id="wrapCaption" className="caption">
                    {wrapEnabled
                      ? `Buying DRW from this pool requires ${quoteSymbol}, not native ETH. This action calls deposit() on ${networkName} ${quoteSymbol}.`
                      : `${quoteSymbol} is a mock or preseeded quote asset on this lane, so public wrapping is disabled. The clean public route here is claim DRW, then tiny sell.`}
                  </p>
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
                        <span>{tokenSymbol} amount</span>
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
                        This QR encodes a {networkName} {tokenSymbol} transfer request. Scan it from another wallet to open a direct token send.
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
                      <code id="poolAddress">{config.pool?.address || ""}</code>
                    </button>
                    <button className="address-row" data-copy-target="drwAddress">
                      <span>{tokenSymbol} token</span>
                      <code id="drwAddress">{config.token?.address || ""}</code>
                    </button>
                    <button className="address-row" data-copy-target="wethAddress">
                      <span id="quoteAddressLabel">{quoteSymbol} token</span>
                      <code id="wethAddress">{config.quote_token?.address || ""}</code>
                    </button>
                    <button id="faucetAddressRow" className="address-row" data-copy-target="faucetAddress" hidden={!faucetEnabled}>
                      <span>{tokenSymbol} faucet</span>
                      <code id="faucetAddress">{config.faucet?.address || ""}</code>
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
                    <li>The public milestone is straightforward usage: claim, trade, and then verify on the activity feed.</li>
                  </ul>
                  <div className="link-row">
                    <a id="liveStatusLink" href={config.links?.live_status || "#"} target="_blank" rel="noreferrer">
                      Live status
                    </a>
                    <a id="marketDocLink" href={config.links?.market_bootstrap || "#"} target="_blank" rel="noreferrer">
                      Market runbook
                    </a>
                    <a id="repoLink" href={config.links?.repo || "#"} target="_blank" rel="noreferrer">
                      Repository
                    </a>
                  </div>
                </section>
              </div>
            </div>
          </details>
        </main>
      </div>
    </>
  );
}
