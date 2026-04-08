const ERC20_ABI = [
  "function symbol() view returns (string)",
  "function decimals() view returns (uint8)",
  "function balanceOf(address) view returns (uint256)",
  "function allowance(address,address) view returns (uint256)",
  "function approve(address,uint256) returns (bool)",
];

const POOL_ABI = [
  "function feeBps() view returns (uint16)",
  "function baseReserve() view returns (uint256)",
  "function quoteReserve() view returns (uint256)",
  "function quoteExactInput(address,uint256) view returns (uint256)",
  "function swapExactInput(address,uint256,uint256,address) returns (uint256)",
];

const WETH_ABI = [
  "function deposit() payable",
  "function balanceOf(address) view returns (uint256)",
  "function allowance(address,address) view returns (uint256)",
  "function approve(address,uint256) returns (bool)",
];

const FAUCET_ABI = [
  "function claim() returns (uint256,uint256)",
  "function nextClaimAt(address) view returns (uint256)",
  "function claimAmount() view returns (uint256)",
  "function nativeDripAmount() view returns (uint256)",
  "function claimCooldown() view returns (uint256)",
];

const state = {
  laneSelection: null,
  config: null,
  runtimeStatus: null,
  activitySummary: null,
  marketStructure: null,
  walletCapabilities: null,
  rpcProvider: null,
  browserProvider: null,
  injectedProvider: null,
  signer: null,
  account: "",
  mode: "buy",
  tinyPreset: "",
  sharePayload: null,
  token: null,
  quoteToken: null,
  pool: null,
  faucet: null,
};

const TINY_SWAP_PRESETS = {
  "tiny-sell": {
    mode: "sell",
    amount: "10",
    slippageBps: "150",
    wrapAmount: "0.00002",
    note: "Tiny sell loaded: claim 100 DRW, then sell 10 DRW for a first public market action.",
  },
  "tiny-buy": {
    mode: "buy",
    amount: "0.00001",
    slippageBps: "150",
    wrapAmount: "0.00002",
    note: "Tiny buy loaded: use 0.00001 WETH to buy a small DRW amount from the live pool.",
  },
  "tiny-wrap": {
    mode: "buy",
    amount: "0.00001",
    slippageBps: "150",
    wrapAmount: "0.00002",
    note: "Tiny wrap loaded: wrap 0.00002 ETH first, then use the tiny buy path if the current lane supports public wrapping.",
  },
};

const els = {};

function $(id) {
  return document.getElementById(id);
}

