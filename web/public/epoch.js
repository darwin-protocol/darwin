const LEGACY_DISTRIBUTOR_ABI = [
  "function isClaimed(uint256) view returns (bool)",
  "function claim(uint256,address,uint256,bytes32[])",
];

const EPOCH_DISTRIBUTOR_ABI = [
  "function isClaimed(uint256,uint256) view returns (bool)",
  "function claim(uint256,uint256,address,uint256,bytes32[])",
];

const epochState = {
  laneSelection: null,
  config: null,
  activitySummary: null,
  rewardClaims: null,
  injectedProvider: null,
  browserProvider: null,
  readProvider: null,
  signer: null,
  account: "",
  walletEventsBound: false,
};

function epoch$(id) {
  return document.getElementById(id);
}

async function loadEpochConfig() {
  epochState.laneSelection = window.DarwinLane ? await window.DarwinLane.resolveSelection() : null;
  const configPath = epochState.laneSelection?.currentLane?.path || "/market-config.json";
  const response = await fetch(`${configPath}?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${configPath}: ${response.status}`);
  }
  epochState.config = await response.json();
}

async function loadEpochSummary() {
  const summaryPath = epochState.laneSelection?.currentLane?.activity_summary_path || "/activity-summary.json";
  const response = await fetch(`${summaryPath}?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    epochState.activitySummary = null;
    return;
  }
  epochState.activitySummary = await response.json();
}

async function loadRewardClaims() {
  const claimsPath = epochState.config?.reward_claims?.claims_path;
  if (!claimsPath) {
    epochState.rewardClaims = null;
    return;
  }
  try {
    const response = await fetch(`${claimsPath}?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      epochState.rewardClaims = null;
      return;
    }
    epochState.rewardClaims = await response.json();
  } catch {
    epochState.rewardClaims = null;
  }
}

function epochRewardPolicy() {
  return epochState.config?.community?.epoch?.reward_policy || null;
}

function rewardClaimsConfig() {
  return epochState.config?.reward_claims || null;
}

function rewardClaimsMode() {
  return rewardClaimsConfig()?.mode || epochState.rewardClaims?.mode || "legacy_merkle";
}

function rewardClaimsAbi() {
  return rewardClaimsMode() === "epoch_distributor" ? EPOCH_DISTRIBUTOR_ABI : LEGACY_DISTRIBUTOR_ABI;
}

function shortAddress(value) {
  return value ? `${value.slice(0, 6)}…${value.slice(-4)}` : "-";
}

function explorerLink(value) {
  const base = epochState.config?.network?.explorer_base_url?.replace(/\/$/, "") || "";
  if (!value || !base) return "#";
  if (value.startsWith("0x") && value.length === 66) {
    return `${base}/tx/${value}`;
  }
  return `${base}/address/${value}`;
}

function progressLine(progress) {
  if (!progress) return "-";
  if (!progress.target) return String(progress.current ?? 0);
  return `${progress.current ?? 0}/${progress.target}`;
}

function progressDetail(progress, noun) {
  if (!progress || !progress.target) return `No ${noun} target configured yet.`;
  if ((progress.remaining ?? 0) <= 0) return `${noun} goal reached in the current window.`;
  return `${progress.remaining} more ${noun} needed in the current window.`;
}

function formatUnits(value, decimals = 18, precision = 4) {
  if (window.ethers) {
    try {
      const text = window.ethers.formatUnits(value ?? 0, decimals);
      const [whole, frac = ""] = text.split(".");
      const trimmed = frac.slice(0, precision).replace(/0+$/, "");
      return trimmed ? `${whole}.${trimmed}` : whole;
    } catch {
      // Fall through to raw text.
    }
  }
  return String(value ?? "0");
}

function formatDeadline(seconds) {
  const total = Number(seconds || 0);
  if (!total) return "-";
  const date = new Date(total * 1000);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}

function claimSymbol() {
  return rewardClaimsConfig()?.currency_symbol || epochState.rewardClaims?.currency_symbol || epochState.config?.token?.symbol || "DRW";
}

