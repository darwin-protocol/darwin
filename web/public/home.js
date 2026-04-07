const homeState = {
  laneSelection: null,
  marketConfig: null,
  communityShare: null,
};

const homeEls = {};

function home$(id) {
  return document.getElementById(id);
}

async function loadJson(path) {
  const response = await fetch(`${path}?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return response.json();
}

async function loadHomeData() {
  homeState.laneSelection = window.DarwinLane ? await window.DarwinLane.resolveSelection() : null;
  const marketConfigPath = homeState.laneSelection?.currentLane?.path || "/market-config.json";
  const communitySharePath =
    homeState.laneSelection?.currentLane?.community_share_path || "/community-share.json";
  const [marketConfig, communityShare] = await Promise.all([
    loadJson(marketConfigPath),
    loadJson(communitySharePath),
  ]);
  homeState.marketConfig = marketConfig;
  homeState.communityShare = communityShare;
}

async function copyText(text, status) {
  await navigator.clipboard.writeText(text);
  homeEls.homeCommunityStatus.textContent = status;
}

function bindCommunityPanel() {
  const share = homeState.communityShare;
  const epoch = share.epoch || {};
  const stats = share.stats || {};
  const links = share.links || {};
  const messages = share.messages || {};
  const networkName = homeState.marketConfig?.network?.name || "Darwin lane";

  if (window.DarwinLane && homeState.laneSelection) {
    window.DarwinLane.renderSwitcher(homeEls.homeLaneSwitcher, homeState.laneSelection);
  }

  homeEls.homeEpochBadge.textContent = epoch.status || "live";
  homeEls.homeEpochTitle.textContent = epoch.title || "Darwin epoch";
  homeEls.homeEpochSummary.textContent = epoch.summary || "";
  homeEls.homePrimaryLaneBadge.textContent = networkName;
  homeEls.homeHeroStatusLine.innerHTML =
    `Public host: <code>usedarwin.xyz</code>. Current lane: <code>${networkName}</code>.`;
  homeEls.homeExternalWallets.textContent = String(stats.external_wallets ?? 0);
  homeEls.homeExternalSwaps.textContent = String(stats.external_swaps ?? 0);
  homeEls.homeTotalEvents.textContent = String(stats.total_events ?? 0);
  homeEls.homeCommunityStatus.textContent =
    stats.external_events > 0 ? "outside activity live" : "waiting for first outside wallet";
  homeEls.homeCommunityUpdatedAt.textContent = share.generated_at
    ? `Updated ${new Date(share.generated_at).toLocaleString()}. ${messages.progress_line || ""}`
    : (messages.progress_line || "Waiting for a live community snapshot.");
  const epochHref = window.DarwinLane && homeState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/epoch/", homeState.laneSelection)
    : (links.epoch || "/epoch/");
  const activityHref = window.DarwinLane && homeState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/activity/", homeState.laneSelection)
    : (links.activity || "/activity/");
  const tinySwapHref = window.DarwinLane && homeState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/trade/?preset=tiny-sell", homeState.laneSelection)
    : (links.tiny_swap || "/trade/?preset=tiny-sell");
  const marketHref = window.DarwinLane && homeState.laneSelection
    ? window.DarwinLane.laneRelativeHref("/trade/", homeState.laneSelection)
    : "/trade/";

  homeEls.homeOpenMarketLink.href = marketHref;
  homeEls.homeHeroTinySwapLink.href = tinySwapHref;
  homeEls.homeHeroEpochLink.href = epochHref;
  homeEls.homeHeroActivityLink.href = activityHref;
  homeEls.homeEpochLink.href = epochHref;
  homeEls.homeActivityLink.href = activityHref;
  homeEls.homeTinySwapLink.href = tinySwapHref;
  homeEls.homeMarketPageLink.href = marketHref;
  homeEls.homeActivityPageLink.href = activityHref;

  homeEls.copyInviteButton.addEventListener("click", () => {
    copyText(messages.invite_long || links.epoch || "", "invite copied").catch((error) => {
      homeEls.homeCommunityStatus.textContent = error?.message || "copy failed";
    });
  });
  homeEls.copyTinySwapHomeButton.addEventListener("click", () => {
    copyText(links.tiny_swap || "/trade/?preset=tiny-sell", "tiny-swap link copied").catch((error) => {
      homeEls.homeCommunityStatus.textContent = error?.message || "copy failed";
    });
  });
  homeEls.copyActivityHomeButton.addEventListener("click", () => {
    copyText(links.activity || "/activity/", "activity link copied").catch((error) => {
      homeEls.homeCommunityStatus.textContent = error?.message || "copy failed";
    });
  });
}

async function bootHome() {
  Object.assign(homeEls, {
    homeEpochBadge: home$("homeEpochBadge"),
    homeEpochTitle: home$("homeEpochTitle"),
    homeEpochSummary: home$("homeEpochSummary"),
    homePrimaryLaneBadge: home$("homePrimaryLaneBadge"),
    homeHeroStatusLine: home$("homeHeroStatusLine"),
    homeExternalWallets: home$("homeExternalWallets"),
    homeExternalSwaps: home$("homeExternalSwaps"),
    homeTotalEvents: home$("homeTotalEvents"),
    homeCommunityStatus: home$("homeCommunityStatus"),
    homeCommunityUpdatedAt: home$("homeCommunityUpdatedAt"),
    homeEpochLink: home$("homeEpochLink"),
    homeActivityLink: home$("homeActivityLink"),
    homeTinySwapLink: home$("homeTinySwapLink"),
    homeOpenMarketLink: home$("homeOpenMarketLink"),
    homeHeroTinySwapLink: home$("homeHeroTinySwapLink"),
    homeHeroEpochLink: home$("homeHeroEpochLink"),
    homeHeroActivityLink: home$("homeHeroActivityLink"),
    homeMarketPageLink: home$("homeMarketPageLink"),
    homeActivityPageLink: home$("homeActivityPageLink"),
    homeLaneSwitcher: home$("homeLaneSwitcher"),
    copyInviteButton: home$("copyInviteButton"),
    copyTinySwapHomeButton: home$("copyTinySwapHomeButton"),
    copyActivityHomeButton: home$("copyActivityHomeButton"),
  });

  await loadHomeData();
  bindCommunityPanel();
}

bootHome().catch((error) => {
  console.error(error);
  if (homeEls.homeCommunityStatus) {
    homeEls.homeCommunityStatus.textContent = error?.message || "community load failed";
  }
});
