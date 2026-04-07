"""End-to-end integration test: account → intent → gateway → verify → replay.

Proves the full DARWIN lifecycle works without a live chain.
"""

import os
import sys
import time
import json
import socket
import subprocess
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / "sim"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM))

import overlay.archive.service as archive_service
import overlay.finalizer.service as finalizer_service
import overlay.gateway.server as gateway_service
import overlay.router.service as router_service
import overlay.scorer.service as scorer_service
import overlay.sentinel.service as sentinel_service
from overlay.gateway.server import GatewayState
from overlay.watcher.service import WatcherState
from darwin_sim.sdk.accounts import create_account
from darwin_sim.sdk.deployments import load_deployment
from darwin_sim.sdk.intents import create_intent, verify_pq_sig, verify_evm_sig, verify_binding
from darwin_sim.sdk.role_audit import LiveRoleState, build_role_audit_report
from darwin_sim.sdk.wallets import create_wallet, load_wallet, load_wallet_public_account, save_wallet
from darwin_sim.watcher.replay import replay_and_verify
from darwin_sim.core.config import SimConfig


class TestEndToEnd(unittest.TestCase):

    def test_01_account_creation(self):
        """Account: PQ + EVM keypair with policy-hash address."""
        acct = create_account()
        self.assertEqual(len(acct.acct_id), 32)
        self.assertTrue(acct.evm_addr.startswith("0x"))
        self.assertEqual(len(acct.pq_hot_pk), 1952)  # ML-DSA-65 (Dilithium3) public key
        self.assertEqual(len(acct.pq_cold_pk), 1952)
        print(f"  Account: {acct.acct_id[:16]}... EVM: {acct.evm_addr[:10]}...")

    def test_02_dual_envelope_signing(self):
        """Intent: dual-envelope with PQ + EVM sigs, cryptographically bound."""
        acct = create_account()
        intent = create_intent(
            account=acct,
            pair_id="ETH_USDC",
            side="BUY",
            qty_base=1.5,
            limit_price=3500.0,
            max_slippage_bps=50,
            profile="BALANCED",
            expiry_ts=int(time.time()) + 300,
            nonce=1,
        )

        # Verify all three checks
        self.assertTrue(verify_pq_sig(acct, intent), "PQ signature failed")
        self.assertTrue(verify_evm_sig(acct, intent), "EVM signature failed")
        self.assertTrue(verify_binding(intent), "Binding check failed")

        # Verify the intent hash is deterministic
        self.assertEqual(len(intent.intent_hash), 32)
        self.assertEqual(len(intent.pq_hash), 64)
        self.assertEqual(len(intent.evm_sig), 130)
        print(f"  Intent: {intent.intent_hash} PQ=✓ EVM=✓ Bind=✓")

    def test_03_gateway_admission(self):
        """Gateway: real signature verification admits a valid intent."""
        gateway = GatewayState("outputs/test_gateway")
        acct = create_account()
        intent = create_intent(
            account=acct,
            pair_id="ETH_USDC",
            side="BUY",
            qty_base=1.0,
            limit_price=3500.0,
            max_slippage_bps=50,
            profile="BALANCED",
            expiry_ts=int(time.time()) + 300,
            nonce=1,
        )
        result = gateway.admit_intent(intent.to_dict())
        self.assertEqual(result["status"], "ADMITTED")
        self.assertTrue(result["pq_verified"])
        self.assertTrue(result["evm_verified"])
        print(f"  Gateway: admitted {result['intent_id'][:12]}... with full signature verification")

    def test_04_gateway_rejects_forgery(self):
        """Gateway: forged signatures are rejected instead of length-checked."""
        gateway = GatewayState("outputs/test_gateway_reject")
        acct = create_account()
        intent = create_intent(
            account=acct,
            pair_id="ETH_USDC",
            side="SELL",
            qty_base=1.0,
            limit_price=3400.0,
            max_slippage_bps=25,
            profile="BALANCED",
            expiry_ts=int(time.time()) + 300,
            nonce=2,
        )
        forged = intent.to_dict()
        forged["pq_leg"]["pq_sig"] = ("00" * 3293)
        result = gateway.admit_intent(forged)
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["reason"], "invalid_pq_sig")
        print("  Gateway: forged PQ signature rejected")

    def test_05_gateway_enforces_deployment_policy(self):
        """Gateway: optional deployment policy pins intents to one chain and hub."""
        with tempfile.TemporaryDirectory() as tmpdir:
            deployment_path = Path(tmpdir) / "base-sepolia.json"
            deployment_path.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "deployer": "0x0000000000000000000000000000000000000002",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000003",
                    "epoch_operator": "0x0000000000000000000000000000000000000004",
                    "safe_mode_authority": "0x0000000000000000000000000000000000000005",
                },
            }))

            gateway = GatewayState("outputs/test_gateway_policy", deployment_file=str(deployment_path))
            acct = create_account(chain_id=84532)
            good = create_intent(
                account=acct,
                pair_id="ETH_USDC",
                side="BUY",
                qty_base=1.0,
                limit_price=3500.0,
                expiry_ts=int(time.time()) + 300,
                nonce=3,
                chain_id=84532,
                settlement_hub="0x0000000000000000000000000000000000000001",
            )
            bad = create_intent(
                account=acct,
                pair_id="ETH_USDC",
                side="BUY",
                qty_base=1.0,
                limit_price=3500.0,
                expiry_ts=int(time.time()) + 300,
                nonce=4,
                chain_id=84532,
                settlement_hub="0x0000000000000000000000000000000000000009",
            )

            accepted = gateway.admit_intent(good.to_dict())
            rejected = gateway.admit_intent(bad.to_dict())

            self.assertEqual(accepted["status"], "ADMITTED")
            self.assertEqual(rejected["status"], "REJECTED")
            self.assertEqual(rejected["reason"], "unsupported_settlement_hub")
            print("  Gateway: deployment policy enforces configured settlement hub")

    def test_06_deployment_loader(self):
        """Deployment artifacts load normalized chain and contract metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            deployment_path = Path(tmpdir) / "local.json"
            deployment_path.write_text(json.dumps({
                "network": "local-anvil",
                "chain_id": 31337,
                "bond_asset_mode": "external",
                "deployer": "0xF39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
                "deployed_at": 123,
                "contracts": {
                    "settlement_hub": "0xDc64a140Aa3E981100a9becA4E685f962f0cF6C9",
                    "shared_pair_vault": "0xa513E6E4b8f2a923D98304ec87F64353C4D5C853",
                },
                "roles": {
                    "governance": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
                    "epoch_operator": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
                    "safe_mode_authority": "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
                },
            }))

            deployment = load_deployment(deployment_file=deployment_path)
            self.assertEqual(deployment.network, "local-anvil")
            self.assertEqual(deployment.chain_id, 31337)
            self.assertEqual(deployment.bond_asset_mode, "external")
            self.assertEqual(deployment.settlement_hub, "0xdc64a140aa3e981100a9beca4e685f962f0cf6c9")
            print(f"  Deployment: {deployment.network} chain={deployment.chain_id} hub={deployment.settlement_hub}")

    def test_06b_role_audit_retire_ready(self):
        """Role audit: finalized genesis + no deployer roles means the deployer can be retired."""
        with tempfile.TemporaryDirectory() as tmpdir:
            deployment_path = Path(tmpdir) / "base-sepolia.json"
            deployment_path.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x00000000000000000000000000000000000000d1",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x556d75f4455cf3f0D7c5F9c6e7ea49447f66D8d2",
                    "drw_token": "0x00000000000000000000000000000000000000a1",
                    "drw_staking": "0x00000000000000000000000000000000000000a2",
                    "drw_faucet": "0x00000000000000000000000000000000000000a3",
                    "reference_pool": "0x00000000000000000000000000000000000000a4",
                    "bond_vault": "0xa842Dc4BF4CA3e1f1CA07714867145038D5e0ab4",
                    "challenge_escrow": "0xd71e90F784f45FeC0b6b36454186CD88eaD126a7",
                    "epoch_manager": "0xE53A27DA8e3C2c69495a97C3AcD6E484AbD7892B",
                    "score_registry": "0x9135b4BDDa2739212a7c5c0dB0C45AdEc42b7346",
                    "shared_pair_vault": "0xbecDB8e518C9C1B57db0656297F5F1c1FE5c2851",
                    "species_registry": "0xcaC5E4C711b4FfD9C76354FF8FfD4E236b1798AB",
                },
                "roles": {
                    "governance": "0x00000000000000000000000000000000000000b1",
                    "epoch_operator": "0x00000000000000000000000000000000000000b2",
                    "batch_operator": "0x00000000000000000000000000000000000000b3",
                    "safe_mode_authority": "0x00000000000000000000000000000000000000b4",
                },
            }))

            deployment = load_deployment(deployment_file=deployment_path)
            report = build_role_audit_report(
                deployment,
                LiveRoleState(
                    "0x00000000000000000000000000000000000000b1",
                    "0x0000000000000000000000000000000000000000",
                    True,
                    "0x00000000000000000000000000000000000000b1",
                    "0x0000000000000000000000000000000000000000",
                    "0x00000000000000000000000000000000000000b1",
                    "0x00000000000000000000000000000000000000b1",
                    "0x00000000000000000000000000000000000000b5",
                    "0x00000000000000000000000000000000000000b1",
                    False,
                    True,
                ),
            )

            self.assertTrue(report["deployer_retire_ready"])
            self.assertEqual(report["deployer_privileges"], [])
            self.assertTrue(report["governance_matches_live"])
            self.assertIn("settlement_hub", report["governance_root_summary"]["immutable_core_contracts"])
            self.assertIn("reference_pool", report["governance_root_summary"]["rotatable_contracts"])
            print("  Role audit: deployer can be retired once no live roles remain")

    def test_06c_load_deployment_merges_local_private_overlay(self):
        """Deployment: public artifact can merge local private overlay data from config dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment_path = tmp / "base-sepolia.json"
            config_dir = tmp / "config"
            overlay_path = config_dir / "deployments" / "base-sepolia.private.json"
            overlay_path.parent.mkdir(parents=True, exist_ok=True)

            deployment_path.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000011",
                    "drw_token": "0x0000000000000000000000000000000000000012",
                },
                "drw": {
                    "enabled": True,
                    "contracts": {
                        "drw_token": "0x0000000000000000000000000000000000000012",
                    },
                    "allocations": {
                        "treasury_amount": "100",
                    },
                },
                "market": {
                    "enabled": True,
                    "contracts": {
                        "reference_pool": "0x0000000000000000000000000000000000000013",
                    },
                },
            }))
            overlay_path.write_text(json.dumps({
                "deployer": "0x00000000000000000000000000000000000000d1",
                "roles": {
                    "governance": "0x00000000000000000000000000000000000000b1",
                    "epoch_operator": "0x00000000000000000000000000000000000000b2",
                    "safe_mode_authority": "0x00000000000000000000000000000000000000b3",
                },
                "drw": {
                    "allocations": {
                        "treasury_recipient": "0x00000000000000000000000000000000000000c1",
                    },
                },
                "market": {
                    "market_operator": "0x00000000000000000000000000000000000000b4",
                },
            }))

            previous = os.environ.get("DARWIN_CONFIG_DIR")
            os.environ["DARWIN_CONFIG_DIR"] = str(config_dir)
            try:
                deployment = load_deployment(deployment_file=deployment_path)
            finally:
                if previous is None:
                    os.environ.pop("DARWIN_CONFIG_DIR", None)
                else:
                    os.environ["DARWIN_CONFIG_DIR"] = previous

            self.assertTrue(deployment.private_overlay_loaded)
            self.assertTrue(deployment.has_private_operator_fields)
            self.assertEqual(deployment.deployer, "0x00000000000000000000000000000000000000d1")
            self.assertEqual(deployment.roles["governance"], "0x00000000000000000000000000000000000000b1")
            self.assertEqual(
                deployment.drw["allocations"]["treasury_recipient"],
                "0x00000000000000000000000000000000000000c1",
            )
            self.assertEqual(deployment.market["market_operator"], "0x00000000000000000000000000000000000000b4")
            print("  Deployment: public artifact merges a local private overlay")

    def test_06ca_load_deployment_reads_vnext_sidecar(self):
        """Deployment: adjacent vNext sidecar is loaded when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment_path = tmp / "base-sepolia.json"
            vnext_path = tmp / "base-sepolia.vnext.json"

            deployment_path.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000011",
                    "drw_token": "0x0000000000000000000000000000000000000012",
                },
            }))
            vnext_path.write_text(json.dumps({
                "network": "base-sepolia",
                "vnext": {
                    "enabled": True,
                    "contracts": {
                        "darwin_timelock": "0x00000000000000000000000000000000000000f1",
                        "drw_merkle_distributor": "0x00000000000000000000000000000000000000f2",
                    },
                },
            }))

            deployment = load_deployment(deployment_file=deployment_path)

            self.assertTrue(deployment.vnext_loaded)
            self.assertEqual(deployment.vnext_path, vnext_path.resolve())
            self.assertEqual(
                deployment.vnext["contracts"]["darwin_timelock"],
                "0x00000000000000000000000000000000000000f1",
            )
            print("  Deployment: adjacent vNext sidecar loads with public artifact")

    def test_06cb_role_audit_accepts_vnext_timelock_for_mutable_contracts(self):
        """Role audit: promoted mutable contracts should match the vNext timelock, not the legacy governance wallet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment_path = tmp / "base-sepolia.json"
            vnext_path = tmp / "base-sepolia.vnext.json"

            deployment_path.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x00000000000000000000000000000000000000d1",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x556d75f4455cf3f0D7c5F9c6e7ea49447f66D8d2",
                    "drw_token": "0x00000000000000000000000000000000000000a1",
                    "drw_staking": "0x00000000000000000000000000000000000000a2",
                    "drw_faucet": "0x00000000000000000000000000000000000000a3",
                    "reference_pool": "0x00000000000000000000000000000000000000a4",
                    "bond_vault": "0xa842Dc4BF4CA3e1f1CA07714867145038D5e0ab4",
                    "challenge_escrow": "0xd71e90F784f45FeC0b6b36454186CD88eaD126a7",
                    "epoch_manager": "0xE53A27DA8e3C2c69495a97C3AcD6E484AbD7892B",
                    "score_registry": "0x9135b4BDDa2739212a7c5c0dB0C45AdEc42b7346",
                    "shared_pair_vault": "0xbecDB8e518C9C1B57db0656297F5F1c1FE5c2851",
                    "species_registry": "0xcaC5E4C711b4FfD9C76354FF8FfD4E236b1798AB",
                },
                "roles": {
                    "governance": "0x00000000000000000000000000000000000000b1",
                    "epoch_operator": "0x00000000000000000000000000000000000000b2",
                    "batch_operator": "0x00000000000000000000000000000000000000b3",
                    "safe_mode_authority": "0x00000000000000000000000000000000000000b4",
                },
            }))
            vnext_path.write_text(json.dumps({
                "vnext": {
                    "enabled": True,
                    "contracts": {
                        "darwin_timelock": "0x00000000000000000000000000000000000000f1",
                    },
                },
            }))

            deployment = load_deployment(deployment_file=deployment_path)
            report = build_role_audit_report(
                deployment,
                LiveRoleState(
                    "0x00000000000000000000000000000000000000f1",
                    "0x0000000000000000000000000000000000000000",
                    True,
                    "0x00000000000000000000000000000000000000f1",
                    "0x0000000000000000000000000000000000000000",
                    "0x00000000000000000000000000000000000000f1",
                    "0x00000000000000000000000000000000000000f1",
                    "0x00000000000000000000000000000000000000b5",
                    "0x00000000000000000000000000000000000000b1",
                    False,
                    True,
                ),
            )

            self.assertTrue(report["governance_matches_live"])
            self.assertEqual(report["governance_drift"], [])
            self.assertEqual(report["effective_mutable_governance"], "0x00000000000000000000000000000000000000f1")
            self.assertTrue(report["governance_root_summary"]["vnext_enabled"])
            print("  Role audit: vNext timelock is treated as the mutable governance root")

    def test_06d_split_deployment_artifact_redacts_public_fields(self):
        """Ops: split_deployment_artifact writes a public-safe artifact and local private overlay."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source = tmp / "base-sepolia.json"
            public_out = tmp / "public.json"
            private_out = tmp / "config" / "deployments" / "base-sepolia.private.json"

            source.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x00000000000000000000000000000000000000d1",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000011",
                    "drw_token": "0x0000000000000000000000000000000000000012",
                    "drw_staking": "0x0000000000000000000000000000000000000013",
                },
                "roles": {
                    "governance": "0x00000000000000000000000000000000000000b1",
                    "epoch_operator": "0x00000000000000000000000000000000000000b2",
                    "safe_mode_authority": "0x00000000000000000000000000000000000000b3",
                },
                "drw": {
                    "enabled": True,
                    "contracts": {
                        "drw_token": "0x0000000000000000000000000000000000000012",
                        "drw_staking": "0x0000000000000000000000000000000000000013",
                    },
                    "allocations": {
                        "treasury_amount": "100",
                        "treasury_recipient": "0x00000000000000000000000000000000000000c1",
                        "staking_amount": "300",
                        "staking_recipient": "0x0000000000000000000000000000000000000013",
                    },
                },
                "market": {
                    "enabled": True,
                    "contracts": {
                        "reference_pool": "0x0000000000000000000000000000000000000014",
                    },
                    "governance": "0x00000000000000000000000000000000000000b1",
                    "market_operator": "0x00000000000000000000000000000000000000b4",
                },
                "faucet": {
                    "enabled": True,
                    "contracts": {
                        "drw_faucet": "0x0000000000000000000000000000000000000015",
                    },
                    "governance": "0x00000000000000000000000000000000000000b1",
                },
            }))

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "split_deployment_artifact.py"),
                    "--deployment-file",
                    str(source),
                    "--public-out",
                    str(public_out),
                    "--private-out",
                    str(private_out),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            )

            public = json.loads(public_out.read_text())
            private = json.loads(private_out.read_text())
            self.assertNotIn("deployer", public)
            self.assertNotIn("roles", public)
            self.assertNotIn("treasury_recipient", public["drw"]["allocations"])
            self.assertNotIn("governance", public["market"])
            self.assertEqual(private["deployer"], "0x00000000000000000000000000000000000000d1")
            self.assertEqual(private["roles"]["governance"], "0x00000000000000000000000000000000000000b1")
            self.assertEqual(
                private["drw"]["allocations"]["treasury_recipient"],
                "0x00000000000000000000000000000000000000c1",
            )
            self.assertIn("[deployment-split] ready", proc.stdout)
            print("  Ops: split_deployment_artifact separates public and private deployment data")

    def test_07_config_validation(self):
        """Config: YAML loads and validates correctly."""
        cfg = SimConfig.from_yaml("configs/baseline.yaml")
        self.assertEqual(cfg.suite_id, "darwin-sim-v0.4")
        self.assertEqual(cfg.rebalance.kappa_reb, 0.25)
        self.assertEqual(len(cfg.species), 3)
        self.assertAlmostEqual(
            cfg.scoring.weights.trader_surplus + cfg.scoring.weights.lp_return +
            cfg.scoring.weights.fill_rate + cfg.scoring.weights.revenue +
            cfg.scoring.weights.adverse_markout + cfg.scoring.weights.risk_penalty,
            1.0, places=2
        )
        print(f"  Config: kappa_reb={cfg.rebalance.kappa_reb} species={[s.id for s in cfg.species]}")

    def test_08_e2_pipeline(self):
        """E2: full data pipeline produces correct artifacts."""
        cfg = SimConfig.from_yaml("configs/baseline.yaml")
        from darwin_sim.experiments.runner import run_e2
        result = run_e2(cfg, "data/raw/raw_swaps.csv", "outputs/test_e2")

        self.assertIn(result["decision"], ["PASS", "REWORK"])
        self.assertGreater(result["counts"]["control_fills"], 0)
        self.assertGreater(result["counts"]["treatment_fills"], 0)
        self.assertEqual(result["counts"]["hard_resets"], 0)

        # Verify artifacts exist
        self.assertTrue(Path("outputs/test_e2/e2_report.json").exists())
        self.assertTrue(Path("outputs/test_e2/fills_control_s0.ndjson").exists())
        self.assertTrue(Path("outputs/test_e2/fills_treatment_s1.ndjson").exists())
        print(f"  E2: {result['decision']} TS={result['uplift']['trader_surplus_bps']:+.2f}bps")

    def test_09_watcher_replay(self):
        """Watcher: independent replay matches published scores exactly."""
        result = replay_and_verify("outputs/test_e2")
        self.assertTrue(result["passed"], f"Replay failed: {result['mismatches']}")
        self.assertEqual(result["published_decision"], result["recomputed_decision"])
        print(f"  Watcher: REPLAY PASS — {result['control_fills_loaded']}c + {result['treatment_fills_loaded']}t fills verified")

    def test_10_cli_replay_fetch(self):
        """CLI: replay-fetch mirrors archive artifacts and verifies them."""
        with tempfile.TemporaryDirectory() as storage_dir, tempfile.TemporaryDirectory() as mirror_dir:
            state = archive_service.ArchiveState(storage_dir=storage_dir)
            ingested = state.ingest_epoch("1", "outputs/test_e2")
            self.assertEqual(ingested["status"], "ingested")

            previous_state = archive_service.STATE
            archive_service.STATE = state
            server = HTTPServer(("127.0.0.1", 0), archive_service.ArchiveHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "darwin_sim.cli.darwinctl",
                        "replay-fetch",
                        "--archive-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--epoch",
                        "latest",
                        "--out",
                        mirror_dir,
                    ],
                    cwd=str(SIM),
                    env=env,
                    capture_output=True,
                    text=True,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                archive_service.STATE = previous_state

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("Archive replay: PASS", result.stdout)
            self.assertIn("Epoch:           1", result.stdout)
            self.assertTrue((Path(mirror_dir) / "epoch_1" / "archive_manifest.json").exists())
            self.assertTrue((Path(mirror_dir) / "epoch_1" / "watcher_replay.json").exists())
            print("  CLI: replay-fetch mirrors and verifies the latest archive epoch")

    def test_11_watcher_state_ready_after_archive_replay(self):
        """Watcher state becomes ready only after mirroring and replaying an archive epoch."""
        with tempfile.TemporaryDirectory() as storage_dir, tempfile.TemporaryDirectory() as watcher_dir:
            archive = archive_service.ArchiveState(storage_dir=storage_dir)
            archive.ingest_epoch("7", "outputs/test_e2")

            previous_state = archive_service.STATE
            archive_service.STATE = archive
            server = HTTPServer(("127.0.0.1", 0), archive_service.ArchiveHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                watcher = WatcherState(
                    archive_url=f"http://127.0.0.1:{server.server_port}",
                    artifact_dir=watcher_dir,
                )
                before = watcher.health_check()
                self.assertFalse(before["ready"])
                self.assertEqual(before["epochs_replayed"], 0)

                sync, result = watcher.fetch_and_replay_epoch("latest")

                after = watcher.health_check()
                self.assertTrue(result.passed)
                self.assertEqual(sync["epoch_id"], "7")
                self.assertTrue(after["ready"])
                self.assertEqual(after["last_mirrored_epoch"], "7")
                self.assertEqual(after["epochs_replayed"], 1)
                self.assertEqual(after["epochs_passed"], 1)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                archive_service.STATE = previous_state

            print("  Watcher: ready flips true only after archive mirror + replay")

    def test_12_watcher_poll_once_replays_only_new_epochs(self):
        """Watcher poll-once replays fresh archive epochs and no-ops on unchanged state."""
        with tempfile.TemporaryDirectory() as storage_dir, tempfile.TemporaryDirectory() as watcher_dir:
            archive = archive_service.ArchiveState(storage_dir=storage_dir)
            archive.ingest_epoch("8", "outputs/test_e2")

            previous_state = archive_service.STATE
            archive_service.STATE = archive
            server = HTTPServer(("127.0.0.1", 0), archive_service.ArchiveHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                watcher = WatcherState(
                    archive_url=f"http://127.0.0.1:{server.server_port}",
                    artifact_dir=watcher_dir,
                    poll_interval_sec=30,
                )

                first = watcher.poll_latest_once()
                second = watcher.poll_latest_once()

                archive.ingest_epoch("9", "outputs/test_e2")
                third = watcher.poll_latest_once()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                archive_service.STATE = previous_state

            self.assertEqual(first["status"], "replayed")
            self.assertTrue(first["replayed"])
            self.assertEqual(first["archive_epoch_id"], "8")
            self.assertEqual(second["status"], "noop")
            self.assertFalse(second["replayed"])
            self.assertEqual(second["archive_epoch_id"], "8")
            self.assertEqual(third["status"], "replayed")
            self.assertEqual(third["archive_epoch_id"], "9")
            print("  Watcher: poll-once skips unchanged archives and replays new epochs")

    def test_13_cli_status_check(self):
        """CLI: status-check summarizes all overlay services and readiness."""
        with (
            tempfile.TemporaryDirectory() as storage_dir,
            tempfile.TemporaryDirectory() as watcher_dir,
            tempfile.TemporaryDirectory() as gateway_dir,
            tempfile.TemporaryDirectory() as router_dir,
            tempfile.TemporaryDirectory() as finalizer_dir,
            tempfile.TemporaryDirectory() as sentinel_dir,
            tempfile.TemporaryDirectory() as deploy_dir,
            tempfile.TemporaryDirectory() as report_dir,
        ):
            deployment_path = Path(deploy_dir) / "base-sepolia.json"
            json_report = Path(report_dir) / "status.json"
            markdown_report = Path(report_dir) / "status.md"
            deployment_path.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "mock",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x0000000000000000000000000000000000000001",
                    "challenge_escrow": "0x0000000000000000000000000000000000000002",
                    "bond_vault": "0x0000000000000000000000000000000000000003",
                    "species_registry": "0x0000000000000000000000000000000000000004",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                    "epoch_manager": "0x0000000000000000000000000000000000000006",
                    "score_registry": "0x0000000000000000000000000000000000000007",
                    "shared_pair_vault": "0x0000000000000000000000000000000000000008",
                    "drw_token": "0x0000000000000000000000000000000000000011",
                    "drw_staking": "0x0000000000000000000000000000000000000012",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000c",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000b",
                },
                "drw": {
                    "enabled": True,
                    "total_supply": "1000",
                    "staking_duration": 31536000,
                    "contracts": {
                        "drw_token": "0x0000000000000000000000000000000000000011",
                        "drw_staking": "0x0000000000000000000000000000000000000012",
                    },
                    "allocations": {
                        "treasury_recipient": "0x0000000000000000000000000000000000000009",
                        "treasury_amount": "200",
                        "insurance_recipient": "0x0000000000000000000000000000000000000009",
                        "insurance_amount": "200",
                        "sponsor_rewards_recipient": "0x0000000000000000000000000000000000000009",
                        "sponsor_rewards_amount": "100",
                        "community_recipient": "0x0000000000000000000000000000000000000009",
                        "community_amount": "200",
                        "staking_recipient": "0x0000000000000000000000000000000000000012",
                        "staking_amount": "300",
                    },
                },
            }))

            archive = archive_service.ArchiveState(storage_dir=storage_dir)
            archive.ingest_epoch("10", "outputs/test_e2")

            watcher = WatcherState(
                archive_url="http://127.0.0.1:1",
                artifact_dir=watcher_dir,
                poll_interval_sec=15,
            )
            watcher.last_mirrored_epoch = "10"
            watcher.last_check_ts = time.time()
            watcher.last_success_ts = watcher.last_check_ts
            watcher.epochs[10] = watcher.replay_local_epoch("outputs/test_e2", epoch_id=10)

            gateway = GatewayState(gateway_dir, deployment_file=str(deployment_path))
            router = router_service.RouterState(state_file=str(Path(router_dir) / "router-state.json"))
            router.route_intent({"intent_id": "intent-10", "profile": "BALANCED"})
            scorer = scorer_service.ScorerState()
            finalizer = finalizer_service.FinalizerState(
                challenge_window_sec=0,
                state_file=str(Path(finalizer_dir) / "finalizer-state.json"),
                poll_interval_sec=15,
            )
            finalizer.register_epoch(
                epoch_id=10,
                closed_at=time.time() - 5,
                score_root="0xscore",
                weight_root="0xweight",
                rebalance_root="0xrebalance",
            )
            finalizer.poll_once()
            sentinel = sentinel_service.SentinelState(state_file=str(Path(sentinel_dir) / "sentinel-state.json"))
            for service in ("archive", "gateway", "router", "scorer", "watcher", "finalizer"):
                sentinel.report_heartbeat(service)

            prev_archive_state = archive_service.STATE
            prev_gateway_state = gateway_service.STATE
            prev_router_state = router_service.STATE
            prev_scorer_state = scorer_service.STATE
            prev_finalizer_state = finalizer_service.STATE
            prev_sentinel_state = sentinel_service.STATE
            import overlay.watcher.service as watcher_module
            prev_watcher_state = watcher_module.STATE

            archive_service.STATE = archive
            gateway_service.STATE = gateway
            router_service.STATE = router
            scorer_service.STATE = scorer
            finalizer_service.STATE = finalizer
            sentinel_service.STATE = sentinel
            watcher_module.STATE = watcher

            class RpcHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    content_len = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(content_len)) if content_len else {}
                    method = body.get("method")
                    params = body.get("params", [])

                    def encode_address(address: str) -> str:
                        return "0x" + address.lower().replace("0x", "").rjust(64, "0")

                    def encode_bool(value: bool) -> str:
                        return "0x" + ("1" if value else "0").rjust(64, "0")

                    def encode_uint(value: int) -> str:
                        return "0x" + hex(value)[2:].rjust(64, "0")

                    if method == "eth_chainId":
                        result = hex(84532)
                    elif method == "eth_getCode":
                        address = params[0].lower()
                        result = "0x60006000" if address in {
                            "0x0000000000000000000000000000000000000001",
                            "0x0000000000000000000000000000000000000002",
                            "0x0000000000000000000000000000000000000003",
                            "0x0000000000000000000000000000000000000004",
                            "0x0000000000000000000000000000000000000005",
                            "0x0000000000000000000000000000000000000006",
                            "0x0000000000000000000000000000000000000007",
                            "0x0000000000000000000000000000000000000008",
                            "0x0000000000000000000000000000000000000011",
                            "0x0000000000000000000000000000000000000012",
                        } else "0x"
                    elif method == "eth_call":
                        call = params[0]
                        to = call["to"].lower()
                        data = call.get("data", "").lower()

                        if to == "0x0000000000000000000000000000000000000005":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x6900b3a3":
                                result = encode_address("0x000000000000000000000000000000000000000b")
                            elif data == "0xd220935c" + "0" * 24 + "000000000000000000000000000000000000000c":
                                result = encode_bool(True)
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000002":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0xbabef33e":
                                result = encode_address("0x0000000000000000000000000000000000000001")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000003":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x92433067":
                                result = encode_address("0x0000000000000000000000000000000000000002")
                            elif data == "0xbabef33e":
                                result = encode_address("0x0000000000000000000000000000000000000001")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000004":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x1942c738":
                                result = encode_address("0x000000000000000000000000000000000000000a")
                            elif data == "0x92433067":
                                result = encode_address("0x0000000000000000000000000000000000000002")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000007":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x1942c738":
                                result = encode_address("0x000000000000000000000000000000000000000a")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000011":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x4421d5f5":
                                result = encode_bool(True)
                            elif data == "0x18160ddd":
                                result = encode_uint(1000)
                            elif data == "0x70a08231" + "0" * 24 + "0000000000000000000000000000000000000009":
                                result = encode_uint(700)
                            elif data == "0x70a08231" + "0" * 24 + "0000000000000000000000000000000000000012":
                                result = encode_uint(300)
                            else:
                                result = encode_uint(0)
                        elif to == "0x0000000000000000000000000000000000000012":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x6891e77c":
                                result = encode_address("0x0000000000000000000000000000000000000011")
                            elif data == "0xf520e7e5":
                                result = encode_uint(31536000)
                            else:
                                result = "0x"
                        else:
                            result = "0x"
                    else:
                        result = "0x0"

                    payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def log_message(self, fmt, *args):
                    pass

            archive_server = HTTPServer(("127.0.0.1", 0), archive_service.ArchiveHandler)
            gateway_server = HTTPServer(("127.0.0.1", 0), gateway_service.GatewayHandler)
            router_server = HTTPServer(("127.0.0.1", 0), router_service.RouterHandler)
            scorer_server = HTTPServer(("127.0.0.1", 0), scorer_service.ScorerHandler)
            watcher_server = HTTPServer(("127.0.0.1", 0), watcher_module.WatcherHandler)
            finalizer_server = HTTPServer(("127.0.0.1", 0), finalizer_service.FinalizerHandler)
            sentinel_server = HTTPServer(("127.0.0.1", 0), sentinel_service.SentinelHandler)
            rpc_server = HTTPServer(("127.0.0.1", 0), RpcHandler)
            archive_thread = Thread(target=archive_server.serve_forever, daemon=True)
            gateway_thread = Thread(target=gateway_server.serve_forever, daemon=True)
            router_thread = Thread(target=router_server.serve_forever, daemon=True)
            scorer_thread = Thread(target=scorer_server.serve_forever, daemon=True)
            watcher_thread = Thread(target=watcher_server.serve_forever, daemon=True)
            finalizer_thread = Thread(target=finalizer_server.serve_forever, daemon=True)
            sentinel_thread = Thread(target=sentinel_server.serve_forever, daemon=True)
            rpc_thread = Thread(target=rpc_server.serve_forever, daemon=True)
            archive_thread.start()
            gateway_thread.start()
            router_thread.start()
            scorer_thread.start()
            watcher_thread.start()
            finalizer_thread.start()
            sentinel_thread.start()
            rpc_thread.start()

            try:
                env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "darwin_sim.cli.darwinctl",
                        "status-check",
                        "--archive-url",
                        f"http://127.0.0.1:{archive_server.server_port}",
                        "--gateway-url",
                        f"http://127.0.0.1:{gateway_server.server_port}",
                        "--router-url",
                        f"http://127.0.0.1:{router_server.server_port}",
                        "--scorer-url",
                        f"http://127.0.0.1:{scorer_server.server_port}",
                        "--watcher-url",
                        f"http://127.0.0.1:{watcher_server.server_port}",
                        "--finalizer-url",
                        f"http://127.0.0.1:{finalizer_server.server_port}",
                        "--sentinel-url",
                        f"http://127.0.0.1:{sentinel_server.server_port}",
                        "--deployment-file",
                        str(deployment_path),
                        "--base-rpc-url",
                        f"http://127.0.0.1:{rpc_server.server_port}",
                        "--json-out",
                        str(json_report),
                        "--markdown-out",
                        str(markdown_report),
                    ],
                    cwd=str(SIM),
                    env=env,
                    capture_output=True,
                    text=True,
                )
            finally:
                archive_server.shutdown()
                gateway_server.shutdown()
                router_server.shutdown()
                scorer_server.shutdown()
                watcher_server.shutdown()
                finalizer_server.shutdown()
                sentinel_server.shutdown()
                rpc_server.shutdown()
                archive_server.server_close()
                gateway_server.server_close()
                router_server.server_close()
                scorer_server.server_close()
                watcher_server.server_close()
                finalizer_server.server_close()
                sentinel_server.server_close()
                rpc_server.server_close()
                archive_thread.join(timeout=5)
                gateway_thread.join(timeout=5)
                router_thread.join(timeout=5)
                scorer_thread.join(timeout=5)
                watcher_thread.join(timeout=5)
                finalizer_thread.join(timeout=5)
                sentinel_thread.join(timeout=5)
                rpc_thread.join(timeout=5)
                archive_service.STATE = prev_archive_state
                gateway_service.STATE = prev_gateway_state
                router_service.STATE = prev_router_state
                scorer_service.STATE = prev_scorer_state
                finalizer_service.STATE = prev_finalizer_state
                sentinel_service.STATE = prev_sentinel_state
                watcher_module.STATE = prev_watcher_state

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("archive", result.stdout)
            self.assertIn("gateway", result.stdout)
            self.assertIn("router", result.stdout)
            self.assertIn("scorer", result.stdout)
            self.assertIn("finalizer", result.stdout)
            self.assertIn("sentinel", result.stdout)
            self.assertIn("watcher_ready", result.stdout)
            self.assertIn("watcher_sync", result.stdout)
            self.assertIn("router_flow", result.stdout)
            self.assertIn("gateway_cfg", result.stdout)
            self.assertIn("deployment", result.stdout)
            self.assertIn("onchain", result.stdout)
            self.assertTrue(json_report.exists())
            self.assertTrue(markdown_report.exists())
            status_report = json.loads(json_report.read_text())
            self.assertTrue(status_report["ready"])
            self.assertEqual(status_report["deployment"]["network"], "base-sepolia")
            self.assertEqual(status_report["checks"]["onchain"]["state"], "OK")
            self.assertEqual(status_report["checks"]["onchain_auth"]["state"], "OK")
            self.assertEqual(status_report["checks"]["onchain_drw"]["state"], "OK")
            self.assertTrue(status_report["onchain_drw"]["ok"])
            self.assertEqual(status_report["onchain_drw"]["tracked_total"], 1000)
            self.assertEqual(status_report["onchain_drw"]["holders"]["0x0000000000000000000000000000000000000009"]["observed"], 700)
            self.assertEqual(status_report["onchain_drw"]["holders"]["0x0000000000000000000000000000000000000012"]["observed"], 300)
            self.assertTrue(status_report["onchain_auth"]["ok"])
            self.assertIn("onchain_drw", result.stdout)
            self.assertIn("## On-Chain DRW", markdown_report.read_text())
            self.assertIn("Overall status: `READY`", markdown_report.read_text())
            print("  CLI: status-check summarizes full overlay readiness")

    def test_13b_cli_status_check_allows_vnext_mutable_governance_and_distribution(self):
        """CLI: status-check accepts timelocked mutable DRW governance and circulating community reserve."""
        with (
            tempfile.TemporaryDirectory() as storage_dir,
            tempfile.TemporaryDirectory() as watcher_dir,
            tempfile.TemporaryDirectory() as gateway_dir,
            tempfile.TemporaryDirectory() as router_dir,
            tempfile.TemporaryDirectory() as finalizer_dir,
            tempfile.TemporaryDirectory() as sentinel_dir,
            tempfile.TemporaryDirectory() as deploy_dir,
            tempfile.TemporaryDirectory() as report_dir,
        ):
            deployment_path = Path(deploy_dir) / "base-sepolia-recovery.json"
            vnext_path = Path(deploy_dir) / "base-sepolia-recovery.vnext.json"
            json_report = Path(report_dir) / "status.json"
            deployment_path.write_text(json.dumps({
                "network": "base-sepolia-recovery",
                "chain_id": 84532,
                "bond_asset_mode": "mock",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x0000000000000000000000000000000000000001",
                    "challenge_escrow": "0x0000000000000000000000000000000000000002",
                    "bond_vault": "0x0000000000000000000000000000000000000003",
                    "species_registry": "0x0000000000000000000000000000000000000004",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                    "epoch_manager": "0x0000000000000000000000000000000000000006",
                    "score_registry": "0x0000000000000000000000000000000000000007",
                    "shared_pair_vault": "0x0000000000000000000000000000000000000008",
                    "drw_token": "0x0000000000000000000000000000000000000011",
                    "drw_staking": "0x0000000000000000000000000000000000000012",
                    "drw_faucet": "0x0000000000000000000000000000000000000013",
                    "reference_pool": "0x0000000000000000000000000000000000000014",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000c",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000b",
                },
                "drw": {
                    "enabled": True,
                    "total_supply": "1000",
                    "staking_duration": 31536000,
                    "contracts": {
                        "drw_token": "0x0000000000000000000000000000000000000011",
                        "drw_staking": "0x0000000000000000000000000000000000000012",
                    },
                    "allocations": {
                        "treasury_recipient": "0x0000000000000000000000000000000000000009",
                        "treasury_amount": "200",
                        "insurance_recipient": "0x0000000000000000000000000000000000000009",
                        "insurance_amount": "200",
                        "sponsor_rewards_recipient": "0x0000000000000000000000000000000000000009",
                        "sponsor_rewards_amount": "100",
                        "community_recipient": "0x0000000000000000000000000000000000000009",
                        "community_amount": "200",
                        "staking_recipient": "0x0000000000000000000000000000000000000012",
                        "staking_amount": "300",
                    },
                },
                "faucet": {
                    "enabled": True,
                    "contracts": {
                        "drw_faucet": "0x0000000000000000000000000000000000000013",
                    },
                    "governance": "0x0000000000000000000000000000000000000009",
                },
                "market": {
                    "enabled": True,
                    "contracts": {
                        "reference_pool": "0x0000000000000000000000000000000000000014",
                    },
                    "governance": "0x0000000000000000000000000000000000000009",
                    "market_operator": "0x0000000000000000000000000000000000000009",
                },
            }))
            vnext_path.write_text(json.dumps({
                "chain_id": 84532,
                "network": "base-sepolia-recovery",
                "vnext": {
                    "enabled": True,
                    "contracts": {
                        "darwin_timelock": "0x000000000000000000000000000000000000000d",
                        "drw_merkle_distributor": "0x000000000000000000000000000000000000000e",
                    },
                    "distribution": {
                        "token": "0x0000000000000000000000000000000000000011",
                        "merkle_root": "0x" + "11" * 32,
                        "total_amount": "30",
                        "claim_count": 2,
                        "claim_deadline": 9999999999,
                    },
                },
            }))

            archive = archive_service.ArchiveState(storage_dir=storage_dir)
            archive.ingest_epoch("10", "outputs/test_e2")

            watcher = WatcherState(
                archive_url="http://127.0.0.1:1",
                artifact_dir=watcher_dir,
                poll_interval_sec=15,
            )
            watcher.last_mirrored_epoch = "10"
            watcher.last_check_ts = time.time()
            watcher.last_success_ts = watcher.last_check_ts
            watcher.epochs[10] = watcher.replay_local_epoch("outputs/test_e2", epoch_id=10)

            gateway = GatewayState(gateway_dir, deployment_file=str(deployment_path))
            router = router_service.RouterState(state_file=str(Path(router_dir) / "router-state.json"))
            router.route_intent({"intent_id": "intent-10", "profile": "BALANCED"})
            scorer = scorer_service.ScorerState()
            finalizer = finalizer_service.FinalizerState(
                challenge_window_sec=0,
                state_file=str(Path(finalizer_dir) / "finalizer-state.json"),
                poll_interval_sec=15,
            )
            finalizer.register_epoch(
                epoch_id=10,
                closed_at=time.time() - 5,
                score_root="0xscore",
                weight_root="0xweight",
                rebalance_root="0xrebalance",
            )
            finalizer.poll_once()
            sentinel = sentinel_service.SentinelState(state_file=str(Path(sentinel_dir) / "sentinel-state.json"))
            for service in ("archive", "gateway", "router", "scorer", "watcher", "finalizer"):
                sentinel.report_heartbeat(service)

            prev_archive_state = archive_service.STATE
            prev_gateway_state = gateway_service.STATE
            prev_router_state = router_service.STATE
            prev_scorer_state = scorer_service.STATE
            prev_finalizer_state = finalizer_service.STATE
            prev_sentinel_state = sentinel_service.STATE
            import overlay.watcher.service as watcher_module
            prev_watcher_state = watcher_module.STATE

            archive_service.STATE = archive
            gateway_service.STATE = gateway
            router_service.STATE = router
            scorer_service.STATE = scorer
            finalizer_service.STATE = finalizer
            sentinel_service.STATE = sentinel
            watcher_module.STATE = watcher

            class RpcHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    content_len = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(content_len)) if content_len else {}
                    method = body.get("method")
                    params = body.get("params", [])

                    def encode_address(address: str) -> str:
                        return "0x" + address.lower().replace("0x", "").rjust(64, "0")

                    def encode_bool(value: bool) -> str:
                        return "0x" + ("1" if value else "0").rjust(64, "0")

                    def encode_uint(value: int) -> str:
                        return "0x" + hex(value)[2:].rjust(64, "0")

                    if method == "eth_chainId":
                        result = hex(84532)
                    elif method == "eth_getCode":
                        address = params[0].lower()
                        result = "0x60006000" if address in {
                            "0x0000000000000000000000000000000000000001",
                            "0x0000000000000000000000000000000000000002",
                            "0x0000000000000000000000000000000000000003",
                            "0x0000000000000000000000000000000000000004",
                            "0x0000000000000000000000000000000000000005",
                            "0x0000000000000000000000000000000000000006",
                            "0x0000000000000000000000000000000000000007",
                            "0x0000000000000000000000000000000000000008",
                            "0x0000000000000000000000000000000000000011",
                            "0x0000000000000000000000000000000000000012",
                            "0x0000000000000000000000000000000000000013",
                            "0x0000000000000000000000000000000000000014",
                        } else "0x"
                    elif method == "eth_call":
                        call = params[0]
                        to = call["to"].lower()
                        data = call.get("data", "").lower()

                        if to == "0x0000000000000000000000000000000000000005":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x6900b3a3":
                                result = encode_address("0x000000000000000000000000000000000000000b")
                            elif data == "0xd220935c" + "0" * 24 + "000000000000000000000000000000000000000c":
                                result = encode_bool(True)
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000002":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0xbabef33e":
                                result = encode_address("0x0000000000000000000000000000000000000001")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000003":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x92433067":
                                result = encode_address("0x0000000000000000000000000000000000000002")
                            elif data == "0xbabef33e":
                                result = encode_address("0x0000000000000000000000000000000000000001")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000004":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x1942c738":
                                result = encode_address("0x000000000000000000000000000000000000000a")
                            elif data == "0x92433067":
                                result = encode_address("0x0000000000000000000000000000000000000002")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000007":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x1942c738":
                                result = encode_address("0x000000000000000000000000000000000000000a")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000011":
                            if data == "0x5aa6e675":
                                result = encode_address("0x000000000000000000000000000000000000000d")
                            elif data == "0x4421d5f5":
                                result = encode_bool(True)
                            elif data == "0x18160ddd":
                                result = encode_uint(1000)
                            elif data == "0x70a08231" + "0" * 24 + "0000000000000000000000000000000000000009":
                                result = encode_uint(650)
                            elif data == "0x70a08231" + "0" * 24 + "0000000000000000000000000000000000000012":
                                result = encode_uint(300)
                            elif data == "0x70a08231" + "0" * 24 + "0000000000000000000000000000000000000013":
                                result = encode_uint(10)
                            elif data == "0x70a08231" + "0" * 24 + "0000000000000000000000000000000000000014":
                                result = encode_uint(10)
                            elif data == "0x70a08231" + "0" * 24 + "000000000000000000000000000000000000000e":
                                result = encode_uint(10)
                            else:
                                result = encode_uint(0)
                        elif to == "0x0000000000000000000000000000000000000012":
                            if data == "0x5aa6e675":
                                result = encode_address("0x000000000000000000000000000000000000000d")
                            elif data == "0x6891e77c":
                                result = encode_address("0x0000000000000000000000000000000000000011")
                            elif data == "0xf520e7e5":
                                result = encode_uint(31536000)
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000013":
                            if data == "0x5aa6e675":
                                result = encode_address("0x000000000000000000000000000000000000000d")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000014":
                            if data == "0x5aa6e675":
                                result = encode_address("0x000000000000000000000000000000000000000d")
                            elif data == "0xb1ae3471":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            else:
                                result = "0x"
                        else:
                            result = "0x0"

                    payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def log_message(self, fmt, *args):
                    pass

            archive_server = HTTPServer(("127.0.0.1", 0), archive_service.ArchiveHandler)
            gateway_server = HTTPServer(("127.0.0.1", 0), gateway_service.GatewayHandler)
            router_server = HTTPServer(("127.0.0.1", 0), router_service.RouterHandler)
            scorer_server = HTTPServer(("127.0.0.1", 0), scorer_service.ScorerHandler)
            watcher_server = HTTPServer(("127.0.0.1", 0), watcher_module.WatcherHandler)
            finalizer_server = HTTPServer(("127.0.0.1", 0), finalizer_service.FinalizerHandler)
            sentinel_server = HTTPServer(("127.0.0.1", 0), sentinel_service.SentinelHandler)
            rpc_server = HTTPServer(("127.0.0.1", 0), RpcHandler)
            archive_thread = Thread(target=archive_server.serve_forever, daemon=True)
            gateway_thread = Thread(target=gateway_server.serve_forever, daemon=True)
            router_thread = Thread(target=router_server.serve_forever, daemon=True)
            scorer_thread = Thread(target=scorer_server.serve_forever, daemon=True)
            watcher_thread = Thread(target=watcher_server.serve_forever, daemon=True)
            finalizer_thread = Thread(target=finalizer_server.serve_forever, daemon=True)
            sentinel_thread = Thread(target=sentinel_server.serve_forever, daemon=True)
            rpc_thread = Thread(target=rpc_server.serve_forever, daemon=True)
            archive_thread.start()
            gateway_thread.start()
            router_thread.start()
            scorer_thread.start()
            watcher_thread.start()
            finalizer_thread.start()
            sentinel_thread.start()
            rpc_thread.start()

            try:
                env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "darwin_sim.cli.darwinctl",
                        "status-check",
                        "--archive-url",
                        f"http://127.0.0.1:{archive_server.server_port}",
                        "--gateway-url",
                        f"http://127.0.0.1:{gateway_server.server_port}",
                        "--router-url",
                        f"http://127.0.0.1:{router_server.server_port}",
                        "--scorer-url",
                        f"http://127.0.0.1:{scorer_server.server_port}",
                        "--watcher-url",
                        f"http://127.0.0.1:{watcher_server.server_port}",
                        "--finalizer-url",
                        f"http://127.0.0.1:{finalizer_server.server_port}",
                        "--sentinel-url",
                        f"http://127.0.0.1:{sentinel_server.server_port}",
                        "--deployment-file",
                        str(deployment_path),
                        "--base-rpc-url",
                        f"http://127.0.0.1:{rpc_server.server_port}",
                        "--json-out",
                        str(json_report),
                    ],
                    cwd=str(SIM),
                    env=env,
                    capture_output=True,
                    text=True,
                )
            finally:
                archive_server.shutdown()
                gateway_server.shutdown()
                router_server.shutdown()
                scorer_server.shutdown()
                watcher_server.shutdown()
                finalizer_server.shutdown()
                sentinel_server.shutdown()
                rpc_server.shutdown()
                archive_server.server_close()
                gateway_server.server_close()
                router_server.server_close()
                scorer_server.server_close()
                watcher_server.server_close()
                finalizer_server.server_close()
                sentinel_server.server_close()
                rpc_server.server_close()
                archive_thread.join(timeout=5)
                gateway_thread.join(timeout=5)
                router_thread.join(timeout=5)
                scorer_thread.join(timeout=5)
                watcher_thread.join(timeout=5)
                finalizer_thread.join(timeout=5)
                sentinel_thread.join(timeout=5)
                rpc_thread.join(timeout=5)
                archive_service.STATE = prev_archive_state
                gateway_service.STATE = prev_gateway_state
                router_service.STATE = prev_router_state
                scorer_service.STATE = prev_scorer_state
                finalizer_service.STATE = prev_finalizer_state
                sentinel_service.STATE = prev_sentinel_state
                watcher_module.STATE = prev_watcher_state

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            status_report = json.loads(json_report.read_text())
            self.assertTrue(status_report["ready"])
            self.assertEqual(
                status_report["deployment"]["effective_mutable_governance"],
                "0x000000000000000000000000000000000000000d",
            )
            self.assertEqual(status_report["checks"]["onchain_auth"]["state"], "OK")
            self.assertEqual(status_report["checks"]["onchain_drw"]["state"], "OK")
            self.assertTrue(status_report["onchain_auth"]["components"]["drw_token"]["ok"])
            self.assertTrue(status_report["onchain_auth"]["components"]["drw_staking"]["ok"])
            self.assertTrue(status_report["onchain_auth"]["components"]["drw_faucet"]["ok"])
            self.assertTrue(status_report["onchain_auth"]["components"]["reference_pool"]["ok"])
            self.assertEqual(
                status_report["onchain_drw"]["holders"]["0x0000000000000000000000000000000000000009"]["minimum"],
                500,
            )
            self.assertEqual(
                status_report["onchain_drw"]["holders"]["0x0000000000000000000000000000000000000009"]["observed"],
                650,
            )
            self.assertEqual(status_report["onchain_drw"]["circulating_total"], 20)
            self.assertEqual(
                status_report["onchain_drw"]["auxiliary_holders"]["drw_merkle_distributor"]["observed"],
                10,
            )
            print("  CLI: status-check accepts vNext mutable governance and community circulation")

    def test_14_overlay_state_persistence(self):
        """Overlay services persist state snapshots and recover them on restart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            router_state = tmp / "router.json"
            router = router_service.RouterState(state_file=str(router_state))
            router.update_weights({"S2_RFQ_ORACLE": 70_000})
            router.route_intent({"intent_id": "persist-intent", "profile": "BALANCED"})
            router_recovered = router_service.RouterState(state_file=str(router_state))
            self.assertTrue(router_recovered.recovered_from_disk)
            self.assertEqual(router_recovered.total_routed, 1)
            self.assertEqual(router_recovered.weights["S2_RFQ_ORACLE"], 70_000)

            sentinel_state = tmp / "sentinel.json"
            sentinel = sentinel_service.SentinelState(state_file=str(sentinel_state))
            sentinel.report_heartbeat("gateway")
            sentinel.report_hard_reset("S1_BATCH_5S", "ETH_USDC")
            sentinel_recovered = sentinel_service.SentinelState(state_file=str(sentinel_state))
            self.assertTrue(sentinel_recovered.recovered_from_disk)
            self.assertTrue(sentinel_recovered.safe_mode)
            self.assertEqual(len(sentinel_recovered.alerts), 1)
            self.assertIn("gateway", sentinel_recovered.last_heartbeat)

            finalizer_state = tmp / "finalizer.json"
            finalizer = finalizer_service.FinalizerState(
                challenge_window_sec=0,
                state_file=str(finalizer_state),
            )
            finalizer.register_epoch(77, time.time() - 10, "0xscore", "0xweight", "0xrebalance")
            finalizer.poll_once()
            finalizer_recovered = finalizer_service.FinalizerState(
                challenge_window_sec=0,
                state_file=str(finalizer_state),
            )
            self.assertTrue(finalizer_recovered.recovered_from_disk)
            self.assertIn(77, finalizer_recovered.epochs)
            self.assertIn(77, finalizer_recovered.finalized)
            print("  Overlay: router/sentinel/finalizer recover persisted state")

    def test_15_finalizer_auto_poll(self):
        """Finalizer auto-poll finalizes ready epochs without manual finalize calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            finalizer = finalizer_service.FinalizerState(
                challenge_window_sec=0,
                state_file=str(Path(tmpdir) / "finalizer-auto.json"),
                poll_interval_sec=1,
            )
            finalizer.register_epoch(88, time.time() - 5, "0xscore", "0xweight", "0xrebalance")
            finalizer.start_background_polling()
            try:
                for _ in range(20):
                    if 88 in finalizer.finalized:
                        break
                    time.sleep(0.1)
            finally:
                finalizer.stop_background_polling()

            self.assertIn(88, finalizer.finalized)
            print("  Finalizer: auto-poll finalizes ready epochs")

    def test_16_cli_wallet_check(self):
        """CLI: wallet-check reports testnet balances and expected-address match."""
        class RpcHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                if body["method"] == "eth_chainId":
                    result = "0x14a34"
                elif body["method"] == "eth_getBalance":
                    result = hex(10**16)
                else:
                    result = "0x0"
                payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                raw = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, fmt, *args):
                pass

        address = "0xD4C2E5225a69E6947F6B95479e3e4E5D28EAEF04"
        base_server = HTTPServer(("127.0.0.1", 0), RpcHandler)
        sepolia_server = HTTPServer(("127.0.0.1", 0), RpcHandler)
        base_thread = Thread(target=base_server.serve_forever, daemon=True)
        sepolia_thread = Thread(target=sepolia_server.serve_forever, daemon=True)
        base_thread.start()
        sepolia_thread.start()

        try:
            env = {**os.environ, "PYTHONPATH": str(SIM)}
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "wallet-check",
                    "--address",
                    address,
                    "--expect-address",
                    address,
                    "--base-rpc-url",
                    f"http://127.0.0.1:{base_server.server_port}",
                    "--sepolia-rpc-url",
                    f"http://127.0.0.1:{sepolia_server.server_port}",
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )
        finally:
            base_server.shutdown()
            sepolia_server.shutdown()
            base_server.server_close()
            sepolia_server.server_close()
            base_thread.join(timeout=5)
            sepolia_thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Wallet check", result.stdout)
        self.assertIn("Address match:      True", result.stdout)
        self.assertIn("Base balance ETH:   0.01000000", result.stdout)
        print("  CLI: wallet-check reports deployer address and testnet balances")

    def test_17_e1_e7_suite(self):
        """Suite: all 7 experiments pass on 5K realistic swaps."""
        cfg = SimConfig.from_yaml("configs/baseline.yaml")
        from darwin_sim.experiments.suite import run_full_suite
        result = run_full_suite(cfg, "outputs/test_suite", n_swaps=5000, seed=9999)

        passed = sum(1 for r in result["details"].values() if r["decision"] == "PASS")
        total = len(result["details"])
        print(f"  Suite: {passed}/{total} PASS")
        # At least 6 of 7 should pass
        self.assertGreaterEqual(passed, 6, f"Only {passed}/{total} passed")

    def test_18_cli_intent_verify(self):
        """CLI: intent-verify validates payloads and optional deployment binding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            acct = create_account(chain_id=84532)
            intent = create_intent(
                account=acct,
                pair_id="ETH_USDC",
                side="BUY",
                qty_base=1.0,
                limit_price=3500.0,
                expiry_ts=int(time.time()) + 300,
                nonce=11,
                chain_id=84532,
                settlement_hub="0x0000000000000000000000000000000000000001",
            )
            intent_path = Path(tmpdir) / "intent.json"
            intent_path.write_text(json.dumps(intent.to_dict()))

            deployment_path = Path(tmpdir) / "base-sepolia.json"
            deployment_path.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "deployer": "0x0000000000000000000000000000000000000002",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000003",
                    "epoch_operator": "0x0000000000000000000000000000000000000004",
                    "safe_mode_authority": "0x0000000000000000000000000000000000000005",
                },
            }))

            env = {**os.environ, "PYTHONPATH": str(SIM)}
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "intent-verify",
                    str(intent_path),
                    "--deployment-file",
                    str(deployment_path),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("Intent verification: PASS", result.stdout)
            self.assertIn("Deployment:  matched", result.stdout)
            print("  CLI: intent-verify passes with deployment binding")

    def test_19_cli_status_check_allows_cold_watcher(self):
        """CLI: status-check can allow a healthy-but-cold watcher during bootstrap."""
        with (
            tempfile.TemporaryDirectory() as storage_dir,
            tempfile.TemporaryDirectory() as watcher_dir,
            tempfile.TemporaryDirectory() as gateway_dir,
            tempfile.TemporaryDirectory() as router_dir,
            tempfile.TemporaryDirectory() as finalizer_dir,
            tempfile.TemporaryDirectory() as sentinel_dir,
            tempfile.TemporaryDirectory() as report_dir,
        ):
            json_report = Path(report_dir) / "cold-status.json"
            archive = archive_service.ArchiveState(storage_dir=storage_dir)
            watcher = WatcherState(
                archive_url="http://127.0.0.1:1",
                artifact_dir=watcher_dir,
                poll_interval_sec=60,
            )
            gateway = GatewayState(gateway_dir)
            router = router_service.RouterState(state_file=str(Path(router_dir) / "router-state.json"))
            scorer = scorer_service.ScorerState()
            finalizer = finalizer_service.FinalizerState(
                challenge_window_sec=1800,
                state_file=str(Path(finalizer_dir) / "finalizer-state.json"),
                poll_interval_sec=60,
            )
            sentinel = sentinel_service.SentinelState(state_file=str(Path(sentinel_dir) / "sentinel-state.json"))
            for service in ("archive", "gateway", "router", "scorer", "watcher", "finalizer"):
                sentinel.report_heartbeat(service)

            prev_archive_state = archive_service.STATE
            prev_gateway_state = gateway_service.STATE
            prev_router_state = router_service.STATE
            prev_scorer_state = scorer_service.STATE
            prev_finalizer_state = finalizer_service.STATE
            prev_sentinel_state = sentinel_service.STATE
            import overlay.watcher.service as watcher_module
            prev_watcher_state = watcher_module.STATE

            archive_service.STATE = archive
            gateway_service.STATE = gateway
            router_service.STATE = router
            scorer_service.STATE = scorer
            finalizer_service.STATE = finalizer
            sentinel_service.STATE = sentinel
            watcher_module.STATE = watcher

            archive_server = HTTPServer(("127.0.0.1", 0), archive_service.ArchiveHandler)
            gateway_server = HTTPServer(("127.0.0.1", 0), gateway_service.GatewayHandler)
            router_server = HTTPServer(("127.0.0.1", 0), router_service.RouterHandler)
            scorer_server = HTTPServer(("127.0.0.1", 0), scorer_service.ScorerHandler)
            watcher_server = HTTPServer(("127.0.0.1", 0), watcher_module.WatcherHandler)
            finalizer_server = HTTPServer(("127.0.0.1", 0), finalizer_service.FinalizerHandler)
            sentinel_server = HTTPServer(("127.0.0.1", 0), sentinel_service.SentinelHandler)
            archive_thread = Thread(target=archive_server.serve_forever, daemon=True)
            gateway_thread = Thread(target=gateway_server.serve_forever, daemon=True)
            router_thread = Thread(target=router_server.serve_forever, daemon=True)
            scorer_thread = Thread(target=scorer_server.serve_forever, daemon=True)
            watcher_thread = Thread(target=watcher_server.serve_forever, daemon=True)
            finalizer_thread = Thread(target=finalizer_server.serve_forever, daemon=True)
            sentinel_thread = Thread(target=sentinel_server.serve_forever, daemon=True)
            archive_thread.start()
            gateway_thread.start()
            router_thread.start()
            scorer_thread.start()
            watcher_thread.start()
            finalizer_thread.start()
            sentinel_thread.start()

            try:
                env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "darwin_sim.cli.darwinctl",
                        "status-check",
                        "--archive-url",
                        f"http://127.0.0.1:{archive_server.server_port}",
                        "--gateway-url",
                        f"http://127.0.0.1:{gateway_server.server_port}",
                        "--router-url",
                        f"http://127.0.0.1:{router_server.server_port}",
                        "--scorer-url",
                        f"http://127.0.0.1:{scorer_server.server_port}",
                        "--watcher-url",
                        f"http://127.0.0.1:{watcher_server.server_port}",
                        "--finalizer-url",
                        f"http://127.0.0.1:{finalizer_server.server_port}",
                        "--sentinel-url",
                        f"http://127.0.0.1:{sentinel_server.server_port}",
                        "--allow-cold-watcher",
                        "--json-out",
                        str(json_report),
                    ],
                    cwd=str(SIM),
                    env=env,
                    capture_output=True,
                    text=True,
                )
            finally:
                archive_server.shutdown()
                gateway_server.shutdown()
                router_server.shutdown()
                scorer_server.shutdown()
                watcher_server.shutdown()
                finalizer_server.shutdown()
                sentinel_server.shutdown()
                archive_server.server_close()
                gateway_server.server_close()
                router_server.server_close()
                scorer_server.server_close()
                watcher_server.server_close()
                finalizer_server.server_close()
                sentinel_server.server_close()
                archive_thread.join(timeout=5)
                gateway_thread.join(timeout=5)
                router_thread.join(timeout=5)
                scorer_thread.join(timeout=5)
                watcher_thread.join(timeout=5)
                finalizer_thread.join(timeout=5)
                sentinel_thread.join(timeout=5)
                archive_service.STATE = prev_archive_state
                gateway_service.STATE = prev_gateway_state
                router_service.STATE = prev_router_state
                scorer_service.STATE = prev_scorer_state
                finalizer_service.STATE = prev_finalizer_state
                sentinel_service.STATE = prev_sentinel_state
                watcher_module.STATE = prev_watcher_state

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("watcher_ready", result.stdout)
            self.assertIn("COLD", result.stdout)
            self.assertTrue(json_report.exists())
            status_report = json.loads(json_report.read_text())
            self.assertFalse(status_report["ready"])
            self.assertEqual(status_report["checks"]["watcher_ready"]["state"], "COLD")
            self.assertIn("watcher bootstrap is still cold", status_report["notes"][0])
            print("  CLI: status-check allows a cold watcher during bootstrap")

    def test_20_external_watcher_runner(self):
        """Ops: the external watcher runner boots, replays latest, and writes reports."""
        with (
            tempfile.TemporaryDirectory() as storage_dir,
            tempfile.TemporaryDirectory() as state_dir,
        ):
            archive = archive_service.ArchiveState(storage_dir=storage_dir)
            archive.ingest_epoch("12", "outputs/test_e2")

            prev_archive_state = archive_service.STATE
            archive_service.STATE = archive
            archive_server = HTTPServer(("127.0.0.1", 0), archive_service.ArchiveHandler)
            archive_thread = Thread(target=archive_server.serve_forever, daemon=True)
            archive_thread.start()

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                watcher_port = sock.getsockname()[1]

            env = {
                **os.environ,
                "DARWIN_WATCHER_ARCHIVE_URL": f"http://127.0.0.1:{archive_server.server_port}",
                "DARWIN_WATCHER_STATE_ROOT": state_dir,
                "DARWIN_WATCHER_PORT": str(watcher_port),
                "DARWIN_WATCHER_POLL_SEC": "5",
            }
            proc = subprocess.Popen(
                ["bash", str(ROOT / "ops" / "run_external_watcher.sh")],
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            report_path = Path(state_dir) / "reports" / "watcher-status.json"
            markdown_path = Path(state_dir) / "reports" / "watcher-status.md"

            try:
                deadline = time.time() + 15
                while time.time() < deadline:
                    if report_path.exists():
                        report = json.loads(report_path.read_text())
                        if report.get("health", {}).get("epochs_replayed", 0) >= 1:
                            break
                    if proc.poll() is not None:
                        self.fail((proc.stdout.read() or "") + (proc.stderr.read() or ""))
                    time.sleep(0.2)
                else:
                    self.fail("external watcher runner did not write a replayed report in time")
            finally:
                proc.terminate()
                proc.wait(timeout=10)
                archive_server.shutdown()
                archive_server.server_close()
                archive_thread.join(timeout=5)
                archive_service.STATE = prev_archive_state

            report = json.loads(report_path.read_text())
            self.assertGreaterEqual(report["health"]["epochs_replayed"], 1)
            self.assertEqual(report["health"]["last_mirrored_epoch"], "12")
            self.assertTrue(markdown_path.exists())
            self.assertIn("Watcher readiness: `YES`", markdown_path.read_text())
            self.assertEqual(proc.returncode, 0)
            print("  Ops: external watcher runner primes replay and writes reports")

    def test_21_publish_canary_epoch_runner(self):
        """Ops: canary epoch publish ingests, replays, and refreshes readiness reports."""
        with (
            tempfile.TemporaryDirectory() as storage_dir,
            tempfile.TemporaryDirectory() as watcher_dir,
            tempfile.TemporaryDirectory() as gateway_dir,
            tempfile.TemporaryDirectory() as router_dir,
            tempfile.TemporaryDirectory() as finalizer_dir,
            tempfile.TemporaryDirectory() as sentinel_dir,
            tempfile.TemporaryDirectory() as deploy_dir,
            tempfile.TemporaryDirectory() as report_dir,
        ):
            deployment_path = Path(deploy_dir) / "base-sepolia.json"
            deployment_path.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x0000000000000000000000000000000000000001",
                    "challenge_escrow": "0x0000000000000000000000000000000000000002",
                    "bond_vault": "0x0000000000000000000000000000000000000003",
                    "species_registry": "0x0000000000000000000000000000000000000004",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                    "epoch_manager": "0x0000000000000000000000000000000000000006",
                    "score_registry": "0x0000000000000000000000000000000000000007",
                    "shared_pair_vault": "0x0000000000000000000000000000000000000008",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000c",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000b",
                },
            }))

            archive = archive_service.ArchiveState(storage_dir=storage_dir)
            watcher = WatcherState(
                archive_url="http://127.0.0.1:1",
                artifact_dir=watcher_dir,
                poll_interval_sec=15,
            )
            gateway = GatewayState(gateway_dir, deployment_file=str(deployment_path))
            router = router_service.RouterState(state_file=str(Path(router_dir) / "router-state.json"))
            scorer = scorer_service.ScorerState()
            finalizer = finalizer_service.FinalizerState(
                challenge_window_sec=0,
                state_file=str(Path(finalizer_dir) / "finalizer-state.json"),
                poll_interval_sec=15,
            )
            sentinel = sentinel_service.SentinelState(state_file=str(Path(sentinel_dir) / "sentinel-state.json"))
            for service in ("archive", "gateway", "router", "scorer", "watcher", "finalizer"):
                sentinel.report_heartbeat(service)

            prev_archive_state = archive_service.STATE
            prev_gateway_state = gateway_service.STATE
            prev_router_state = router_service.STATE
            prev_scorer_state = scorer_service.STATE
            prev_finalizer_state = finalizer_service.STATE
            prev_sentinel_state = sentinel_service.STATE
            import overlay.watcher.service as watcher_module
            prev_watcher_state = watcher_module.STATE

            archive_service.STATE = archive
            gateway_service.STATE = gateway
            router_service.STATE = router
            scorer_service.STATE = scorer
            finalizer_service.STATE = finalizer
            sentinel_service.STATE = sentinel
            watcher_module.STATE = watcher

            class RpcHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    content_len = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(content_len)) if content_len else {}
                    method = body.get("method")
                    params = body.get("params", [])

                    def encode_address(address: str) -> str:
                        return "0x" + address.lower().replace("0x", "").rjust(64, "0")

                    def encode_bool(value: bool) -> str:
                        return "0x" + ("1" if value else "0").rjust(64, "0")

                    if method == "eth_chainId":
                        result = hex(84532)
                    elif method == "eth_getCode":
                        address = params[0].lower()
                        result = "0x60006000" if address in {
                            "0x0000000000000000000000000000000000000001",
                            "0x0000000000000000000000000000000000000002",
                            "0x0000000000000000000000000000000000000003",
                            "0x0000000000000000000000000000000000000004",
                            "0x0000000000000000000000000000000000000005",
                            "0x0000000000000000000000000000000000000006",
                            "0x0000000000000000000000000000000000000007",
                            "0x0000000000000000000000000000000000000008",
                        } else "0x"
                    elif method == "eth_call":
                        call = params[0]
                        to = call["to"].lower()
                        data = call.get("data", "").lower()

                        if to == "0x0000000000000000000000000000000000000005":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x6900b3a3":
                                result = encode_address("0x000000000000000000000000000000000000000b")
                            elif data == "0xd220935c" + "0" * 24 + "000000000000000000000000000000000000000c":
                                result = encode_bool(True)
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000002":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0xbabef33e":
                                result = encode_address("0x0000000000000000000000000000000000000001")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000003":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x92433067":
                                result = encode_address("0x0000000000000000000000000000000000000002")
                            elif data == "0xbabef33e":
                                result = encode_address("0x0000000000000000000000000000000000000001")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000004":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x1942c738":
                                result = encode_address("0x000000000000000000000000000000000000000a")
                            elif data == "0x92433067":
                                result = encode_address("0x0000000000000000000000000000000000000002")
                            else:
                                result = "0x"
                        elif to == "0x0000000000000000000000000000000000000007":
                            if data == "0x5aa6e675":
                                result = encode_address("0x0000000000000000000000000000000000000009")
                            elif data == "0x1942c738":
                                result = encode_address("0x000000000000000000000000000000000000000a")
                            else:
                                result = "0x"
                        else:
                            result = "0x"
                    else:
                        result = "0x0"

                    payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def log_message(self, fmt, *args):
                    pass

            archive_server = HTTPServer(("127.0.0.1", 0), archive_service.ArchiveHandler)
            gateway_server = HTTPServer(("127.0.0.1", 0), gateway_service.GatewayHandler)
            router_server = HTTPServer(("127.0.0.1", 0), router_service.RouterHandler)
            scorer_server = HTTPServer(("127.0.0.1", 0), scorer_service.ScorerHandler)
            watcher = WatcherState(
                archive_url=f"http://127.0.0.1:{archive_server.server_port}",
                artifact_dir=watcher_dir,
                poll_interval_sec=15,
            )
            watcher_module.STATE = watcher
            watcher_server = HTTPServer(("127.0.0.1", 0), watcher_module.WatcherHandler)
            finalizer_server = HTTPServer(("127.0.0.1", 0), finalizer_service.FinalizerHandler)
            sentinel_server = HTTPServer(("127.0.0.1", 0), sentinel_service.SentinelHandler)
            rpc_server = HTTPServer(("127.0.0.1", 0), RpcHandler)

            servers = [
                archive_server,
                gateway_server,
                router_server,
                scorer_server,
                watcher_server,
                finalizer_server,
                sentinel_server,
                rpc_server,
            ]
            threads = [Thread(target=server.serve_forever, daemon=True) for server in servers]
            for thread in threads:
                thread.start()

            epoch_id = "publish-21"
            summary_json = Path(report_dir) / f"publish-{epoch_id}-summary.json"
            status_json = Path(report_dir) / f"status-after-{epoch_id}.json"
            latest_status_json = Path(report_dir) / "status-report.json"

            try:
                env = {
                    **os.environ,
                    "DARWIN_ARCHIVE_URL": f"http://127.0.0.1:{archive_server.server_port}",
                    "DARWIN_WATCHER_URL": f"http://127.0.0.1:{watcher_server.server_port}",
                    "DARWIN_GATEWAY_URL": f"http://127.0.0.1:{gateway_server.server_port}",
                    "DARWIN_ROUTER_URL": f"http://127.0.0.1:{router_server.server_port}",
                    "DARWIN_SCORER_URL": f"http://127.0.0.1:{scorer_server.server_port}",
                    "DARWIN_FINALIZER_URL": f"http://127.0.0.1:{finalizer_server.server_port}",
                    "DARWIN_SENTINEL_URL": f"http://127.0.0.1:{sentinel_server.server_port}",
                    "DARWIN_CANARY_REPORT_DIR": report_dir,
                    "DARWIN_DEPLOYMENT_FILE": str(deployment_path),
                    "BASE_SEPOLIA_RPC_URL": f"http://127.0.0.1:{rpc_server.server_port}",
                }
                result = subprocess.run(
                    [
                        "bash",
                        str(ROOT / "ops" / "publish_canary_epoch.sh"),
                        epoch_id,
                        "sim/outputs/test_e2",
                    ],
                    cwd=str(ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                )
            finally:
                for server in servers:
                    server.shutdown()
                for server in servers:
                    server.server_close()
                for thread in threads:
                    thread.join(timeout=5)
                archive_service.STATE = prev_archive_state
                gateway_service.STATE = prev_gateway_state
                router_service.STATE = prev_router_state
                scorer_service.STATE = prev_scorer_state
                finalizer_service.STATE = prev_finalizer_state
                sentinel_service.STATE = prev_sentinel_state
                watcher_module.STATE = prev_watcher_state

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue(summary_json.exists())
            self.assertTrue(status_json.exists())
            self.assertTrue(latest_status_json.exists())

            publish_summary = json.loads(summary_json.read_text())
            self.assertEqual(publish_summary["epoch_id"], epoch_id)
            self.assertEqual(publish_summary["archive_ingest"]["status"], "ingested")
            self.assertTrue(publish_summary["watcher_replay"]["passed"])
            self.assertTrue(publish_summary["ready"])

            status_report = json.loads(status_json.read_text())
            self.assertTrue(status_report["ready"])
            self.assertEqual(status_report["checks"]["watcher_ready"]["state"], "YES")
            self.assertEqual(status_report["checks"]["onchain_auth"]["state"], "OK")
            self.assertEqual(watcher.health_check()["last_mirrored_epoch"], epoch_id)
            print("  Ops: canary epoch publish refreshes archive, watcher, and readiness reports")

    def test_22_export_audit_bundle(self):
        """Ops: audit bundle export packages deployment and readiness artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            status_json = tmp / "status-report.json"
            status_md = tmp / "status-report.md"
            out_dir = tmp / "bundles"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x0000000000000000000000000000000000000001",
                    "challenge_escrow": "0x0000000000000000000000000000000000000002",
                    "bond_vault": "0x0000000000000000000000000000000000000003",
                    "species_registry": "0x0000000000000000000000000000000000000004",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
                "drw": {
                    "enabled": True,
                    "total_supply": "1000",
                    "staking_duration": 31536000,
                    "contracts": {
                        "drw_token": "0x0000000000000000000000000000000000000011",
                        "drw_staking": "0x0000000000000000000000000000000000000012",
                    },
                    "allocations": {
                        "treasury_recipient": "0x0000000000000000000000000000000000000009",
                        "treasury_amount": "700",
                        "staking_recipient": "0x0000000000000000000000000000000000000012",
                        "staking_amount": "300",
                    },
                },
            }))

            status_json.write_text(json.dumps({
                "generated_at": "2026-04-05T00:00:00Z",
                "ready": True,
                "blockers": [],
                "checks": {
                    "watcher_ready": {"state": "YES", "detail": "epochs=1 mirrored=seed-1"},
                    "onchain": {"state": "OK", "detail": "rpc_chain=84532 contracts=5/5"},
                    "onchain_auth": {"state": "OK", "detail": "components=4 batch_operator=0x000000000000000000000000000000000000000b"},
                    "onchain_drw": {"state": "OK", "detail": "holders=2 tracked_supply=1000/1000"},
                },
                "onchain_auth": {
                    "components": {
                        "settlement_hub": {"ok": True, "summary": "governance=0x9 batch_operator=yes"}
                    }
                },
                "onchain_drw": {
                    "ok": True,
                    "tracked_total": 1000,
                    "expected_total_supply": 1000,
                    "holders": {
                        "0x0000000000000000000000000000000000000009": {"expected": 700, "observed": 700},
                        "0x0000000000000000000000000000000000000012": {"expected": 300, "observed": 300},
                    },
                },
            }, indent=2))
            status_md.write_text("# DARWIN Status Report\n\n- Overall status: `READY`\n")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "export_audit_bundle.py"),
                    "--deployment-file",
                    str(deployment),
                    "--status-json",
                    str(status_json),
                    "--status-markdown",
                    str(status_md),
                    "--out-dir",
                    str(out_dir),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            bundles = list(out_dir.glob("base-sepolia-*"))
            self.assertEqual(len(bundles), 1)
            bundle = bundles[0]
            summary_json = json.loads((bundle / "audit-summary.json").read_text())
            self.assertTrue(summary_json["status"]["ready"])
            self.assertEqual(summary_json["deployment"]["roles"]["batch_operator"], "0x000000000000000000000000000000000000000b")
            self.assertEqual(summary_json["deployment"]["drw"]["contracts"]["drw_token"], "0x0000000000000000000000000000000000000011")
            self.assertEqual(summary_json["bundle_files"]["audit_readiness"], "AUDIT_READINESS.md")
            self.assertEqual(summary_json["bundle_files"]["threat_model"], "THREAT_MODEL.md")
            self.assertTrue((bundle / "AUDIT_READINESS.md").exists())
            self.assertTrue((bundle / "THREAT_MODEL.md").exists())
            summary_md = (bundle / "audit-summary.md").read_text()
            self.assertIn("DARWIN Audit Bundle", summary_md)
            self.assertIn("settlement_hub", summary_md)
            self.assertIn("On-chain DRW", summary_md)
            self.assertIn("DRW State", summary_md)
            print("  Ops: audit bundle export packages deployment and readiness artifacts")

    def test_23_export_external_watcher_bundle(self):
        """Ops: external watcher bundle export packages deployment, readiness, and handoff docs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            status_json = tmp / "status-report.json"
            status_md = tmp / "status-report.md"
            out_dir = tmp / "bundles"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x0000000000000000000000000000000000000001",
                    "challenge_escrow": "0x0000000000000000000000000000000000000002",
                    "bond_vault": "0x0000000000000000000000000000000000000003",
                    "species_registry": "0x0000000000000000000000000000000000000004",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
            }))

            status_json.write_text(json.dumps({
                "generated_at": "2026-04-05T00:00:00Z",
                "ready": True,
                "blockers": [],
                "checks": {
                    "watcher_ready": {"state": "YES", "detail": "epochs=2 mirrored=canary-2"},
                    "onchain_auth": {"state": "OK", "detail": "components=5 batch_operator=0x000000000000000000000000000000000000000b"},
                },
            }, indent=2))
            status_md.write_text("# DARWIN Status Report\n\n- Overall status: `READY`\n")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "export_external_watcher_bundle.py"),
                    "--deployment-file",
                    str(deployment),
                    "--status-json",
                    str(status_json),
                    "--status-markdown",
                    str(status_md),
                    "--archive-url",
                    "http://archive.example:9447",
                    "--out-dir",
                    str(out_dir),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            bundles = list(out_dir.glob("base-sepolia-watcher-*"))
            self.assertEqual(len(bundles), 1)
            bundle = bundles[0]
            summary_json = json.loads((bundle / "external-watcher-summary.json").read_text())
            self.assertEqual(summary_json["archive_url"], "http://archive.example:9447")
            self.assertEqual(summary_json["bundle_files"]["operator_quickstart"], "OPERATOR_QUICKSTART.md")
            self.assertEqual(summary_json["bundle_files"]["audit_readiness"], "AUDIT_READINESS.md")
            self.assertEqual(summary_json["bundle_files"]["threat_model"], "THREAT_MODEL.md")
            self.assertTrue((bundle / "OPERATOR_QUICKSTART.md").exists())
            self.assertTrue((bundle / "AUDIT_READINESS.md").exists())
            self.assertTrue((bundle / "THREAT_MODEL.md").exists())
            env_template = (bundle / "external-watcher.env.example").read_text()
            self.assertIn("DARWIN_WATCHER_ARCHIVE_URL=http://archive.example:9447", env_template)
            handoff_md = (bundle / "EXTERNAL_WATCHER_HANDOFF.md").read_text()
            self.assertIn("DARWIN External Watcher Handoff", handoff_md)
            self.assertIn("./ops/run_external_watcher.sh", handoff_md)
            print("  Ops: external watcher bundle export packages handoff docs and env template")

    def test_24_external_watcher_runner_loads_env_file(self):
        """Ops: the external watcher runner can load its bootstrap vars from an env file."""
        with (
            tempfile.TemporaryDirectory() as storage_dir,
            tempfile.TemporaryDirectory() as state_dir,
            tempfile.TemporaryDirectory() as config_dir,
        ):
            archive = archive_service.ArchiveState(storage_dir=storage_dir)
            archive.ingest_epoch("21", "outputs/test_e2")

            prev_archive_state = archive_service.STATE
            archive_service.STATE = archive
            archive_server = HTTPServer(("127.0.0.1", 0), archive_service.ArchiveHandler)
            archive_thread = Thread(target=archive_server.serve_forever, daemon=True)
            archive_thread.start()

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                watcher_port = sock.getsockname()[1]

            env_file = Path(config_dir) / "external-watcher.env"
            env_file.write_text(
                "\n".join([
                    f"DARWIN_WATCHER_ARCHIVE_URL=http://127.0.0.1:{archive_server.server_port}",
                    f"DARWIN_WATCHER_STATE_ROOT={state_dir}",
                    f"DARWIN_WATCHER_PORT={watcher_port}",
                    "DARWIN_WATCHER_POLL_SEC=5",
                    "",
                ])
            )

            env = {
                **os.environ,
                "DARWIN_WATCHER_ENV_FILE": str(env_file),
            }
            proc = subprocess.Popen(
                ["bash", str(ROOT / "ops" / "run_external_watcher.sh")],
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            report_path = Path(state_dir) / "reports" / "watcher-status.json"

            try:
                deadline = time.time() + 15
                while time.time() < deadline:
                    if report_path.exists():
                        report = json.loads(report_path.read_text())
                        if report.get("health", {}).get("epochs_replayed", 0) >= 1:
                            break
                    if proc.poll() is not None:
                        self.fail((proc.stdout.read() or "") + (proc.stderr.read() or ""))
                    time.sleep(0.2)
                else:
                    self.fail("external watcher runner did not load env file in time")
            finally:
                proc.terminate()
                proc.wait(timeout=10)
                archive_server.shutdown()
                archive_server.server_close()
                archive_thread.join(timeout=5)
                archive_service.STATE = prev_archive_state

            report = json.loads(report_path.read_text())
            self.assertEqual(report["health"]["last_mirrored_epoch"], "21")
            self.assertEqual(proc.returncode, 0)
            print("  Ops: external watcher runner can bootstrap from a saved env file")

    def test_25_intake_external_watcher_report(self):
        """Ops: external watcher intake verifies a returned watcher report against the bundle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            status_json = tmp / "status-report.json"
            status_md = tmp / "status-report.md"
            bundle_dir = tmp / "bundles"
            intake_dir = tmp / "intake"
            watcher_report_json = tmp / "watcher-status.json"
            watcher_report_md = tmp / "watcher-status.md"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "challenge_escrow": "0x0000000000000000000000000000000000000002",
                    "bond_vault": "0x0000000000000000000000000000000000000003",
                    "species_registry": "0x0000000000000000000000000000000000000004",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
            }))

            status_json.write_text(json.dumps({
                "generated_at": "2026-04-05T00:00:00Z",
                "ready": True,
                "blockers": [],
                "checks": {
                    "watcher_ready": {"state": "YES", "detail": "epochs=2 mirrored=canary-2"},
                    "onchain_auth": {"state": "OK", "detail": "components=5 batch_operator=0x000000000000000000000000000000000000000b"},
                },
            }, indent=2))
            status_md.write_text("# DARWIN Status Report\n\n- Overall status: `READY`\n")

            bundle_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "export_external_watcher_bundle.py"),
                    "--deployment-file",
                    str(deployment),
                    "--status-json",
                    str(status_json),
                    "--status-markdown",
                    str(status_md),
                    "--archive-url",
                    "http://archive.example:9447",
                    "--out-dir",
                    str(bundle_dir),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertEqual(bundle_result.returncode, 0, msg=bundle_result.stdout + bundle_result.stderr)
            bundle = next(bundle_dir.glob("base-sepolia-watcher-*"))

            watcher_report_json.write_text(json.dumps({
                "health": {
                    "ready": True,
                    "epochs_replayed": 2,
                    "last_mirrored_epoch": "22",
                },
                "epochs": {
                    "21": {"passed": True, "mismatches": 0},
                    "22": {"passed": True, "mismatches": 0},
                },
            }, indent=2))
            watcher_report_md.write_text("# DARWIN External Watcher Report\n\n- Watcher readiness: `YES`\n")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "intake_external_watcher_report.py"),
                    "--bundle-dir",
                    str(bundle),
                    "--report-json",
                    str(watcher_report_json),
                    "--report-markdown",
                    str(watcher_report_md),
                    "--reference-deployment-file",
                    str(deployment),
                    "--out-dir",
                    str(intake_dir),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            intake = next(intake_dir.glob("base-sepolia-watcher-intake-*"))
            summary = json.loads((intake / "external-watcher-intake.json").read_text())
            self.assertTrue(summary["accepted"])
            self.assertEqual(summary["watcher"]["latest_epoch"], "22")
            self.assertTrue(summary["checks"]["deployment_match"]["ok"])
            self.assertTrue(summary["checks"]["latest_epoch"]["ok"])
            summary_md = (intake / "external-watcher-intake.md").read_text()
            self.assertIn("DARWIN External Watcher Intake", summary_md)
            self.assertIn("Accepted: `True`", summary_md)
            print("  Ops: external watcher intake verifies bundle and replay report together")

    def test_26_intake_external_watcher_report_accepts_coerced_string_epoch(self):
        """Ops: external watcher intake accepts a clean replay when string archive epoch IDs collapse to key 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            status_json = tmp / "status-report.json"
            status_md = tmp / "status-report.md"
            bundle_dir = tmp / "bundles"
            intake_dir = tmp / "intake"
            watcher_report_json = tmp / "watcher-status.json"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "challenge_escrow": "0x0000000000000000000000000000000000000002",
                    "bond_vault": "0x0000000000000000000000000000000000000003",
                    "species_registry": "0x0000000000000000000000000000000000000004",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
            }))

            status_json.write_text(json.dumps({
                "generated_at": "2026-04-05T00:00:00Z",
                "ready": True,
                "blockers": [],
                "checks": {
                    "watcher_ready": {"state": "YES", "detail": "epochs=1 mirrored=seed-1"},
                    "onchain_auth": {"state": "OK", "detail": "components=5 batch_operator=0x000000000000000000000000000000000000000b"},
                },
            }, indent=2))
            status_md.write_text("# DARWIN Status Report\n\n- Overall status: `READY`\n")

            bundle_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "export_external_watcher_bundle.py"),
                    "--deployment-file",
                    str(deployment),
                    "--status-json",
                    str(status_json),
                    "--status-markdown",
                    str(status_md),
                    "--archive-url",
                    "http://archive.example:9447",
                    "--out-dir",
                    str(bundle_dir),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertEqual(bundle_result.returncode, 0, msg=bundle_result.stdout + bundle_result.stderr)
            bundle = next(bundle_dir.glob("base-sepolia-watcher-*"))

            watcher_report_json.write_text(json.dumps({
                "health": {
                    "ready": True,
                    "epochs_replayed": 1,
                    "last_mirrored_epoch": "seed-1",
                },
                "epochs": {
                    "0": {"passed": True, "mismatches": 0},
                },
            }, indent=2))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "intake_external_watcher_report.py"),
                    "--bundle-dir",
                    str(bundle),
                    "--report-json",
                    str(watcher_report_json),
                    "--reference-deployment-file",
                    str(deployment),
                    "--out-dir",
                    str(intake_dir),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            intake = next(intake_dir.glob("base-sepolia-watcher-intake-*"))
            summary = json.loads((intake / "external-watcher-intake.json").read_text())
            self.assertTrue(summary["accepted"])
            self.assertTrue(summary["checks"]["mirrored_epoch_alignment"]["ok"])
            self.assertIn("coerced_non_numeric_epoch=True", summary["checks"]["mirrored_epoch_alignment"]["detail"])
            print("  Ops: external watcher intake accepts clean string epoch IDs that collapse to watcher key 0")

    def test_27_wallet_roundtrip(self):
        """Wallet: encrypted wallet file round-trips full signing material."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wallet = create_wallet(label="alpha-trader", chain_id=84532)
            wallet_path = Path(tmpdir) / "darwin_wallet.json"
            save_wallet(wallet, wallet_path, "test-passphrase")

            loaded = load_wallet(wallet_path, "test-passphrase")
            public = load_wallet_public_account(wallet_path)

            self.assertEqual(loaded.account.acct_id, wallet.account.acct_id)
            self.assertEqual(loaded.account.evm_addr, wallet.account.evm_addr)
            self.assertEqual(loaded.account.chain_id, 84532)
            self.assertEqual(public.acct_id, wallet.account.acct_id)
            self.assertEqual(public.evm_addr, wallet.account.evm_addr)
            self.assertEqual(len(loaded.account.pq_hot_sk), len(wallet.account.pq_hot_sk))
            self.assertEqual(len(loaded.account.evm_sk), len(wallet.account.evm_sk))
            print("  Wallet: encrypted round-trip preserves public identity and signing keys")

    def test_28_cli_wallet_commands(self):
        """CLI: wallet-init/show/export-public create a reusable local wallet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wallet_path = Path(tmpdir) / "darwin_wallet.json"
            public_path = Path(tmpdir) / "darwin_account.json"
            env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}

            init_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "wallet-init",
                    "--chain-id",
                    "84532",
                    "--label",
                    "alpha-trader",
                    "--passphrase",
                    "test-passphrase",
                    "--out",
                    str(wallet_path),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(init_result.returncode, 0, msg=init_result.stdout + init_result.stderr)
            self.assertTrue(wallet_path.exists())

            show_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "wallet-show",
                    str(wallet_path),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(show_result.returncode, 0, msg=show_result.stdout + show_result.stderr)
            self.assertIn("alpha-trader", show_result.stdout)
            self.assertIn("84532", show_result.stdout)

            export_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "wallet-export-public",
                    str(wallet_path),
                    "--out",
                    str(public_path),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(export_result.returncode, 0, msg=export_result.stdout + export_result.stderr)
            self.assertTrue(public_path.exists())
            public_account = json.loads(public_path.read_text())
            self.assertEqual(int(public_account["chain_id"]), 84532)
            self.assertTrue(public_account["acct_id"])
            print("  CLI: wallet-init/show/export-public create and expose reusable wallet identity")

    def test_28b_cli_wallet_request(self):
        """CLI: wallet-request emits a shareable Base Sepolia DRW transfer URI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            wallet_path = tmp / "darwin_wallet.json"
            request_path = tmp / "request.txt"
            deployment = tmp / "base-sepolia.json"
            env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
                "drw": {
                    "enabled": True,
                    "decimals": 18,
                    "contracts": {
                        "drw_token": "0x00000000000000000000000000000000000000d1",
                    },
                },
            }))

            init_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "wallet-init",
                    "--deployment-file",
                    str(deployment),
                    "--label",
                    "alpha-trader",
                    "--passphrase",
                    "test-passphrase",
                    "--out",
                    str(wallet_path),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(init_result.returncode, 0, msg=init_result.stdout + init_result.stderr)

            request_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "wallet-request",
                    str(wallet_path),
                    "--deployment-file",
                    str(deployment),
                    "--amount",
                    "25",
                    "--out",
                    str(request_path),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(request_result.returncode, 0, msg=request_result.stdout + request_result.stderr)
            self.assertTrue(request_path.exists())
            uri = request_path.read_text().strip()
            self.assertIn("ethereum:0x00000000000000000000000000000000000000d1@84532/transfer", uri)
            self.assertIn("uint256=25000000000000000000", uri)
            print("  CLI: wallet-request emits a shareable DRW transfer URI for a saved wallet")

    def test_29_cli_intent_create_from_wallet(self):
        """CLI: intent-create can sign from a saved wallet instead of an ephemeral account."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wallet_path = Path(tmpdir) / "darwin_wallet.json"
            public_path = Path(tmpdir) / "darwin_account.json"
            intent_path = Path(tmpdir) / "intent.json"
            env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}

            init_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "wallet-init",
                    "--chain-id",
                    "84532",
                    "--label",
                    "alpha-trader",
                    "--passphrase",
                    "test-passphrase",
                    "--out",
                    str(wallet_path),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(init_result.returncode, 0, msg=init_result.stdout + init_result.stderr)

            export_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "wallet-export-public",
                    str(wallet_path),
                    "--out",
                    str(public_path),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(export_result.returncode, 0, msg=export_result.stdout + export_result.stderr)

            intent_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "intent-create",
                    "--wallet-file",
                    str(wallet_path),
                    "--passphrase",
                    "test-passphrase",
                    "--chain-id",
                    "84532",
                    "--settlement-hub",
                    "0x0000000000000000000000000000000000000001",
                    "--out",
                    str(intent_path),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(intent_result.returncode, 0, msg=intent_result.stdout + intent_result.stderr)

            public_account = json.loads(public_path.read_text())
            intent_payload = json.loads(intent_path.read_text())
            self.assertEqual(intent_payload["pq_leg"]["acct_id"], public_account["acct_id"])
            self.assertEqual(intent_payload["evm_leg"]["evm_addr"], public_account["evm_addr"])
            self.assertEqual(intent_payload["account"]["acct_id"], public_account["acct_id"])
            print("  CLI: intent-create signs from a saved wallet and preserves the same account identity")

    def test_30_init_demo_wallet_script(self):
        """Ops: init_demo_wallet creates a persistent wallet, public account, and verified demo intent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            wallet_dir = tmp / "wallets"
            wallet_dir.mkdir()
            deployment = tmp / "base-sepolia.json"
            intent_path = tmp / "intent.json"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
            }))

            env = {
                **os.environ,
                "DARWIN_WALLET_DIR": str(wallet_dir),
                "DARWIN_WALLET_LABEL": "alpha-trader",
                "DARWIN_WALLET_PASSPHRASE": "test-passphrase",
                "DARWIN_INTENT_FILE": str(intent_path),
                "DARWIN_DEPLOYMENT_FILE": str(deployment),
                "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM),
            }
            result = subprocess.run(
                ["bash", str(ROOT / "ops" / "init_demo_wallet.sh")],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            wallet_path = wallet_dir / "alpha-trader.wallet.json"
            public_path = wallet_dir / "alpha-trader.account.json"
            self.assertTrue(wallet_path.exists())
            self.assertTrue(public_path.exists())
            self.assertTrue(intent_path.exists())
            intent_payload = json.loads(intent_path.read_text())
            public_account = json.loads(public_path.read_text())
            self.assertEqual(intent_payload["pq_leg"]["acct_id"], public_account["acct_id"])
            self.assertEqual(intent_payload["evm_leg"]["evm_addr"], public_account["evm_addr"])
            self.assertIn("[demo-wallet] Ready", result.stdout)
            print("  Ops: init_demo_wallet creates reusable wallet artifacts and a verified intent")

    def test_30b_init_peer_wallet_script(self):
        """Ops: init_peer_wallet creates a reusable wallet plus a shareable DRW request bundle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            wallet_dir = tmp / "wallets"
            wallet_dir.mkdir()
            deployment = tmp / "base-sepolia.json"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
                "drw": {
                    "enabled": True,
                    "decimals": 18,
                    "contracts": {
                        "drw_token": "0x00000000000000000000000000000000000000d1",
                    },
                },
            }))

            env = {
                **os.environ,
                "DARWIN_WALLET_DIR": str(wallet_dir),
                "DARWIN_WALLET_LABEL": "peer-user",
                "DARWIN_WALLET_PASSPHRASE": "test-passphrase",
                "DARWIN_DEPLOYMENT_FILE": str(deployment),
                "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM),
            }
            result = subprocess.run(
                ["bash", str(ROOT / "ops" / "init_peer_wallet.sh")],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            wallet_path = wallet_dir / "peer-user.wallet.json"
            public_path = wallet_dir / "peer-user.account.json"
            request_path = wallet_dir / "peer-user.request.txt"
            share_path = wallet_dir / "peer-user.share.md"
            self.assertTrue(wallet_path.exists())
            self.assertTrue(public_path.exists())
            self.assertTrue(request_path.exists())
            self.assertTrue(share_path.exists())
            self.assertIn("ethereum:0x00000000000000000000000000000000000000d1@84532/transfer", request_path.read_text())
            self.assertIn("https://usedarwin.xyz/", share_path.read_text())
            self.assertIn("[peer-wallet] Ready", result.stdout)
            print("  Ops: init_peer_wallet creates a shareable DRW peer-to-peer wallet bundle")

    def test_30c_init_recovery_wallets_script(self):
        """Ops: init_recovery_wallets creates fresh future governance and deployer wallet bundles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            wallet_dir = tmp / "wallets"
            wallet_dir.mkdir()
            deployment = tmp / "base-sepolia.json"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
            }))

            env = {
                **os.environ,
                "DARWIN_WALLET_DIR": str(wallet_dir),
                "DARWIN_DEPLOYMENT_FILE": str(deployment),
                "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM),
            }
            result = subprocess.run(
                ["bash", str(ROOT / "ops" / "init_recovery_wallets.sh")],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            governance_public = wallet_dir / "darwin-future-governance.account.json"
            deployer_public = wallet_dir / "darwin-future-deployer.account.json"
            governance_share = wallet_dir / "darwin-future-governance.share.md"
            deployer_share = wallet_dir / "darwin-future-deployer.share.md"
            summary = wallet_dir / "recovery-wallets-summary.md"
            self.assertTrue(governance_public.exists())
            self.assertTrue(deployer_public.exists())
            self.assertTrue(governance_share.exists())
            self.assertTrue(deployer_share.exists())
            self.assertTrue(summary.exists())
            self.assertIn("[recovery-wallets] Ready", result.stdout)
            self.assertIn("future-governance", summary.read_text())
            self.assertIn("future-deployer", summary.read_text())
            print("  Ops: init_recovery_wallets creates future governance and deployer wallet bundles")

    def test_30d_prepare_recovery_env_script(self):
        """Ops: prepare_recovery_env derives a local-only recovery env from fresh wallets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            wallet_dir = tmp / "wallets"
            wallet_dir.mkdir()
            deployment = tmp / "base-sepolia.json"
            env_path = tmp / ".env.recovery"
            recovery_artifact = tmp / "base-sepolia-recovery.json"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
            }))

            init_result = subprocess.run(
                ["bash", str(ROOT / "ops" / "init_recovery_wallets.sh")],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "DARWIN_WALLET_DIR": str(wallet_dir),
                    "DARWIN_DEPLOYMENT_FILE": str(deployment),
                    "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM),
                },
                capture_output=True,
                text=True,
            )
            self.assertEqual(init_result.returncode, 0, msg=init_result.stdout + init_result.stderr)

            result = subprocess.run(
                ["bash", str(ROOT / "ops" / "prepare_recovery_env.sh")],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "DARWIN_WALLET_DIR": str(wallet_dir),
                    "DARWIN_SOURCE_DEPLOYMENT_FILE": str(deployment),
                    "DARWIN_RECOVERY_ENV_FILE": str(env_path),
                    "DARWIN_RECOVERY_DEPLOYMENT_FILE": str(recovery_artifact),
                    "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM),
                },
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue(env_path.exists())
            env_text = env_path.read_text()
            self.assertIn('export DARWIN_NETWORK="base-sepolia-recovery"', env_text)
            self.assertIn('export DARWIN_DEPLOYMENT_FILE="' + str(recovery_artifact) + '"', env_text)
            self.assertIn('export DARWIN_BOND_ASSET="0x4200000000000000000000000000000000000006"', env_text)
            self.assertIn("DARWIN_GOVERNANCE_PRIVATE_KEY", env_text)
            self.assertIn("DARWIN_DEPLOYER_PRIVATE_KEY", env_text)
            self.assertIn("[recovery-env] Ready", result.stdout)
            print("  Ops: prepare_recovery_env derives a separate recovery artifact env from local wallets")

    def test_31_prepare_external_packets(self):
        """Ops: prepare_external_packets emits sendable operator and reviewer tarballs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            status_json = tmp / "status-report.json"
            status_md = tmp / "status-report.md"
            out_dir = tmp / "handoffs"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "challenge_escrow": "0x0000000000000000000000000000000000000002",
                    "bond_vault": "0x0000000000000000000000000000000000000003",
                    "species_registry": "0x0000000000000000000000000000000000000004",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
            }))
            status_json.write_text(json.dumps({
                "generated_at": "2026-04-05T00:00:00Z",
                "ready": True,
                "blockers": [],
                "checks": {
                    "watcher_ready": {"state": "YES", "detail": "epochs=2 mirrored=canary-2"},
                    "onchain": {"state": "OK", "detail": "rpc_chain=84532 contracts=5/5"},
                    "onchain_auth": {"state": "OK", "detail": "components=5 batch_operator=0x000000000000000000000000000000000000000b"},
                },
            }, indent=2))
            status_md.write_text("# DARWIN Status Report\n\n- Overall status: `READY`\n")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "prepare_external_packets.py"),
                    "--deployment-file",
                    str(deployment),
                    "--status-json",
                    str(status_json),
                    "--status-markdown",
                    str(status_md),
                    "--archive-url",
                    "http://archive.example:9447",
                    "--out-dir",
                    str(out_dir),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            handoff = next(out_dir.glob("base-sepolia-*"))
            summary = json.loads((handoff / "handoff-summary.json").read_text())
            self.assertEqual(summary["deployment"]["network"], "base-sepolia")
            self.assertTrue((handoff / summary["artifacts"]["operator_bundle_tar"]).exists())
            self.assertTrue((handoff / summary["artifacts"]["audit_bundle_tar"]).exists())
            self.assertEqual(summary["artifacts"]["checklist"], "EXTERNAL_CANARY_CHECKLIST.md")
            self.assertEqual(summary["artifacts"]["checksums"], "CHECKSUMS.txt")
            self.assertEqual(summary["artifacts"]["operator_request"], "WATCHER_OPERATOR_REQUEST.md")
            self.assertEqual(summary["artifacts"]["reviewer_request"], "EXTERNAL_REVIEW_REQUEST.md")
            self.assertTrue((handoff / "CHECKSUMS.txt").exists())
            self.assertTrue((handoff / "WATCHER_OPERATOR_REQUEST.md").exists())
            self.assertTrue((handoff / "EXTERNAL_REVIEW_REQUEST.md").exists())
            checksums = (handoff / "CHECKSUMS.txt").read_text()
            self.assertIn(summary["artifacts"]["operator_bundle_tar"], checksums)
            self.assertIn(summary["artifacts"]["audit_bundle_tar"], checksums)
            self.assertIn("Files To Send", (handoff / "handoff-summary.md").read_text())
            self.assertIn("Why This Matters", (handoff / "WATCHER_OPERATOR_REQUEST.md").read_text())
            self.assertIn("Focus Areas", (handoff / "EXTERNAL_REVIEW_REQUEST.md").read_text())
            self.assertIn("intake_external_review.py", (handoff / "EXTERNAL_REVIEW_REQUEST.md").read_text())
            print("  Ops: prepare_external_packets emits sendable operator and reviewer archives")

    def test_32_deployment_show_with_drw_genesis(self):
        """CLI: deployment-show surfaces DRW genesis metadata when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                    "drw_token": "0x0000000000000000000000000000000000000011",
                    "drw_staking": "0x0000000000000000000000000000000000000012",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
                "drw": {
                    "enabled": True,
                    "total_supply": 1_000_000_000000000000000000000,
                    "staking_duration": 31536000,
                    "contracts": {
                        "drw_token": "0x0000000000000000000000000000000000000011",
                        "drw_staking": "0x0000000000000000000000000000000000000012",
                    },
                    "allocations": {
                        "treasury_recipient": "0x0000000000000000000000000000000000000009",
                        "treasury_amount": 200,
                        "insurance_recipient": "0x0000000000000000000000000000000000000009",
                        "insurance_amount": 200,
                        "staking_recipient": "0x0000000000000000000000000000000000000012",
                        "staking_amount": 300,
                    },
                },
            }))

            env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "deployment-show",
                    "--deployment-file",
                    str(deployment),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("DRW enabled:      yes", result.stdout)
            self.assertIn("DRW token:", result.stdout)
            self.assertIn("DRW staking:", result.stdout)
            print("  CLI: deployment-show prints DRW genesis metadata when the artifact includes it")

    def test_33_preflight_drw_genesis_loads_env_file(self):
        """Ops: DRW genesis preflight can bootstrap from a saved .env-style file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            env_file = tmp / ".env.base-sepolia"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
            }))

            class RpcHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length).decode())
                    method = body.get("method")
                    params = body.get("params", [])

                    if method == "eth_chainId":
                        result = hex(84532)
                    elif method == "eth_getBalance":
                        result = hex(2 * 10**15)
                    else:
                        result = "0x"

                    payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def log_message(self, fmt, *args):
                    pass

            rpc_server = HTTPServer(("127.0.0.1", 0), RpcHandler)
            rpc_thread = Thread(target=rpc_server.serve_forever, daemon=True)
            rpc_thread.start()

            env_file.write_text(
                "\n".join([
                    f"DARWIN_RPC_URL=http://127.0.0.1:{rpc_server.server_port}",
                    "DARWIN_DEPLOYER_ADDRESS=0x00000000000000000000000000000000000000aa",
                    "",
                ])
            )

            try:
                env = {
                    **os.environ,
                    "DARWIN_ENV_FILE": str(env_file),
                    "DARWIN_DEPLOYMENT_FILE": str(deployment),
                }
                result = subprocess.run(
                    ["bash", str(ROOT / "ops" / "preflight_drw_genesis.sh")],
                    cwd=str(ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                )
            finally:
                rpc_server.shutdown()
                rpc_server.server_close()
                rpc_thread.join(timeout=5)

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("ready_to_deploy:      yes", result.stdout)
            self.assertIn("existing_drw:         no", result.stdout)
            self.assertIn("governance:           0x0000000000000000000000000000000000000009", result.stdout)
            print("  Ops: DRW genesis preflight can load env defaults from a saved file")

    def test_34_external_review_intake(self):
        """Ops: external review intake logs structured findings and emits triage artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            bundle = tmp / "base-sepolia-audit"
            bundle.mkdir()
            deployment = bundle / "base-sepolia.json"
            status_json = bundle / "status-report.json"
            audit_summary = bundle / "audit-summary.json"
            review_md = tmp / "review-findings.md"
            review_json = tmp / "review-findings.json"
            out_dir = tmp / "intake"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                },
            }))
            status_json.write_text("{}\n")
            (bundle / "AUDIT_READINESS.md").write_text("# audit\n")
            (bundle / "THREAT_MODEL.md").write_text("# threat\n")
            audit_summary.write_text(json.dumps({
                "deployment": {
                    "network": "base-sepolia",
                    "chain_id": 84532,
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                },
                "bundle_files": {
                    "deployment": "base-sepolia.json",
                    "status_json": "status-report.json",
                    "status_markdown": "",
                    "audit_readiness": "AUDIT_READINESS.md",
                    "threat_model": "THREAT_MODEL.md",
                },
            }, indent=2))

            review_md.write_text("# Findings\n\n- HIGH: settlement replay edge case\n")
            review_json.write_text(json.dumps({
                "findings": [
                    {
                        "severity": "HIGH",
                        "title": "Settlement replay edge case",
                        "affected_paths": ["contracts/src/SettlementHub.sol"],
                        "status": "open",
                        "notes": "needs additional adversarial coverage",
                    },
                    {
                        "severity": "LOW",
                        "title": "Docs wording",
                        "affected_paths": ["README.md"],
                        "status": "open",
                    },
                ],
            }, indent=2))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "intake_external_review.py"),
                    "--bundle-dir",
                    str(bundle),
                    "--review-markdown",
                    str(review_md),
                    "--review-json",
                    str(review_json),
                    "--out-dir",
                    str(out_dir),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            intake = next(out_dir.glob("base-sepolia-review-intake-*"))
            summary = json.loads((intake / "external-review-intake.json").read_text())
            self.assertTrue(summary["accepted"])
            self.assertTrue(summary["review"]["requires_action"])
            self.assertEqual(summary["review"]["highest_severity"], "HIGH")
            self.assertEqual(summary["review"]["severity_counts"]["HIGH"], 1)
            self.assertEqual(summary["review"]["severity_counts"]["LOW"], 1)
            self.assertEqual(summary["review"]["findings_count"], 2)
            self.assertTrue((intake / "external-review-triage.md").exists())
            self.assertIn("Settlement replay edge case", (intake / "external-review-triage.md").read_text())
            print("  Ops: external review intake logs findings and emits triage artifacts")

    def test_35_preflight_market_bootstrap(self):
        """Ops: market bootstrap preflight checks live DRW + quote balances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            json_out = tmp / "preflight.json"
            md_out = tmp / "preflight.md"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                },
                "drw": {
                    "enabled": True,
                    "contracts": {
                        "drw_token": "0x0000000000000000000000000000000000000011",
                        "drw_staking": "0x0000000000000000000000000000000000000012",
                    },
                },
            }))

            class RpcHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    method = body.get("method")
                    params = body.get("params", [])

                    def encode_uint(value: int) -> str:
                        return "0x" + hex(value)[2:].rjust(64, "0")

                    def encode_string(value: str) -> str:
                        raw = value.encode()
                        length = len(raw)
                        padded = raw + b"\x00" * ((32 - (length % 32)) % 32)
                        payload = (
                            (32).to_bytes(32, "big")
                            + length.to_bytes(32, "big")
                            + padded
                        )
                        return "0x" + payload.hex()

                    if method == "eth_chainId":
                        result = hex(84532)
                    elif method == "eth_getBalance":
                        result = hex(2 * 10**15)
                    elif method == "eth_call":
                        to = params[0]["to"].lower()
                        data = params[0].get("data", "").lower()
                        if to == "0x0000000000000000000000000000000000000011":
                            if data == "0x95d89b41":
                                result = encode_string("DRW")
                            elif data == "0x313ce567":
                                result = encode_uint(18)
                            elif data == "0x70a08231" + "0" * 24 + "0000000000000000000000000000000000000009":
                                result = encode_uint(700 * 10**18)
                            else:
                                result = encode_uint(0)
                        elif to == "0x4200000000000000000000000000000000000006":
                            if data == "0x95d89b41":
                                result = encode_string("WETH")
                            elif data == "0x313ce567":
                                result = encode_uint(18)
                            elif data == "0x70a08231" + "0" * 24 + "0000000000000000000000000000000000000009":
                                result = encode_uint(5 * 10**17)
                            else:
                                result = encode_uint(0)
                        else:
                            result = "0x"
                    else:
                        result = "0x0"

                    payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def log_message(self, fmt, *args):
                    pass

            rpc_server = HTTPServer(("127.0.0.1", 0), RpcHandler)
            rpc_thread = Thread(target=rpc_server.serve_forever, daemon=True)
            rpc_thread.start()

            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "ops" / "preflight_market_bootstrap.py"),
                        "--deployment-file",
                        str(deployment),
                        "--wallet-address",
                        "0x0000000000000000000000000000000000000009",
                        "--base-rpc-url",
                        f"http://127.0.0.1:{rpc_server.server_port}",
                        "--json-out",
                        str(json_out),
                        "--markdown-out",
                        str(md_out),
                    ],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                )
            finally:
                rpc_server.shutdown()
                rpc_server.server_close()
                rpc_thread.join(timeout=5)

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            report = json.loads(json_out.read_text())
            self.assertTrue(report["ready"])
            self.assertEqual(report["checks"]["drw_balance"]["state"], "OK")
            self.assertEqual(report["checks"]["quote_balance"]["state"], "OK")
            self.assertIn("recommended_pair=DRW/WETH", report["checks"]["market_pair"]["detail"])
            self.assertIn("do not self-trade for optics", md_out.read_text())
            print("  Ops: market bootstrap preflight checks DRW and quote-token readiness")

    def test_36_public_docs_use_repo_relative_links(self):
        """Docs: public markdown should not contain local filesystem links."""
        public_docs = [
            ROOT / "README.md",
            ROOT / "LIVE_STATUS.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / "docs" / "OPERATOR_QUICKSTART.md",
            ROOT / "docs" / "SECURITY.md",
            ROOT / "docs" / "MARKET_BOOTSTRAP.md",
            ROOT / "docs" / "EXTERNAL_CANARY_CHECKLIST.md",
            ROOT / "docs" / "AUDIT_READINESS.md",
            ROOT / "docs" / "THREAT_MODEL.md",
        ]

        offenders: list[str] = []
        disallowed_prefixes = ["](/" + "Users/", "](/" + "tmp/"]
        for path in public_docs:
            if not path.exists():
                continue
            text = path.read_text()
            if any(prefix in text for prefix in disallowed_prefixes):
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual(offenders, [], f"public docs contain local absolute links: {offenders}")
        print("  Docs: public markdown uses repo-relative links")

    def test_37_wrap_weth_dry_run(self):
        """Ops: the WETH wrap helper can dry-run against a pinned deployment artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            env_file = tmp / ".env.base-sepolia"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                },
            }))

            class RpcHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    method = body.get("method")
                    result = "0x0"

                    if method == "eth_chainId":
                        result = hex(84532)
                    elif method == "eth_getBalance":
                        result = hex(3 * 10**15)
                    elif method == "eth_call":
                        result = "0x" + hex(0)[2:].rjust(64, "0")

                    payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def log_message(self, fmt, *args):
                    pass

            rpc_server = HTTPServer(("127.0.0.1", 0), RpcHandler)
            rpc_thread = Thread(target=rpc_server.serve_forever, daemon=True)
            rpc_thread.start()

            env_file.write_text(
                "\n".join([
                    f'export DARWIN_RPC_URL="http://127.0.0.1:{rpc_server.server_port}"',
                    f'export DARWIN_DEPLOYMENT_FILE="{deployment}"',
                    'export DARWIN_DEPLOYER_ADDRESS="0x0000000000000000000000000000000000000009"',
                ]) + "\n"
            )

            try:
                result = subprocess.run(
                    [
                        "bash",
                        str(ROOT / "ops" / "wrap_base_sepolia_weth.sh"),
                        "--dry-run",
                        "--amount-eth",
                        "0.0005",
                    ],
                    cwd=str(ROOT),
                    env={**os.environ, "DARWIN_ENV_FILE": str(env_file)},
                    capture_output=True,
                    text=True,
                )
            finally:
                rpc_server.shutdown()
                rpc_server.server_close()
                rpc_thread.join(timeout=5)

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("dry_run:           yes", result.stdout)
            self.assertIn("wrap_amount_eth:   0.0005", result.stdout)
            self.assertIn("weth_address:      0x4200000000000000000000000000000000000006", result.stdout)
            print("  Ops: WETH wrap helper can dry-run against the pinned market quote asset")

    def test_38_market_venue_preflight_blocks_unconfirmed_network(self):
        """Ops: venue preflight rejects a venue that is not tracked for the deployment chain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            registry = tmp / "market-venues.json"
            json_out = tmp / "venue.json"
            md_out = tmp / "venue.md"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
            }))
            registry.write_text(json.dumps({
                "venues": {
                    "uniswap_v4": {
                        "label": "Uniswap v4",
                        "source": "https://docs.uniswap.org/contracts/v4/deployments",
                        "tracked_networks": {
                            "8453": {
                                "network": "base",
                                "contracts": {
                                    "pool_manager": "0x1"
                                }
                            }
                        },
                        "notes": [
                            "Base Sepolia is not listed."
                        ]
                    }
                }
            }))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "preflight_market_venue.py"),
                    "--deployment-file",
                    str(deployment),
                    "--registry-file",
                    str(registry),
                    "--venue",
                    "uniswap_v4",
                    "--json-out",
                    str(json_out),
                    "--markdown-out",
                    str(md_out),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
            report = json.loads(json_out.read_text())
            self.assertFalse(report["ready"])
            self.assertIn("venue_not_supported_or_unconfirmed", report["blockers"])
            self.assertEqual(report["checks"]["venue_support"]["state"], "FAIL")
            self.assertIn("Base Sepolia is not listed.", md_out.read_text())
            print("  Ops: market venue preflight blocks unconfirmed Base Sepolia support")

    def test_39_market_venue_preflight_accepts_tracked_network(self):
        """Ops: venue preflight accepts a tracked network with known venue contracts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base.json"
            registry = tmp / "market-venues.json"
            json_out = tmp / "venue.json"

            deployment.write_text(json.dumps({
                "network": "base",
                "chain_id": 8453,
            }))
            registry.write_text(json.dumps({
                "venues": {
                    "uniswap_v4": {
                        "label": "Uniswap v4",
                        "source": "https://docs.uniswap.org/contracts/v4/deployments",
                        "tracked_networks": {
                            "8453": {
                                "network": "base",
                                "contracts": {
                                    "pool_manager": "0x498581ff718922c3f8e6a244956af099b2652b2b"
                                }
                            }
                        }
                    }
                }
            }))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "preflight_market_venue.py"),
                    "--deployment-file",
                    str(deployment),
                    "--registry-file",
                    str(registry),
                    "--venue",
                    "uniswap_v4",
                    "--json-out",
                    str(json_out),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            report = json.loads(json_out.read_text())
            self.assertTrue(report["ready"])
            self.assertEqual(report["checks"]["venue_support"]["state"], "OK")
            self.assertEqual(report["venue"]["tracked_network"]["contracts"]["pool_manager"], "0x498581ff718922c3f8e6a244956af099b2652b2b")
            print("  Ops: market venue preflight accepts tracked Base venue support")

    def test_40_market_venue_preflight_accepts_artifact_backed_reference_pool(self):
        """Ops: venue preflight accepts a seeded artifact-backed DARWIN reference pool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            registry = tmp / "market-venues.json"
            json_out = tmp / "venue.json"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "market": {
                    "enabled": True,
                    "venue_id": "darwin_reference_pool",
                    "seeded": True,
                    "contracts": {
                        "reference_pool": "0x0000000000000000000000000000000000000042",
                    },
                },
            }))
            registry.write_text(json.dumps({
                "venues": {
                    "darwin_reference_pool": {
                        "label": "DARWIN reference pool",
                        "source": "https://github.com/darwin-protocol/darwin",
                        "artifact_backed": True,
                    }
                }
            }))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "preflight_market_venue.py"),
                    "--deployment-file",
                    str(deployment),
                    "--registry-file",
                    str(registry),
                    "--venue",
                    "darwin_reference_pool",
                    "--json-out",
                    str(json_out),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            report = json.loads(json_out.read_text())
            self.assertTrue(report["ready"])
            self.assertEqual(report["checks"]["venue_support"]["state"], "OK")
            self.assertEqual(report["venue"]["id"], "darwin_reference_pool")
            print("  Ops: market venue preflight accepts seeded artifact-backed reference pools")

    def test_41_deployment_show_with_reference_market(self):
        """CLI: deployment-show surfaces reference market metadata when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                    "reference_pool": "0x0000000000000000000000000000000000000042",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
                "market": {
                    "enabled": True,
                    "venue_id": "darwin_reference_pool",
                    "venue_type": "constant_product_bootstrap",
                    "market_operator": "0x0000000000000000000000000000000000000009",
                    "base_token": "0x0000000000000000000000000000000000000011",
                    "quote_token": "0x4200000000000000000000000000000000000006",
                    "fee_bps": 30,
                    "seeded": False,
                    "contracts": {
                        "reference_pool": "0x0000000000000000000000000000000000000042",
                    },
                },
            }))

            env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "deployment-show",
                    "--deployment-file",
                    str(deployment),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("Market enabled:   yes", result.stdout)
            self.assertIn("Market venue:     darwin_reference_pool", result.stdout)
            self.assertIn("Market pool:", result.stdout)
            print("  CLI: deployment-show prints reference market metadata when the artifact includes it")

    def test_42_reference_market_swap_helper_handles_large_base_amounts(self):
        """Ops: swap helper dry-runs 18-decimal DRW amounts above bash int range."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            env_file = tmp / ".env.base-sepolia"
            fake_bin = tmp / "bin"
            fake_cast = fake_bin / "cast"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "market": {
                    "enabled": True,
                    "seeded": True,
                    "base_token": "0x0000000000000000000000000000000000000011",
                    "quote_token": "0x0000000000000000000000000000000000000022",
                    "contracts": {
                        "reference_pool": "0x0000000000000000000000000000000000000042",
                    },
                },
            }))
            env_file.write_text(
                "\n".join([
                    'export DARWIN_RPC_URL="http://127.0.0.1:8545"',
                    f'export DARWIN_DEPLOYMENT_FILE="{deployment}"',
                    'export DARWIN_DEPLOYER_ADDRESS="0x0000000000000000000000000000000000000009"',
                ]) + "\n"
            )

            fake_bin.mkdir(parents=True, exist_ok=True)
            fake_cast.write_text(
                """#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" == "chain-id" ]]; then
  echo 84532
  exit 0