function renderRewards() {
  const rewardWindow = epoch$("epochRewardWindow");
  const rewardRules = epoch$("epochRewardRules");
  if (!rewardWindow || !rewardRules) return;
  rewardRules.innerHTML = "";
  const reward = epochRewardPolicy();
  if (!reward || !(reward.rules || []).length) {
    rewardWindow.textContent = "No public reward pilot configured.";
    rewardRules.innerHTML = "<li>Set reward_policy in ops/community_epoch.json.</li>";
    return;
  }

  rewardWindow.textContent = reward.window_label || "Current reward window";
  for (const rule of reward.rules || []) {
    const li = document.createElement("li");
    const amount = Number(rule.amount || 0);
    li.textContent = amount
      ? `${rule.label || "Reward"}: ${amount} ${reward.currency_symbol || "DRW"}. ${rule.detail || ""}`.trim()
      : `${rule.label || "Reward"}: ${rule.detail || "Locked for a later phase."}`;
    rewardRules.appendChild(li);
  }
}

function renderProgress() {
  const progress = epochState.activitySummary?.progress;
  const antiAbuseNote = epochState.activitySummary?.anti_abuse?.note || "";
  const badge = epoch$("epochProgressBadge");
  const walletProgress = epoch$("epochWalletProgress");
  const walletDetail = epoch$("epochWalletProgressDetail");
  const swapProgress = epoch$("epochSwapProgress");
  const swapDetail = epoch$("epochSwapProgressDetail");
  const note = epoch$("epochProgressNote");
  if (!badge || !walletProgress || !walletDetail || !swapProgress || !swapDetail || !note) return;

  if (!progress) {
    badge.textContent = "unavailable";
    walletProgress.textContent = "-";
    walletDetail.textContent = "Waiting for wallet progress.";
    swapProgress.textContent = "-";
    swapDetail.textContent = "Waiting for swap progress.";
    note.textContent = "The local outside-activity classifier has not published a public snapshot yet.";
    return;
  }

  badge.textContent = progress.traction_ready ? "unlock ready" : "canonical only";
  walletProgress.textContent = progressLine(progress.wallets || {});
  walletDetail.textContent = progressDetail(progress.wallets || {}, "outside wallet");
  swapProgress.textContent = progressLine(progress.swaps || {});
  swapDetail.textContent = progressDetail(progress.swaps || {}, "outside swap");
  note.textContent = progress.traction_ready
    ? `Canonical traction is real on this lane. Experimental and incentivized routes can open without fragmenting thin liquidity.${antiAbuseNote ? ` ${antiAbuseNote}` : ""}`
    : `Keep routing everyone through the canonical pool until both wallet and swap goals are real.${antiAbuseNote ? ` ${antiAbuseNote}` : ""}`;
}

function renderLeaderboard() {
  const board = epochState.activitySummary?.leaderboard;
  const eligibilityNote = board?.eligibility_note || epochState.activitySummary?.anti_abuse?.note || "";
  const claimOnlyWallets = Number(board?.excluded?.claim_only_wallets ?? epochState.activitySummary?.summary?.claim_only_wallets ?? 0);
  const badge = epoch$("epochLeaderboardBadge");
  const list = epoch$("epochLeaderboardList");
  if (!badge || !list) return;
  list.innerHTML = "";
  if (!board || !(board.entries || []).length) {
    badge.textContent = "waiting";
    if (claimOnlyWallets > 0) {
      list.innerHTML = `<p class="caption">${claimOnlyWallets} claim-only wallets are visible, but the leaderboard opens after the first swap.</p>`;
    } else {
      list.innerHTML = "<p class=\"caption\">No outside wallets are on the leaderboard yet.</p>";
    }
    return;
  }

  badge.textContent = board.scoring_label || "live";
  if (eligibilityNote) {
    const note = document.createElement("p");
    note.className = "caption";
    note.textContent = eligibilityNote;
    list.appendChild(note);
  }
  for (const entry of board.entries || []) {
    const row = document.createElement("article");
    row.className = "leaderboard-row";

    const top = document.createElement("div");
    top.className = "leaderboard-top";

    const rank = document.createElement("span");
    rank.className = "badge";
    rank.textContent = `#${entry.rank}`;
    top.appendChild(rank);

    const actor = document.createElement("a");
    actor.className = "mono";
    actor.href = explorerLink(entry.actor);
    actor.target = "_blank";
    actor.rel = "noreferrer";
    actor.textContent = shortAddress(entry.actor);
    top.appendChild(actor);
    row.appendChild(top);

    const title = document.createElement("strong");
    title.textContent = `${entry.points} ${(board.scoring_label || "points").toLowerCase()}`;
    row.appendChild(title);

    const detail = document.createElement("p");
    detail.className = "caption";
    detail.textContent = `${entry.events} events, ${entry.swaps} swaps, ${entry.claims} claims.`;
    row.appendChild(detail);

    list.appendChild(row);
  }
}

