const epochState = {
  laneSelection: null,
  config: null,
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

function bootEpoch() {
  const switcher = epoch$("epochLaneSwitcher");
  const tinySellLink = epoch$("epochTinySellLink");
  const tinyBuyLink = epoch$("epochTinyBuyLink");
  const activityLink = epoch$("epochActivityLink");
  const summaryLine = epoch$("epochSummaryLine");

  if (window.DarwinLane && epochState.laneSelection) {
    window.DarwinLane.renderSwitcher(switcher, epochState.laneSelection);
    tinySellLink.href = window.DarwinLane.laneRelativeHref("/trade/?preset=tiny-sell", epochState.laneSelection);
    tinyBuyLink.href = window.DarwinLane.laneRelativeHref("/trade/?preset=tiny-buy", epochState.laneSelection);
    activityLink.href = window.DarwinLane.laneRelativeHref("/activity/", epochState.laneSelection);
  }

  if (summaryLine && epochState.config?.network?.name) {
    summaryLine.textContent =
      `The first outside Darwin actions on ${epochState.config.network.name} should be small, public, and easy to repeat.`;
  }
}

loadEpochConfig()
  .then(bootEpoch)
  .catch((error) => {
    console.error(error);
  });