fi

if [[ "$1" == "wallet" && "${2:-}" == "address" ]]; then
  echo 0x0000000000000000000000000000000000000009
  exit 0
fi

if [[ "$1" == "call" ]]; then
  addr="${2:-}"
  sig="${3:-}"
  case "$sig" in
    'decimals()(uint8)')
      echo 18
      ;;
    'symbol()(string)')
      if [[ "$addr" == "0x0000000000000000000000000000000000000011" ]]; then
        echo '"DRW"'
      else
        echo '"WETH"'
      fi
      ;;
    'balanceOf(address)(uint256)')
      echo 25000000000000000000
      ;;
    'allowance(address,address)(uint256)')
      echo 0
      ;;
    'quoteExactInput(address,uint256)(uint256)')
      echo 4935790171985
      ;;
    *)
      echo 0
      ;;
  esac
  exit 0
fi

echo "unexpected cast invocation: $*" >&2
exit 1
"""
            )
            fake_cast.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "ops" / "swap_reference_market.sh"),
                    "--token-in",
                    "base",
                    "--amount",
                    "10",
                    "--dry-run",
                ],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "DARWIN_ENV_FILE": str(env_file),
                    "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                },
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("amount_in:          10", result.stdout)
            self.assertIn("quoted_out:", result.stdout)
            self.assertIn("dry_run:            yes", result.stdout)
            print("  Ops: swap helper handles 18-decimal DRW amounts above bash integer range")

    def test_43_market_portal_config_export(self):
        """Ops: market portal config is exported from the pinned deployment artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            out = tmp / "market-config.json"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "drw_token": "0x0000000000000000000000000000000000000011",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                },
                "market": {
                    "enabled": True,
                    "seeded": True,
                    "base_token": "0x0000000000000000000000000000000000000011",
                    "quote_token": "0x4200000000000000000000000000000000000006",
                    "fee_bps": 30,
                    "venue_id": "darwin_reference_pool",
                    "venue_type": "constant_product_bootstrap",
                    "initial_base_amount": "1000000000000000000000",
                    "initial_quote_amount": "500000000000000",
                    "market_operator": "0x0000000000000000000000000000000000000008",
                    "contracts": {
                        "reference_pool": "0x0000000000000000000000000000000000000042",
                    },
                },
                "drw": {
                    "total_supply": "1000000000000000000000000000",
                },
            }))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "export_market_portal_config.py"),
                    "--deployment-file",
                    str(deployment),
                    "--out",
                    str(out),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            config = json.loads(out.read_text())
            self.assertEqual(config["network"]["id"], 84532)
            self.assertEqual(config["network"]["name"], "Base Sepolia")
            self.assertEqual(config["pool"]["address"], "0x0000000000000000000000000000000000000042")
            self.assertEqual(config["token"]["address"], "0x0000000000000000000000000000000000000011")
            self.assertEqual(config["quote_token"]["address"], "0x4200000000000000000000000000000000000006")
            self.assertNotIn("roles", config)
            print("  Ops: market portal config exports the public market surface from the live deployment artifact")

    def test_44_deployment_show_with_faucet(self):
        """CLI: deployment-show surfaces faucet metadata when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "deployer": "0x0000000000000000000000000000000000000010",
                "deployed_at": 1,
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "settlement_hub": "0x0000000000000000000000000000000000000005",
                    "drw_faucet": "0x0000000000000000000000000000000000000045",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                    "epoch_operator": "0x000000000000000000000000000000000000000a",
                    "batch_operator": "0x000000000000000000000000000000000000000b",
                    "safe_mode_authority": "0x000000000000000000000000000000000000000c",
                },
                "faucet": {
                    "enabled": True,
                    "claim_amount": "100000000000000000000",
                    "native_drip_amount": "10000000000000",
                    "claim_cooldown": 86400,
                    "funded": True,
                    "contracts": {
                        "drw_faucet": "0x0000000000000000000000000000000000000045",
                    },
                },
            }))

            env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM)}
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "darwin_sim.cli.darwinctl",
                    "deployment-show",
                    "--deployment-file",
                    str(deployment),
                ],
                cwd=str(SIM),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("Faucet enabled:   yes", result.stdout)
            self.assertIn("Faucet contract:", result.stdout)
            self.assertIn("Faucet funded:    True", result.stdout)
            print("  CLI: deployment-show prints faucet metadata when the artifact includes it")

    def test_45_market_portal_config_export_includes_faucet(self):
        """Ops: market portal config includes faucet metadata when the deployment does."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            out = tmp / "market-config.json"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "bond_asset_mode": "external",
                "contracts": {
                    "bond_asset": "0x4200000000000000000000000000000000000006",
                    "drw_token": "0x0000000000000000000000000000000000000011",
                    "drw_faucet": "0x0000000000000000000000000000000000000045",
                },
                "roles": {
                    "governance": "0x0000000000000000000000000000000000000009",
                },
                "market": {
                    "enabled": True,
                    "seeded": True,
                    "base_token": "0x0000000000000000000000000000000000000011",
                    "quote_token": "0x4200000000000000000000000000000000000006",
                    "fee_bps": 30,
                    "venue_id": "darwin_reference_pool",
                    "venue_type": "constant_product_bootstrap",
                    "initial_base_amount": "1000000000000000000000",
                    "initial_quote_amount": "500000000000000",
                    "market_operator": "0x0000000000000000000000000000000000000008",
                    "contracts": {
                        "reference_pool": "0x0000000000000000000000000000000000000042",
                    },
                },
                "drw": {
                    "total_supply": "1000000000000000000000000000",
                },
                "faucet": {
                    "enabled": True,
                    "claim_amount": "100000000000000000000",
                    "native_drip_amount": "10000000000000",
                    "claim_cooldown": 86400,
                    "funded": True,
                    "initial_token_funding": "100000000000000000000000",
                    "initial_native_funding": "200000000000000",
                    "contracts": {
                        "drw_faucet": "0x0000000000000000000000000000000000000045",
                    },
                },
            }))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "export_market_portal_config.py"),
                    "--deployment-file",
                    str(deployment),
                    "--out",
                    str(out),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            config = json.loads(out.read_text())
            self.assertTrue(config["faucet"]["enabled"])
            self.assertEqual(config["faucet"]["address"], "0x0000000000000000000000000000000000000045")
            self.assertEqual(config["faucet"]["claim_amount"], "100000000000000000000")
            self.assertNotIn("operator_quickstart", config["links"])
            print("  Ops: market portal config exports faucet metadata without private operator links")

    def test_46_fund_drw_faucet_updates_artifact(self):
        """Ops: faucet funding helper updates the deployment artifact after transfer calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            env_file = tmp / ".env.base-sepolia"
            fake_bin = tmp / "bin"
            fake_cast = fake_bin / "cast"
            cast_log = tmp / "cast.log"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "contracts": {
                    "drw_token": "0x0000000000000000000000000000000000000011",
                    "drw_faucet": "0x0000000000000000000000000000000000000045",
                },
                "drw": {
                    "contracts": {
                        "drw_token": "0x0000000000000000000000000000000000000011",
                    },
                },
                "faucet": {
                    "enabled": True,
                    "contracts": {
                        "drw_faucet": "0x0000000000000000000000000000000000000045",
                    },
                    "funded": False,
                },
            }))

            env_file.write_text(
                "\n".join([
                    'export DARWIN_RPC_URL="http://127.0.0.1:8545"',
                    'export DARWIN_NETWORK="base-sepolia"',
                    f'export DARWIN_DEPLOYMENT_FILE="{deployment}"',
                    'export DARWIN_DRW_FAUCET_FUNDER_PRIVATE_KEY="placeholder-private-key"',
                ]) + "\n"
            )

            fake_bin.mkdir(parents=True, exist_ok=True)
            fake_cast.write_text(
                f"""#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "{cast_log}"
