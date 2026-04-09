import { readFile } from "node:fs/promises";
import path from "node:path";

const SITE_URL = "https://usedarwin.xyz";
const DEFAULT_LANE_PATH = "/market-config.json";
const DEFAULT_ACTIVITY_SUMMARY_PATH = "/activity-summary.json";
const DEFAULT_COMMUNITY_SHARE_PATH = "/community-share.json";
const LANE_INDEX_PATH = "/market-lanes.json";
const PUBLIC_DIR = path.join(process.cwd(), "public");

const DEFAULT_LANE_INDEX = {
  lanes: [
    {
      path: DEFAULT_LANE_PATH,
      default: true,
      slug: "base-sepolia-recovery",
      name: "Base Sepolia",
      activity_summary_path: DEFAULT_ACTIVITY_SUMMARY_PATH,
      community_share_path: DEFAULT_COMMUNITY_SHARE_PATH,
      network: {
        name: "Base Sepolia",
        slug: "base-sepolia-recovery",
      },
    },
  ],
};

function numberValue(value) {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function slugFromPath(configPath) {
  const normalized = String(configPath || DEFAULT_LANE_PATH).replace(/^\/+|\.json$/g, "");
  return normalized.replace(/^market-config-?/, "") || "default";
}

function normalizeLane(lane = {}) {
  const slug = lane.slug || lane.network?.slug || slugFromPath(lane.path);
  return {
    ...lane,
    slug,
    path: lane.path || DEFAULT_LANE_PATH,
    activity_summary_path: lane.activity_summary_path || DEFAULT_ACTIVITY_SUMMARY_PATH,
    community_share_path: lane.community_share_path || DEFAULT_COMMUNITY_SHARE_PATH,
  };
}

async function readPublicJson(publicPath, fallback) {
  try {
    const filePath = path.join(PUBLIC_DIR, String(publicPath || "").replace(/^\/+/, ""));
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function gateTargets(config, pool) {
  const defaults = config?.market_structure?.progress_targets || {};
  const rule = pool?.unlock_rule || {};
  return {
    externalWalletsTarget: numberValue(
      rule.external_wallets_target ?? defaults.external_wallets_target ?? 25,
    ),
    externalSwapsTarget: numberValue(
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

export function buildMarketStructure(config, summary = {}) {
  const structure = config?.market_structure || {};
  const defaultEntry = structure.default_entry || "canonical";
  const rawExternalWallets = numberValue(summary?.external_wallets);
  const rawExternalSwaps = numberValue(summary?.external_swaps);
  const eligibleWallets = numberValue(summary?.eligible_wallets ?? rawExternalWallets);
  const eligibleSwaps = numberValue(summary?.eligible_swaps ?? rawExternalSwaps);
  const definedPools = Array.isArray(structure.pools) ? structure.pools : [];
  const pools = definedPools.length ? definedPools : [fallbackPool(config, defaultEntry)];

  return {
    strategy: structure.strategy || "single_canonical_until_traction",
    summary:
      structure.summary ||
      "Keep one canonical pool live until outside usage is real, then unlock the next Darwin routes.",
    defaultEntry,
    externalWallets: eligibleWallets,
    externalSwaps: eligibleSwaps,
    rawExternalWallets,
    rawExternalSwaps,
    pools: pools.map((pool) => {
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
    }),
  };
}

export function laneHref(routePath, selection, lane = selection?.defaultLane) {
  const chosenLane = typeof lane === "string"
    ? selection?.lanes?.find((entry) => entry.slug === lane) || selection?.defaultLane
    : (lane || selection?.defaultLane);
  const url = new URL(routePath, SITE_URL);
  if (selection?.defaultLane?.slug && chosenLane?.slug && chosenLane.slug !== selection.defaultLane.slug) {
    url.searchParams.set("lane", chosenLane.slug);
  } else {
    url.searchParams.delete("lane");
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

export function shortAddress(value) {
  if (!value) return "-";
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

export function explorerAddressHref(config, address) {
  const base = String(config?.network?.explorer_base_url || "").replace(/\/$/, "");
  if (!base || !address) {
    return "#";
  }
  return `${base}/address/${address}`;
}

export function formatUnits(value, decimals, precision = 4) {
  try {
    const raw = BigInt(String(value ?? 0));
    const base = 10n ** BigInt(decimals);
    const whole = raw / base;
    const fraction = (raw % base)
      .toString()
      .padStart(decimals, "0")
      .slice(0, precision)
      .replace(/0+$/, "");
    return fraction ? `${whole}.${fraction}` : whole.toString();
  } catch {
    return "-";
  }
}

export function formatDuration(seconds) {
  const total = numberValue(seconds);
  if (total <= 0) return "none";
  if (total % 86400 === 0) return `${total / 86400}d`;
  if (total % 3600 === 0) return `${total / 3600}h`;
  if (total % 60 === 0) return `${total / 60}m`;
  return `${total}s`;
}

export function communityStateText(stats = {}) {
  const eligibleWallets = numberValue(stats?.eligible_wallets ?? stats?.external_wallets);
  if (eligibleWallets > 0) {
    return "swap-active wallets live";
  }
  if (numberValue(stats?.external_events) > 0) {
    return "claims seen, waiting for first swap";
  }
  return "waiting for first outside wallet";
}

export function communityUpdatedText(share = {}) {
  const messages = share.messages || {};
  const antiAbuse = share.anti_abuse || {};
  const eligibilityNote = messages.eligibility_note || antiAbuse.note || "";
  const progressLine = messages.progress_line || "Waiting for a live community snapshot.";
  if (!share.generated_at) {
    return `${progressLine} ${eligibilityNote}`.trim();
  }
  const updatedAt = new Date(share.generated_at);
  const updatedText = Number.isNaN(updatedAt.getTime())
    ? share.generated_at
    : updatedAt.toLocaleString("en-US");
  return `Updated ${updatedText}. ${progressLine} ${eligibilityNote}`.trim();
}

export async function loadPublishedLaneData() {
  const laneIndex = await readPublicJson(LANE_INDEX_PATH, DEFAULT_LANE_INDEX);
  const lanes = Array.isArray(laneIndex?.lanes) && laneIndex.lanes.length
    ? laneIndex.lanes.map(normalizeLane)
    : DEFAULT_LANE_INDEX.lanes.map(normalizeLane);
  const defaultLane = lanes.find((lane) => lane.default) || lanes[0];

  const artifactEntries = await Promise.all(
    lanes.map(async (lane) => {
      const config = await readPublicJson(lane.path, {});
      const share = await readPublicJson(lane.community_share_path, {});
      const activity = await readPublicJson(lane.activity_summary_path, {});
      const stats = share.stats || activity.summary || {};
      return [
        lane.slug,
        {
          lane,
          config,
          share,
          activity,
          stats,
          structure: buildMarketStructure(config, stats),
        },
      ];
    }),
  );

  const artifacts = Object.fromEntries(artifactEntries);
  return {
    lanes,
    defaultLane,
    artifacts,
    current: artifacts[defaultLane.slug],
  };
}
