const activityState = {
  laneSelection: null,
  config: null,
  runtimeStatus: null,
  activitySummary: null,
  marketStructure: null,
  provider: null,
  events: [],
  filter: "all",
  blockCache: new Map(),
};

const activityEls = {};
const TINY_SWAP_PATH = "/trade/?preset=tiny-sell";

const POOL_IFACE = new ethers.Interface([
  "event SwapExecuted(address indexed trader,address indexed tokenIn,uint256 amountIn,address indexed tokenOut,uint256 amountOut,address to)",
]);
const FAUCET_IFACE = new ethers.Interface([
  "event Claimed(address indexed claimer,address indexed recipient,uint256 tokenAmount,uint256 nativeAmount,uint256 nextEligibleAt)",
]);
const DISTRIBUTOR_IFACE = new ethers.Interface([
  "event Claimed(uint256 indexed index,address indexed account,uint256 amount)",
]);

const EVENT_TOPICS = {
  swap: ethers.id("SwapExecuted(address,address,uint256,address,uint256,address)"),
  faucet: ethers.id("Claimed(address,address,uint256,uint256,uint256)"),
  distributor: ethers.id("Claimed(uint256,address,uint256)"),
};
const LOG_CHUNK_SIZE = 2000;

function activity$(id) {
  return document.getElementById(id);
}

function shortAddress(value) {
  return value ? `${value.slice(0, 6)}…${value.slice(-4)}` : "-";
}

function explorerLink(addressOrTx) {
  const base = activityState.config.network.explorer_base_url.replace(/\/$/, "");
  if ((addressOrTx || "").startsWith("0x") && addressOrTx.length === 42) {
    return `${base}/address/${addressOrTx}`;
  }
  return `${base}/tx/${addressOrTx}`;
}

function absoluteUrl(path) {
  if (window.DarwinLane && activityState.laneSelection) {
    return window.DarwinLane.laneAbsoluteHref(path, activityState.laneSelection);
  }
  return new URL(path, window.location.origin).toString();
}

async function copyText(value, successMessage) {
  await navigator.clipboard.writeText(value);
  activityEls.activityFeedStatus.textContent = successMessage;
}

function formatUnits(value, decimals, precision = 6) {
  const text = ethers.formatUnits(value, decimals);
  const [whole, frac = ""] = text.split(".");
  if (!frac) return whole;
  const trimmed = frac.slice(0, precision).replace(/0+$/, "");
  return trimmed ? `${whole}.${trimmed}` : whole;
}

async function loadActivityConfig() {
  activityState.laneSelection = window.DarwinLane ? await window.DarwinLane.resolveSelection() : null;
  const configPath = activityState.laneSelection?.currentLane?.path || "/market-config.json";
  const response = await fetch(configPath, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load market config: ${response.status}`);
  }
  activityState.config = await response.json();
  const readRpcUrl = activityState.config.network.read_rpc_url || activityState.config.network.rpc_url;
  activityState.provider = new ethers.JsonRpcProvider(readRpcUrl);
}

async function loadRuntimeStatus() {
  try {
    const response = await fetch(`../runtime-status.json?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) return;
    activityState.runtimeStatus = await response.json();
    if (activityEls.activityRuntimeStatus && activityState.runtimeStatus?.summary) {
      activityEls.activityRuntimeStatus.textContent = activityState.runtimeStatus.summary;
    }
  } catch {
    // Keep fallback copy.
  }
}