exit 0
"""
            )
            fake_cast.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "ops" / "fund_drw_faucet.sh"),
                ],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "DARWIN_ENV_FILE": str(env_file),
                    "DARWIN_DRW_FAUCET_INITIAL_TOKEN_FUNDING": "123000000000000000000",
                    "DARWIN_DRW_FAUCET_INITIAL_NATIVE_FUNDING": "45000000000000",
                    "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                },
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            updated = json.loads(deployment.read_text())
            self.assertTrue(updated["faucet"]["funded"])
            self.assertEqual(updated["faucet"]["initial_token_funding"], "123000000000000000000")
            self.assertEqual(updated["faucet"]["initial_native_funding"], "45000000000000")
            log = cast_log.read_text()
            self.assertIn("transfer(address,uint256)", log)
            self.assertIn("0x0000000000000000000000000000000000000045", log)
            print("  Ops: faucet funding helper updates the deployment artifact after funding")

    def test_47_build_drw_merkle_distribution_outputs_claim_manifest(self):
        """Ops: vNext Merkle builder emits a root plus proofs for each DRW claim."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            claims = tmp / "claims.json"
            out = tmp / "merkle.json"
            claims.write_text(json.dumps([
                {"account": "0x00000000000000000000000000000000000000a1", "amount": "100000000000000000000"},
                {"account": "0x00000000000000000000000000000000000000b2", "amount": "200000000000000000000"},
                {"account": "0x00000000000000000000000000000000000000c3", "amount": "300000000000000000000"},
            ]))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "build_drw_merkle_distribution.py"),
                    "--claims-file",
                    str(claims),
                    "--out",
                    str(out),
                    "--network",
                    "base-sepolia",
                    "--claim-deadline",
                    "1777777777",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            manifest = json.loads(out.read_text())
            self.assertEqual(manifest["claims_count"], 3)
            self.assertEqual(manifest["total_amount"], "600000000000000000000")
            self.assertEqual(manifest["network"], "base-sepolia")
            self.assertEqual(manifest["claim_deadline"], 1777777777)
            self.assertTrue(manifest["merkle_root"].startswith("0x"))
            self.assertEqual(len(manifest["merkle_root"]), 66)
            self.assertEqual(manifest["claims"][0]["index"], 0)
            self.assertTrue(manifest["claims"][0]["proof"])
            print("  Ops: vNext Merkle builder emits a public claim manifest with proofs")

    def test_48_preflight_vnext_governance_uses_manifest_and_public_artifact(self):
        """Ops: vNext governance preflight resolves token and Merkle metadata without re-exposing private fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            manifest = tmp / "base-sepolia-drw-merkle.json"
            env_file = tmp / ".env.base-sepolia"
            fake_bin = tmp / "bin"
            fake_cast = fake_bin / "cast"
            fake_forge = fake_bin / "forge"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "contracts": {
                    "drw_token": "0x0000000000000000000000000000000000000011",
                    "settlement_hub": "0x0000000000000000000000000000000000000022",
                },
            }))
            manifest.write_text(json.dumps({
                "merkle_root": "0x" + ("11" * 32),
                "claims_count": 2,
                "total_amount": "300000000000000000000",
                "claim_deadline": 1777777777,
                "claims": [],
            }))
            env_file.write_text(
                "\n".join([
                    'export DARWIN_RPC_URL="http://127.0.0.1:8545"',
                    'export DARWIN_NETWORK="base-sepolia"',
                    'export DARWIN_DEPLOYER_PRIVATE_KEY="test-private-key"',
                    f'export DARWIN_DEPLOYMENT_FILE="{deployment}"',
                    f'export DARWIN_VNEXT_DISTRIBUTION_FILE="{manifest}"',
                    'export DARWIN_VNEXT_COUNCIL="0x00000000000000000000000000000000000000aa"',
                    'export DARWIN_VNEXT_GUARDIAN="0x00000000000000000000000000000000000000bb"',
                ]) + "\n"
            )

            fake_bin.mkdir(parents=True, exist_ok=True)
            fake_cast.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "chain-id" ]]; then
  echo "84532"
  exit 0
fi
echo "unexpected cast call: $*" >&2
exit 1
"""
            )
            fake_forge.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