function shortAddress(value) {
  if (!value) return "-";
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

function explorerLink(addressOrTx) {
  const base = state.config.network.explorer_base_url.replace(/\/$/, "");
  if (addressOrTx.startsWith("0x") && addressOrTx.length === 42) {
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

function formatDuration(seconds) {
  const total = Number(seconds || 0);
  if (total <= 0) return "none";
  if (total % 86400 === 0) {
    return `${total / 86400}d`;
  }
  if (total % 3600 === 0) {
    return `${total / 3600}h`;
  }
  if (total % 60 === 0) {
    return `${total / 60}m`;
  }
  return `${total}s`;
}

function formatTimestamp(seconds) {
  const total = Number(seconds || 0);
  if (!total) return "now";
  const date = new Date(total * 1000);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}

function isHexAddress(value) {
  return /^0x[a-fA-F0-9]{40}$/.test(value || "");
}

function buildDrwTransferUri(recipient, amountText) {
  if (!isHexAddress(recipient)) {
    return "";
  }

  const chainId = state.config.network.chain_id || state.config.network.id || 84532;
  const trimmedAmount = (amountText || "").trim();
  if (!trimmedAmount || Number(trimmedAmount) <= 0) {
    return `ethereum:${state.config.token.address}@${chainId}/transfer?address=${recipient}`;
  }

  const amount = ethers.parseUnits(trimmedAmount, state.config.token.decimals).toString();
  return `ethereum:${state.config.token.address}@${chainId}/transfer?address=${recipient}&uint256=${amount}`;
}

function buildTinySwapUrl(presetName) {
  const baseHref = window.DarwinLane && state.laneSelection
    ? window.DarwinLane.laneAbsoluteHref("/trade/", state.laneSelection)
    : window.location.href;
  const url = new URL(baseHref, window.location.origin);
  url.searchParams.set("preset", presetName || "tiny-sell");
  return url.toString();
}

function absoluteUrl(path) {
  if (window.DarwinLane && state.laneSelection) {
    return window.DarwinLane.laneAbsoluteHref(path, state.laneSelection);
  }
  return new URL(path, window.location.origin).toString();
}

function attributionSuffix() {
  return state.config?.attribution?.builder_code_suffix || "";
}

function appendDataSuffix(data) {
  const suffix = attributionSuffix();
  if (!suffix || !data || !data.startsWith("0x")) {
    return data;
  }
  return `${data}${suffix.slice(2)}`;
}

function buildContractRequest(contract, methodName, args = [], overrides = {}) {
  return {
    to: contract.target,
    data: appendDataSuffix(contract.interface.encodeFunctionData(methodName, args)),
    ...overrides,
  };
}

async function sendContractTransaction(contract, methodName, args = [], overrides = {}) {
  const request = buildContractRequest(contract, methodName, args, overrides);
  return state.signer.sendTransaction(request);
}

function setMessage(kind, text, txHash = "") {
  els.messageKind.textContent = kind;
  els.messageText.textContent = text;
  if (txHash) {
    els.messageLink.hidden = false;
    els.messageLink.href = explorerLink(txHash);
    els.messageLink.textContent = `View transaction ${shortAddress(txHash)}`;
  } else {
    els.messageLink.hidden = true;
    els.messageLink.href = "#";
    els.messageLink.textContent = "";
  }
}

function setSharePayload(payload = null, prompt = "") {
  state.sharePayload = payload;
  const enabled = Boolean(payload?.url);
  els.shareActionButton.disabled = !enabled;
  els.copyActionLinkButton.disabled = !enabled;
  els.sharePrompt.textContent =
    prompt || (enabled ? `${payload.text} ${payload.url}` : "Complete a claim, wrap, or swap to create a shareable Darwin proof link.");
}

async function shareCurrentPayload() {
  if (!state.sharePayload?.url) return;
  if (navigator.share) {
    await navigator.share(state.sharePayload);
    setMessage("share", "Shared Darwin progress.");
    return;
  }
  await navigator.clipboard.writeText(`${state.sharePayload.text}\n${state.sharePayload.url}`);
  setMessage("share", "Share text copied.");
}

function actionSharePayload(kind, txHash = "") {
  const epoch = state.config.community?.epoch || {};
  const tinySwapUrl = absoluteUrl(state.config.community?.tiny_swap_path || "/trade/?preset=tiny-sell");
  const epochUrl = absoluteUrl(epoch.share_path || state.config.community?.epoch_path || "/epoch/");
  const activityUrl = absoluteUrl(state.config.community?.activity_path || "/activity/");

  if (kind === "faucet") {
    return {
      title: "Claimed DRW",
      text: `I claimed DRW on ${state.config.network.name} and the next Darwin move is a tiny swap. ${shortAddress(txHash)}`,
      url: epochUrl,
    };
  }
  if (kind === "wrap") {
    return {
      title: "Wrapped for Darwin",
      text: `I wrapped a small amount of ${state.config.network.name} ETH to get ready for a Darwin tiny swap. ${shortAddress(txHash)}`,
      url: tinySwapUrl,
    };
  }
  if (kind === "swap") {
    return {
      title: "Tiny Darwin swap",
      text: `I just used the Darwin tiny-swap path on ${state.config.network.name}. Public proof is on the activity page. ${shortAddress(txHash)}`,
      url: activityUrl,
    };
  }
  return {
    title: "Use Darwin",
    text: epoch.share_text || state.config.community?.share_text || "Claim DRW, make one tiny swap, and share the Darwin activity page.",
    url: epochUrl,
  };
}

function epochRewardPolicy() {
  return state.config?.community?.epoch?.reward_policy || null;
}

function renderTradeRewardRules() {
  if (!els.tradeRewardRules || !els.tradeEpochProgress) return;
  const reward = epochRewardPolicy();
  const progress = state.activitySummary?.progress;
  els.tradeRewardRules.innerHTML = "";
  if (!reward || !(reward.rules || []).length) {
    els.tradeEpochProgress.textContent = "No public reward pilot configured yet.";
    els.tradeRewardRules.innerHTML = "<li>The current Darwin lane is live without a public reward pilot.</li>";
    return;
  }

  const walletProgress = progress?.wallets?.target
    ? `${progress.wallets.current}/${progress.wallets.target} wallets`
    : `${progress?.wallets?.current ?? 0} wallets`;
  const swapProgress = progress?.swaps?.target
    ? `${progress.swaps.current}/${progress.swaps.target} swaps`
    : `${progress?.swaps?.current ?? 0} swaps`;
  els.tradeEpochProgress.textContent =
    `${reward.window_label || "Current window"}: ${walletProgress}, ${swapProgress}. Incentivized routes stay locked until the canonical traction gate is real.`;

  for (const rule of reward.rules || []) {
    const li = document.createElement("li");
    const amount = Number(rule.amount || 0);
    li.textContent = amount
      ? `${rule.label || "Reward"}: ${amount} ${reward.currency_symbol || "DRW"}. ${rule.detail || ""}`.trim()
      : `${rule.label || "Reward"}: ${rule.detail || "Locked for a later phase."}`;
    els.tradeRewardRules.appendChild(li);
  }
}

async function discoverInjectedProvider() {
  const providers = [];
  window.addEventListener("eip6963:announceProvider", (event) => {
    providers.push(event.detail);
  });
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  await new Promise((resolve) => setTimeout(resolve, 300));

  const pick =
    providers
      .filter((entry) => entry?.provider)
      .sort((left, right) => rankInjectedProvider(left) - rankInjectedProvider(right))[0] ||
    providers[0];

  return pick?.provider || window.ethereum || null;
}

function rankInjectedProvider(entry) {
  const provider = entry?.provider || {};
  const info = entry?.info || {};
  const rdns = String(info.rdns || "").toLowerCase();
  const name = String(info.name || "").toLowerCase();

  if (
    provider.isBaseAccount ||
    provider.isCoinbaseWallet ||
    rdns.includes("coinbase") ||
    rdns.includes("base") ||
    name.includes("coinbase") ||
    name.includes("base")
  ) {
    return 0;
  }
  if (provider.isMetaMask || rdns.includes("metamask") || name.includes("metamask")) {
    return 1;
  }
  return 2;
}

async function ensureWallet() {
  if (state.injectedProvider) return state.injectedProvider;
  const provider = await discoverInjectedProvider();
  if (!provider) {
    throw new Error("No browser wallet found. Open this portal in MetaMask, Rabby, or another EIP-1193 wallet.");
  }
  state.injectedProvider = provider;
  return provider;
}

async function ensureCorrectNetwork() {
  const provider = await ensureWallet();
  const chainHex = await provider.request({ method: "eth_chainId" });
  if (chainHex.toLowerCase() === state.config.network.hex.toLowerCase()) {
    return true;
  }

  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: state.config.network.hex }],
    });
  } catch (error) {
    if (error?.code !== 4902) {
      throw error;
    }
    await provider.request({
      method: "wallet_addEthereumChain",
      params: [
        {
          chainId: state.config.network.hex,
          chainName: state.config.network.name,
          nativeCurrency: {
            name: state.config.network.native_symbol,
            symbol: state.config.network.native_symbol,
            decimals: 18,
          },
          rpcUrls: [state.config.network.rpc_url],
          blockExplorerUrls: [state.config.network.explorer_base_url],
        },
      ],
    });
  }

  return true;
}

