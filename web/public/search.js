const searchState = {
  laneSelection: null,
  config: null,
  provider: null,
  runtimeStatus: null,
  blockCache: new Map(),
  lastResolved: null,
};

const searchEls = {};
const SEARCH_LOOKBACK_FALLBACK = 50000;
const SEARCH_LOG_CHUNK_SIZE = 2000;

const SEARCH_ERC20_IFACE = new ethers.Interface([
  "function name() view returns (string)",
  "function symbol() view returns (string)",
  "function totalSupply() view returns (uint256)",
  "function balanceOf(address) view returns (uint256)",
  "function allowance(address,address) view returns (uint256)",
  "function approve(address,uint256) returns (bool)",
  "function transfer(address,uint256) returns (bool)",
]);
const SEARCH_WETH_IFACE = new ethers.Interface([
  "function deposit() payable",
  "function withdraw(uint256)",
  "function balanceOf(address) view returns (uint256)",
]);
const SEARCH_POOL_IFACE = new ethers.Interface([
  "function getReserves() view returns (uint256,uint256)",
  "function swapExactInput(address,uint256,uint256,address) returns (uint256)",
  "event SwapExecuted(address indexed trader,address indexed tokenIn,uint256 amountIn,address indexed tokenOut,uint256 amountOut,address to)",
]);
const SEARCH_FAUCET_IFACE = new ethers.Interface([
  "function claim() returns (uint256,uint256)",
  "function claimAmount() view returns (uint256)",
  "function claimCooldown() view returns (uint256)",
  "function nextClaimAt(address) view returns (uint256)",
  "event Claimed(address indexed claimer,address indexed recipient,uint256 tokenAmount,uint256 nativeAmount,uint256 nextEligibleAt)",
]);
const SEARCH_DISTRIBUTOR_IFACE = new ethers.Interface([
  "event Claimed(uint256 indexed index,address indexed account,uint256 amount)",
]);

const SEARCH_EVENT_TOPICS = {
  swap: ethers.id("SwapExecuted(address,address,uint256,address,uint256,address)"),
  faucet: ethers.id("Claimed(address,address,uint256,uint256,uint256)"),
  distributor: ethers.id("Claimed(uint256,address,uint256)"),
};

function search$(id) {
  return document.getElementById(id);
}

function shortAddress(value) {
  return value ? `${value.slice(0, 6)}…${value.slice(-4)}` : "-";
}

function isTxHash(value) {
  return /^0x[a-fA-F0-9]{64}$/.test((value || "").trim());
}

function isAddress(value) {
  return /^0x[a-fA-F0-9]{40}$/.test((value || "").trim());
}

function explorerLink(addressOrTx) {
  const base = searchState.config.network.explorer_base_url.replace(/\/$/, "");
  if ((addressOrTx || "").startsWith("0x") && addressOrTx.length === 42) {
    return `${base}/address/${addressOrTx}`;
  }
  return `${base}/tx/${addressOrTx}`;
}

function currentSearchUrl(query = "") {
  const url = new URL(window.location.href);
  if (query) {
    url.searchParams.set("q", query);
  } else {
    url.searchParams.delete("q");
  }
  return url.toString();
}

function absoluteUrl(path) {
  if (window.DarwinLane && searchState.laneSelection) {
    return window.DarwinLane.laneAbsoluteHref(path, searchState.laneSelection);
  }
  return new URL(path, window.location.origin).toString();
}

function formatUnits(value, decimals, precision = 6) {
  const text = ethers.formatUnits(value || 0n, decimals);
  const [whole, fraction = ""] = text.split(".");
  if (!fraction) return whole;
  const trimmed = fraction.slice(0, precision).replace(/0+$/, "");
  return trimmed ? `${whole}.${trimmed}` : whole;
}

function formatNative(value) {
  return `${formatUnits(value, 18, 6)} ETH`;
}

function attributionSuffix() {
  return String(searchState.config?.attribution?.builder_code_suffix || "").toLowerCase();
}

function hasBuilderSuffix(data) {
  const suffix = attributionSuffix();
  if (!suffix || !data || !data.startsWith("0x")) return false;
  return data.toLowerCase().endsWith(suffix.slice(2));
}

function stripBuilderSuffix(data) {
  const suffix = attributionSuffix();
  if (!hasBuilderSuffix(data)) return data;
  return `0x${data.slice(2, data.length - (suffix.length - 2))}`;
}

