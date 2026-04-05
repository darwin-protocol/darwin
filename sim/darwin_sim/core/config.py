"""Load and validate DARWIN simulator config from YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(slots=True)
class SpeciesCfg:
    id: str = ""
    kind: str = ""
    enabled: bool = True
    canary: bool = False
    batch_window_sec: int = 5


@dataclass(slots=True)
class WeightCoefficients:
    trader_surplus: float = 0.35
    lp_return: float = 0.20
    fill_rate: float = 0.15
    revenue: float = 0.10
    adverse_markout: float = 0.12
    risk_penalty: float = 0.08

    def __post_init__(self):
        total = (self.trader_surplus + self.lp_return + self.fill_rate
                 + self.revenue + self.adverse_markout + self.risk_penalty)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weight coefficients must sum to 1.0, got {total:.4f}")


@dataclass(slots=True)
class ScoringCfg:
    entity_cap_bps: int = 1500
    trim_alpha_bps: int = 500
    min_external_fills: int = 25
    markout_horizon_sec: int = 60
    fee_floor_bps: float = 2.0
    protocol_notional_floor_bps: float = 0.5
    weights: WeightCoefficients = field(default_factory=WeightCoefficients)


@dataclass(slots=True)
class RebalanceCfg:
    soft_idle_drift_bps: int = 15
    soft_rebalance_bps: int = 50
    hard_rebalance_bps: int = 200
    gain_bps: int = 2500
    forced_batches: int = 4
    max_hard_breaches: int = 2

    @property
    def kappa_reb(self) -> float:
        """gain_bps / 10000 — the ONLY valid decoding."""
        return self.gain_bps / 10_000

    @property
    def theta_soft_idle(self) -> float:
        return self.soft_idle_drift_bps / 10_000

    @property
    def theta_soft(self) -> float:
        return self.soft_rebalance_bps / 10_000

    @property
    def theta_hard(self) -> float:
        return self.hard_rebalance_bps / 10_000


@dataclass(slots=True)
class RoutingCfg:
    policy: str = "softmax"
    beta_default: float = 2.0
    epsilon_default: float = 0.08
    novelty_bonus_x1e6: int = 25000
    canary_weight_cap_bps: int = 500


@dataclass(slots=True)
class EpochsCfg:
    duration_sec: int = 3600
    warmup_epochs: int = 6
    control_share_bps_default: int = 1500


@dataclass(slots=True)
class SimConfig:
    suite_id: str = "darwin-sim-v0.4"
    pairs: list[str] = field(default_factory=lambda: ["ETH_USDC"])
    species: list[SpeciesCfg] = field(default_factory=list)
    epochs: EpochsCfg = field(default_factory=EpochsCfg)
    routing: RoutingCfg = field(default_factory=RoutingCfg)
    scoring: ScoringCfg = field(default_factory=ScoringCfg)
    rebalance: RebalanceCfg = field(default_factory=RebalanceCfg)

    @staticmethod
    def from_yaml(path: str | Path) -> SimConfig:
        path = Path(path)
        with path.open() as f:
            raw = yaml.safe_load(f)

        cfg = SimConfig()
        cfg.suite_id = raw.get("suite_id", cfg.suite_id)
        cfg.pairs = raw.get("pairs", cfg.pairs)

        # species
        cfg.species = []
        for s in raw.get("species", []):
            cfg.species.append(SpeciesCfg(
                id=s["id"],
                kind=s["kind"],
                enabled=s.get("enabled", True),
                canary=s.get("canary", False),
                batch_window_sec=s.get("batch_window_sec", 5),
            ))

        # epochs
        ep = raw.get("epochs", {})
        cfg.epochs = EpochsCfg(
            duration_sec=ep.get("duration_sec", 3600),
            warmup_epochs=ep.get("warmup_epochs", 6),
            control_share_bps_default=ep.get("control_share_bps_default", 1500),
        )

        # routing
        rt = raw.get("routing", {})
        cfg.routing = RoutingCfg(
            policy=rt.get("policy", "softmax"),
            beta_default=rt.get("beta_default", 2.0),
            epsilon_default=rt.get("epsilon_default", 0.08),
            novelty_bonus_x1e6=rt.get("novelty_bonus_x1e6", 25000),
            canary_weight_cap_bps=rt.get("canary_weight_cap_bps", 500),
        )

        # scoring
        sc = raw.get("scoring", {})
        wc = sc.get("weight_coefficients", {})
        cfg.scoring = ScoringCfg(
            entity_cap_bps=sc.get("entity_cap_bps", 1500),
            trim_alpha_bps=sc.get("trim_alpha_bps", 500),
            min_external_fills=sc.get("min_external_fills", 25),
            markout_horizon_sec=sc.get("markout_horizon_sec", 60),
            fee_floor_bps=sc.get("fee_floor_bps", 2.0),
            protocol_notional_floor_bps=sc.get("protocol_notional_floor_bps", 0.5),
            weights=WeightCoefficients(
                trader_surplus=wc.get("trader_surplus", 0.35),
                lp_return=wc.get("lp_return", 0.20),
                fill_rate=wc.get("fill_rate", 0.15),
                revenue=wc.get("revenue", 0.10),
                adverse_markout=wc.get("adverse_markout", 0.12),
                risk_penalty=wc.get("risk_penalty", 0.08),
            ),
        )

        # rebalance
        rb = raw.get("rebalance", {})
        cfg.rebalance = RebalanceCfg(
            soft_idle_drift_bps=rb.get("soft_idle_drift_bps", 15),
            soft_rebalance_bps=rb.get("soft_rebalance_bps", 50),
            hard_rebalance_bps=rb.get("hard_rebalance_bps", 200),
            gain_bps=rb.get("gain_bps", 2500),
            forced_batches=rb.get("forced_batches", 4),
            max_hard_breaches=rb.get("max_hard_breaches", 2),
        )

        return cfg