async function connectWallet() {
  const provider = await ensureWallet();
  await ensureCorrectNetwork();
  await provider.request({ method: "eth_requestAccounts" });
  state.browserProvider = new ethers.BrowserProvider(provider);
  state.signer = await state.browserProvider.getSigner();
  state.account = await state.signer.getAddress();
  await loadWalletCapabilities();
  els.walletStatus.textContent = "Connected";
  els.walletAddress.textContent = state.account;
  setMessage("wallet", `Connected ${shortAddress(state.account)} on ${state.config.network.name}.`);
  await refreshWallet();
}

function syncModeButtons() {
  for (const button of document.querySelectorAll(".segment")) {
    button.classList.toggle("is-active", button.dataset.mode === state.mode);
  }
  const buyMode = state.mode === "buy";
  els.tokenInDisplay.value = buyMode ? state.config.quote_token.symbol : state.config.token.symbol;
  els.swapButton.textContent = buyMode ? "Buy DRW" : "Sell DRW";
}

function syncTinyPresetButtons() {
  for (const button of document.querySelectorAll("[data-tiny-preset]")) {
    button.classList.toggle("is-active", button.dataset.tinyPreset === state.tinyPreset);
  }
}

async function loadConfig() {
  state.laneSelection = window.DarwinLane ? await window.DarwinLane.resolveSelection() : null;
  const configPath = state.laneSelection?.currentLane?.path || "/market-config.json";
  const response = await fetch(configPath, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load market config: ${response.status}`);
  }
  state.config = await response.json();
  state.rpcProvider = new ethers.JsonRpcProvider(
    state.config.network.read_rpc_url || state.config.network.rpc_url,
  );
  state.token = new ethers.Contract(state.config.token.address, ERC20_ABI, state.rpcProvider);
  state.quoteToken = new ethers.Contract(state.config.quote_token.address, WETH_ABI, state.rpcProvider);
  state.pool = new ethers.Contract(state.config.pool.address, POOL_ABI, state.rpcProvider);
  if (state.config.faucet?.enabled && state.config.faucet.address) {
    state.faucet = new ethers.Contract(state.config.faucet.address, FAUCET_ABI, state.rpcProvider);
  }
}

async function loadWalletCapabilities() {
  state.walletCapabilities = null;
  if (!state.account) return null;
  try {
    const provider = await ensureWallet();
    state.walletCapabilities = await provider.request({
      method: "wallet_getCapabilities",
      params: [state.account],
    });
  } catch {
    state.walletCapabilities = null;
  }
  return state.walletCapabilities;
}

function currentChainCapabilities() {
  if (!state.walletCapabilities) return null;
  const candidateKeys = [
    state.config.network.hex,
    state.config.network.hex?.toLowerCase(),
    String(state.config.network.chain_id),
    String(Number.parseInt(state.config.network.hex || "0x0", 16)),
  ].filter(Boolean);
  for (const key of candidateKeys) {
    if (state.walletCapabilities[key]) {
      return state.walletCapabilities[key];
    }
  }
  return null;
}

async function loadRuntimeStatus() {
  try {
    const response = await fetch(`../runtime-status.json?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    state.runtimeStatus = await response.json();
    if (els.runtimeHostStatus && state.runtimeStatus?.summary) {
      els.runtimeHostStatus.textContent = state.runtimeStatus.summary;
    }
  } catch {
    // Keep the built-in fallback text if runtime status cannot be loaded.
  }
}