function currentClaimEntry() {
  if (!epochState.account || !epochState.rewardClaims) return null;
  const key = epochState.account.toLowerCase();
  const indexed = epochState.rewardClaims.claims_by_account?.[key];
  if (indexed) return indexed;
  return (epochState.rewardClaims.claims || []).find((claim) => (claim.account || "").toLowerCase() === key) || null;
}

async function ensureWallet() {
  if (epochState.injectedProvider) return epochState.injectedProvider;
  if (!window.ethereum) {
    throw new Error("No browser wallet found. Open Darwin in MetaMask, Rabby, or another EIP-1193 wallet.");
  }
  epochState.injectedProvider = window.ethereum;
  return epochState.injectedProvider;
}

async function ensureCorrectNetwork() {
  const provider = await ensureWallet();
  const expected = epochState.config?.network?.hex || "";
  if (!expected) return true;
  const current = String(await provider.request({ method: "eth_chainId" })).toLowerCase();
  if (current === expected.toLowerCase()) return true;

  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: expected }],
    });
  } catch (error) {
    if (error?.code !== 4902) throw error;
    await provider.request({
      method: "wallet_addEthereumChain",
      params: [
        {
          chainId: expected,
          chainName: epochState.config.network.name,
          nativeCurrency: {
            name: epochState.config.network.native_symbol || "ETH",
            symbol: epochState.config.network.native_symbol || "ETH",
            decimals: 18,
          },
          rpcUrls: [epochState.config.network.rpc_url],
          blockExplorerUrls: [epochState.config.network.explorer_base_url],
        },
      ],
    });
  }
  return true;
}

function bindWalletEvents(provider) {
  if (!provider || epochState.walletEventsBound || typeof provider.on !== "function") return;
  provider.on("accountsChanged", async (accounts) => {
    epochState.account = (accounts?.[0] || "").toLowerCase();
    if (epochState.account && window.ethers) {
      epochState.browserProvider = new window.ethers.BrowserProvider(provider);
      epochState.signer = await epochState.browserProvider.getSigner();
    } else {
      epochState.browserProvider = null;
      epochState.signer = null;
    }
    renderClaimSurface();
  });
  provider.on("chainChanged", () => {
    window.location.reload();
  });
  epochState.walletEventsBound = true;
}

async function connectWallet() {
  await ensureCorrectNetwork();
  const provider = await ensureWallet();
  const accounts = await provider.request({ method: "eth_requestAccounts" });
  if (!window.ethers) {
    throw new Error("ethers failed to load");
  }
  epochState.browserProvider = new window.ethers.BrowserProvider(provider);
  epochState.signer = await epochState.browserProvider.getSigner();
  epochState.account = (accounts?.[0] || await epochState.signer.getAddress()).toLowerCase();
  bindWalletEvents(provider);
  await renderClaimSurface();
}

async function claimReadContract() {
  if (!window.ethers) return null;
  if (!epochState.readProvider) {
    const rpcUrl = epochState.config?.network?.read_rpc_url || epochState.config?.network?.rpc_url;
    if (!rpcUrl) return null;
    epochState.readProvider = new window.ethers.JsonRpcProvider(rpcUrl);
  }
  const config = rewardClaimsConfig();
  if (!config?.distributor) return null;
  return new window.ethers.Contract(config.distributor, rewardClaimsAbi(), epochState.readProvider);
}

function setClaimStatus(text, kind = "info") {
  const node = epoch$("epochClaimStatus");
  const badge = epoch$("epochClaimBadge");
  if (node) {
    node.textContent = text;
  }
  if (badge && kind) {
    badge.textContent = kind;
  }
}

function setClaimTxLink(txHash = "") {
  const link = epoch$("epochClaimTxLink");
  if (!link) return;
  if (!txHash) {
    link.hidden = true;
    link.href = "#";
    link.textContent = "";
    return;
  }
  link.hidden = false;
  link.href = explorerLink(txHash);
  link.textContent = `View ${shortAddress(txHash)}`;
}

function renderClaimBreakdown(items, emptyText) {
  const list = epoch$("epochClaimBreakdown");
  if (!list) return;
  list.innerHTML = "";
  if (!items || !items.length) {
    const li = document.createElement("li");
    li.textContent = emptyText;
    list.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    const amount = formatUnits(item.amount || "0", 18, 3);
    li.textContent = `${item.label || item.rule_id || "Reward"}: ${amount} ${claimSymbol()}. ${item.detail || ""}`.trim();
    list.appendChild(li);
  }
}

