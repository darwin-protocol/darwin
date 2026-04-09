(function () {
  const DEFAULT_LANE_PATH = "/market-config.json";
  const DEFAULT_ACTIVITY_SUMMARY_PATH = "/activity-summary.json";
  const DEFAULT_COMMUNITY_SHARE_PATH = "/community-share.json";
  const LANE_INDEX_PATH = "/market-lanes.json";

  function slugFromPath(path) {
    const normalized = (path || DEFAULT_LANE_PATH).replace(/^\/+|\.json$/g, "");
    return normalized.replace(/^market-config-?/, "") || "default";
  }

  function normalizeLane(lane) {
    const slug = lane.slug || lane.network?.slug || slugFromPath(lane.path);
    return {
      ...lane,
      slug,
      path: lane.path || DEFAULT_LANE_PATH,
      activity_summary_path: lane.activity_summary_path || DEFAULT_ACTIVITY_SUMMARY_PATH,
      community_share_path: lane.community_share_path || DEFAULT_COMMUNITY_SHARE_PATH,
    };
  }

  async function loadIndex() {
    try {
      const response = await fetch(`${LANE_INDEX_PATH}?ts=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`lane index failed: ${response.status}`);
      }
      const payload = await response.json();
      const lanes = Array.isArray(payload?.lanes) ? payload.lanes.map(normalizeLane) : [];
      if (lanes.length) {
        return { lanes };
      }
    } catch {
      // Fall through to the built-in default lane.
    }

    return {
      lanes: [
        normalizeLane({
          path: DEFAULT_LANE_PATH,
          default: true,
          slug: "base-sepolia-recovery",
          name: "Base Sepolia",
          network: {
            name: "Base Sepolia",
            slug: "base-sepolia-recovery",
          },
        }),
      ],
    };
  }

  async function resolveSelection() {
    const index = await loadIndex();
    const defaultLane = index.lanes.find((lane) => lane.default) || index.lanes[0];
    const requested = new URLSearchParams(window.location.search).get("lane");
    const currentLane =
      index.lanes.find((lane) => lane.slug === requested || lane.path === requested) || defaultLane;
    return {
      lanes: index.lanes,
      defaultLane,
      currentLane,
    };
  }

  function laneRelativeHref(path, selection, lane = selection?.currentLane) {
    const chosenLane = typeof lane === "string"
      ? selection.lanes.find((entry) => entry.slug === lane) || selection.defaultLane
      : (lane || selection?.defaultLane);
    const url = new URL(path, window.location.origin);
    if (selection && chosenLane && chosenLane.slug !== selection.defaultLane.slug) {
      url.searchParams.set("lane", chosenLane.slug);
    } else {
      url.searchParams.delete("lane");
    }
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function laneAbsoluteHref(path, selection, lane = selection?.currentLane) {
    return new URL(laneRelativeHref(path, selection, lane), window.location.origin).toString();
  }

  function currentLocationHref(selection, lane = selection?.currentLane) {
    return laneRelativeHref(`${window.location.pathname}${window.location.search}${window.location.hash}`, selection, lane);
  }

  function renderSwitcher(mount, selection) {
    if (!mount || !selection || selection.lanes.length < 2) {
      return;
    }
    mount.innerHTML = "";
    for (const lane of selection.lanes) {
      const link = document.createElement("a");
      link.className = `button button-secondary tiny-button${lane.slug === selection.currentLane.slug ? " is-active" : ""}`;
      link.href = currentLocationHref(selection, lane);
      link.textContent = lane.name || lane.network?.name || lane.slug;
      mount.appendChild(link);
    }
  }

  function gateTargets(config, pool) {
    const defaults = config?.market_structure?.progress_targets || {};
    const rule = pool?.unlock_rule || {};
    return {
      externalWalletsTarget: Number(
        rule.external_wallets_target ?? defaults.external_wallets_target ?? 25,
      ),
      externalSwapsTarget: Number(
        rule.external_swaps_target ?? defaults.external_swaps_target ?? 40,
      ),
    };
  }

  function fallbackPool(config, defaultEntry) {
    const tokenSymbol = config?.token?.symbol || "DRW";
    const quoteSymbol = config?.quote_token?.symbol || "WETH";
    return {
      id: defaultEntry,
      label: "Canonical pool",
      enabled: true,
      status: "live",
      pool_address: config?.pool?.address || "",
      purpose: `Start on the live ${tokenSymbol} / ${quoteSymbol} reference pool.`,
      entry_path: config?.community?.tiny_swap_path || "/trade/?preset=tiny-sell",
      entry_label: "Open tiny sell",
      reason: "This is the current public route for a first Darwin trade.",
    };
  }

  function buildMarketStructure(config, summary) {
    const structure = config?.market_structure || {};
    const defaultEntry = structure.default_entry || "canonical";
    const definedPools = Array.isArray(structure.pools) ? structure.pools : [];
    const pools = definedPools.length ? definedPools : [fallbackPool(config, defaultEntry)];
    const rawExternalWallets = Number(summary?.external_wallets || 0);
    const rawExternalSwaps = Number(summary?.external_swaps || 0);
    const eligibleWallets = Number(summary?.eligible_wallets ?? rawExternalWallets);
    const eligibleSwaps = Number(summary?.eligible_swaps ?? rawExternalSwaps);

    const normalizedPools = pools.map((pool) => {
      const targets = gateTargets(config, pool);
      const gateMet =
        eligibleWallets >= targets.externalWalletsTarget &&
        eligibleSwaps >= targets.externalSwapsTarget;
      const isLive = Boolean(pool.enabled);
      const derivedStatus = isLive
        ? (pool.status || "live")
        : (gateMet ? "eligible" : (pool.status || "locked"));
      return {
        ...pool,
        derivedStatus,
        gateMet,
        isDefault: pool.id === defaultEntry,
        externalWallets: eligibleWallets,
        externalSwaps: eligibleSwaps,
        rawExternalWallets,
        rawExternalSwaps,
        progressLabel: `${eligibleWallets}/${targets.externalWalletsTarget} swap-active wallets, ${eligibleSwaps}/${targets.externalSwapsTarget} swaps`,
      };
    });

    return {
      strategy: structure.strategy || "single_canonical_until_traction",
      summary:
        structure.summary ||
        "Keep one canonical pool live until outside usage is real, then unlock the next Darwin routes.",
      defaultEntry,
      pools: normalizedPools,
      externalWallets: eligibleWallets,
      externalSwaps: eligibleSwaps,
      rawExternalWallets,
      rawExternalSwaps,
    };
  }

  window.DarwinLane = {
    resolveSelection,
    laneRelativeHref,
    laneAbsoluteHref,
    currentLocationHref,
    renderSwitcher,
    buildMarketStructure,
  };
})();