function knownEntries() {
  const entries = [
    {
      alias: "drw",
      aliases: ["drw", "token"],
      label: "DRW token",
      detail: "Public lane token contract",
      address: searchState.config.token.address,
    },
    {
      alias: "quote",
      aliases: ["quote", "weth"],
      label: `${searchState.config.quote_token.symbol} token`,
      detail: "Current lane quote token",
      address: searchState.config.quote_token.address,
    },
    {
      alias: "pool",
      aliases: ["pool", "canonical"],
      label: "Reference pool",
      detail: "Live DRW reference pool",
      address: searchState.config.pool.address,
    },
  ];

  if (searchState.config.faucet?.enabled && searchState.config.faucet.address) {
    entries.push({
      alias: "faucet",
      aliases: ["faucet", "claim"],
      label: "Faucet",
      detail: "Public DRW claim surface",
      address: searchState.config.faucet.address,
    });
  }
  if (searchState.config.vnext?.enabled && searchState.config.vnext.distributor) {
    entries.push({
      alias: "distributor",
      aliases: ["distributor", "merkle"],
      label: "Distributor",
      detail: "Merkle distribution contract",
      address: searchState.config.vnext.distributor,
    });
  }
  if (searchState.config.vnext?.enabled && searchState.config.vnext.timelock) {
    entries.push({
      alias: "timelock",
      aliases: ["timelock", "governance"],
      label: "Timelock",
      detail: "Mutable governance root",
      address: searchState.config.vnext.timelock,
    });
  }
  return entries;
}

function knownEntryByAddress(address) {
  const normalized = String(address || "").toLowerCase();
  return knownEntries().find((entry) => entry.address.toLowerCase() === normalized) || null;
}

function resolveSearchInput(rawValue) {
  const value = String(rawValue || "").trim();
  if (!value) return { kind: "empty", raw: value };
  const lowered = value.toLowerCase();
  const aliasEntry = knownEntries().find((entry) => entry.aliases.some((alias) => alias === lowered));
  if (aliasEntry) {
    return {
      kind: "address",
      raw: value,
      value: aliasEntry.address,
      knownEntry: aliasEntry,
    };
  }
  if (isTxHash(value)) {
    return { kind: "tx", raw: value, value };
  }
  if (isAddress(value)) {
    return { kind: "address", raw: value, value: ethers.getAddress(value) };
  }
  return { kind: "invalid", raw: value };
}

async function loadSearchConfig() {
  searchState.laneSelection = window.DarwinLane ? await window.DarwinLane.resolveSelection() : null;
  const configPath = searchState.laneSelection?.currentLane?.path || "/market-config.json";
  const response = await fetch(configPath, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load market config: ${response.status}`);
  }
  searchState.config = await response.json();
  const readRpcUrl = searchState.config.network.read_rpc_url || searchState.config.network.rpc_url;
  searchState.provider = new ethers.JsonRpcProvider(readRpcUrl);
}

async function loadRuntimeStatus() {
  try {
    const response = await fetch(`../runtime-status.json?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) return;
    searchState.runtimeStatus = await response.json();
    if (searchState.runtimeStatus?.summary) {
      searchEls.searchRuntimeStatus.textContent = searchState.runtimeStatus.summary;
    }
  } catch {
    // Keep the default hero copy if runtime status is unavailable.
  }
}

function bindSearchStatics() {
  if (window.DarwinLane && searchState.laneSelection) {
    window.DarwinLane.renderSwitcher(searchEls.searchLaneSwitcher, searchState.laneSelection);
  }
  searchEls.searchChainBadge.textContent = searchState.config.network.name;
  searchEls.searchExplorerBadge.textContent = searchState.config.network.explorer_base_url
    .replace(/^https?:\/\//, "")
    .replace(/\/$/, "");
  searchEls.searchAttributionBadge.textContent = searchState.config.attribution?.builder_code
    ? `builder ${searchState.config.attribution.builder_code}`
    : "direct mode";
  searchEls.searchOpenMarketLink.href = window.DarwinLane && searchState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/trade/", searchState.laneSelection)
    : "/trade/";
  searchEls.searchOpenActivityLink.href = window.DarwinLane && searchState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/activity/", searchState.laneSelection)
    : "/activity/";
  searchEls.searchOpenTinySwapLink.href = window.DarwinLane && searchState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/trade/?preset=tiny-sell", searchState.laneSelection)
    : "/trade/?preset=tiny-sell";
}

function renderQuickActions() {
  searchEls.searchQuickActions.innerHTML = "";
  for (const entry of knownEntries()) {
    const button = document.createElement("button");
    button.className = "button button-secondary tiny-button";
    button.textContent = entry.label;
    button.addEventListener("click", () => {
      searchEls.searchInput.value = entry.alias;
      runSearch(entry.alias).catch((error) => renderError(error?.message || "Search failed."));
    });
    searchEls.searchQuickActions.appendChild(button);
  }
}

function metricCard(label, value, detail) {
  const article = document.createElement("article");
  article.className = "metric";
  const labelNode = document.createElement("span");
  labelNode.className = "label";
  labelNode.textContent = label;
  article.appendChild(labelNode);
  const valueNode = document.createElement("strong");
  valueNode.textContent = value;
  article.appendChild(valueNode);
  const detailNode = document.createElement("small");
  detailNode.textContent = detail;
  article.appendChild(detailNode);
  return article;
}

function detailCard(label, value, detail = "") {
  const article = document.createElement("article");
  article.className = "detail-card";
  const labelNode = document.createElement("span");
  labelNode.className = "label";
  labelNode.textContent = label;
  article.appendChild(labelNode);
  const valueNode = document.createElement("strong");
  valueNode.textContent = value;
  article.appendChild(valueNode);
  if (detail) {
    const detailNode = document.createElement("p");
    detailNode.className = "tiny-hint";
    detailNode.textContent = detail;
    article.appendChild(detailNode);
  }
  return article;
}

function renderSummary(cards) {
  searchEls.searchSummaryGrid.innerHTML = "";
  for (const card of cards) {
    searchEls.searchSummaryGrid.appendChild(metricCard(card.label, card.value, card.detail));
  }
}

function renderDetails(items) {
  searchEls.searchDetails.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "caption";
    empty.textContent = "No Darwin-specific detail was available for this query.";
    searchEls.searchDetails.appendChild(empty);
    return;
  }
  for (const item of items) {
    searchEls.searchDetails.appendChild(detailCard(item.label, item.value, item.detail));
  }
}

