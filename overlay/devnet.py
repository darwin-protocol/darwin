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

from overlay.http_utils import request_headers, resolve_bind_host

BIND_HOST = resolve_bind_host()
CONNECT_HOST = os.environ.get(
    "DARWIN_DEVNET_CONNECT_HOST",
    "127.0.0.1" if BIND_HOST in {"0.0.0.0", "::"} else BIND_HOST,
)

SERVICES = {
    "gateway":   {"port": 9443, "cmd": ["python", "overlay/gateway/server.py",   "9443", "/tmp/darwin_devnet_full/gateway"]},
    "router":    {"port": 9444, "cmd": ["python", "overlay/router/service.py",    "9444", "1500", "/tmp/darwin_devnet_full/router/state.json"]},
    "scorer":    {"port": 9445, "cmd": ["python", "overlay/scorer/service.py",    "9445", f"http://{CONNECT_HOST}:9447"]},
    "watcher":   {"port": 9446, "cmd": ["python", "overlay/watcher/service.py",   "9446", "/tmp/darwin_devnet_full/watcher", f"http://{CONNECT_HOST}:9447"]},
    "archive":   {"port": 9447, "cmd": ["python", "overlay/archive/service.py",   "9447", "/tmp/darwin_devnet_full/archive"]},
    "finalizer": {"port": 9448, "cmd": ["python", "overlay/finalizer/service.py", "9448", "3", "/tmp/darwin_devnet_full/finalizer/state.json", "1"]},
    "sentinel":  {"port": 9449, "cmd": ["python", "overlay/sentinel/service.py",  "9449", "/tmp/darwin_devnet_full/sentinel/state.json"]},
}


def _post(url: str, data: dict) -> dict:
    req = Request(url, data=json.dumps(data).encode(), headers=request_headers({"Content-Type": "application/json"}))
    try:
        return json.loads(urlopen(req).read())
    except HTTPError as e:
        return {"error": f"http_{e.code}", "body": e.read().decode()}


def _get(url: str) -> dict:
    try:
        req = Request(url, headers=request_headers())
        return json.loads(urlopen(req).read())
    except HTTPError as e:
        return {"error": f"http_{e.code}", "body": e.read().decode()}


def _wait_healthy(port: int, timeout: int = 20) -> bool:
    for _ in range(timeout * 10):
        try:
            r = _get(f"http://{CONNECT_HOST}:{port}/healthz")
            if r.get("status") == "ok":
                return True
        except (URLError, ConnectionRefusedError, OSError):
            pass
        time.sleep(0.1)
    return False


def _kill_port_processes(port: int) -> None:
    result = subprocess.run(
        ["lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    for raw_pid in result.stdout.splitlines():
        raw_pid = raw_pid.strip()
        if not raw_pid:
            continue
        try:
            os.kill(int(raw_pid), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            continue


def _child_env() -> dict[str, str]:
    existing = os.environ.get("PYTHONPATH", "")
    parts = [str(ROOT), str(SIM)]
    if existing:
        parts.append(existing)
    return {**os.environ, "PYTHONPATH": os.pathsep.join(parts)}


def _tail_log(path: Path, lines: int = 20) -> list[str]:
    if not path.exists():
        return []
    content = path.read_text(errors="replace").splitlines()
    return content[-lines:]


def main():
    env = _child_env()
    procs: list[subprocess.Popen] = []
    log_dir = Path("/tmp/darwin_devnet_full/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Kill any leftover processes on our ports
    for svc in SERVICES.values():
        _kill_port_processes(svc["port"])
    time.sleep(0.5)

    print("=" * 60)
    print("  DARWIN OVERLAY DEVNET")
    print("=" * 60)
    print(f"  Bind host: {BIND_HOST}")
    print(f"  Connect:   {CONNECT_HOST}")

    # Start all services
    for name, cfg in SERVICES.items():
        log_path = log_dir / f"{name}.log"
        log_handle = log_path.open("w")
        p = subprocess.Popen(cfg["cmd"], cwd=str(ROOT), env=env,
                             stdout=log_handle, stderr=subprocess.STDOUT)
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
        for name, cfg in SERVICES.items():
            log_path = log_dir / f"{name}.log"
            tail = _tail_log(log_path)
            if tail:
                print(f"\n[{name}] recent log:")
                for line in tail:
                    print(f"  {line}")
        for p in procs:
            p.kill()
        return

    # Heartbeats
    print("\n[2/8] Sentinel heartbeats...")
    for svc in SERVICES:
        _post(f"http://{CONNECT_HOST}:9449/v1/heartbeat", {"service": svc})
    sentinel = _get(f"http://{CONNECT_HOST}:9449/v1/status")
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
    arch = _post(f"http://{CONNECT_HOST}:9447/v1/ingest",
                 {"epoch_id": "1", "source_dir": "/tmp/darwin_devnet_full/e2"})
    print(f"  Status: {arch.get('status')}  Files: {arch.get('files')}")

    # Score
    print("\n[5/8] Scoring epoch...")
    score = _post(f"http://{CONNECT_HOST}:9445/v1/score",
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
        admission = _post(f"http://{CONNECT_HOST}:9443/v1/intents", intent.to_dict())

        # Route
        route = _post(f"http://{CONNECT_HOST}:9444/v1/route",
                      {"intent_id": admission.get("intent_id", ""), "profile": "BALANCED"})

    stats = _get(f"http://{CONNECT_HOST}:9444/v1/stats")
    print(f"  Routed: {stats['total_routed']}  By species: {dict(stats['routes_by_species'])}")
    gw_stats = _get(f"http://{CONNECT_HOST}:9443/v1/stats")
    print(f"  Gateway admitted: {gw_stats['admitted']}  Rejected: {gw_stats['rejected']}")

    # Watcher replay through the archive path
    print("\n[7/8] Watcher replay verification...")
    archive_epochs = _get(f"http://{CONNECT_HOST}:9446/v1/archive/epochs")
    replay = _post(f"http://{CONNECT_HOST}:9446/v1/replay/latest", {})
    ready = _get(f"http://{CONNECT_HOST}:9446/readyz")
    mirrored_epoch = replay.get("archive_epoch_id", "")
    print(f"  Passed: {replay['passed']}  Mismatches: {len(replay['mismatches'])}")
    print(f"  Archive epochs: {len(archive_epochs.get('epochs', []))}  Mirrored epoch: {mirrored_epoch}  Ready: {ready.get('ready')}")

    # Finalize
    print("\n[8/8] Epoch finalization...")
    _post(f"http://{CONNECT_HOST}:9448/v1/register", {
        "epoch_id": 1,
        "closed_at": time.time(),
        "score_root": score.get("score_root", ""),
        "weight_root": score.get("weight_root", ""),
    })
    time.sleep(4)
    _post(f"http://{CONNECT_HOST}:9448/v1/poll-once", {})
    fin_status = _get(f"http://{CONNECT_HOST}:9448/v1/status")
    fin = _get(f"http://{CONNECT_HOST}:9448/v1/check/1")
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