async function renderClaimSurface() {
  const config = rewardClaimsConfig();
  const deadlineValue = Number(config?.claim_deadline || epochState.rewardClaims?.claim_deadline || 0);
  const claimsCount = Number(config?.claims_count || epochState.rewardClaims?.claims_count || 0);
  const totalAmount = config?.total_amount || epochState.rewardClaims?.total_amount || "0";
  const summary = epoch$("epochClaimSummary");
  const amount = epoch$("epochClaimAmount");
  const amountDetail = epoch$("epochClaimAmountDetail");
  const deadline = epoch$("epochClaimDeadline");
  const deadlineDetail = epoch$("epochClaimDeadlineDetail");
  const connectButton = epoch$("epochConnectWalletButton");
  const claimButton = epoch$("epochClaimButton");

  if (!summary || !amount || !amountDetail || !deadline || !deadlineDetail || !connectButton || !claimButton) return;

  setClaimTxLink("");
  connectButton.textContent = epochState.account ? shortAddress(epochState.account) : "Connect wallet";

  if (!config?.distributor) {
    setClaimStatus("No proof-based reward distributor is configured for this lane yet.", "not live");
    summary.textContent = "Darwin can show the reward pilot before it opens claim proofs. When a distributor and published manifest are live, this panel becomes the claim surface.";
    amount.textContent = "-";
    amountDetail.textContent = "No claim surface is live on this lane yet.";
    deadline.textContent = "-";
    deadlineDetail.textContent = "Waiting for a distributor-backed epoch manifest.";
    claimButton.disabled = true;
    renderClaimBreakdown(config?.rules_applied || [], "Reward rules will appear here when a claim surface is published.");
    return;
  }

  summary.textContent = config.eligibility_note || "Only swap-active wallets from the published epoch snapshot receive proof-based bonus claims.";
  deadline.textContent = formatDeadline(deadlineValue);
  deadlineDetail.textContent = deadlineValue
    ? `${claimsCount} published claims across ${formatUnits(totalAmount, 18, 3)} ${claimSymbol()}.`
    : "Claim deadline is not available yet.";

  if (!epochState.rewardClaims) {
    setClaimStatus("Reward distributor is known, but the published claim manifest is not live yet.", config.status || "pending");
    amount.textContent = "-";
    amountDetail.textContent = "Published proofs are still pending for this lane.";
    claimButton.disabled = true;
    renderClaimBreakdown(config?.rules_applied || [], "The claim manifest has not been published yet.");
    return;
  }

  if (!epochState.account) {
    setClaimStatus("Connect a wallet to resolve this lane's published claim snapshot.", "connect wallet");
    amount.textContent = "-";
    amountDetail.textContent = "This panel checks the published Merkle manifest against your connected wallet.";
    claimButton.disabled = true;
    claimButton.textContent = "Claim rewards";
    renderClaimBreakdown(epochState.rewardClaims.rules_applied || [], "Connect a wallet to resolve any claim on this lane.");
    return;
  }

  const entry = currentClaimEntry();
  if (!entry) {
    setClaimStatus("No reward claim is published for this wallet on the current epoch snapshot.", "not eligible");
    amount.textContent = "0";
    amountDetail.textContent = "This lane only publishes bonus claims for wallets that were swap-active in the snapshot window.";
    claimButton.disabled = true;
    claimButton.textContent = "Claim rewards";
    renderClaimBreakdown(epochState.rewardClaims.rules_applied || [], "This wallet is not in the current published claim set.");
    return;
  }

  amount.textContent = `${formatUnits(entry.amount || "0", 18, 3)} ${claimSymbol()}`;
  amountDetail.textContent = `${entry.points || 0} score, ${entry.swaps || 0} swaps, ${entry.claims || 0} claims in the published window.`;
  renderClaimBreakdown(entry.breakdown || [], "No claim breakdown was attached to this wallet.");

  const now = Math.floor(Date.now() / 1000);
  if (deadlineValue && now > deadlineValue) {
    setClaimStatus("The claim window for this published reward set has already closed.", "closed");
    claimButton.disabled = true;
    claimButton.textContent = "Claim closed";
    return;
  }

  claimButton.disabled = false;
  claimButton.textContent = `Claim ${formatUnits(entry.amount || "0", 18, 3)} ${claimSymbol()}`;

  try {
    const contract = await claimReadContract();
    if (contract) {
      const claimed = rewardClaimsMode() === "epoch_distributor"
        ? await contract.isClaimed(BigInt(config.epoch_id || epochState.rewardClaims.epoch_id || 0), BigInt(entry.index))
        : await contract.isClaimed(BigInt(entry.index));
      if (claimed) {
        setClaimStatus("This wallet already claimed its published reward allocation.", "claimed");
        claimButton.disabled = true;
        claimButton.textContent = "Already claimed";
        return;
      }
    }
  } catch (error) {
    console.error(error);
    setClaimStatus("Published proof found. Claim-status check failed, but you can still try claiming after connecting.", "ready");
    return;
  }

  setClaimStatus("Published proof found. This wallet can claim its bonus allocation now.", "ready");
}

