"""DARWIN Overlay Devnet — runs all 7 services and executes a full epoch lifecycle.

This is the integration harness that proves the entire overlay works end-to-end:
  SDK → Gateway → Router → Species → Scorer → Archive → Watcher → Finalizer → Sentinel

Usage: python overlay/devnet.py
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "sim"
sys.path.insert(0, str(SIM))

SERVICES = {
    "gateway":   {"port": 9443, "cmd": ["python", "overlay/gateway/server.py",   "9443", "/tmp/darwin_devnet_full/gateway"]},
    "router":    {"port": 9444, "cmd": ["python", "overlay/router/service.py",    "9444", "1500", "/tmp/darwin_devnet_full/router/state.json"]},
    "scorer":    {"port": 9445, "cmd": ["python", "overlay/scorer/service.py",    "9445"]},
    "watcher":   {"port": 9446, "cmd": ["python", "overlay/watcher/service.py",   "9446", "/tmp/darwin_devnet_full/watcher", "http://localhost:9447"]},
    "archive":   {"port": 9447, "cmd": ["python", "overlay/archive/service.py",   "9447", "/tmp/darwin_devnet_full/archive"]},
    "finalizer": {"port": 9448, "cmd": ["python", "overlay/finalizer/service.py", "9448", "3", "/tmp/darwin_devnet_full/finalizer/state.json", "1"]},
    "sentinel":  {"port": 9449, "cmd": ["python", "overlay/sentinel/service.py",  "9449", "/tmp/darwin_devnet_full/sentinel/state.json"]},
}


def _post(url: str, data: dict) -> dict:
    req = Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    try:
        return json.loads(urlopen(req).read())
    except HTTPError as e:
        return {"error": f"http_{e.code}", "body": e.read().decode()}


def _get(url: str) -> dict:
    try:
        return json.loads(urlopen(url).read())
    except HTTPError as e:
        return {"error": f"http_{e.code}", "body": e.read().decode()}


def _wait_healthy(port: int, timeout: int = 10) -> bool:
    for _ in range(timeout * 10):
        try:
            r = _get(f"http://localhost:{port}/healthz")
            if r.get("status") == "ok":
                return True
        except (URLError, ConnectionRefusedError, OSError):
            pass
        time.sleep(0.1)
    return False


def main():
    env = {**os.environ, "PYTHONPATH": str(SIM)}
    procs: list[subprocess.Popen] = []

    # Kill any leftover processes on our ports
    for svc in SERVICES.values():
        os.system(f"lsof -ti:{svc['port']} | xargs kill 2>/dev/null")
    time.sleep(0.5)

    print("=" * 60)
    print("  DARWIN OVERLAY DEVNET")
    print("=" * 60)

    # Start all services
    for name, cfg in SERVICES.items():
        p = subprocess.Popen(cfg["cmd"], cwd=str(ROOT), env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)

    # Wait for health
    print("\n[1/8] Starting 7 services...")
    all_ok = True
    for name, cfg in SERVICES.items():
        ok = _wait_healthy(cfg["port"])
        status = "UP" if ok else "DOWN"
        print(f"  {name:12s} :{cfg['port']} → {status}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("FAILED — not all services started")
        for p in procs:
            p.kill()
        return

    # Heartbeats
    print("\n[2/8] Sentinel heartbeats...")
    for svc in SERVICES:
        _post("http://localhost:9449/v1/heartbeat", {"service": svc})
    sentinel = _get("http://localhost:9449/v1/status")
    print(f"  Safe mode: {sentinel['safe_mode']}  Services: {len(sentinel['heartbeats'])}")

    # Run E2 experiment
    print("\n[3/8] Running E2 experiment...")
    from darwin_sim.core.config import SimConfig
    from darwin_sim.experiments.runner import run_e2
    cfg = SimConfig.from_yaml(str(SIM / "configs" / "baseline.yaml"))
    e2 = run_e2(cfg, str(SIM / "data" / "raw" / "raw_swaps.csv"), "/tmp/darwin_devnet_full/e2")
    print(f"  Decision: {e2['decision']}  TS={e2['uplift']['trader_surplus_bps']:+.2f}bps")

    # Archive ingest
    print("\n[4/8] Archiving epoch artifacts...")
    arch = _post("http://localhost:9447/v1/ingest",
                 {"epoch_id": "1", "source_dir": "/tmp/darwin_devnet_full/e2"})
    print(f"  Status: {arch.get('status')}  Files: {arch.get('files')}")

    # Score
    print("\n[5/8] Scoring epoch...")
    score = _post("http://localhost:9445/v1/score",
                  {"epoch_id": "1", "artifact_dir": "/tmp/darwin_devnet_full/e2"})
    print(f"  Score root: {score.get('score_root', '')[:16]}...  Fitness: {score.get('fitness')}")

    # Route intents
    print("\n[6/8] Routing 20 intents...")
    from darwin_sim.sdk.accounts import create_account
    from darwin_sim.sdk.intents import create_intent, verify_pq_sig, verify_evm_sig, verify_binding

    for i in range(20):
        acct = create_account()
        intent = create_intent(acct, "ETH_USDC", "BUY" if i % 2 == 0 else "SELL",
                               1.0 + i * 0.1, 3500.0, 50, "BALANCED",
                               int(time.time()) + 300, i + 1)

        # Submit to gateway
        admission = _post("http://localhost:9443/v1/intents", intent.to_dict())

        # Route
        route = _post("http://localhost:9444/v1/route",
                      {"intent_id": admission.get("intent_id", ""), "profile": "BALANCED"})

    stats = _get("http://localhost:9444/v1/stats")
    print(f"  Routed: {stats['total_routed']}  By species: {dict(stats['routes_by_species'])}")
    gw_stats = _get("http://localhost:9443/v1/stats")
    print(f"  Gateway admitted: {gw_stats['admitted']}  Rejected: {gw_stats['rejected']}")

    # Watcher replay through the archive path
    print("\n[7/8] Watcher replay verification...")
    archive_epochs = _get("http://localhost:9446/v1/archive/epochs")
    replay = _post("http://localhost:9446/v1/replay/latest", {})
    ready = _get("http://localhost:9446/readyz")
    mirrored_epoch = replay.get("archive_epoch_id", "")
    print(f"  Passed: {replay['passed']}  Mismatches: {len(replay['mismatches'])}")
    print(f"  Archive epochs: {len(archive_epochs.get('epochs', []))}  Mirrored epoch: {mirrored_epoch}  Ready: {ready.get('ready')}")

    # Finalize
    print("\n[8/8] Epoch finalization...")
    _post("http://localhost:9448/v1/register", {
        "epoch_id": 1,
        "closed_at": time.time(),
        "score_root": score.get("score_root", ""),
        "weight_root": score.get("weight_root", ""),
    })
    time.sleep(4)
    _post("http://localhost:9448/v1/poll-once", {})
    fin_status = _get("http://localhost:9448/v1/status")
    fin = _get("http://localhost:9448/v1/check/1")
    epoch_status = "finalized" if fin_status.get("latest_finalized_epoch") == 1 else fin.get("reason", "pending")
    print(f"  Status: {epoch_status}")

    # Final summary
    print("\n" + "=" * 60)
    print("  DEVNET RESULTS")
    print("=" * 60)
    print(f"  Services:     7/7 UP")
    print(f"  E2 Decision:  {e2['decision']}")
    print(f"  Fitness:      {score.get('fitness')}")
    print(f"  Intents:      {gw_stats['admitted']} admitted, {gw_stats['rejected']} rejected")
    print(f"  Routed:       {stats['total_routed']} ({dict(stats['routes_by_species'])})")
    print(f"  Watcher:      {'PASS' if replay['passed'] else 'FAIL'}")
    print(f"  Epoch:        {epoch_status}")
    print(f"  Safe mode:    {sentinel['safe_mode']}")
    print("=" * 60)

    # Cleanup
    for p in procs:
        p.kill()
    print("\nAll services stopped.")


if __name__ == "__main__":
    main()