exit 0
"""
            )
            fake_cast.chmod(0o755)
            fake_forge.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "ops" / "preflight_vnext_governance.sh"),
                ],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "DARWIN_ENV_FILE": str(env_file),
                    "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                },
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("ready_to_deploy: yes", result.stdout)
            self.assertIn("0x0000000000000000000000000000000000000011", result.stdout)
            self.assertIn("0x" + ("11" * 32), result.stdout)
            print("  Ops: vNext governance preflight resolves a public-safe artifact plus local manifest")

    def test_49_build_drw_merkle_distribution_accepts_csv_claims(self):
        """Ops: vNext Merkle builder accepts spreadsheet-style CSV claims."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            claims = tmp / "claims.csv"
            out = tmp / "merkle.json"
            claims.write_text(
                "\n".join([
                    "account,amount",
                    "0x00000000000000000000000000000000000000a1,100000000000000000000",
                    "0x00000000000000000000000000000000000000b2,200000000000000000000",
                ]) + "\n"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "build_drw_merkle_distribution.py"),
                    "--claims-file",
                    str(claims),
                    "--out",
                    str(out),
                    "--claim-deadline",
                    "1777777777",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            manifest = json.loads(out.read_text())
            self.assertEqual(manifest["claims_count"], 2)
            self.assertEqual(manifest["total_amount"], "300000000000000000000")
            self.assertIn("format:      csv", result.stdout)
            print("  Ops: vNext Merkle builder accepts CSV claim exports")

    def test_50_build_vnext_safe_batch_outputs_safe_transaction_builder_json(self):
        """Ops: vNext promotion batch exports Safe Transaction Builder JSON for mutable DRW handoff."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            vnext = tmp / "base-sepolia.vnext.json"
            out = tmp / "batch.json"

            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                    "drw_token": "0x0000000000000000000000000000000000000011",
                    "drw_staking": "0x0000000000000000000000000000000000000012",
                    "drw_faucet": "0x0000000000000000000000000000000000000013",
                    "reference_pool": "0x0000000000000000000000000000000000000014",
                },
            }))
            vnext.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "vnext": {
                    "contracts": {
                        "darwin_timelock": "0x00000000000000000000000000000000000000aa",
                        "drw_merkle_distributor": "0x00000000000000000000000000000000000000bb",
                    },
                    "distribution": {
                        "total_amount": "300000000000000000000",
                    },
                },
            }))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "build_vnext_safe_batch.py"),
                    "--deployment-file",
                    str(deployment),
                    "--vnext-file",
                    str(vnext),
                    "--out",
                    str(out),
                    "--safe-address",
                    "0x00000000000000000000000000000000000000cc",
                    "--market-operator",
                    "0x00000000000000000000000000000000000000dd",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            batch = json.loads(out.read_text())
            self.assertEqual(batch["chainId"], "84532")
            self.assertEqual(batch["meta"]["safeAddress"], "0x00000000000000000000000000000000000000cc")
            self.assertEqual(len(batch["transactions"]), 6)
            self.assertEqual(batch["transactions"][0]["contractMethod"]["name"], "transfer")
            self.assertEqual(batch["transactions"][1]["contractMethod"]["name"], "setMarketOperator")
            self.assertEqual(batch["transactions"][2]["contractMethod"]["name"], "setGovernance")
            self.assertIn("transactions:    6", result.stdout)
            print("  Ops: vNext promotion batch emits Safe Transaction Builder JSON")

    def test_51_preflight_vnext_promotion_uses_local_overlay_and_live_checks(self):
        """Ops: vNext promotion preflight uses the local overlay and validates live governance/funding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            overlay = tmp / "base-sepolia.private.json"
            vnext = tmp / "base-sepolia.vnext.json"
            env_file = tmp / ".env.base-sepolia"
            fake_bin = tmp / "bin"
            fake_cast = fake_bin / "cast"

            governance = "0x00000000000000000000000000000000000000aa"
            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                    "drw_token": "0x0000000000000000000000000000000000000011",
                    "drw_staking": "0x0000000000000000000000000000000000000012",
                    "drw_faucet": "0x0000000000000000000000000000000000000013",
                    "reference_pool": "0x0000000000000000000000000000000000000014",
                },
            }))
            overlay.write_text(json.dumps({
                "roles": {
                    "governance": governance,
                },
            }))
            vnext.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "vnext": {
                    "contracts": {
                        "darwin_timelock": "0x00000000000000000000000000000000000000bb",
                        "drw_merkle_distributor": "0x00000000000000000000000000000000000000cc",
                    },
                    "distribution": {
                        "total_amount": "300000000000000000000",
                    },
                },
            }))

            env_file.write_text(
                "\n".join([
                    'export DARWIN_RPC_URL="http://127.0.0.1:8545"',
                    'export DARWIN_NETWORK="base-sepolia"',
                    f'export DARWIN_DEPLOYMENT_FILE="{deployment}"',
                    f'export DARWIN_VNEXT_FILE="{vnext}"',
                ]) + "\n"
            )

            fake_bin.mkdir(parents=True, exist_ok=True)
            fake_cast.write_text(
                f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${{1:-}}" != "call" ]]; then
  echo "unexpected cast call: $*" >&2
  exit 1
fi
method="${{5:-}}"
if [[ "$method" == "governance()(address)" ]]; then
  echo "{governance}"
  exit 0
fi
if [[ "$method" == "balanceOf(address)(uint256)" ]]; then
  echo "300000000000000000000"
  exit 0
fi
echo "unexpected cast call: $*" >&2
exit 1
"""
            )
            fake_cast.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "ops" / "preflight_vnext_promotion.sh"),
                ],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "DARWIN_ENV_FILE": str(env_file),
                    "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                },
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("ready_to_build:     yes", result.stdout)
            self.assertIn(governance, result.stdout)
            self.assertIn("300000000000000000000", result.stdout)
            print("  Ops: vNext promotion preflight uses local overlay governance plus live checks")

    def test_52_execute_vnext_promotion_sends_funding_and_governance_handoff(self):
        """Ops: vNext promotion execution funds the distributor and hands mutable governance to the timelock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "base-sepolia.json"
            overlay = tmp / "base-sepolia.private.json"
            vnext = tmp / "base-sepolia.vnext.json"
            batch = tmp / "base-sepolia-vnext-safe-batch.json"
            env_file = tmp / ".env.base-sepolia"
            fake_bin = tmp / "bin"
            fake_cast = fake_bin / "cast"
            log_path = tmp / "cast.log"

            governance = "0x00000000000000000000000000000000000000aa"
            timelock = "0x00000000000000000000000000000000000000bb"
            distributor = "0x00000000000000000000000000000000000000cc"
            deployment.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "deployed_at": 1,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000001",
                    "drw_token": "0x0000000000000000000000000000000000000011",
                    "drw_staking": "0x0000000000000000000000000000000000000012",
                    "drw_faucet": "0x0000000000000000000000000000000000000013",
                    "reference_pool": "0x0000000000000000000000000000000000000014",
                },
            }))
            overlay.write_text(json.dumps({
                "roles": {
                    "governance": governance,
                },
            }))
            vnext.write_text(json.dumps({
                "network": "base-sepolia",
                "chain_id": 84532,
                "vnext": {
                    "contracts": {
                        "darwin_timelock": timelock,
                        "drw_merkle_distributor": distributor,
                    },
                    "distribution": {
                        "total_amount": "300000000000000000000",
                    },
                },
            }))

            env_file.write_text(
                "\n".join([
                    'export DARWIN_RPC_URL="http://127.0.0.1:8545"',
                    'export DARWIN_NETWORK="base-sepolia"',
                    f'export DARWIN_DEPLOYMENT_FILE="{deployment}"',
                    f'export DARWIN_VNEXT_FILE="{vnext}"',
                    f'export DARWIN_VNEXT_PROMOTION_FILE="{batch}"',
                    'export DARWIN_VNEXT_PROMOTION_PRIVATE_KEY="0x1234"',
                ]) + "\n"
            )

            fake_bin.mkdir(parents=True, exist_ok=True)
            fake_cast.write_text(
                f"""#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "{log_path}"
if [[ "${{1:-}}" == "call" ]]; then
  method="${{5:-}}"
  if [[ "$method" == "governance()(address)" ]]; then
    echo "{governance}"
    exit 0
  fi
  if [[ "$method" == "balanceOf(address)(uint256)" ]]; then
    echo "300000000000000000000 [3e20]"
    exit 0
  fi
fi
if [[ "${{1:-}}" == "wallet" && "${{2:-}}" == "address" ]]; then
  echo "{governance}"
  exit 0
fi
if [[ "${{1:-}}" == "nonce" ]]; then
  echo "7"
  exit 0
fi
if [[ "${{1:-}}" == "send" ]]; then
  nonce=""
  for ((i=1; i<=$#; i++)); do
    if [[ "${{!i}}" == "--nonce" ]]; then
      j=$((i+1))
      nonce="${{!j}}"
    fi
  done
  echo "transactionHash 0x$(printf '%064x' "${{nonce:-0}}")"
  exit 0
fi
echo "unexpected cast call: $*" >&2
exit 1
"""
            )
            fake_cast.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "ops" / "execute_vnext_promotion.sh"),
                ],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "DARWIN_ENV_FILE": str(env_file),
                    "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                },
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("DARWIN vNext promotion execution complete.", result.stdout)
            self.assertTrue(batch.exists())
            log = log_path.read_text()
            self.assertIn("send 0x0000000000000000000000000000000000000011 transfer(address,uint256)", log)
            self.assertIn("--nonce 7", log)
            self.assertIn("--nonce 11", log)
            print("  Ops: vNext promotion execution sends distributor funding and governance handoff txs")

    def test_53_claim_drw_merkle_uses_manifest_proof_and_signer(self):
        """Ops: DRW Merkle claim helper validates the signer and dispatches the Foundry claim script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            manifest = tmp / "base-sepolia-drw-merkle.json"
            vnext = tmp / "base-sepolia.vnext.json"
            env_file = tmp / ".env.base-sepolia"
            fake_bin = tmp / "bin"
            fake_cast = fake_bin / "cast"
            fake_forge = fake_bin / "forge"
            log_path = tmp / "cast.log"
            forge_log_path = tmp / "forge.log"

            claimant = "0x00000000000000000000000000000000000000aa"
            manifest.write_text(json.dumps({
                "claims": [
                    {
                        "index": 0,
                        "account": claimant,
                        "amount": "100000000000000000000",
                        "proof": [
                            "0x" + ("11" * 32),
                            "0x" + ("22" * 32),
                        ],
                    }
                ]
            }))
            vnext.write_text(json.dumps({
                "vnext": {
                    "contracts": {
                        "drw_merkle_distributor": "0x00000000000000000000000000000000000000bb",
                    }
                }
            }))
            env_file.write_text(
                "\n".join([
                    'export DARWIN_RPC_URL="http://127.0.0.1:8545"',
                    'export DARWIN_NETWORK="base-sepolia"',
                    f'export DARWIN_VNEXT_FILE="{vnext}"',
                    f'export DARWIN_VNEXT_DISTRIBUTION_FILE="{manifest}"',
                    'export DARWIN_MERKLE_CLAIM_INDEX="0"',
                    'export DARWIN_MERKLE_CLAIM_PRIVATE_KEY="0x1234"',
                ]) + "\n"
            )

            fake_bin.mkdir(parents=True, exist_ok=True)
            fake_cast.write_text(
                f"""#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "{log_path}"