async function loadActivitySummary() {
  try {
    const summaryPath = state.laneSelection?.currentLane?.activity_summary_path || "/activity-summary.json";
    const response = await fetch(`${summaryPath}?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    state.activitySummary = await response.json();
  } catch {
    state.activitySummary = null;
  }
  state.marketStructure = window.DarwinLane
    ? window.DarwinLane.buildMarketStructure(state.config, state.activitySummary?.summary || {})
    : null;
}

function poolEntryHref(pool) {
  if (!pool?.entry_path) return "";
  return window.DarwinLane && state.laneSelection
    ? window.DarwinLane.laneRelativeHref(pool.entry_path, state.laneSelection)
    : pool.entry_path;
}

function renderPoolStructure() {
  if (!els.poolStructureGrid || !state.marketStructure) return;
  const structure = state.marketStructure;
  els.poolStructureGrid.innerHTML = "";
  els.poolStructureBadge.textContent = structure.defaultEntry || "canonical";
  els.poolStructureNote.textContent = structure.summary || "";

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

    if (pool.pool_address) {
      const meta = document.createElement("span");
      meta.className = "label";
      meta.textContent = `Pool ${shortAddress(pool.pool_address)}`;
      card.appendChild(meta);
    }

    if (pool.enabled && pool.entry_path) {
      const link = document.createElement("a");
      link.className = "button button-secondary tiny-button";
      link.href = poolEntryHref(pool);
      link.textContent = pool.entry_label || "Open route";
      card.appendChild(link);
    }

    els.poolStructureGrid.appendChild(card);
  }
}

function bindStaticConfig() {
  els.chainBadge.textContent = state.config.network.name;
  els.feeBadge.textContent = `${state.config.pool.fee_bps} bps`;
  if (window.DarwinLane && state.laneSelection) {
    window.DarwinLane.renderSwitcher(els.tradeLaneSwitcher, state.laneSelection);
  }

  els.poolAddress.textContent = state.config.pool.address;
  els.drwAddress.textContent = state.config.token.address;
  els.wethAddress.textContent = state.config.quote_token.address;
  els.walletQuoteLabel.textContent = state.config.quote_token.symbol;
  els.quoteAddressLabel.textContent = `${state.config.quote_token.symbol} token`;
  if (state.config.faucet?.enabled && state.config.faucet.address) {
    els.faucetPanel.hidden = false;
    els.faucetAddressRow.hidden = false;
    els.faucetAddress.textContent = state.config.faucet.address;
    els.faucetClaimAmount.textContent = formatUnits(state.config.faucet.claim_amount || 0, state.config.token.decimals, 3);
    els.faucetNativeAmount.textContent = formatUnits(state.config.faucet.native_drip_amount || 0, 18, 6);
    els.faucetCooldown.textContent = formatDuration(state.config.faucet.claim_cooldown || 0);
    els.faucetBadge.textContent = state.config.faucet.funded ? "funded faucet" : "unfunded faucet";
  }

  els.poolLink.href = explorerLink(state.config.pool.address);
  els.poolLink.textContent = shortAddress(state.config.pool.address);
  els.tokenLink.href = explorerLink(state.config.token.address);
  els.tokenLink.textContent = shortAddress(state.config.token.address);
  if (els.tradeViewActivityLink) {
    els.tradeViewActivityLink.href = window.DarwinLane && state.laneSelection
      ? window.DarwinLane.laneRelativeHref("/activity/", state.laneSelection)
      : "/activity/";
  }
  if (els.tradeViewEpochLink) {
    els.tradeViewEpochLink.href = window.DarwinLane && state.laneSelection
      ? window.DarwinLane.laneRelativeHref("/epoch/", state.laneSelection)
      : "/epoch/";
  }
  if (els.tradeJoinCohortLink) {
    els.tradeJoinCohortLink.href = window.DarwinLane && state.laneSelection
      ? window.DarwinLane.laneRelativeHref(
        state.config.community?.starter_cohort_path || "/join/",
        state.laneSelection,
      )
      : (state.config.community?.starter_cohort_path || "/join/");
  }
  if (els.tradeSearchLink) {
    els.tradeSearchLink.href = window.DarwinLane && state.laneSelection
      ? window.DarwinLane.laneRelativeHref("/search/", state.laneSelection)
      : "/search/";
  }
  els.liveStatusLink.href = state.config.links.live_status;
  els.marketDocLink.href = state.config.links.market_bootstrap;
  els.repoLink.href = state.config.links.repo;
  els.tokenSupply.textContent = formatUnits(state.config.token.total_supply || 0, state.config.token.decimals, 3);

  const epoch = state.config.community?.epoch;
  if (epoch) {
    els.tradeEpochBadge.textContent = epoch.status || "live";
    els.tradeEpochTitle.textContent = epoch.title || "Darwin epoch";
    els.tradeEpochSummary.textContent = epoch.summary || "";
    els.tradeEpochLink.href = absoluteUrl(epoch.share_path || state.config.community?.epoch_path || "/epoch/");
    els.tradeCommunityHint.textContent = epoch.focus || els.tradeCommunityHint.textContent;
  }

  const wrapEnabled = Boolean(state.config.quote_token?.wrap_enabled);
  if (wrapEnabled) {
    els.wrapBadge.textContent = `${state.config.network.name} ${state.config.quote_token.symbol}`;
    els.wrapCaption.textContent =
      `Buying DRW from this pool requires ${state.config.quote_token.symbol}, not native ETH. This action calls deposit() on ${state.config.network.name} ${state.config.quote_token.symbol}.`;
    els.wrapButton.disabled = false;
  } else {
    els.wrapBadge.textContent = `${state.config.quote_token.symbol} is preseeded`;
    els.wrapCaption.textContent =
      `${state.config.quote_token.symbol} is a mock/operator-seeded quote asset on this lane, so public wrapping is disabled. The public first move here is claim DRW, then tiny sell.`;
    els.wrapButton.disabled = true;
  }

  const summary = state.activitySummary?.summary;
  if (summary) {
    els.tradeExternalWalletCount.textContent = String(summary.external_wallets ?? 0);
    els.tradeExternalSwapCount.textContent = String(summary.external_swaps ?? 0);
  }
  renderTradeRewardRules();

  const builderCode = state.config.attribution?.builder_code;
  const smartStartEnabled = Boolean(state.config.attribution?.smart_start_enabled && state.config.faucet?.enabled);
  els.smartStartButton.disabled = !smartStartEnabled;
  els.tinyAttributionHint.textContent = builderCode
    ? `Builder Code ${builderCode} is configured for this lane. Standard calls append attribution and supported wallets can batch the first claim-plus-swap path.`
    : "Direct mode is live. Supported wallets can still try a one-click smart start, but transaction attribution is not configured for this lane yet.";

  renderPoolStructure();
}

async function refreshMarket() {
  const [baseReserve, quoteReserve] = await Promise.all([
    state.pool.baseReserve(),
    state.pool.quoteReserve(),
  ]);

  els.poolBaseReserve.textContent = formatUnits(baseReserve, state.config.token.decimals, 9);
  els.poolQuoteReserve.textContent = formatUnits(quoteReserve, state.config.quote_token.decimals, 12);
  els.portalState.textContent = "Live";
  els.portalSubstate.textContent = `Public ${state.config.network.name} canonical pool`;
}

async function refreshWallet() {
  if (!state.account) {
    els.walletEth.textContent = "-";
    els.walletDrw.textContent = "-";
    els.walletWeth.textContent = "-";
    updateQrState();
    return;
  }

  const [ethBalance, drwBalance, wethBalance] = await Promise.all([
    state.rpcProvider.getBalance(state.account),
    state.token.balanceOf(state.account),
    state.quoteToken.balanceOf(state.account),
  ]);

  els.walletEth.textContent = formatUnits(ethBalance, 18, 6);
  els.walletDrw.textContent = formatUnits(drwBalance, state.config.token.decimals, 6);
  els.walletWeth.textContent = formatUnits(wethBalance, state.config.quote_token.decimals, 12);
  if (!els.qrRecipient.value.trim()) {
    els.qrRecipient.value = state.account;
  }
  updateQrState();
  await refreshFaucet();
}

async function refreshFaucet() {
  if (!state.config.faucet?.enabled || !state.faucet) {
    return;
  }

  if (!state.account) {
    els.faucetNextClaim.textContent = "connect wallet";
    return;
  }

  try {
    const nextClaimAt = await state.faucet.nextClaimAt(state.account);
    const nextTs = Number(nextClaimAt);
    els.faucetNextClaim.textContent = nextTs === 0 || nextTs <= Math.floor(Date.now() / 1000) ? "now" : formatTimestamp(nextTs);
  } catch (error) {
    els.faucetNextClaim.textContent = "unavailable";
  }
}

async function refreshQuote() {
  const amount = els.swapAmount.value.trim();
  const slippageBps = Number.parseInt(els.slippageBps.value || "100", 10);

  if (!amount || Number(amount) <= 0) {
    els.quotedOutput.textContent = "-";
    els.minOutput.textContent = "-";
    return;
  }

  try {
    const buyMode = state.mode === "buy";
    const decimals = buyMode ? state.config.quote_token.decimals : state.config.token.decimals;
    const tokenInAddress = buyMode ? state.config.quote_token.address : state.config.token.address;
    const tokenOutDecimals = buyMode ? state.config.token.decimals : state.config.quote_token.decimals;
    const amountIn = ethers.parseUnits(amount, decimals);
    const quoted = await state.pool.quoteExactInput(tokenInAddress, amountIn);
    const minOut = (quoted * BigInt(10_000 - slippageBps)) / 10_000n;
    els.quotedOutput.textContent = `${formatUnits(quoted, tokenOutDecimals, 12)} ${buyMode ? "DRW" : "WETH"}`;
    els.minOutput.textContent = `${formatUnits(minOut, tokenOutDecimals, 12)} ${buyMode ? "DRW" : "WETH"}`;
  } catch (error) {
    els.quotedOutput.textContent = "quote failed";
    els.minOutput.textContent = "-";
  }
}

async function applyTinyPreset(presetName, { announce = true, persist = true } = {}) {
  const preset = TINY_SWAP_PRESETS[presetName];
  if (!preset) {
    return;
  }

  state.tinyPreset = presetName;
  if (preset.mode) {
    state.mode = preset.mode;
    syncModeButtons();
  }
  if (preset.amount) {
    els.swapAmount.value = preset.amount;
  }
  if (preset.slippageBps) {
    els.slippageBps.value = preset.slippageBps;
  }
  if (preset.wrapAmount) {
    els.wrapAmount.value = preset.wrapAmount;
  }
  if (els.tinySwapHint) {
    els.tinySwapHint.textContent = preset.note;
  }
  syncTinyPresetButtons();
  if (persist && window.history?.replaceState) {
    const url = new URL(window.location.href);
    url.searchParams.set("preset", presetName);
    window.history.replaceState({}, "", url);
  }
  await refreshQuote();
  if (announce) {
    setMessage("tiny-swap", preset.note);
  }
}

async function loadTinyPresetFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const presetName = params.get("preset");
  if (!presetName || !TINY_SWAP_PRESETS[presetName]) {
    syncTinyPresetButtons();
    return;
  }
  await applyTinyPreset(presetName, { announce: false, persist: false });
}

async function maybeApprove(tokenContract, amount, spender) {
  const allowance = await tokenContract.allowance(state.account, spender);
  if (allowance >= amount) return null;
  const tx = await sendContractTransaction(tokenContract, "approve", [spender, amount]);
  setMessage("approval", "Approval submitted.", tx.hash);
  await tx.wait();
  return tx.hash;
}

async function handleSwap() {
  if (!state.account) {
    await connectWallet();
    return;
  }

  await ensureCorrectNetwork();

  const rawAmount = els.swapAmount.value.trim();
  if (!rawAmount || Number(rawAmount) <= 0) {
    setMessage("input", "Enter a positive swap amount.");
    return;
  }

  const buyMode = state.mode === "buy";
  const tokenInAddress = buyMode ? state.config.quote_token.address : state.config.token.address;
  const tokenInContract = buyMode ? state.quoteToken : state.token;
  const inputDecimals = buyMode ? state.config.quote_token.decimals : state.config.token.decimals;
  const outputDecimals = buyMode ? state.config.token.decimals : state.config.quote_token.decimals;
  const slippageBps = Number.parseInt(els.slippageBps.value || "100", 10);
  const amountIn = ethers.parseUnits(rawAmount, inputDecimals);
  const quoted = await state.pool.quoteExactInput(tokenInAddress, amountIn);
  const minOut = (quoted * BigInt(10_000 - slippageBps)) / 10_000n;

  els.swapButton.disabled = true;
  try {
    await maybeApprove(tokenInContract, amountIn, state.config.pool.address);
    const tx = await sendContractTransaction(
      state.pool,
      "swapExactInput",
      [tokenInAddress, amountIn, minOut, state.account],
    );
    setMessage(
      "swap",
      `Swap submitted for ${rawAmount} ${buyMode ? "WETH" : "DRW"} -> ${formatUnits(quoted, outputDecimals, 12)} ${buyMode ? "DRW" : "WETH"}.`,
      tx.hash,
    );
    await tx.wait();
    setMessage("swap", `Swap confirmed on ${state.config.network.name}.`, tx.hash);
    setSharePayload(
      actionSharePayload("swap", tx.hash),
      "Swap confirmed. Share the Darwin activity page so another wallet can follow the same tiny path.",
    );
    await Promise.all([refreshMarket(), refreshWallet(), refreshQuote()]);
  } catch (error) {
    setMessage("error", error?.shortMessage || error?.message || "Swap failed.");
  } finally {
    els.swapButton.disabled = false;
  }
}

async function handleWrap() {
  if (!state.config.quote_token?.wrap_enabled) {
    setMessage("wrap", `${state.config.quote_token.symbol} wrapping is disabled on ${state.config.network.name}.`);
    return;
  }
  if (!state.account) {
    await connectWallet();
    return;
  }

  await ensureCorrectNetwork();
  const rawAmount = els.wrapAmount.value.trim();
  if (!rawAmount || Number(rawAmount) <= 0) {
    setMessage("input", "Enter a positive wrap amount.");
    return;
  }

  const amount = ethers.parseEther(rawAmount);
  els.wrapButton.disabled = true;
  try {
    const tx = await sendContractTransaction(state.quoteToken, "deposit", [], { value: amount });
    setMessage("wrap", `Wrap submitted for ${rawAmount} ETH.`, tx.hash);
    await tx.wait();
    setMessage("wrap", `Wrap confirmed on ${state.config.network.name}.`, tx.hash);
    setSharePayload(
      actionSharePayload("wrap", tx.hash),
      "Wrap confirmed. You can share the tiny-buy path or continue into a tiny swap.",
    );
    await Promise.all([refreshWallet(), refreshQuote(), refreshMarket()]);
  } catch (error) {
    setMessage("error", error?.shortMessage || error?.message || "Wrap failed.");
  } finally {
    els.wrapButton.disabled = false;
  }
}

async function handleClaim() {
  if (!state.config.faucet?.enabled || !state.faucet) {
    setMessage("faucet", "No faucet is enabled in the current deployment artifact.");
    return;
  }
  if (!state.account) {
    await connectWallet();
    return;
  }

  await ensureCorrectNetwork();
  els.claimButton.disabled = true;
  try {
    const tx = await sendContractTransaction(state.faucet, "claim", []);
    setMessage("faucet", "Faucet claim submitted.", tx.hash);
    await tx.wait();
    setMessage("faucet", "Faucet claim confirmed.", tx.hash);
    await applyTinyPreset("tiny-sell", { announce: false, persist: true });
    setSharePayload(
      actionSharePayload("faucet", tx.hash),
      "Claim confirmed. The recommended next move is a tiny sell, then share the public activity page.",
    );
    await Promise.all([refreshWallet(), refreshMarket(), refreshQuote()]);
  } catch (error) {
    setMessage("error", error?.shortMessage || error?.message || "Faucet claim failed.");
  } finally {
    els.claimButton.disabled = false;
  }
}

function resolveCallsId(result) {
  if (typeof result === "string") return result;
  return result?.id || result?.callsId || result?.callId || "";
}

function callsReceipts(status) {
  if (Array.isArray(status?.receipts)) return status.receipts;
  if (Array.isArray(status?.result?.receipts)) return status.result.receipts;
  return [];
}

function callsStatusCode(status) {
  return status?.status ?? status?.result?.status ?? "";
}

function callsTransactionHash(status) {
  const receipts = callsReceipts(status);
  return receipts.at(-1)?.transactionHash || receipts[0]?.transactionHash || "";
}

async function waitForCallsStatus(callsId, timeoutMs = 120000) {
  const provider = await ensureWallet();
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await provider.request({
      method: "wallet_getCallsStatus",
      params: [callsId],
    });
    const code = callsStatusCode(status);
    if (code === 200 || code === "confirmed" || code === "CONFIRMED") {
      return status;
    }
    if (code === 500 || code === "failed" || code === "FAILED") {
      throw new Error("Smart start batch failed.");
    }
    await new Promise((resolve) => setTimeout(resolve, 2500));
  }
  throw new Error("Timed out waiting for smart start confirmation.");
}

function walletSupportsSendCalls() {
  const capabilities = currentChainCapabilities();
  if (!capabilities) {
    return true;
  }
  return Boolean(
    capabilities?.atomicBatch ||
    capabilities?.atomic ||
    capabilities?.paymasterService ||
    capabilities?.auxiliaryFunds,
  );
}

async function handleSmartStart() {
  if (!state.config.faucet?.enabled || !state.faucet) {
    setMessage("smart-start", "Smart start is only available on lanes with a live faucet.");
    return;
  }
  if (!state.account) {
    await connectWallet();
    return;
  }

  await ensureCorrectNetwork();
  await applyTinyPreset("tiny-sell", { announce: false, persist: true });
  const rawAmount = els.swapAmount.value.trim() || TINY_SWAP_PRESETS["tiny-sell"].amount;
  const slippageBps = Number.parseInt(els.slippageBps.value || "150", 10);
  const sellAmount = ethers.parseUnits(rawAmount, state.config.token.decimals);
  const quoted = await state.pool.quoteExactInput(state.config.token.address, sellAmount);
  const minOut = (quoted * BigInt(10_000 - slippageBps)) / 10_000n;
  const provider = await ensureWallet();
  const capabilities = currentChainCapabilities();

  if (!walletSupportsSendCalls()) {
    setMessage(
      "smart-start",
      "This wallet does not expose batch calls on the current lane. Use Claim DRW, then Tiny sell.",
    );
    return;
  }

  const request = {
    version: "1.0",
    chainId: state.config.network.hex,
    from: state.account,
    atomicRequired: true,
    calls: [
      buildContractRequest(state.faucet, "claim", []),
      buildContractRequest(state.token, "approve", [state.config.pool.address, sellAmount]),
      buildContractRequest(
        state.pool,
        "swapExactInput",
        [state.config.token.address, sellAmount, minOut, state.account],
      ),
    ],
  };

  if (state.config.attribution?.paymaster_service_url && capabilities?.paymasterService) {
    request.capabilities = {
      paymasterService: {
        url: state.config.attribution.paymaster_service_url,
      },
    };
  }

  els.smartStartButton.disabled = true;
  try {
    const result = await provider.request({
      method: "wallet_sendCalls",
      params: [request],
    });
    const callsId = resolveCallsId(result);
    if (!callsId) {
      throw new Error("wallet_sendCalls did not return a batch identifier.");
    }
    setMessage("smart-start", "Smart start submitted. Waiting for claim, approval, and tiny sell confirmation.");
    const status = await waitForCallsStatus(callsId);
    const txHash = callsTransactionHash(status);
    setMessage("smart-start", "Smart start confirmed on-chain.", txHash);
    setSharePayload(
      actionSharePayload("swap", txHash),
      "Smart start confirmed. Share the public activity page so another outside wallet can follow the same path.",
    );
    await Promise.all([refreshWallet(), refreshMarket(), refreshQuote(), refreshFaucet()]);
  } catch (error) {
    setMessage(
      "smart-start",
      error?.shortMessage || error?.message || "Smart start failed. Use Claim DRW, then Tiny sell.",
    );
  } finally {
    els.smartStartButton.disabled = !Boolean(state.config.attribution?.smart_start_enabled && state.config.faucet?.enabled);
  }
}

async function watchAsset() {
  const provider = await ensureWallet();
  try {
    await provider.request({
      method: "wallet_watchAsset",
      params: {
        type: "ERC20",
        options: {
          address: state.config.token.address,
          symbol: state.config.token.symbol,
          decimals: state.config.token.decimals,
          image: new URL("../drw-logo.svg", window.location.href).toString(),
        },
      },
    });
    setMessage("wallet", "Requested DRW wallet import.");
  } catch (error) {
    setMessage("error", error?.message || "Failed to add DRW to the wallet.");
  }
}

function drawQr(uri) {
  const mount = els.qrCanvas;
  const hasRenderer = Boolean(window.QRCode);
  mount.innerHTML = "";

  if (!uri || !hasRenderer) {
    mount.textContent = hasRenderer ? "Enter a valid wallet" : "QR loader missing";
    mount.classList.add("qr-empty");
    return;
  }
  mount.classList.remove("qr-empty");
  try {
    new window.QRCode(mount, {
      text: uri,
      width: 176,
      height: 176,
      colorDark: "#14202f",
      colorLight: "#f4efe5",
      correctLevel: window.QRCode.CorrectLevel.M,
    });
  } catch (error) {
    console.error(error);
    mount.textContent = "QR render failed";
    mount.classList.add("qr-empty");
  }
}

function updateQrState() {
  const recipient = els.qrRecipient.value.trim();
  const amount = els.qrAmount.value.trim();
  const uri = buildDrwTransferUri(recipient, amount);
  els.qrUri.value = uri || `Enter a valid ${state.config?.network?.name || "Darwin lane"} wallet address to generate a DRW transfer QR.`;
  els.copyQrUriButton.disabled = !uri;
  drawQr(uri);
}

function installCopyHandlers() {
  for (const row of document.querySelectorAll("[data-copy-target]")) {
    row.addEventListener("click", async () => {
      const target = row.getAttribute("data-copy-target");
      const text = $(target).textContent;
      await navigator.clipboard.writeText(text);
      setMessage("copy", `Copied ${text} to clipboard.`);
    });
  }
}

async function boot() {
  Object.assign(els, {
    connectButton: $("connectButton"),
    networkButton: $("networkButton"),
    watchAssetButton: $("watchAssetButton"),
    refreshButton: $("refreshButton"),
    swapAmount: $("swapAmount"),
    slippageBps: $("slippageBps"),
    swapButton: $("swapButton"),
    wrapAmount: $("wrapAmount"),
    wrapButton: $("wrapButton"),
    wrapBadge: $("wrapBadge"),
    wrapCaption: $("wrapCaption"),
    qrCanvas: $("qrCanvas"),
    qrRecipient: $("qrRecipient"),
    qrAmount: $("qrAmount"),
    qrUri: $("qrUri"),
    copyQrUriButton: $("copyQrUriButton"),
    copyTinySwapLinkButton: $("copyTinySwapLinkButton"),
    useConnectedWalletButton: $("useConnectedWalletButton"),
    faucetPanel: $("faucetPanel"),
    faucetBadge: $("faucetBadge"),
    faucetClaimAmount: $("faucetClaimAmount"),
    faucetNativeAmount: $("faucetNativeAmount"),
    faucetCooldown: $("faucetCooldown"),
    faucetNextClaim: $("faucetNextClaim"),
    claimButton: $("claimButton"),
    tokenInDisplay: $("tokenInDisplay"),
    poolBaseReserve: $("poolBaseReserve"),
    poolQuoteReserve: $("poolQuoteReserve"),
    tokenSupply: $("tokenSupply"),
    portalState: $("portalState"),
    portalSubstate: $("portalSubstate"),
    poolStructureBadge: $("poolStructureBadge"),
    poolStructureNote: $("poolStructureNote"),
    poolStructureGrid: $("poolStructureGrid"),
    quotedOutput: $("quotedOutput"),
    minOutput: $("minOutput"),
    walletStatus: $("walletStatus"),
    walletAddress: $("walletAddress"),
    walletEth: $("walletEth"),
    walletDrw: $("walletDrw"),
    walletWeth: $("walletWeth"),
    walletQuoteLabel: $("walletQuoteLabel"),
    poolLink: $("poolLink"),
    tokenLink: $("tokenLink"),
    chainBadge: $("chainBadge"),
    feeBadge: $("feeBadge"),
    runtimeHostStatus: $("runtimeHostStatus"),
    tinySwapHint: $("tinySwapHint"),
    poolAddress: $("poolAddress"),
    drwAddress: $("drwAddress"),
    wethAddress: $("wethAddress"),
    quoteAddressLabel: $("quoteAddressLabel"),
    faucetAddressRow: $("faucetAddressRow"),
    faucetAddress: $("faucetAddress"),
    qrCaption: $("qrCaption"),
    liveStatusLink: $("liveStatusLink"),
    marketDocLink: $("marketDocLink"),
    repoLink: $("repoLink"),
    messageKind: $("messageKind"),
    messageText: $("messageText"),
    messageLink: $("messageLink"),
    tradeEpochBadge: $("tradeEpochBadge"),
    tradeEpochTitle: $("tradeEpochTitle"),
    tradeEpochSummary: $("tradeEpochSummary"),
    tradeEpochProgress: $("tradeEpochProgress"),
    tradeRewardRules: $("tradeRewardRules"),
    tradeExternalWalletCount: $("tradeExternalWalletCount"),
    tradeExternalSwapCount: $("tradeExternalSwapCount"),
    tradeEpochLink: $("tradeEpochLink"),
    tradeLaneSwitcher: $("tradeLaneSwitcher"),
    tradeViewActivityLink: $("tradeViewActivityLink"),
    tradeViewEpochLink: $("tradeViewEpochLink"),
    tradeJoinCohortLink: $("tradeJoinCohortLink"),
    tradeSearchLink: $("tradeSearchLink"),
    shareEpochButton: $("shareEpochButton"),
    tradeCommunityHint: $("tradeCommunityHint"),
    shareActionButton: $("shareActionButton"),
    copyActionLinkButton: $("copyActionLinkButton"),
    sharePrompt: $("sharePrompt"),
    tinyAttributionHint: $("tinyAttributionHint"),
    smartStartButton: $("smartStartButton"),
  });

  await loadConfig();
  await loadRuntimeStatus();
  await loadActivitySummary();
  bindStaticConfig();
  syncModeButtons();
  syncTinyPresetButtons();
  installCopyHandlers();
  updateQrState();
  await loadTinyPresetFromUrl();
  await refreshMarket();
  await refreshQuote();

  document.querySelectorAll(".segment").forEach((button) => {
    button.addEventListener("click", async () => {
      state.mode = button.dataset.mode;
      syncModeButtons();
      await refreshQuote();
    });
  });

  document.querySelectorAll("[data-tiny-preset]").forEach((button) => {
    button.addEventListener("click", () => applyTinyPreset(button.dataset.tinyPreset).catch((error) => {
      setMessage("error", error?.message || "Tiny preset failed.");
    }));
  });

  els.connectButton.addEventListener("click", () => connectWallet().catch((error) => {
    setMessage("error", error?.message || "Wallet connection failed.");
  }));
  els.networkButton.addEventListener("click", () => ensureCorrectNetwork().then(() => {
    setMessage("network", `Switched to ${state.config.network.name}.`);
  }).catch((error) => {
    setMessage("error", error?.message || "Network switch failed.");
  }));
  els.watchAssetButton.addEventListener("click", () => watchAsset());
  els.refreshButton.addEventListener("click", () => Promise.all([
    refreshMarket(),
    refreshWallet(),
    refreshQuote(),
    refreshFaucet(),
    loadActivitySummary().then(() => bindStaticConfig()),
  ]).then(() => {
    setMessage("refresh", "Market state refreshed.");
  }).catch((error) => {
    setMessage("error", error?.message || "Refresh failed.");
  }));
  els.swapAmount.addEventListener("input", () => refreshQuote());
  els.slippageBps.addEventListener("input", () => refreshQuote());
  els.qrRecipient.addEventListener("input", () => updateQrState());
  els.qrAmount.addEventListener("input", () => updateQrState());
  els.swapButton.addEventListener("click", () => handleSwap());
  els.wrapButton.addEventListener("click", () => handleWrap());
  els.claimButton?.addEventListener("click", () => handleClaim());
  els.smartStartButton?.addEventListener("click", () => handleSmartStart());
  els.copyQrUriButton.addEventListener("click", async () => {
    if (!els.copyQrUriButton.disabled) {
      await navigator.clipboard.writeText(els.qrUri.value);
      setMessage("copy", "Copied DRW transfer request URI.");
    }
  });
  els.copyTinySwapLinkButton.addEventListener("click", async () => {
    const url = buildTinySwapUrl(state.tinyPreset || "tiny-sell");
    await navigator.clipboard.writeText(url);
    setMessage("share", `Copied ${state.tinyPreset || "tiny-sell"} link.`);
  });
  els.shareEpochButton?.addEventListener("click", async () => {
    const payload = actionSharePayload("epoch");
    if (navigator.share) {
      await navigator.share(payload);
      setMessage("share", "Epoch shared.");
      return;
    }
    await navigator.clipboard.writeText(`${payload.text}\n${payload.url}`);
    setMessage("share", "Epoch share text copied.");
  });
  els.shareActionButton?.addEventListener("click", () => shareCurrentPayload().catch((error) => {
    setMessage("error", error?.message || "Share failed.");
  }));
  els.copyActionLinkButton?.addEventListener("click", async () => {
    if (!state.sharePayload?.url) return;
    await navigator.clipboard.writeText(state.sharePayload.url);
    setMessage("share", "Copied proof link.");
  });
  els.useConnectedWalletButton.addEventListener("click", async () => {
    if (!state.account) {
      await connectWallet();
    }
    els.qrRecipient.value = state.account;
    updateQrState();
    setMessage("wallet", "QR request updated for the connected wallet.");
  });

  setSharePayload(
    actionSharePayload("epoch"),
    "Epoch share is ready. Complete a claim or swap to generate a more specific proof link.",
  );
  els.qrCaption.textContent =
    `This QR encodes a ${state.config.network.name} DRW transfer request. Scan it from another wallet to open a direct token send.`;
  setMessage("ready", "Portal ready. Connect a wallet to trade.");
}

boot().catch((error) => {
  console.error(error);
  setMessage("error", error?.message || "Portal boot failed.");
});