async function claimRewards() {
  const config = rewardClaimsConfig();
  const entry = currentClaimEntry();
  if (!config?.distributor || !entry) return;

  try {
    if (!epochState.signer) {
      await connectWallet();
    }
    if (!window.ethers) {
      throw new Error("ethers failed to load");
    }

    const contract = new window.ethers.Contract(config.distributor, rewardClaimsAbi(), epochState.signer);
    setClaimStatus("Submitting reward claim onchain…", "submitting");

    const tx = rewardClaimsMode() === "epoch_distributor"
      ? await contract.claim(
          BigInt(config.epoch_id || epochState.rewardClaims.epoch_id || 0),
          BigInt(entry.index),
          entry.account,
          BigInt(entry.amount),
          entry.proof,
        )
      : await contract.claim(
          BigInt(entry.index),
          entry.account,
          BigInt(entry.amount),
          entry.proof,
        );

    setClaimTxLink(tx.hash);
    setClaimStatus("Reward claim submitted. Waiting for confirmation…", "pending");
    await tx.wait();
    setClaimStatus("Reward claim confirmed onchain.", "claimed");
    epoch$("epochClaimButton").disabled = true;
    epoch$("epochClaimButton").textContent = "Claimed";
  } catch (error) {
    console.error(error);
    setClaimStatus(error?.shortMessage || error?.message || "Reward claim failed.", "error");
  }
}

function bootEpoch() {
  const switcher = epoch$("epochLaneSwitcher");
  const tinySellLink = epoch$("epochTinySellLink");
  const tinyBuyLink = epoch$("epochTinyBuyLink");
  const activityLink = epoch$("epochActivityLink");
  const summaryLine = epoch$("epochSummaryLine");
  const connectButton = epoch$("epochConnectWalletButton");
  const claimButton = epoch$("epochClaimButton");
  const epoch = epochState.config?.community?.epoch || {};

  if (window.DarwinLane && epochState.laneSelection) {
    window.DarwinLane.renderSwitcher(switcher, epochState.laneSelection);
    tinySellLink.href = window.DarwinLane.laneRelativeHref("/trade/?preset=tiny-sell", epochState.laneSelection);
    tinyBuyLink.href = window.DarwinLane.laneRelativeHref("/trade/?preset=tiny-buy", epochState.laneSelection);
    activityLink.href = window.DarwinLane.laneRelativeHref("/activity/", epochState.laneSelection);
  }

  if (summaryLine && epochState.config?.network?.name) {
    summaryLine.textContent = epoch.summary
      ? `${epoch.summary} Lane: ${epochState.config.network.name}.`
      : `The first outside Darwin actions on ${epochState.config.network.name} should be small, public, and easy to repeat.`;
  }

  connectButton?.addEventListener("click", () => {
    connectWallet().catch((error) => {
      console.error(error);
      setClaimStatus(error?.message || "Wallet connection failed.", "error");
    });
  });
  claimButton?.addEventListener("click", () => {
    claimRewards().catch((error) => {
      console.error(error);
      setClaimStatus(error?.message || "Reward claim failed.", "error");
    });
  });

  renderProgress();
  renderRewards();
  renderLeaderboard();
  renderClaimSurface().catch((error) => {
    console.error(error);
    setClaimStatus(error?.message || "Failed to render the reward claim surface.", "error");
  });
}

loadEpochConfig()
  .then(loadEpochSummary)
  .then(loadRewardClaims)
  .then(bootEpoch)
  .catch((error) => {
    console.error(error);
  });
