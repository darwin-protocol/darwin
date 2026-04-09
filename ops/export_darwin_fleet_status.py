#!/usr/bin/env python3
"""Export a public-safe Darwin node fleet status snapshot."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "web" / "public" / "node-fleet.json"
DEFAULT_LANES = [
    {
        "slug": "base-sepolia-recovery",
        "label": "Base Recovery",
        "role": "public",
        "market_config_path": "/market-config.json",
        "state_root": str(REPO_ROOT / "ops" / "state" / "base-sepolia-recovery-node"),
        "port_base": int(os.environ.get("DARWIN_BASE_RECOVERY_GATEWAY_PORT", "9443")),
    },
    {
        "slug": "base-sepolia",
        "label": "Base Canary",
        "role": "operator",
        "market_config_path": "",
        "state_root": str(REPO_ROOT / "ops" / "state" / "base-sepolia-canary"),
        "port_base": int(os.environ.get("DARWIN_CANARY_GATEWAY_PORT", "9443")),
    },
    {
        "slug": "arbitrum-sepolia",
        "label": "Arbitrum Sepolia",
        "role": "public",
        "market_config_path": "/market-config-arbitrum-sepolia.json",
        "state_root": str(REPO_ROOT / "ops" / "state" / "arbitrum-sepolia-node"),
        "port_base": int(os.environ.get("DARWIN_ARBITRUM_GATEWAY_PORT", "9543")),
    },
]
SERVICE_PORTS = {
    "gateway": 0,
    "router": 1,
    "scorer": 2,
    "watcher": 3,
    "archive": 4,
    "finalizer": 5,
    "sentinel": 6,
}
DEFAULT_STALE_AFTER_SEC = 6 * 60 * 60


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Output path for the fleet status JSON",
    )
    parser.add_argument(
        "--lane",
        action="append",
        default=[],
        help="Optional lane override as a JSON object",
    )
    parser.add_argument(
        "--stale-after-sec",
        type=int,
        default=DEFAULT_STALE_AFTER_SEC,
        help="Report staleness threshold in seconds",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=0.8,
        help="HTTP timeout for local live probes",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return load_json(path)


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def age_seconds(value: str) -> int | None:
    parsed = parse_time(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(int(delta.total_seconds()), 0)


def normalize_address(value: str) -> str:
    return str(value or "").strip().lower()


def pid_alive(pid_file: Path) -> bool:
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def request_json(url: str, timeout_sec: float) -> tuple[int | None, dict, str]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "darwin-fleet/1"})
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body or "{}"), ""
    except HTTPError as error:
        try:
            body = error.read().decode("utf-8")
            payload = json.loads(body or "{}")
        except Exception:
            payload = {}
        return error.code, payload, str(error)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        return None, {}, str(error)


def default_lane_route(slug: str, route: str) -> str:
    return route if slug == "base-sepolia-recovery" else f"{route}?lane={slug}"


def latest_smoke_summary(report_dir: Path) -> dict:
    matches = sorted(report_dir.glob("smoke-intent-*-summary.json"))
    if not matches:
        return {}
    latest = matches[-1]
    summary = load_optional_json(latest)
    return {
        "generated_at": summary.get("generated_at", ""),
        "gateway_delta": summary.get("gateway_delta", {}),
        "router_delta": summary.get("router_delta", {}),
    }


def probe_lane(lane: dict, expected_chain_id: int | None, expected_hub: str, timeout_sec: float) -> dict:
    port_base = lane.get("port_base")
    if port_base in (None, ""):
        return {
            "matched": False,
            "state": "unknown",
            "summary": "no live probe configured",
            "services": {},
            "gateway_config": {},
        }

    try:
        base_port = int(port_base)
    except (TypeError, ValueError):
        return {
            "matched": False,
            "state": "unknown",
            "summary": "invalid live probe port",
            "services": {},
            "gateway_config": {},
        }

    gateway_url = f"http://127.0.0.1:{base_port}"
    gateway_code, gateway_config, gateway_error = request_json(f"{gateway_url}/v1/config", timeout_sec)
    if gateway_code != 200:
        return {
            "matched": False,
            "state": "down",
            "summary": gateway_error or "gateway config unavailable",
            "services": {},
            "gateway_config": {},
        }

    chain_match = expected_chain_id is None or int(gateway_config.get("allowed_chain_id") or 0) == int(expected_chain_id)
    hub_match = not expected_hub or normalize_address(gateway_config.get("allowed_settlement_hub")) == expected_hub
    if not chain_match or not hub_match:
        mismatch = []
        if not chain_match:
            mismatch.append(
                f"chain={gateway_config.get('allowed_chain_id')} expected={expected_chain_id}"
            )
        if not hub_match:
            mismatch.append("settlement hub mismatch")
        return {
            "matched": False,
            "state": "shadowed",
            "summary": ", ".join(mismatch) if mismatch else "gateway mismatch",
            "services": {},
            "gateway_config": gateway_config,
        }

    services: dict[str, dict] = {}
    all_up = True
    for name, offset in SERVICE_PORTS.items():
        url = f"http://127.0.0.1:{base_port + offset}/healthz"
        code, payload, error = request_json(url, timeout_sec)
        ok = code == 200
        all_up = all_up and ok
        services[name] = {
            "ok": ok,
            "status_code": code,
            "detail": payload.get("status") or payload.get("role") or error or ("ok" if ok else "down"),
        }

    watcher_code, watcher_payload, watcher_error = request_json(
        f"http://127.0.0.1:{base_port + SERVICE_PORTS['watcher']}/readyz",
        timeout_sec,
    )
    watcher_ready = watcher_code == 200 and bool(watcher_payload.get("ready"))
    services["watcher_ready"] = {
        "ok": watcher_ready,
        "status_code": watcher_code,
        "detail": watcher_payload.get("detail") or watcher_error or ("ready" if watcher_ready else "cold"),
    }

    finalizer_code, finalizer_payload, _ = request_json(
        f"http://127.0.0.1:{base_port + SERVICE_PORTS['finalizer']}/v1/status",
        timeout_sec,
    )
    services["finalizer_status"] = {
        "ok": finalizer_code == 200,
        "status_code": finalizer_code,
        "detail": (
            f"registered={int(finalizer_payload.get('registered_epochs', 0))} "
            f"finalized={int(finalizer_payload.get('finalized_epochs', 0))}"
        ).strip(),
    }

    sentinel_code, sentinel_payload, _ = request_json(
        f"http://127.0.0.1:{base_port + SERVICE_PORTS['sentinel']}/v1/status",
        timeout_sec,
    )
    alerts = sentinel_payload.get("alerts")
    stale = sentinel_payload.get("stale")
    services["sentinel_status"] = {
        "ok": sentinel_code == 200,
        "status_code": sentinel_code,
        "detail": (
            f"alerts={len(alerts) if isinstance(alerts, list) else int(alerts or 0)} "
            f"stale={int(stale or 0)}"
        ).strip(),
    }

    if all_up and watcher_ready:
        state = "live"
    elif all_up:
        state = "warming"
    else:
        state = "degraded"

    summary = "all services healthy" if state == "live" else (
        "services healthy, watcher still warming" if state == "warming" else "one or more services failed health"
    )
    return {
        "matched": True,
        "state": state,
        "summary": summary,
        "services": services,
        "gateway_config": gateway_config,
    }


def parse_lane_specs(values: list[str]) -> list[dict]:
    if not values:
        return [dict(spec) for spec in DEFAULT_LANES]
    lanes = []
    for raw in values:
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SystemExit(f"invalid --lane JSON: {error}") from error
        if not isinstance(item, dict) or not item.get("slug") or not item.get("state_root"):
            raise SystemExit("each --lane must include at least slug and state_root")
        lanes.append(item)
    return lanes


def build_lane_status(lane: dict, stale_after_sec: int, timeout_sec: float) -> dict:
    state_root = Path(str(lane["state_root"])).expanduser().resolve()
    report_dir = state_root / "reports"
    report_path = report_dir / "status-report.json"
    pid_path = state_root / "darwin-node.pid"
    report = load_optional_json(report_path)
    deployment = report.get("deployment") or {}
    checks = report.get("checks") or {}

    report_generated_at = str(report.get("generated_at", "") or "")
    report_age = age_seconds(report_generated_at)
    report_freshness = "fresh" if report_age is not None and report_age <= stale_after_sec else ("stale" if report_generated_at else "missing")
    expected_chain_id = int(deployment.get("chain_id") or 0) or None
    expected_hub = normalize_address(deployment.get("settlement_hub"))
    probe = probe_lane(lane, expected_chain_id, expected_hub, timeout_sec)
    smoke = latest_smoke_summary(report_dir)
    smoke_age = age_seconds(str(smoke.get("generated_at", "") or ""))

    if probe["matched"]:
        status = probe["state"]
    elif report_path.exists() or pid_path.exists():
        status = "staged"
    else:
        status = "missing"

    status_copy = {
        "live": "Live",
        "warming": "Warming",
        "staged": "Staged",
        "degraded": "Degraded",
        "missing": "Missing",
    }
    public_links = {}
    if lane.get("market_config_path"):
        public_links = {
            "trade_path": default_lane_route(str(lane["slug"]), "/trade/"),
            "activity_path": default_lane_route(str(lane["slug"]), "/activity/"),
            "epoch_path": default_lane_route(str(lane["slug"]), "/epoch/"),
        }

    if not probe["matched"] and probe.get("state") == "down" and report_path.exists():
        summary = "no live local overlay responding on the expected ports"
    else:
        summary = probe.get("summary") or checks.get("watcher_ready", {}).get("detail") or (
            "deployment is staged but not currently pinned to a live local overlay"
            if report_path.exists()
            else "no local state captured yet"
        )

    return {
        "slug": str(lane["slug"]),
        "label": str(lane.get("label") or lane["slug"]),
        "role": str(lane.get("role") or "public"),
        "market_config_path": str(lane.get("market_config_path") or ""),
        "status": status,
        "status_label": status_copy.get(status, status.title()),
        "summary": summary,
        "pid_alive": pid_alive(pid_path),
        "report_generated_at": report_generated_at,
        "report_age_sec": report_age,
        "report_freshness": report_freshness,
        "deployment": {
            "network": deployment.get("network", lane["slug"]),
            "chain_id": deployment.get("chain_id"),
            "settlement_hub": deployment.get("settlement_hub", ""),
        },
        "checks": {
            "watcher_ready": checks.get("watcher_ready", {}),
            "watcher_sync": checks.get("watcher_sync", {}),
            "finalizer_status": checks.get("finalizer_status", {}),
            "router_flow": checks.get("router_flow", {}),
            "sentinel_status": checks.get("sentinel_status", {}),
        },
        "live_probe": probe,
        "latest_intent_smoke": {
            "generated_at": smoke.get("generated_at", ""),
            "age_sec": smoke_age,
            "gateway_delta": smoke.get("gateway_delta", {}),
            "router_delta": smoke.get("router_delta", {}),
        },
        "links": public_links,
    }


def summarize(lanes: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for lane in lanes:
        counts[lane["status"]] = counts.get(lane["status"], 0) + 1
    public_lanes = [lane for lane in lanes if lane.get("role") == "public"]
    public_live = sum(1 for lane in public_lanes if lane["status"] == "live")
    return {
        "total_lanes": len(lanes),
        "public_lanes": len(public_lanes),
        "live": counts.get("live", 0),
        "warming": counts.get("warming", 0),
        "staged": counts.get("staged", 0),
        "degraded": counts.get("degraded", 0),
        "missing": counts.get("missing", 0),
        "public_live": public_live,
        "public_summary": f"{public_live}/{len(public_lanes)} public lanes live" if public_lanes else "no public lanes configured",
        "operator_summary": ", ".join(
            f"{counts[key]} {key}" for key in ("live", "warming", "staged", "degraded", "missing") if counts.get(key, 0)
        ),
    }


def main() -> int:
    args = parse_args()
    lanes = [build_lane_status(lane, args.stale_after_sec, args.timeout_sec) for lane in parse_lane_specs(args.lane)]
    payload = {
        "generated_at": utc_now(),
        "summary": summarize(lanes),
        "lanes": lanes,
    }
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("[darwin-fleet] exported")
    print(f"  out:       {out_path}")
    print(f"  summary:   {payload['summary']['operator_summary']}")
    print(f"  public:    {payload['summary']['public_summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