function renderState(cards, hint, badge) {
  searchEls.searchStateGrid.innerHTML = "";
  for (const card of cards) {
    searchEls.searchStateGrid.appendChild(metricCard(card.label, card.value, card.detail));
  }
  searchEls.searchStateHint.textContent = hint;
  searchEls.searchStateBadge.textContent = badge;
}

function clearActivityMatches(message = "Search a wallet or contract to load matching Darwin events from the current lane.") {
  searchEls.searchActivityList.innerHTML = `<p class="caption">${message}</p>`;
  searchEls.searchMatchesBadge.textContent = "idle";
}

function parseSwapLog(log) {
  const parsed = SEARCH_POOL_IFACE.parseLog(log);
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
      tokenIn.toLowerCase() === searchState.config.token.address.toLowerCase()
        ? `Sold ${formatUnits(amountIn, searchState.config.token.decimals, 6)} ${searchState.config.token.symbol}`
        : `Bought ${formatUnits(amountOut, searchState.config.token.decimals, 6)} ${searchState.config.token.symbol}`,
    detail: `${formatUnits(amountIn, tokenIn.toLowerCase() === searchState.config.token.address.toLowerCase() ? searchState.config.token.decimals : searchState.config.quote_token.decimals, 6)} ${tokenIn.toLowerCase() === searchState.config.token.address.toLowerCase() ? searchState.config.token.symbol : searchState.config.quote_token.symbol} -> ${formatUnits(amountOut, tokenOut.toLowerCase() === searchState.config.token.address.toLowerCase() ? searchState.config.token.decimals : searchState.config.quote_token.decimals, 12)} ${tokenOut.toLowerCase() === searchState.config.token.address.toLowerCase() ? searchState.config.token.symbol : searchState.config.quote_token.symbol}`,
  };
}

function parseFaucetLog(log) {
  const parsed = SEARCH_FAUCET_IFACE.parseLog(log);
  return {
    type: "faucet",
    blockNumber: Number(log.blockNumber),
    txHash: log.transactionHash,
    actor: parsed.args.claimer,
    title: `Claimed ${formatUnits(parsed.args.tokenAmount, searchState.config.token.decimals, 6)} DRW`,
    detail: `${formatUnits(parsed.args.tokenAmount, searchState.config.token.decimals, 6)} DRW + ${formatUnits(parsed.args.nativeAmount, 18, 6)} ETH drip`,
  };
}

function parseDistributorLog(log) {
  const parsed = SEARCH_DISTRIBUTOR_IFACE.parseLog(log);
  return {
    type: "distributor",
    blockNumber: Number(log.blockNumber),
    txHash: log.transactionHash,
    actor: parsed.args.account,
    title: `Claimed ${formatUnits(parsed.args.amount, searchState.config.token.decimals, 6)} DRW`,
    detail: "Merkle distribution claim",
  };
}

function parseKnownLog(log) {
  try {
    if (log.address.toLowerCase() === searchState.config.pool.address.toLowerCase()) {
      return parseSwapLog(log);
    }
    if (searchState.config.faucet?.enabled && log.address.toLowerCase() === searchState.config.faucet.address.toLowerCase()) {
      return parseFaucetLog(log);
    }
    if (searchState.config.vnext?.enabled && searchState.config.vnext.distributor && log.address.toLowerCase() === searchState.config.vnext.distributor.toLowerCase()) {
      return parseDistributorLog(log);
    }
  } catch {
    return null;
  }
  return null;
}