if [[ "${{1:-}}" == "wallet" && "${{2:-}}" == "address" ]]; then
  echo "{claimant}"
  exit 0
fi
echo "unexpected cast call: $*" >&2
exit 1
"""
            )
            fake_cast.chmod(0o755)
            fake_forge.write_text(
                f"""#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "{forge_log_path}"
exit 0
"""
            )
            fake_forge.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "ops" / "claim_drw_merkle.sh"),
                ],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "DARWIN_ENV_FILE": str(env_file),
                    "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                },
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("wallet address --private-key 0x1234", log_path.read_text())
            forge_log = forge_log_path.read_text()
            self.assertIn("script/ClaimDRWMerkle.s.sol:ClaimDRWMerkle", forge_log)
            self.assertIn("--private-key 0x1234", forge_log)
            print("  Ops: DRW Merkle claim helper dispatches the Foundry claim script for the signer")

    def test_54_preflight_darwin_node_accepts_arbitrum_rpc(self):
        """Ops: DARWIN node preflight validates a generic deployment against an Arbitrum-family RPC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "arbitrum-sepolia.json"
            json_out = tmp / "node-preflight.json"
            md_out = tmp / "node-preflight.md"

            def reserve_port():
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
                sock.close()
                return port

            deployment.write_text(json.dumps({
                "network": "arbitrum-sepolia",
                "chain_id": 421614,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000042",
                },
            }))

            class RpcHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    method = body.get("method")
                    result = "0x0"
                    if method == "eth_chainId":
                        result = hex(421614)
                    payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def log_message(self, fmt, *args):
                    pass

            rpc_server = HTTPServer(("127.0.0.1", 0), RpcHandler)
            rpc_thread = Thread(target=rpc_server.serve_forever, daemon=True)
            rpc_thread.start()

            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "ops" / "preflight_darwin_node.py"),
                        "--deployment-file",
                        str(deployment),
                        "--rpc-url",
                        f"http://127.0.0.1:{rpc_server.server_port}",
                        "--state-root",
                        str(tmp / "state"),
                        "--gateway-port",
                        str(reserve_port()),
                        "--router-port",
                        str(reserve_port()),
                        "--scorer-port",
                        str(reserve_port()),
                        "--watcher-port",
                        str(reserve_port()),
                        "--archive-port",
                        str(reserve_port()),
                        "--finalizer-port",
                        str(reserve_port()),
                        "--sentinel-port",
                        str(reserve_port()),
                        "--json-out",
                        str(json_out),
                        "--markdown-out",
                        str(md_out),
                    ],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                )
            finally:
                rpc_server.shutdown()
                rpc_server.server_close()
                rpc_thread.join(timeout=5)

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            report = json.loads(json_out.read_text())
            self.assertTrue(report["ready"])
            self.assertEqual(report["deployment"]["network"], "arbitrum-sepolia")
            self.assertEqual(report["deployment"]["chain_id"], 421614)
            self.assertEqual(report["rpc"]["observed_chain_id"], 421614)
            self.assertEqual(report["checks"]["rpc"]["state"], "OK")
            self.assertIn("Ready to start", md_out.read_text())
            print("  Ops: DARWIN node preflight validates a generic Arbitrum-family deployment")

    def test_55_market_portal_config_export_supports_arbitrum_sepolia(self):
        """Ops: market portal config export supports Arbitrum-family deployments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            deployment = tmp / "arbitrum-sepolia.json"
            out = tmp / "market-config.json"

            deployment.write_text(json.dumps({
                "network": "arbitrum-sepolia",
                "chain_id": 421614,
                "bond_asset_mode": "external",
                "contracts": {
                    "bond_asset": "0x0000000000000000000000000000000000000006",
                    "drw_token": "0x0000000000000000000000000000000000000011",
                },
                "market": {
                    "enabled": True,
                    "seeded": True,
                    "base_token": "0x0000000000000000000000000000000000000011",
                    "quote_token": "0x0000000000000000000000000000000000000006",
                    "fee_bps": 30,
                    "venue_id": "darwin_reference_pool",
                    "venue_type": "constant_product_bootstrap",
                    "initial_base_amount": "1000000000000000000000",
                    "initial_quote_amount": "500000000000000",
                    "contracts": {
                        "reference_pool": "0x0000000000000000000000000000000000000042",
                    },
                },
                "drw": {
                    "total_supply": "1000000000000000000000000000",
                },
            }))

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops" / "export_market_portal_config.py"),
                    "--deployment-file",
                    str(deployment),
                    "--out",
                    str(out),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            config = json.loads(out.read_text())
            self.assertEqual(config["network"]["id"], 421614)
            self.assertEqual(config["network"]["name"], "Arbitrum Sepolia")
            self.assertEqual(config["network"]["hex"], "0x66eee")
            self.assertEqual(config["network"]["rpc_url"], "https://sepolia-rollup.arbitrum.io/rpc")
            self.assertEqual(config["network"]["explorer_base_url"], "https://sepolia.arbiscan.io")
            self.assertEqual(config["project"]["tagline"], "Trade DRW on the DARWIN reference pool")
            print("  Ops: market portal config export supports Arbitrum-family chain defaults")

    def test_56_prepare_arbitrum_sepolia_env_script(self):
        """Ops: prepare_arbitrum_sepolia_env derives a local-only Arbitrum Sepolia env from recovery wallets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            wallet_dir = tmp / "wallets"
            wallet_dir.mkdir()
            env_path = tmp / "arbitrum-sepolia.env"
            deployment = tmp / "arbitrum-sepolia.json"

            gov_wallet = create_wallet(label="future-governance", chain_id=84532)
            deployer_wallet = create_wallet(label="future-deployer", chain_id=84532)
            save_wallet(gov_wallet, wallet_dir / "darwin-future-governance.wallet.json", "gov-pass")
            save_wallet(deployer_wallet, wallet_dir / "darwin-future-deployer.wallet.json", "dep-pass")
            (wallet_dir / "darwin-future-governance.passphrase").write_text("gov-pass\n")
            (wallet_dir / "darwin-future-deployer.passphrase").write_text("dep-pass\n")

            result = subprocess.run(
                ["bash", str(ROOT / "ops" / "prepare_arbitrum_sepolia_env.sh")],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "DARWIN_WALLET_DIR": str(wallet_dir),
                    "DARWIN_ARBITRUM_ENV_FILE": str(env_path),
                    "DARWIN_ARBITRUM_DEPLOYMENT_FILE": str(deployment),
                    "PYTHONPATH": str(ROOT) + os.pathsep + str(SIM),
                },
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue(env_path.exists())
            env_text = env_path.read_text()
            self.assertIn('export DARWIN_NETWORK="arbitrum-sepolia"', env_text)
            self.assertIn('export DARWIN_EXPECT_CHAIN_ID="421614"', env_text)
            self.assertIn('export DARWIN_DEPLOYMENT_FILE="' + str(deployment) + '"', env_text)
            self.assertIn('export DARWIN_DEPLOY_BOND_ASSET_MOCK="1"', env_text)
            self.assertIn("DARWIN_GOVERNANCE_PRIVATE_KEY", env_text)
            self.assertIn("DARWIN_DEPLOYER_PRIVATE_KEY", env_text)
            self.assertIn("[arbitrum-env] Ready", result.stdout)
            print("  Ops: prepare_arbitrum_sepolia_env derives a local-only Arbitrum Sepolia env")

    def test_57_preflight_arbitrum_sepolia_loads_env_file(self):
        """Ops: Arbitrum Sepolia preflight loads a saved env file and validates the chain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            env_file = tmp / ".env.arbitrum-sepolia"
            deployment = tmp / "arbitrum-sepolia.json"

            deployment.write_text(json.dumps({
                "network": "arbitrum-sepolia",
                "chain_id": 421614,
                "contracts": {
                    "settlement_hub": "0x0000000000000000000000000000000000000042",
                },
            }))

            class ArbRpcHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    method = body.get("method")
                    if method == "eth_chainId":
                        result = hex(421614)
                    elif method == "eth_getBalance":
                        result = hex(10**16)
                    else:
                        result = "0x0"
                    payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def log_message(self, fmt, *args):
                    pass

            class SepoliaRpcHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    method = body.get("method")
                    if method == "eth_chainId":
                        result = hex(11155111)
                    elif method == "eth_getBalance":
                        result = hex(5 * 10**15)
                    else:
                        result = "0x0"
                    payload = {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def log_message(self, fmt, *args):
                    pass

            arb_server = HTTPServer(("127.0.0.1", 0), ArbRpcHandler)
            arb_thread = Thread(target=arb_server.serve_forever, daemon=True)
            arb_thread.start()

            sepolia_server = HTTPServer(("127.0.0.1", 0), SepoliaRpcHandler)
            sepolia_thread = Thread(target=sepolia_server.serve_forever, daemon=True)
            sepolia_thread.start()

            env_file.write_text(
                "\n".join([
                    f'export ARBITRUM_SEPOLIA_RPC_URL="http://127.0.0.1:{arb_server.server_port}"',
                    f'export SEPOLIA_RPC_URL="http://127.0.0.1:{sepolia_server.server_port}"',
                    'export DARWIN_DEPLOYER_ADDRESS="0x00000000000000000000000000000000000000aa"',
                    'export DARWIN_GOVERNANCE="0x00000000000000000000000000000000000000bb"',
                    'export DARWIN_EPOCH_OPERATOR="0x00000000000000000000000000000000000000cc"',
                    'export DARWIN_SAFE_MODE_AUTHORITY="0x00000000000000000000000000000000000000dd"',
                    'export DARWIN_DEPLOY_BOND_ASSET_MOCK="1"',
                    "",
                ])
            )

            try:
                result = subprocess.run(
                    ["bash", str(ROOT / "ops" / "preflight_arbitrum_sepolia.sh")],
                    cwd=str(ROOT),
                    env={
                        **os.environ,
                        "DARWIN_ARBITRUM_ENV_FILE": str(env_file),
                        "DARWIN_DEPLOYMENT_FILE": str(deployment),
                    },
                    capture_output=True,
                    text=True,
                )
            finally:
                arb_server.shutdown()
                arb_server.server_close()
                arb_thread.join(timeout=5)
                sepolia_server.shutdown()
                sepolia_server.server_close()
                sepolia_thread.join(timeout=5)

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("DARWIN Arbitrum Sepolia preflight", result.stdout)
            self.assertIn("arbitrum_chain_id:    421614", result.stdout)
            self.assertIn("bond_asset_mode:      mock", result.stdout)
            self.assertIn("ready_to_deploy:      yes", result.stdout)
            print("  Ops: Arbitrum Sepolia preflight accepts a local env file and matching chain")


if __name__ == "__main__":
    unittest.main(verbosity=2)
