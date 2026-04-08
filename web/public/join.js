const joinState = {
  laneSelection: null,
  config: null,
  communityShare: null,
};

const joinEls = {};

function join$(id) {
  return document.getElementById(id);
}

function isHexAddress(value) {
  return /^0x[a-fA-F0-9]{40}$/.test((value || "").trim());
}

function shortAddress(value) {
  if (!value) return "-";
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

function formatUnits(value, decimals, precision = 4) {
  const raw = BigInt(value || 0);
  const base = 10n ** BigInt(decimals);
  const whole = raw / base;
  const fraction = (raw % base).toString().padStart(decimals, "0").slice(0, precision).replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole.toString();
}

async function loadJson(path) {
  const response = await fetch(`${path}?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return response.json();
}

async function discoverInjectedProvider() {
  const providers = [];
  window.addEventListener("eip6963:announceProvider", (event) => {
    providers.push(event.detail);
  });
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  await new Promise((resolve) => setTimeout(resolve, 300));
  return providers.find((entry) => entry.provider?.isMetaMask)?.provider || window.ethereum || null;
}

async function loadJoinData() {
  joinState.laneSelection = window.DarwinLane ? await window.DarwinLane.resolveSelection() : null;
  const marketConfigPath = joinState.laneSelection?.currentLane?.path || "/market-config.json";
  const communitySharePath =
    joinState.laneSelection?.currentLane?.community_share_path || "/community-share.json";
  const [config, communityShare] = await Promise.all([
    loadJson(marketConfigPath),
    loadJson(communitySharePath),
  ]);
  joinState.config = config;
  joinState.communityShare = communityShare;
}

function buildJoinRow() {
  const account = joinEls.joinWalletAddress.value.trim();
  if (!isHexAddress(account)) {
    return null;
  }
  return {
    account: account.toLowerCase(),
    amount: String(joinState.config.community?.starter_cohort_amount || "100000000000000000000"),
    label: joinEls.joinWalletLabel.value.trim(),
    source: joinEls.joinWalletSource.value.trim() || "starter-cohort",
    notes: joinEls.joinWalletNotes.value.trim(),
    lane: joinState.config.network?.slug || "",
  };
}

function buildCsvRow(row) {
  const values = [row.account, row.amount, row.label, row.source, row.notes, row.lane];
  return values.map((value) => `"${String(value || "").replaceAll("\"", "\"\"")}"`).join(",");
}

function buildInvitePacket(row) {
  const share = joinState.communityShare || {};
  const links = share.links || {};
  return [
    `Darwin starter cohort row for ${shortAddress(row.account)}`,
    buildCsvRow(row),
    `Tiny swap: ${links.tiny_swap || ""}`,
    `Activity: ${links.activity || ""}`,
    `Epoch: ${links.epoch || ""}`,
  ].join("\n");
}

function refreshJoinRow() {
  const row = buildJoinRow();
  if (!row) {
    joinEls.joinRowStatus.textContent = "waiting";
    joinEls.joinCsvRow.value = 'account,amount,label,source,notes,lane';
    joinEls.joinJsonRow.value = "{}";
    joinEls.joinExportHint.textContent = "Enter a valid wallet to prepare a starter-cohort row.";
    return;
  }
  joinEls.joinRowStatus.textContent = "ready";
  joinEls.joinCsvRow.value = `account,amount,label,source,notes,lane\n${buildCsvRow(row)}`;
  joinEls.joinJsonRow.value = JSON.stringify(row, null, 2);
  joinEls.joinExportHint.textContent =
    "This row is public-safe. Send it to the operator or merge it into the local starter cohort file.";
}

function bindJoinPanel() {
  const share = joinState.communityShare || {};
  const links = share.links || {};
  const stats = share.stats || {};
  const networkName = joinState.config.network?.name || "Darwin lane";

  if (window.DarwinLane && joinState.laneSelection) {
    window.DarwinLane.renderSwitcher(joinEls.joinLaneSwitcher, joinState.laneSelection);
  }

  joinEls.joinLaneBadge.textContent = networkName;
  joinEls.joinStarterAmount.textContent = `${formatUnits(joinState.config.community?.starter_cohort_amount || 0, 18, 3)} DRW`;
  joinEls.joinExternalWallets.textContent = String(stats.external_wallets ?? 0);
  joinEls.joinExternalSwaps.textContent = String(stats.external_swaps ?? 0);

  const tradeHref = window.DarwinLane && joinState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/trade/?preset=tiny-sell", joinState.laneSelection)
    : (links.tiny_swap || "/trade/?preset=tiny-sell");
  const epochHref = window.DarwinLane && joinState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/epoch/", joinState.laneSelection)
    : (links.epoch || "/epoch/");
  const activityHref = window.DarwinLane && joinState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/activity/", joinState.laneSelection)
    : (links.activity || "/activity/");

  joinEls.joinTradeLink.href = tradeHref;
  joinEls.joinEpochLink.href = epochHref;
  joinEls.joinActivityLink.href = activityHref;
  joinEls.joinWalletSource.value = `starter-cohort:${joinState.config.network?.slug || "lane"}`;
}