async function blockTimestamp(blockNumber) {
  if (!searchState.blockCache.has(blockNumber)) {
    const block = await searchState.provider.getBlock(blockNumber);
    searchState.blockCache.set(blockNumber, block?.timestamp || 0);
  }
  return searchState.blockCache.get(blockNumber) || 0;
}

async function hydrateTimestamps(events) {
  await Promise.all(events.map(async (event) => {
    event.timestamp = await blockTimestamp(event.blockNumber);
  }));
}

function renderActivityMatches(events, badgeText = "live") {
  searchEls.searchActivityList.innerHTML = "";
  searchEls.searchMatchesBadge.textContent = badgeText;

  if (!events.length) {
    const empty = document.createElement("p");
    empty.className = "caption";
    empty.textContent = "No Darwin events matched this query in the current lookback.";
    searchEls.searchActivityList.appendChild(empty);
    return;
  }

  for (const event of events) {
    const card = document.createElement("article");
    card.className = "activity-card";

    const top = document.createElement("div");
    top.className = "activity-top";

    const kind = document.createElement("span");
    kind.className = "badge";
    kind.textContent = event.type;
    top.appendChild(kind);

    const actor = document.createElement("a");
    actor.className = "mono";
    actor.href = explorerLink(event.actor);
    actor.target = "_blank";
    actor.rel = "noreferrer";
    actor.textContent = shortAddress(event.actor);
    top.appendChild(actor);
    card.appendChild(top);

    const title = document.createElement("strong");
    title.textContent = event.title;
    card.appendChild(title);

    const detail = document.createElement("p");
    detail.className = "caption";
    detail.textContent = event.detail;
    card.appendChild(detail);

    const meta = document.createElement("div");
    meta.className = "activity-meta";

    const tx = document.createElement("a");
    tx.href = explorerLink(event.txHash);
    tx.target = "_blank";
    tx.rel = "noreferrer";
    tx.textContent = shortAddress(event.txHash);
    meta.appendChild(tx);

    const when = document.createElement("span");
    when.className = "mono";
    when.textContent = event.timestamp
      ? new Date(event.timestamp * 1000).toLocaleString()
      : `Block ${event.blockNumber}`;
    meta.appendChild(when);
    card.appendChild(meta);

    searchEls.searchActivityList.appendChild(card);
  }
}

async function getLogsChunked(filter) {
  const logs = [];
  for (let chunkStart = Number(filter.fromBlock); chunkStart <= Number(filter.toBlock); chunkStart += SEARCH_LOG_CHUNK_SIZE) {
    const chunkEnd = Math.min(Number(filter.toBlock), chunkStart + SEARCH_LOG_CHUNK_SIZE - 1);
    const chunkLogs = await searchState.provider.getLogs({
      ...filter,
      fromBlock: chunkStart,
      toBlock: chunkEnd,
    });
    logs.push(...chunkLogs);
  }
  return logs;
}

function zeroPadAddress(address) {
  return ethers.zeroPadValue(address, 32);
}