async function loadActivitySummary() {
  try {
    const summaryPath =
      activityState.laneSelection?.currentLane?.activity_summary_path || "/activity-summary.json";
    const response = await fetch(`${summaryPath}?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) return;
    activityState.activitySummary = await response.json();
  } catch {
    activityState.activitySummary = null;
  }
  activityState.marketStructure = window.DarwinLane
    ? window.DarwinLane.buildMarketStructure(activityState.config, activityState.activitySummary?.summary || {})
    : null;
}

function bindActivityStatics() {
  if (window.DarwinLane && activityState.laneSelection) {
    window.DarwinLane.renderSwitcher(activityEls.activityLaneSwitcher, activityState.laneSelection);
  }
  activityEls.activityChainBadge.textContent = activityState.config.network.name;
  activityEls.activityLookback.textContent = `${activityState.config.activity.lookback_blocks.toLocaleString()} blocks`;
  activityEls.activityMarketDocLink.href = activityState.config.links.market_bootstrap;
  activityEls.activityCommunityDocLink.href =
    activityState.config.links.community_bootstrap || activityState.config.links.market_bootstrap;
  activityEls.activityRepoLink.href = activityState.config.links.repo;
  activityEls.activityOpenTinySwapLink.href = window.DarwinLane && activityState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/trade/?preset=tiny-sell", activityState.laneSelection)
    : "/trade/?preset=tiny-sell";
  activityEls.activityOpenEpochLink.href = window.DarwinLane && activityState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/epoch/", activityState.laneSelection)
    : "/epoch/";
  activityEls.activityOpenMarketLink.href = window.DarwinLane && activityState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/trade/", activityState.laneSelection)
    : "/trade/";
  if (activityEls.activityOpenSearchLink) {
    activityEls.activityOpenSearchLink.href = window.DarwinLane && activityState.laneSelection
      ? window.DarwinLane.laneRelativeHref("/search/", activityState.laneSelection)
      : "/search/";
  }
  if (activityEls.explorerLookupStatus) {
    activityEls.explorerLookupStatus.textContent =
      `Paste any Darwin-related address or transaction hash to open the ${activityState.config.network.name} explorer.`;
  }
}

function renderCommunitySummary() {
  const summary = activityState.activitySummary?.summary;
  if (!summary) {
    activityEls.communityStatusBadge.textContent = "unavailable";
    activityEls.communityUpdatedAt.textContent = "Local outside-activity summary is not available yet.";
    return;
  }

  activityEls.externalEventCount.textContent = String(summary.external_events ?? 0);
  activityEls.externalWalletCount.textContent = String(summary.external_wallets ?? 0);
  activityEls.externalSwapCount.textContent = String(summary.external_swaps ?? 0);
  activityEls.externalClaimCount.textContent = String(summary.external_claims ?? 0);
  activityEls.communityStatusBadge.textContent =
    Number(summary.external_events || 0) > 0 ? "outside wallets seen" : "waiting for first outside loop";
  const generatedAt = activityState.activitySummary?.generated_at
    ? new Date(activityState.activitySummary.generated_at).toLocaleString()
    : "unknown";
  activityEls.communityUpdatedAt.textContent =
    `Updated ${generatedAt}. This snapshot is derived from the local project-wallet allowlist, not guessed in the browser.`;
}

function renderEpoch() {
  const epoch = activityState.config.community?.epoch;
  if (!epoch) {
    activityEls.epochBadge.textContent = "not set";
    activityEls.epochTitle.textContent = "No public epoch configured.";
    activityEls.epochSummary.textContent = "Add a community epoch config to the portal export to drive the public campaign.";
    activityEls.epochGoals.innerHTML = "<li>Set a new epoch in ops/community_epoch.json.</li>";
    activityEls.epochFocus.textContent = "";
    return;
  }

  activityEls.epochBadge.textContent = epoch.status || "live";
  activityEls.epochTitle.textContent = epoch.title || "Darwin epoch";
  activityEls.epochSummary.textContent = epoch.summary || "";
  activityEls.epochFocus.textContent = epoch.focus || "";
  const epochCtaPath = epoch.cta_path || activityState.config.community?.tiny_swap_path || TINY_SWAP_PATH;
  const epochActivityPath = epoch.activity_path || activityState.config.community?.activity_path || "/activity/";
  activityEls.epochCtaLink.href = window.DarwinLane && activityState.laneSelection
    ? window.DarwinLane.laneRelativeHref(epochCtaPath, activityState.laneSelection)
    : epochCtaPath;
  activityEls.epochCtaLink.textContent = epoch.cta_label || "Start epoch";
  activityEls.epochActivityLink.href = window.DarwinLane && activityState.laneSelection
    ? window.DarwinLane.laneRelativeHref(epochActivityPath, activityState.laneSelection)
    : epochActivityPath;

  activityEls.epochGoals.innerHTML = "";
  for (const goal of epoch.goals || []) {
    const li = document.createElement("li");
    li.textContent = goal;
    activityEls.epochGoals.appendChild(li);
  }
}

function poolEntryHref(pool) {
  if (!pool?.entry_path) return "";
  return window.DarwinLane && activityState.laneSelection
    ? window.DarwinLane.laneRelativeHref(pool.entry_path, activityState.laneSelection)
    : pool.entry_path;
}

function renderMarketStructure() {
  if (!activityEls.activityStructureGrid || !activityState.marketStructure) return;
  const structure = activityState.marketStructure;
  activityEls.activityStructureGrid.innerHTML = "";
  activityEls.activityStructureBadge.textContent = structure.defaultEntry || "canonical";
  activityEls.activityStructureNote.textContent = structure.summary || "";

  for (const pool of structure.pools || []) {
    const card = document.createElement("article");
    card.className = `route-card route-${pool.derivedStatus || pool.status || "locked"}`;

    const top = document.createElement("div");
    top.className = "route-top";

    const title = document.createElement("strong");
    title.textContent = pool.label || pool.id || "Pool";
    top.appendChild(title);

    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = pool.derivedStatus || pool.status || "locked";
    top.appendChild(badge);
    card.appendChild(top);

    const purpose = document.createElement("p");
    purpose.className = "caption";
    purpose.textContent = pool.purpose || "";
    card.appendChild(purpose);

    const progress = document.createElement("p");
    progress.className = "tiny-hint";
    progress.textContent = pool.isDefault
      ? `Default route. ${pool.reason || ""}`
      : `${pool.progressLabel}. ${pool.reason || ""}`;
    card.appendChild(progress);

    if (pool.enabled && pool.entry_path) {
      const link = document.createElement("a");
      link.className = "button button-secondary tiny-button";
      link.href = poolEntryHref(pool);
      link.textContent = pool.entry_label || "Open route";
      card.appendChild(link);
    }

    activityEls.activityStructureGrid.appendChild(card);
  }
}

function renderContracts() {
  const mount = activityEls.activityContracts;
  mount.innerHTML = "";

  const entries = [
    {
      label: "DRW token",
      detail: "Public token contract",
      address: activityState.config.token.address,
    },
    {
      label: "Reference pool",
      detail: "Live DRW / WETH pool",
      address: activityState.config.pool.address,
    },
  ];

  if (activityState.config.faucet?.enabled && activityState.config.faucet.address) {
    entries.push({
      label: "Faucet",
      detail: "Public DRW claim path",
      address: activityState.config.faucet.address,
    });
  }

  if (activityState.config.vnext?.enabled && activityState.config.vnext.distributor) {
    entries.push({
      label: "Distributor",
      detail: "Merkle claim surface",
      address: activityState.config.vnext.distributor,
    });
  }

  if (activityState.config.vnext?.enabled && activityState.config.vnext.timelock) {
    entries.push({
      label: "Timelock",
      detail: "Mutable governance root",
      address: activityState.config.vnext.timelock,
    });
  }

  for (const entry of entries) {
    const card = document.createElement("article");
    card.className = "contract-card";

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = entry.label;
    card.appendChild(label);

    const title = document.createElement("strong");
    title.textContent = shortAddress(entry.address);
    card.appendChild(title);

    const detail = document.createElement("p");
    detail.className = "caption";
    detail.textContent = entry.detail;
    card.appendChild(detail);

    const link = document.createElement("a");
    link.className = "mono";
    link.href = explorerLink(entry.address);
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "Open in explorer";
    card.appendChild(link);

    mount.appendChild(card);
  }
}

async function blockTimestamp(blockNumber) {
  if (!activityState.blockCache.has(blockNumber)) {
    const block = await activityState.provider.getBlock(blockNumber);
    activityState.blockCache.set(blockNumber, block?.timestamp || 0);
  }
  return activityState.blockCache.get(blockNumber) || 0;
}

function tokenSymbol(address) {
  const normalized = (address || "").toLowerCase();
  if (normalized === activityState.config.token.address.toLowerCase()) return activityState.config.token.symbol;
  if (normalized === activityState.config.quote_token.address.toLowerCase()) return activityState.config.quote_token.symbol;
  return shortAddress(address);
}

function tokenDecimals(address) {
  const normalized = (address || "").toLowerCase();
  if (normalized === activityState.config.token.address.toLowerCase()) return activityState.config.token.decimals;
  if (normalized === activityState.config.quote_token.address.toLowerCase()) return activityState.config.quote_token.decimals;
  return 18;
}

function parseSwap(log) {
  const parsed = POOL_IFACE.parseLog(log);
  const tokenIn = parsed.args.tokenIn;
  const tokenOut = parsed.args.tokenOut;
  const amountIn = parsed.args.amountIn;
  const amountOut = parsed.args.amountOut;
  return {
    type: "swap",
    blockNumber: Number(log.blockNumber),
    txHash: log.transactionHash,
    actor: parsed.args.trader,
    title:
      tokenIn.toLowerCase() === activityState.config.token.address.toLowerCase()
        ? `Sold ${formatUnits(amountIn, tokenDecimals(tokenIn), 6)} ${tokenSymbol(tokenIn)}`
        : `Bought ${formatUnits(amountOut, tokenDecimals(tokenOut), 6)} ${tokenSymbol(tokenOut)}`,
    detail: `${formatUnits(amountIn, tokenDecimals(tokenIn), 6)} ${tokenSymbol(tokenIn)} -> ${formatUnits(amountOut, tokenDecimals(tokenOut), 12)} ${tokenSymbol(tokenOut)}`,
  };
}

function parseFaucetClaim(log) {
  const parsed = FAUCET_IFACE.parseLog(log);
  return {
    type: "faucet",
    blockNumber: Number(log.blockNumber),
    txHash: log.transactionHash,
    actor: parsed.args.claimer,
    title: `Claimed ${formatUnits(parsed.args.tokenAmount, activityState.config.token.decimals, 6)} DRW`,
    detail: `${formatUnits(parsed.args.tokenAmount, activityState.config.token.decimals, 6)} DRW + ${formatUnits(parsed.args.nativeAmount, 18, 6)} ETH drip`,
  };
}

function parseDistributorClaim(log) {
  const parsed = DISTRIBUTOR_IFACE.parseLog(log);
  return {
    type: "distributor",
    blockNumber: Number(log.blockNumber),
    txHash: log.transactionHash,
    actor: parsed.args.account,
    title: `Claimed ${formatUnits(parsed.args.amount, activityState.config.token.decimals, 6)} DRW`,
    detail: `Merkle distribution claim`,
  };
}

async function fetchEvents() {
  const latestBlock = await activityState.provider.getBlockNumber();
  const fromBlock = Math.max(0, latestBlock - (activityState.config.activity.lookback_blocks || 200000));
  const queries = [
    getLogsChunked({
      address: activityState.config.pool.address,
      fromBlock,
      toBlock: latestBlock,
      topics: [EVENT_TOPICS.swap],
    }),
  ];

  if (activityState.config.faucet?.enabled && activityState.config.faucet.address) {
    queries.push(
      getLogsChunked({
        address: activityState.config.faucet.address,
        fromBlock,
        toBlock: latestBlock,
        topics: [EVENT_TOPICS.faucet],
      }),
    );
  } else {
    queries.push(Promise.resolve([]));
  }

  if (activityState.config.vnext?.enabled && activityState.config.vnext.distributor) {
    queries.push(
      getLogsChunked({
        address: activityState.config.vnext.distributor,
        fromBlock,
        toBlock: latestBlock,
        topics: [EVENT_TOPICS.distributor],
      }),
    );
  } else {
    queries.push(Promise.resolve([]));
  }

  const [swapLogs, faucetLogs, distributorLogs] = await Promise.all(queries);
  const events = [
    ...swapLogs.map(parseSwap),
    ...faucetLogs.map(parseFaucetClaim),
    ...distributorLogs.map(parseDistributorClaim),
  ];

  await Promise.all(
    events.map(async (entry) => {
      entry.timestamp = await blockTimestamp(entry.blockNumber);
    }),
  );

  events.sort((left, right) => {
    if (right.blockNumber !== left.blockNumber) return right.blockNumber - left.blockNumber;
    return right.txHash.localeCompare(left.txHash);
  });
  activityState.events = events;
  activityEls.activityUpdatedAt.textContent =
    `Updated ${new Date().toLocaleString()} from live ${activityState.config.network.name} RPC.`;
}

async function getLogsChunked(filter) {
  const logs = [];
  for (let chunkStart = Number(filter.fromBlock); chunkStart <= Number(filter.toBlock); chunkStart += LOG_CHUNK_SIZE) {
    const chunkEnd = Math.min(Number(filter.toBlock), chunkStart + LOG_CHUNK_SIZE - 1);
    const chunkLogs = await activityState.provider.getLogs({
      ...filter,
      fromBlock: chunkStart,
      toBlock: chunkEnd,
    });
    logs.push(...chunkLogs);
  }
  return logs;
}

function applyActivityFilter(filterValue) {
  activityState.filter = filterValue;
  for (const button of document.querySelectorAll("[data-activity-filter]")) {
    button.classList.toggle("is-active", button.dataset.activityFilter === filterValue);
  }
  renderEvents();
}

function renderStats() {
  const events = activityState.events;
  const uniqueWallets = new Set(events.map((item) => item.actor.toLowerCase()));
  const swapCount = events.filter((item) => item.type === "swap").length;
  const claimCount = events.filter((item) => item.type === "faucet" || item.type === "distributor").length;
  activityEls.activityCount.textContent = String(events.length);
  activityEls.activityWalletCount.textContent = String(uniqueWallets.size);
  activityEls.activitySwapCount.textContent = String(swapCount);
  activityEls.activityClaimCount.textContent = String(claimCount);
}

async function shareUrl(title, text, url) {
  if (navigator.share) {
    await navigator.share({ title, text, url });
    activityEls.activityFeedStatus.textContent = "shared";
    return;
  }
  await navigator.clipboard.writeText(`${text}\n${url}`);
  activityEls.activityFeedStatus.textContent = "share text copied";
}

function renderEvents() {
  const mount = activityEls.activityList;
  mount.innerHTML = "";
  const filtered = activityState.filter === "all"
    ? activityState.events
    : activityState.events.filter((item) => item.type === activityState.filter);

  activityEls.activityFeedStatus.textContent = `${filtered.length} shown`;

  if (!filtered.length) {
    const empty = document.createElement("p");
    empty.className = "caption";
    empty.textContent = "No DARWIN activity matched the current filter.";
    mount.appendChild(empty);
    return;
  }

  for (const entry of filtered.slice(0, 50)) {
    const card = document.createElement("article");
    card.className = "activity-card";

    const top = document.createElement("div");
    top.className = "activity-top";

    const typeBadge = document.createElement("span");
    typeBadge.className = "badge";
    typeBadge.textContent = entry.type;
    top.appendChild(typeBadge);

    const actor = document.createElement("a");
    actor.className = "mono";
    actor.href = explorerLink(entry.actor);
    actor.target = "_blank";
    actor.rel = "noreferrer";
    actor.textContent = shortAddress(entry.actor);
    top.appendChild(actor);
    card.appendChild(top);

    const title = document.createElement("strong");
    title.textContent = entry.title;
    card.appendChild(title);

    const detail = document.createElement("p");
    detail.className = "caption";
    detail.textContent = entry.detail;
    card.appendChild(detail);

    const meta = document.createElement("div");
    meta.className = "activity-meta";

    const tx = document.createElement("a");
    tx.href = explorerLink(entry.txHash);
    tx.target = "_blank";
    tx.rel = "noreferrer";
    tx.textContent = shortAddress(entry.txHash);
    meta.appendChild(tx);

    const timestamp = document.createElement("span");
    timestamp.className = "mono";
    timestamp.textContent = entry.timestamp ? new Date(entry.timestamp * 1000).toLocaleString() : `Block ${entry.blockNumber}`;
    meta.appendChild(timestamp);
    card.appendChild(meta);

    mount.appendChild(card);
  }
}

async function refreshActivity() {
  activityEls.activityFeedStatus.textContent = "loading";
  await loadActivitySummary();
  renderMarketStructure();
  await fetchEvents();
  renderStats();
  renderCommunitySummary();
  renderEvents();
}

async function bootActivity() {
  Object.assign(activityEls, {
    activityRuntimeStatus: activity$("activityRuntimeStatus"),
    activityLaneSwitcher: activity$("activityLaneSwitcher"),
    activityChainBadge: activity$("activityChainBadge"),
    activityLookback: activity$("activityLookback"),
    activityCount: activity$("activityCount"),
    activityWalletCount: activity$("activityWalletCount"),
    activitySwapCount: activity$("activitySwapCount"),
    activityClaimCount: activity$("activityClaimCount"),
    activityFeedStatus: activity$("activityFeedStatus"),
    activityUpdatedAt: activity$("activityUpdatedAt"),
    activityList: activity$("activityList"),
    activityContracts: activity$("activityContracts"),
    activityRefreshButton: activity$("activityRefreshButton"),
    activityMarketDocLink: activity$("activityMarketDocLink"),
    activityCommunityDocLink: activity$("activityCommunityDocLink"),
    activityRepoLink: activity$("activityRepoLink"),
    activityOpenTinySwapLink: activity$("activityOpenTinySwapLink"),
    activityOpenEpochLink: activity$("activityOpenEpochLink"),
    activityOpenMarketLink: activity$("activityOpenMarketLink"),
    activityOpenSearchLink: activity$("activityOpenSearchLink"),
    copyActivityLinkButton: activity$("copyActivityLinkButton"),
    shareActivityButton: activity$("shareActivityButton"),
    copyTinySwapLinkButton: activity$("copyTinySwapLinkButton"),
    copyTinySwapButton: activity$("copyTinySwapButton"),
    communityStatusBadge: activity$("communityStatusBadge"),
    communityUpdatedAt: activity$("communityUpdatedAt"),
    externalEventCount: activity$("externalEventCount"),
    externalWalletCount: activity$("externalWalletCount"),
    externalSwapCount: activity$("externalSwapCount"),
    externalClaimCount: activity$("externalClaimCount"),
    epochBadge: activity$("epochBadge"),
    epochTitle: activity$("epochTitle"),
    epochSummary: activity$("epochSummary"),
    epochFocus: activity$("epochFocus"),
    epochGoals: activity$("epochGoals"),
    epochCtaLink: activity$("epochCtaLink"),
    epochActivityLink: activity$("epochActivityLink"),
    copyEpochLinkButton: activity$("copyEpochLinkButton"),
    copyEpochShareButton: activity$("copyEpochShareButton"),
    activityStructureBadge: activity$("activityStructureBadge"),
    activityStructureNote: activity$("activityStructureNote"),
    activityStructureGrid: activity$("activityStructureGrid"),
    explorerLookupInput: activity$("explorerLookupInput"),
    openExplorerLookupButton: activity$("openExplorerLookupButton"),
    openSearchLookupButton: activity$("openSearchLookupButton"),
    explorerLookupStatus: activity$("explorerLookupStatus"),
  });

  await loadActivityConfig();
  await loadRuntimeStatus();
  await loadActivitySummary();
  bindActivityStatics();
  renderContracts();
  renderEpoch();
  renderMarketStructure();
  await refreshActivity();

  document.querySelectorAll("[data-activity-filter]").forEach((button) => {
    button.addEventListener("click", () => applyActivityFilter(button.dataset.activityFilter));
  });
  activityEls.activityRefreshButton.addEventListener("click", () => refreshActivity().catch((error) => {
    activityEls.activityFeedStatus.textContent = "error";
    activityEls.activityUpdatedAt.textContent = error?.message || "Failed to refresh activity.";
  }));
  activityEls.copyActivityLinkButton?.addEventListener("click", () => {
    copyText(absoluteUrl("/activity/"), "activity link copied").catch((error) => {
      activityEls.activityFeedStatus.textContent = error?.message || "copy failed";
    });
  });
  activityEls.shareActivityButton?.addEventListener("click", () => {
    shareUrl(
      "DARWIN activity",
      `DARWIN onchain activity on ${activityState.config.network.name}: swaps, claims, and outside-wallet progress.`,
      absoluteUrl("/activity/"),
    ).catch((error) => {
      activityEls.activityFeedStatus.textContent = error?.message || "share failed";
    });
  });
  const tinySwapHandler = () => {
    copyText(absoluteUrl(TINY_SWAP_PATH), "tiny-swap link copied").catch((error) => {
      activityEls.activityFeedStatus.textContent = error?.message || "copy failed";
    });
  };
  activityEls.copyTinySwapLinkButton?.addEventListener("click", tinySwapHandler);
  activityEls.copyTinySwapButton?.addEventListener("click", tinySwapHandler);
  const epochLinkHandler = () => {
    copyText(absoluteUrl(activityState.config.community?.epoch?.share_path || "/epoch/"), "epoch link copied").catch((error) => {
      activityEls.activityFeedStatus.textContent = error?.message || "copy failed";
    });
  };
  activityEls.copyEpochLinkButton?.addEventListener("click", epochLinkHandler);
  activityEls.copyEpochShareButton?.addEventListener("click", epochLinkHandler);
  activityEls.openExplorerLookupButton?.addEventListener("click", () => {
    const value = activityEls.explorerLookupInput.value.trim();
    const isAddress = /^0x[a-fA-F0-9]{40}$/.test(value);
    const isTx = /^0x[a-fA-F0-9]{64}$/.test(value);
    if (!isAddress && !isTx) {
      activityEls.explorerLookupStatus.textContent = "Enter a valid 0x address or 0x transaction hash.";
      return;
    }
    const url = explorerLink(value);
    window.open(url, "_blank", "noopener,noreferrer");
    activityEls.explorerLookupStatus.textContent = `Opened ${isAddress ? "address" : "transaction"} in explorer.`;
  });
  activityEls.openSearchLookupButton?.addEventListener("click", () => {
    const value = activityEls.explorerLookupInput.value.trim();
    if (!value) {
      activityEls.explorerLookupStatus.textContent = "Enter a Darwin alias, 0x address, or 0x transaction hash first.";
      return;
    }
    const href = window.DarwinLane && activityState.laneSelection
      ? window.DarwinLane.laneRelativeHref(`/search/?q=${encodeURIComponent(value)}`, activityState.laneSelection)
      : `/search/?q=${encodeURIComponent(value)}`;
    window.location.href = href;
  });
}

bootActivity().catch((error) => {
  console.error(error);
  if (activityEls.activityFeedStatus) {
    activityEls.activityFeedStatus.textContent = "error";
  }
  if (activityEls.activityList) {
    activityEls.activityList.innerHTML = `<p class="caption">${error?.message || "Failed to load DARWIN activity."}</p>`;
  }
});