async function useConnectedWallet() {
  const provider = await discoverInjectedProvider();
  if (!provider) {
    throw new Error("No browser wallet found.");
  }
  const accounts = await provider.request({ method: "eth_requestAccounts" });
  if (!accounts?.[0]) {
    throw new Error("No wallet account returned.");
  }
  joinEls.joinWalletAddress.value = accounts[0];
  refreshJoinRow();
}

function downloadOneRowCsv() {
  const row = buildJoinRow();
  if (!row) {
    throw new Error("Enter a valid wallet first.");
  }
  const blob = new Blob([joinEls.joinCsvRow.value + "\n"], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${joinState.config.network?.slug || "darwin"}-starter-cohort.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function bootJoin() {
  Object.assign(joinEls, {
    joinLaneSwitcher: join$("joinLaneSwitcher"),
    joinUseConnectedWalletButton: join$("joinUseConnectedWalletButton"),
    joinTradeLink: join$("joinTradeLink"),
    joinEpochLink: join$("joinEpochLink"),
    joinActivityLink: join$("joinActivityLink"),
    joinLaneBadge: join$("joinLaneBadge"),
    joinStarterAmount: join$("joinStarterAmount"),
    joinExternalWallets: join$("joinExternalWallets"),
    joinExternalSwaps: join$("joinExternalSwaps"),
    joinWalletAddress: join$("joinWalletAddress"),
    joinWalletLabel: join$("joinWalletLabel"),
    joinWalletSource: join$("joinWalletSource"),
    joinWalletNotes: join$("joinWalletNotes"),
    joinRowStatus: join$("joinRowStatus"),
    joinCsvRow: join$("joinCsvRow"),
    joinJsonRow: join$("joinJsonRow"),
    joinCopyCsvButton: join$("joinCopyCsvButton"),
    joinCopyJsonButton: join$("joinCopyJsonButton"),
    joinDownloadCsvButton: join$("joinDownloadCsvButton"),
    joinCopyInviteButton: join$("joinCopyInviteButton"),
    joinExportHint: join$("joinExportHint"),
  });

  await loadJoinData();
  bindJoinPanel();
  refreshJoinRow();

  joinEls.joinWalletAddress.addEventListener("input", refreshJoinRow);
  joinEls.joinWalletLabel.addEventListener("input", refreshJoinRow);
  joinEls.joinWalletSource.addEventListener("input", refreshJoinRow);
  joinEls.joinWalletNotes.addEventListener("input", refreshJoinRow);

  joinEls.joinUseConnectedWalletButton.addEventListener("click", () => {
    useConnectedWallet().catch((error) => {
      joinEls.joinExportHint.textContent = error?.message || "Wallet discovery failed.";
    });
  });
  joinEls.joinCopyCsvButton.addEventListener("click", async () => {
    await navigator.clipboard.writeText(joinEls.joinCsvRow.value);
    joinEls.joinExportHint.textContent = "CSV row copied.";
  });
  joinEls.joinCopyJsonButton.addEventListener("click", async () => {
    await navigator.clipboard.writeText(joinEls.joinJsonRow.value);
    joinEls.joinExportHint.textContent = "JSON row copied.";
  });
  joinEls.joinDownloadCsvButton.addEventListener("click", () => {
    try {
      downloadOneRowCsv();
      joinEls.joinExportHint.textContent = "One-row CSV downloaded.";
    } catch (error) {
      joinEls.joinExportHint.textContent = error?.message || "Download failed.";
    }
  });
  joinEls.joinCopyInviteButton.addEventListener("click", async () => {
    const row = buildJoinRow();
    if (!row) {
      joinEls.joinExportHint.textContent = "Enter a valid wallet first.";
      return;
    }
    await navigator.clipboard.writeText(buildInvitePacket(row));
    joinEls.joinExportHint.textContent = "Invite packet copied.";
  });
}

bootJoin().catch((error) => {
  console.error(error);
  if (joinEls.joinExportHint) {
    joinEls.joinExportHint.textContent = error?.message || "Join page failed to load.";
  }
});