async function fetchAddressMatches(address) {
  const latestBlock = await searchState.provider.getBlockNumber();
  const lookback = searchState.config.activity?.lookback_blocks || SEARCH_LOOKBACK_FALLBACK;
  const fromBlock = Math.max(0, latestBlock - lookback);
  const normalized = address.toLowerCase();
  const known = knownEntryByAddress(normalized);

  let logs = [];
  if (known?.address.toLowerCase() === searchState.config.pool.address.toLowerCase()) {
    logs = await getLogsChunked({
      address: searchState.config.pool.address,
      fromBlock,
      toBlock: latestBlock,
      topics: [SEARCH_EVENT_TOPICS.swap],
    });
  } else if (searchState.config.faucet?.enabled && known?.address.toLowerCase() === searchState.config.faucet.address.toLowerCase()) {
    logs = await getLogsChunked({
      address: searchState.config.faucet.address,
      fromBlock,
      toBlock: latestBlock,
      topics: [SEARCH_EVENT_TOPICS.faucet],
    });
  } else if (searchState.config.vnext?.enabled && searchState.config.vnext.distributor && known?.address.toLowerCase() === searchState.config.vnext.distributor.toLowerCase()) {
    logs = await getLogsChunked({
      address: searchState.config.vnext.distributor,
      fromBlock,
      toBlock: latestBlock,
      topics: [SEARCH_EVENT_TOPICS.distributor],
    });
  } else {
    const actorTopic = zeroPadAddress(address);
    const queries = [
      getLogsChunked({
        address: searchState.config.pool.address,
        fromBlock,
        toBlock: latestBlock,
        topics: [SEARCH_EVENT_TOPICS.swap, actorTopic],
      }),
    ];
    if (searchState.config.faucet?.enabled && searchState.config.faucet.address) {
      queries.push(
        getLogsChunked({
          address: searchState.config.faucet.address,
          fromBlock,
          toBlock: latestBlock,
          topics: [SEARCH_EVENT_TOPICS.faucet, actorTopic],
        }),
      );
      queries.push(
        getLogsChunked({
          address: searchState.config.faucet.address,
          fromBlock,
          toBlock: latestBlock,
          topics: [SEARCH_EVENT_TOPICS.faucet, null, actorTopic],
        }),
      );
    }
    if (searchState.config.vnext?.enabled && searchState.config.vnext.distributor) {
      queries.push(
        getLogsChunked({
          address: searchState.config.vnext.distributor,
          fromBlock,
          toBlock: latestBlock,
          topics: [SEARCH_EVENT_TOPICS.distributor, null, actorTopic],
        }),
      );
    }
    logs = (await Promise.all(queries)).flat();
  }

  const deduped = [];
  const seen = new Set();
  for (const log of logs) {
    const key = `${log.transactionHash}:${log.index ?? log.logIndex ?? 0}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const parsed = parseKnownLog(log);
    if (parsed) deduped.push(parsed);
  }
  await hydrateTimestamps(deduped);
  deduped.sort((left, right) => {
    if (right.blockNumber !== left.blockNumber) return right.blockNumber - left.blockNumber;
    return right.txHash.localeCompare(left.txHash);
  });
  return deduped.slice(0, 20);
}

async function fetchTokenMetadata(address) {
  const contract = new ethers.Contract(address, SEARCH_ERC20_IFACE, searchState.provider);
  try {
    const [name, symbol, totalSupply] = await Promise.all([
      contract.name(),
      contract.symbol(),
      contract.totalSupply(),
    ]);
    return { name, symbol, totalSupply };
  } catch {
    return null;
  }
}

function decodeCall(tx) {
  const data = stripBuilderSuffix(tx.data || "0x");
  const interfaces = [
    { label: "Reference pool", iface: SEARCH_POOL_IFACE },
    { label: "DRW token", iface: SEARCH_ERC20_IFACE },
    { label: `${searchState.config.quote_token.symbol} token`, iface: SEARCH_WETH_IFACE },
    { label: "Faucet", iface: SEARCH_FAUCET_IFACE },
  ];

  for (const candidate of interfaces) {
    try {
      const parsed = candidate.iface.parseTransaction({ data, value: tx.value });
      if (parsed) {
        return { label: candidate.label, parsed };
      }
    } catch {
      // Try the next interface.
    }
  }
  return null;
}

function decodeDetails(decoded) {
  if (!decoded) return [];
  const { label, parsed } = decoded;
  const items = [
    {
      label: "Decoded target",
      value: label,
      detail: `Method ${parsed.name}`,
    },
  ];

  if (parsed.name === "claim") {
    items.push({
      label: "Call",
      value: "claim()",
      detail: "Public DRW faucet claim",
    });
    return items;
  }
  if (parsed.name === "deposit") {
    items.push({
      label: "Call",
      value: "deposit()",
      detail: `Wraps native ${searchState.config.network.native_symbol} into ${searchState.config.quote_token.symbol}`,
    });
    return items;
  }
  if (parsed.name === "approve") {
    items.push({
      label: "Spender",
      value: shortAddress(parsed.args[0]),
      detail: knownEntryByAddress(parsed.args[0])?.label || parsed.args[0],
    });
    items.push({
      label: "Amount",
      value: formatUnits(parsed.args[1], parsed.fragment.name === "approve" && label === "DRW token"
        ? searchState.config.token.decimals
        : searchState.config.quote_token.decimals, 6),
      detail: label,
    });
    return items;
  }
  if (parsed.name === "transfer") {
    items.push({
      label: "Recipient",
      value: shortAddress(parsed.args[0]),
      detail: parsed.args[0],
    });
    items.push({
      label: "Amount",
      value: formatUnits(parsed.args[1], label === "DRW token" ? searchState.config.token.decimals : searchState.config.quote_token.decimals, 6),
      detail: label,
    });
    return items;
  }
  if (parsed.name === "swapExactInput") {
    const tokenIn = parsed.args[0];
    const inputIsDrw = tokenIn.toLowerCase() === searchState.config.token.address.toLowerCase();
    items.push({
      label: "Token in",
      value: inputIsDrw ? searchState.config.token.symbol : searchState.config.quote_token.symbol,
      detail: tokenIn,
    });
    items.push({
      label: "Amount in",
      value: formatUnits(parsed.args[1], inputIsDrw ? searchState.config.token.decimals : searchState.config.quote_token.decimals, 6),
      detail: inputIsDrw ? "Selling DRW" : "Buying DRW",
    });
    items.push({
      label: "Minimum out",
      value: formatUnits(parsed.args[2], inputIsDrw ? searchState.config.quote_token.decimals : searchState.config.token.decimals, 12),
      detail: inputIsDrw ? searchState.config.quote_token.symbol : searchState.config.token.symbol,
    });
    items.push({
      label: "Recipient",
      value: shortAddress(parsed.args[3]),
      detail: parsed.args[3],
    });
    return items;
  }
  return items;
}

async function lookupTransaction(resolved) {
  const hash = resolved.value;
  const [tx, receipt] = await Promise.all([
    searchState.provider.getTransaction(hash),
    searchState.provider.getTransactionReceipt(hash),
  ]);
  if (!tx) {
    throw new Error("Transaction not found on the current Darwin lane.");
  }

  const toLabel = knownEntryByAddress(tx.to)?.label || shortAddress(tx.to || "");
  const blockNumber = receipt?.blockNumber || tx.blockNumber;
  const block = blockNumber ? await searchState.provider.getBlock(blockNumber) : null;
  const decoded = decodeCall(tx);
  const receiptEvents = (receipt?.logs || [])
    .map(parseKnownLog)
    .filter(Boolean);
  await hydrateTimestamps(receiptEvents);

  searchState.lastResolved = hash;
  searchEls.searchKindBadge.textContent = "transaction";
  searchEls.searchResolvedBadge.textContent = decoded?.parsed?.name || (knownEntryByAddress(tx.to)?.label ? "known target" : "raw");
  searchEls.searchExplorerLink.href = explorerLink(hash);

  renderSummary([
    { label: "Type", value: "Transaction", detail: searchState.config.network.name },
    {
      label: "Resolved",
      value: knownEntryByAddress(tx.to)?.label || "unknown target",
      detail: tx.to || "contract creation",
    },
    {
      label: "Builder Code",
      value: hasBuilderSuffix(tx.data) ? "detected" : "not detected",
      detail: searchState.config.attribution?.builder_code || "no builder code configured",
    },
    {
      label: "Explorer",
      value: shortAddress(hash),
      detail: "current lane tx lookup",
    },
  ]);

  renderDetails([
    {
      label: "Status",
      value: receipt ? (receipt.status === 1 ? "confirmed" : "reverted") : "pending",
      detail: block?.timestamp ? new Date(block.timestamp * 1000).toLocaleString() : `Block ${blockNumber || "pending"}`,
    },
    {
      label: "From",
      value: shortAddress(tx.from),
      detail: tx.from,
    },
    {
      label: "To",
      value: toLabel,
      detail: tx.to || "contract creation",
    },
    {
      label: "Nonce",
      value: String(tx.nonce),
      detail: `Gas limit ${tx.gasLimit.toString()}`,
    },
    {
      label: "Value",
      value: formatNative(tx.value),
      detail: `Effective gas price ${receipt?.gasPrice ? formatUnits(receipt.gasPrice, 9, 6) : formatUnits(tx.gasPrice || 0n, 9, 6)} gwei`,
    },
    {
      label: "Method",
      value: decoded?.parsed?.name || (tx.data?.slice(0, 10) || "0x"),
      detail: decoded?.label || "No Darwin-specific decoder matched this input.",
    },
    ...decodeDetails(decoded),
  ]);

  renderState([
    { label: "Receipt status", value: receipt ? (receipt.status === 1 ? "success" : "failed") : "pending", detail: "transaction lifecycle" },
    { label: "Gas used", value: receipt?.gasUsed ? receipt.gasUsed.toString() : "-", detail: "execution result" },
    { label: "Block", value: blockNumber ? String(blockNumber) : "-", detail: "current lane" },
    { label: "Receipt events", value: String(receiptEvents.length), detail: "Darwin logs decoded from this tx" },
  ], "Transaction lookups focus on the Darwin contracts and whether attribution reached calldata.", "tx");

  renderActivityMatches(receiptEvents, receiptEvents.length ? "tx events" : "no Darwin logs");
}

async function lookupAddress(resolved) {
  const address = resolved.value;
  const normalized = address.toLowerCase();
  const known = resolved.knownEntry || knownEntryByAddress(address);
  const [balance, code, nonce, drwBalance, quoteBalance, tokenMeta, matches] = await Promise.all([
    searchState.provider.getBalance(address),
    searchState.provider.getCode(address),
    searchState.provider.getTransactionCount(address),
    new ethers.Contract(searchState.config.token.address, SEARCH_ERC20_IFACE, searchState.provider).balanceOf(address),
    new ethers.Contract(searchState.config.quote_token.address, SEARCH_ERC20_IFACE, searchState.provider).balanceOf(address),
    fetchTokenMetadata(address),
    fetchAddressMatches(address),
  ]);

  let poolReserves = null;
  if (normalized === searchState.config.pool.address.toLowerCase()) {
    try {
      const pool = new ethers.Contract(searchState.config.pool.address, SEARCH_POOL_IFACE, searchState.provider);
      const [reserveToken, reserveQuote] = await pool.getReserves();
      poolReserves = { reserveToken, reserveQuote };
    } catch {
      poolReserves = null;
    }
  }

  searchState.lastResolved = address;
  searchEls.searchKindBadge.textContent = code && code !== "0x" ? "contract" : "address";
  searchEls.searchResolvedBadge.textContent = known?.label || (code && code !== "0x" ? "contract" : "wallet");
  searchEls.searchExplorerLink.href = explorerLink(address);

  renderSummary([
    { label: "Type", value: code && code !== "0x" ? "Address / contract" : "Address / wallet", detail: searchState.config.network.name },
    { label: "Resolved", value: known?.label || "unlabeled address", detail: address },
    {
      label: "Builder Code",
      value: known?.address.toLowerCase() === searchState.config.pool.address.toLowerCase() ? "pool surface" : "n/a",
      detail: "Builder Code is checked on transactions, not stored on addresses",
    },
    { label: "Explorer", value: shortAddress(address), detail: "current lane address lookup" },
  ]);

  const details = [
    {
      label: "Address",
      value: shortAddress(address),
      detail: address,
    },
    {
      label: "Kind",
      value: code && code !== "0x" ? "contract" : "wallet",
      detail: known?.detail || "Detected from live code at the current lane address.",
    },
    {
      label: "Nonce",
      value: String(nonce),
      detail: "current lane transaction count",
    },
  ];

  if (tokenMeta) {
    details.push({
      label: "Token metadata",
      value: `${tokenMeta.name} (${tokenMeta.symbol})`,
      detail: `Total supply ${formatUnits(tokenMeta.totalSupply, searchState.config.token.decimals, 3)}`,
    });
  }
  if (poolReserves) {
    details.push({
      label: "Pool reserves",
      value: `${formatUnits(poolReserves.reserveToken, searchState.config.token.decimals, 6)} ${searchState.config.token.symbol}`,
      detail: `${formatUnits(poolReserves.reserveQuote, searchState.config.quote_token.decimals, 12)} ${searchState.config.quote_token.symbol}`,
    });
  }
  renderDetails(details);

  renderState([
    { label: "Native ETH", value: formatNative(balance), detail: searchState.config.network.name },
    { label: "DRW", value: `${formatUnits(drwBalance, searchState.config.token.decimals, 6)} ${searchState.config.token.symbol}`, detail: "current lane token balance" },
    { label: `${searchState.config.quote_token.symbol}`, value: `${formatUnits(quoteBalance, searchState.config.quote_token.decimals, 12)} ${searchState.config.quote_token.symbol}`, detail: "current lane quote balance" },
    { label: "Darwin matches", value: String(matches.length), detail: `last ${searchState.config.activity?.lookback_blocks || SEARCH_LOOKBACK_FALLBACK} blocks` },
  ], known?.label ? `Known Darwin surface: ${known.label}.` : "Wallet and contract lookups read balances from the current Darwin lane.", known?.label || (code && code !== "0x" ? "contract" : "wallet"));

  renderActivityMatches(matches, matches.length ? "matched" : "none");
}

function resetSearchView() {
  searchState.lastResolved = null;
  searchEls.searchStatusBadge.textContent = "idle";
  searchEls.searchKindBadge.textContent = "waiting";
  searchEls.searchResolvedBadge.textContent = "none";
  searchEls.searchExplorerLink.href = "#";
  renderSummary([
    { label: "Type", value: "-", detail: "transaction or address" },
    { label: "Resolved", value: "-", detail: "known Darwin label if matched" },
    { label: "Builder Code", value: "-", detail: "suffix detection when relevant" },
    { label: "Explorer", value: "-", detail: "current Darwin lane" },
  ]);
  renderDetails([]);
  renderState([
    { label: "Native ETH", value: "-", detail: "search a wallet or contract" },
    { label: "DRW", value: "-", detail: "current lane token balance" },
    { label: "Quote asset", value: "-", detail: "current lane quote token balance" },
    { label: "Recent Darwin matches", value: "-", detail: "within the current lookback" },
  ], "Search a wallet or contract to load DRW balances, quote-token balances, pool reserves, or recent Darwin activity.", "idle");
  clearActivityMatches();
}

function renderError(message) {
  searchEls.searchStatusBadge.textContent = "error";
  searchEls.searchKindBadge.textContent = "error";
  searchEls.searchResolvedBadge.textContent = "invalid";
  searchEls.searchHint.textContent = message;
  renderDetails([{ label: "Search error", value: message, detail: "The Darwin search surface only supports tx hashes, wallet addresses, and known Darwin aliases." }]);
  clearActivityMatches(message);
}

async function runSearch(rawQuery = searchEls.searchInput.value) {
  const resolved = resolveSearchInput(rawQuery);
  if (resolved.kind === "empty") {
    history.replaceState({}, "", currentSearchUrl(""));
    searchEls.searchHint.textContent = "Try drw, pool, faucet, distributor, timelock, an address, or a transaction hash.";
    resetSearchView();
    return;
  }
  if (resolved.kind === "invalid") {
    renderError("Enter a valid 0x transaction hash, 0x address, or a known Darwin alias.");
    return;
  }

  searchEls.searchStatusBadge.textContent = "loading";
  searchEls.searchHint.textContent = `Searching ${resolved.kind === "tx" ? "transaction" : "address"} on ${searchState.config.network.name}.`;
  history.replaceState({}, "", currentSearchUrl(rawQuery.trim()));

  if (resolved.kind === "tx") {
    await lookupTransaction(resolved);
  } else {
    await lookupAddress(resolved);
  }

  searchEls.searchStatusBadge.textContent = "live";
}

async function copyText(value, status) {
  await navigator.clipboard.writeText(value);
  searchEls.searchStatusBadge.textContent = status;
}

async function bootSearch() {
  Object.assign(searchEls, {
    searchRuntimeStatus: search$("searchRuntimeStatus"),
    searchLaneSwitcher: search$("searchLaneSwitcher"),
    searchChainBadge: search$("searchChainBadge"),
    searchExplorerBadge: search$("searchExplorerBadge"),
    searchAttributionBadge: search$("searchAttributionBadge"),
    searchOpenMarketLink: search$("searchOpenMarketLink"),
    searchOpenActivityLink: search$("searchOpenActivityLink"),
    searchOpenTinySwapLink: search$("searchOpenTinySwapLink"),
    copySearchLinkButton: search$("copySearchLinkButton"),
    searchStatusBadge: search$("searchStatusBadge"),
    searchInput: search$("searchInput"),
    runSearchButton: search$("runSearchButton"),
    clearSearchButton: search$("clearSearchButton"),
    copySearchQueryLinkButton: search$("copySearchQueryLinkButton"),
    searchQuickActions: search$("searchQuickActions"),
    searchHint: search$("searchHint"),
    searchKindBadge: search$("searchKindBadge"),
    searchSummaryGrid: search$("searchSummaryGrid"),
    searchResolvedBadge: search$("searchResolvedBadge"),
    searchDetails: search$("searchDetails"),
    searchStateBadge: search$("searchStateBadge"),
    searchStateGrid: search$("searchStateGrid"),
    searchStateHint: search$("searchStateHint"),
    searchMatchesBadge: search$("searchMatchesBadge"),
    searchActivityList: search$("searchActivityList"),
    searchExplorerLink: search$("searchExplorerLink"),
    copyResolvedValueButton: search$("copyResolvedValueButton"),
  });

  await loadSearchConfig();
  await loadRuntimeStatus();
  bindSearchStatics();
  renderQuickActions();
  resetSearchView();

  searchEls.runSearchButton.addEventListener("click", () => {
    runSearch().catch((error) => renderError(error?.message || "Search failed."));
  });
  searchEls.clearSearchButton.addEventListener("click", () => {
    searchEls.searchInput.value = "";
    runSearch("").catch((error) => renderError(error?.message || "Search failed."));
  });
  searchEls.copySearchLinkButton.addEventListener("click", () => {
    copyText(currentSearchUrl(searchEls.searchInput.value.trim()), "search link copied").catch((error) => {
      searchEls.searchStatusBadge.textContent = error?.message || "copy failed";
    });
  });
  searchEls.copySearchQueryLinkButton.addEventListener("click", () => {
    copyText(currentSearchUrl(searchEls.searchInput.value.trim()), "search link copied").catch((error) => {
      searchEls.searchStatusBadge.textContent = error?.message || "copy failed";
    });
  });
  searchEls.copyResolvedValueButton.addEventListener("click", () => {
    if (!searchState.lastResolved) {
      searchEls.searchStatusBadge.textContent = "nothing resolved";
      return;
    }
    copyText(searchState.lastResolved, "resolved value copied").catch((error) => {
      searchEls.searchStatusBadge.textContent = error?.message || "copy failed";
    });
  });
  searchEls.searchInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    runSearch().catch((error) => renderError(error?.message || "Search failed."));
  });

  const seededQuery = new URL(window.location.href).searchParams.get("q");
  if (seededQuery) {
    searchEls.searchInput.value = seededQuery;
    await runSearch(seededQuery);
  }
}

bootSearch().catch((error) => {
  console.error(error);
  renderError(error?.message || "Failed to boot Darwin search.");
});
