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
  config: null,
  runtimeStatus: null,
  rpcProvider: null,
  browserProvider: null,
  injectedProvider: null,
  signer: null,
  account: "",
  mode: "buy",
  token: null,
  quoteToken: null,
  pool: null,
  faucet: null,
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

  const chainId = state.config.network.chain_id || 84532;
  const trimmedAmount = (amountText || "").trim();
  if (!trimmedAmount || Number(trimmedAmount) <= 0) {
    return `ethereum:${state.config.token.address}@${chainId}/transfer?address=${recipient}`;
  }

  const amount = ethers.parseUnits(trimmedAmount, state.config.token.decimals).toString();
  return `ethereum:${state.config.token.address}@${chainId}/transfer?address=${recipient}&uint256=${amount}`;
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

async function discoverInjectedProvider() {
  const providers = [];
  window.addEventListener("eip6963:announceProvider", (event) => {
    providers.push(event.detail);
  });
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  await new Promise((resolve) => setTimeout(resolve, 300));

  const pick =
    providers.find((entry) => /metamask/i.test(entry.info?.name || "")) ||
    providers.find((entry) => entry.provider?.isMetaMask) ||
    providers[0];

  return pick?.provider || window.ethereum || null;
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

async function loadConfig() {
  const response = await fetch("../market-config.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load market config: ${response.status}`);
  }
  state.config = await response.json();
  state.rpcProvider = new ethers.JsonRpcProvider(state.config.network.rpc_url);
  state.token = new ethers.Contract(state.config.token.address, ERC20_ABI, state.rpcProvider);
  state.quoteToken = new ethers.Contract(state.config.quote_token.address, WETH_ABI, state.rpcProvider);
  state.pool = new ethers.Contract(state.config.pool.address, POOL_ABI, state.rpcProvider);
  if (state.config.faucet?.enabled && state.config.faucet.address) {
    state.faucet = new ethers.Contract(state.config.faucet.address, FAUCET_ABI, state.rpcProvider);
  }
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

function bindStaticConfig() {
  els.chainBadge.textContent = state.config.network.name;
  els.feeBadge.textContent = `${state.config.pool.fee_bps} bps`;

  els.poolAddress.textContent = state.config.pool.address;
  els.drwAddress.textContent = state.config.token.address;
  els.wethAddress.textContent = state.config.quote_token.address;
  els.governanceAddress.textContent = state.config.roles.governance;
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
  els.liveStatusLink.href = state.config.links.live_status;
  els.marketDocLink.href = state.config.links.market_bootstrap;
  els.operatorQuickstartLink.href = state.config.links.operator_quickstart;
  els.artifactLink.href = state.config.links.deployment_artifact;
  els.repoLink.href = state.config.links.repo;
}

async function refreshMarket() {
  const [baseReserve, quoteReserve, governanceBalance] = await Promise.all([
    state.pool.baseReserve(),
    state.pool.quoteReserve(),
    state.token.balanceOf(state.config.roles.governance),
  ]);

  els.poolBaseReserve.textContent = formatUnits(baseReserve, state.config.token.decimals, 9);
  els.poolQuoteReserve.textContent = formatUnits(quoteReserve, state.config.quote_token.decimals, 12);
  els.governanceDrw.textContent = formatUnits(governanceBalance, state.config.token.decimals, 3);
  els.portalState.textContent = "Live";
  els.portalSubstate.textContent = "Artifact-backed Base Sepolia pool";
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

async function maybeApprove(tokenContract, amount, spender) {
  const allowance = await tokenContract.allowance(state.account, spender);
  if (allowance >= amount) return null;
  const tx = await tokenContract.connect(state.signer).approve(spender, amount);
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
    const tx = await state.pool.connect(state.signer).swapExactInput(
      tokenInAddress,
      amountIn,
      minOut,
      state.account,
    );
    setMessage(
      "swap",
      `Swap submitted for ${rawAmount} ${buyMode ? "WETH" : "DRW"} -> ${formatUnits(quoted, outputDecimals, 12)} ${buyMode ? "DRW" : "WETH"}.`,
      tx.hash,
    );
    await tx.wait();
    setMessage("swap", "Swap confirmed on Base Sepolia.", tx.hash);
    await Promise.all([refreshMarket(), refreshWallet(), refreshQuote()]);
  } catch (error) {
    setMessage("error", error?.shortMessage || error?.message || "Swap failed.");
  } finally {
    els.swapButton.disabled = false;
  }
}

async function handleWrap() {
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
    const tx = await state.quoteToken.connect(state.signer).deposit({ value: amount });
    setMessage("wrap", `Wrap submitted for ${rawAmount} ETH.`, tx.hash);
    await tx.wait();
    setMessage("wrap", "Wrap confirmed on Base Sepolia.", tx.hash);
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
    const tx = await state.faucet.connect(state.signer).claim();
    setMessage("faucet", "Faucet claim submitted.", tx.hash);
    await tx.wait();
    setMessage("faucet", "Faucet claim confirmed.", tx.hash);
    await Promise.all([refreshWallet(), refreshMarket(), refreshQuote()]);
  } catch (error) {
    setMessage("error", error?.shortMessage || error?.message || "Faucet claim failed.");
  } finally {
    els.claimButton.disabled = false;
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
  els.qrUri.value = uri || "Enter a valid Base Sepolia wallet address to generate a DRW transfer QR.";
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
    qrCanvas: $("qrCanvas"),
    qrRecipient: $("qrRecipient"),
    qrAmount: $("qrAmount"),
    qrUri: $("qrUri"),
    copyQrUriButton: $("copyQrUriButton"),
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
    governanceDrw: $("governanceDrw"),
    portalState: $("portalState"),
    portalSubstate: $("portalSubstate"),
    quotedOutput: $("quotedOutput"),
    minOutput: $("minOutput"),
    walletStatus: $("walletStatus"),
    walletAddress: $("walletAddress"),
    walletEth: $("walletEth"),
    walletDrw: $("walletDrw"),
    walletWeth: $("walletWeth"),
    poolLink: $("poolLink"),
    tokenLink: $("tokenLink"),
    chainBadge: $("chainBadge"),
    feeBadge: $("feeBadge"),
    runtimeHostStatus: $("runtimeHostStatus"),
    poolAddress: $("poolAddress"),
    drwAddress: $("drwAddress"),
    wethAddress: $("wethAddress"),
    faucetAddressRow: $("faucetAddressRow"),
    faucetAddress: $("faucetAddress"),
    governanceAddress: $("governanceAddress"),
    liveStatusLink: $("liveStatusLink"),
    marketDocLink: $("marketDocLink"),
    operatorQuickstartLink: $("operatorQuickstartLink"),
    artifactLink: $("artifactLink"),
    repoLink: $("repoLink"),
    messageKind: $("messageKind"),
    messageText: $("messageText"),
    messageLink: $("messageLink"),
  });

  await loadConfig();
  await loadRuntimeStatus();
  bindStaticConfig();
  syncModeButtons();
  installCopyHandlers();
  updateQrState();
  await refreshMarket();
  await refreshQuote();

  document.querySelectorAll(".segment").forEach((button) => {
    button.addEventListener("click", async () => {
      state.mode = button.dataset.mode;
      syncModeButtons();
      await refreshQuote();
    });
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
  els.copyQrUriButton.addEventListener("click", async () => {
    if (!els.copyQrUriButton.disabled) {
      await navigator.clipboard.writeText(els.qrUri.value);
      setMessage("copy", "Copied DRW transfer request URI.");
    }
  });
  els.useConnectedWalletButton.addEventListener("click", async () => {
    if (!state.account) {
      await connectWallet();
    }
    els.qrRecipient.value = state.account;
    updateQrState();
    setMessage("wallet", "QR request updated for the connected wallet.");
  });

  setMessage("ready", "Portal ready. Connect a wallet to trade.");
}

boot().catch((error) => {
  console.error(error);
  setMessage("error", error?.message || "Portal boot failed.");
});
