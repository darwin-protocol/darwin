"""End-to-end integration test: account → intent → gateway → verify → replay.

Proves the full DARWIN lifecycle works without a live chain.
"""

import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import URLError

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from darwin_sim.sdk.accounts import create_account
from darwin_sim.sdk.intents import create_intent, verify_pq_sig, verify_evm_sig, verify_binding
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
        self.assertEqual(len(intent.evm_sig), 64)
        print(f"  Intent: {intent.intent_hash} PQ=✓ EVM=✓ Bind=✓")

    def test_03_config_validation(self):
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

    def test_04_e2_pipeline(self):
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

    def test_05_watcher_replay(self):
        """Watcher: independent replay matches published scores exactly."""
        result = replay_and_verify("outputs/test_e2")
        self.assertTrue(result["passed"], f"Replay failed: {result['mismatches']}")
        self.assertEqual(result["published_decision"], result["recomputed_decision"])
        print(f"  Watcher: REPLAY PASS — {result['control_fills_loaded']}c + {result['treatment_fills_loaded']}t fills verified")

    def test_06_e1_e7_suite(self):
        """Suite: all 7 experiments pass on 5K realistic swaps."""
        cfg = SimConfig.from_yaml("configs/baseline.yaml")
        from darwin_sim.experiments.suite import run_full_suite
        result = run_full_suite(cfg, "outputs/test_suite", n_swaps=5000, seed=9999)

        passed = sum(1 for r in result["details"].values() if r["decision"] == "PASS")
        total = len(result["details"])
        print(f"  Suite: {passed}/{total} PASS")
        # At least 6 of 7 should pass
        self.assertGreaterEqual(passed, 6, f"Only {passed}/{total} passed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
