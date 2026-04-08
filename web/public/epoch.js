const epochState = {
  laneSelection: null,
  config: null,
  activitySummary: null,
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

function epochRewardPolicy() {
  return epochState.config?.community?.epoch?.reward_policy || null;
}

function shortAddress(value) {
  return value ? `${value.slice(0, 6)}…${value.slice(-4)}` : "-";
}

function explorerLink(address) {
  const base = epochState.config?.network?.explorer_base_url?.replace(/\/$/, "") || "";
  return `${base}/address/${address}`;
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
    ? "Canonical traction is real on this lane. Experimental and incentivized routes can open without fragmenting thin liquidity."
    : "Keep routing everyone through the canonical pool until both wallet and swap goals are real.";
}

function renderLeaderboard() {
  const board = epochState.activitySummary?.leaderboard;
  const badge = epoch$("epochLeaderboardBadge");
  const list = epoch$("epochLeaderboardList");
  if (!badge || !list) return;
  list.innerHTML = "";
  if (!board || !(board.entries || []).length) {
    badge.textContent = "waiting";
    list.innerHTML = "<p class=\"caption\">No outside wallets are on the leaderboard yet.</p>";
    return;
  }

  badge.textContent = board.scoring_label || "live";
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

function bootEpoch() {
  const switcher = epoch$("epochLaneSwitcher");
  const tinySellLink = epoch$("epochTinySellLink");
  const tinyBuyLink = epoch$("epochTinyBuyLink");
  const activityLink = epoch$("epochActivityLink");
  const summaryLine = epoch$("epochSummaryLine");
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

  renderProgress();
  renderRewards();
  renderLeaderboard();
}

loadEpochConfig()
  .then(loadEpochSummary)
  .then(bootEpoch)
  .catch((error) => {
    console.error(error);
  });
