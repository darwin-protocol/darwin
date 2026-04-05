"""darwinctl — DARWIN operator CLI.

Commands:
  keys gen          Generate PQ + EVM keypair
  config lint       Validate a node config against schema
  intent create     Create and sign a dual-envelope intent
  intent verify     Verify a dual-envelope intent's signatures
  replay verify     Watcher replay verification on published artifacts
  sim run-e2        Run E2 batch-lane uplift experiment
  sim run-suite     Run full E1-E7 experiment suite
  sim sweep         Run beta/epsilon parameter sweep
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def cmd_keys_gen(args):
    from darwin_sim.sdk.accounts import create_account
    account = create_account()
    out = Path(args.out) if args.out else Path("darwin_account.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(account.to_dict(), f, indent=2)
    print(f"[darwinctl] Account created")
    print(f"  acct_id:  {account.acct_id}")
    print(f"  evm_addr: {account.evm_addr}")
    print(f"  PQ hot:   {account.pq_hot_pk.hex()[:16]}...")
    print(f"  PQ cold:  {account.pq_cold_pk.hex()[:16]}...")
    print(f"  Output:   {out}")


def cmd_config_lint(args):
    from darwin_sim.core.config import SimConfig
    try:
        cfg = SimConfig.from_yaml(args.config)
        # Validate critical fields
        errors = []
        if not cfg.pairs:
            errors.append("No pairs defined")
        if not cfg.species:
            errors.append("No species defined")
        if cfg.rebalance.kappa_reb <= 0 or cfg.rebalance.kappa_reb > 1:
            errors.append(f"kappa_reb={cfg.rebalance.kappa_reb} out of range (0,1]. gain_bps={cfg.rebalance.gain_bps}")
        if abs(sum([cfg.scoring.weights.trader_surplus, cfg.scoring.weights.lp_return,
                     cfg.scoring.weights.fill_rate, cfg.scoring.weights.revenue,
                     cfg.scoring.weights.adverse_markout, cfg.scoring.weights.risk_penalty]) - 1.0) > 0.01:
            errors.append("Scoring weight coefficients don't sum to 1.0")

        sentinel_found = any(s.id == "S0_SENTINEL" for s in cfg.species)
        if not sentinel_found:
            errors.append("S0_SENTINEL species missing — constitutional baseline required")

        if errors:
            print(f"[darwinctl] Config INVALID: {args.config}")
            for e in errors:
                print(f"  ERROR: {e}")
            sys.exit(1)
        else:
            print(f"[darwinctl] Config VALID: {args.config}")
            print(f"  suite_id: {cfg.suite_id}")
            print(f"  pairs: {cfg.pairs}")
            print(f"  species: {[s.id for s in cfg.species]}")
            print(f"  kappa_reb: {cfg.rebalance.kappa_reb} (gain_bps={cfg.rebalance.gain_bps} / 10000)")
            print(f"  control_share: {cfg.epochs.control_share_bps_default/100:.1f}%")
    except Exception as e:
        print(f"[darwinctl] Config FAILED: {e}")
        sys.exit(1)


def cmd_intent_create(args):
    from darwin_sim.sdk.accounts import create_account
    from darwin_sim.sdk.intents import create_intent, verify_pq_sig, verify_evm_sig, verify_binding

    account = create_account()
    intent = create_intent(
        account=account,
        pair_id=args.pair,
        side=args.side.upper(),
        qty_base=args.qty,
        limit_price=args.price,
        max_slippage_bps=args.slippage,
        profile=args.profile.upper(),
        expiry_ts=int(time.time()) + 300,
        nonce=1,
    )

    # Verify
    pq_ok = verify_pq_sig(account, intent)
    evm_ok = verify_evm_sig(account, intent)
    bind_ok = verify_binding(intent)

    out = Path(args.out) if args.out else Path("intent.json")
    with out.open("w") as f:
        json.dump(intent.to_dict(), f, indent=2)

    print(f"[darwinctl] Intent created")
    print(f"  intent_hash: {intent.intent_hash}")
    print(f"  acct_id:     {intent.acct_id}")
    print(f"  pair:        {intent.pair_id}")
    print(f"  side:        {intent.side}")
    print(f"  qty:         {intent.qty_base}")
    print(f"  price:       {intent.limit_price}")
    print(f"  profile:     {intent.profile}")
    print(f"  PQ sig OK:   {pq_ok}")
    print(f"  EVM sig OK:  {evm_ok}")
    print(f"  Binding OK:  {bind_ok}")
    print(f"  Output:      {out}")


def cmd_replay_verify(args):
    from darwin_sim.watcher.replay import replay_and_verify
    result = replay_and_verify(args.artifacts)
    status = "PASS" if result["passed"] else "FAIL"
    print(f"[darwinctl] Replay verification: {status}")
    print(f"  Control fills:   {result['control_fills_loaded']}")
    print(f"  Treatment fills: {result['treatment_fills_loaded']}")
    print(f"  Recomputed:      {result['recomputed_uplift']}")
    print(f"  Published:       {result['published_uplift']}")
    if result["mismatches"]:
        print(f"  MISMATCHES ({len(result['mismatches'])}):")
        for m in result["mismatches"]:
            print(f"    {m}")
    if not result["passed"]:
        sys.exit(1)


def cmd_sim_e2(args):
    from darwin_sim.core.config import SimConfig
    from darwin_sim.experiments.runner import run_e2
    cfg = SimConfig.from_yaml(args.config)
    run_e2(cfg, args.data, args.out)


def cmd_sim_suite(args):
    from darwin_sim.core.config import SimConfig
    from darwin_sim.experiments.suite import run_full_suite
    cfg = SimConfig.from_yaml(args.config)
    run_full_suite(cfg, args.out, n_swaps=args.n_swaps, seed=args.seed)


def cmd_sim_sweep(args):
    from darwin_sim.core.config import SimConfig
    from darwin_sim.experiments.sweep import run_parameter_sweep
    cfg = SimConfig.from_yaml(args.config)
    run_parameter_sweep(cfg, args.out, n_swaps=args.n_swaps, seed=args.seed)


def main():
    parser = argparse.ArgumentParser(prog="darwinctl", description="DARWIN operator CLI")
    sub = parser.add_subparsers(dest="command")

    # keys gen
    p = sub.add_parser("keys-gen", help="Generate PQ + EVM keypair")
    p.add_argument("--out", default="darwin_account.json")

    # config lint
    p = sub.add_parser("config-lint", help="Validate config")
    p.add_argument("config")

    # intent create
    p = sub.add_parser("intent-create", help="Create dual-envelope intent")
    p.add_argument("--pair", default="ETH_USDC")
    p.add_argument("--side", default="BUY")
    p.add_argument("--qty", type=float, default=1.0)
    p.add_argument("--price", type=float, default=3500.0)
    p.add_argument("--slippage", type=int, default=50)
    p.add_argument("--profile", default="BALANCED")
    p.add_argument("--out", default="intent.json")

    # replay verify
    p = sub.add_parser("replay-verify", help="Watcher replay verification")
    p.add_argument("artifacts", help="Path to artifact directory")

    # sim run-e2
    p = sub.add_parser("sim-e2", help="Run E2 experiment")
    p.add_argument("--config", default="configs/baseline.yaml")
    p.add_argument("--data", default="data/raw/raw_swaps.csv")
    p.add_argument("--out", default="outputs/e2")

    # sim run-suite
    p = sub.add_parser("sim-suite", help="Run E1-E7 suite")
    p.add_argument("--config", default="configs/baseline.yaml")
    p.add_argument("--out", default="outputs/suite")
    p.add_argument("--n-swaps", type=int, default=10000)
    p.add_argument("--seed", type=int, default=2026)

    # sim sweep
    p = sub.add_parser("sim-sweep", help="Run parameter sweep")
    p.add_argument("--config", default="configs/baseline.yaml")
    p.add_argument("--out", default="outputs/sweep")
    p.add_argument("--n-swaps", type=int, default=10000)
    p.add_argument("--seed", type=int, default=2026)

    args = parser.parse_args()

    if args.command == "keys-gen":
        cmd_keys_gen(args)
    elif args.command == "config-lint":
        cmd_config_lint(args)
    elif args.command == "intent-create":
        cmd_intent_create(args)
    elif args.command == "replay-verify":
        cmd_replay_verify(args)
    elif args.command == "sim-e2":
        cmd_sim_e2(args)
    elif args.command == "sim-suite":
        cmd_sim_suite(args)
    elif args.command == "sim-sweep":
        cmd_sim_sweep(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
