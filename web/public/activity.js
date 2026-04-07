const activityState = {
  config: null,
  runtimeStatus: null,
  provider: null,
  events: [],
  filter: "all",
  blockCache: new Map(),
};

const activityEls = {};

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
const LOG_CHUNK_SIZE = 10000;

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

function formatUnits(value, decimals, precision = 6) {
  const text = ethers.formatUnits(value, decimals);
  const [whole, frac = ""] = text.split(".");
  if (!frac) return whole;
  const trimmed = frac.slice(0, precision).replace(/0+$/, "");
  return trimmed ? `${whole}.${trimmed}` : whole;
}

async function loadActivityConfig() {
  const response = await fetch("../market-config.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load market config: ${response.status}`);
  }
  activityState.config = await response.json();
  activityState.provider = new ethers.JsonRpcProvider(activityState.config.network.rpc_url);
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

function bindActivityStatics() {
  activityEls.activityChainBadge.textContent = activityState.config.network.name;
  activityEls.activityLookback.textContent = `${activityState.config.activity.lookback_blocks.toLocaleString()} blocks`;
  activityEls.activityMarketDocLink.href = activityState.config.links.market_bootstrap;
  activityEls.activityRepoLink.href = activityState.config.links.repo;
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
  activityEls.activityUpdatedAt.textContent = `Updated ${new Date().toLocaleString()} from live Base Sepolia RPC.`;
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
  await fetchEvents();
  renderStats();
  renderEvents();
}

async function bootActivity() {
  Object.assign(activityEls, {
    activityRuntimeStatus: activity$("activityRuntimeStatus"),
    activityChainBadge: activity$("activityChainBadge"),
    activityLookback: activity$("activityLookback"),
    activityCount: activity$("activityCount"),
    activityWalletCount: activity$("activityWalletCount"),
    activitySwapCount: activity$("activitySwapCount"),
    activityClaimCount: activity$("activityClaimCount"),
    activityFeedStatus: activity$("activityFeedStatus"),
    activityUpdatedAt: activity$("activityUpdatedAt"),
    activityList: activity$("activityList"),
    activityRefreshButton: activity$("activityRefreshButton"),
    activityMarketDocLink: activity$("activityMarketDocLink"),
    activityRepoLink: activity$("activityRepoLink"),
  });

  await loadActivityConfig();
  await loadRuntimeStatus();
  bindActivityStatics();
  await refreshActivity();

  document.querySelectorAll("[data-activity-filter]").forEach((button) => {
    button.addEventListener("click", () => applyActivityFilter(button.dataset.activityFilter));
  });
  activityEls.activityRefreshButton.addEventListener("click", () => refreshActivity().catch((error) => {
    activityEls.activityFeedStatus.textContent = "error";
    activityEls.activityUpdatedAt.textContent = error?.message || "Failed to refresh activity.";
  }));
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
