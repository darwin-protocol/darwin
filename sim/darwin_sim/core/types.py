"""DARWIN v0.8 merged data types — combines v0.4 typed engine with v0.8 real-data pipeline."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Fixed-point
# ---------------------------------------------------------------------------

X18 = 10**18
BPS = 10_000


def to_x18(f: float) -> int:
    return int(round(f * X18))


def from_x18(v: int) -> float:
    return v / X18


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Side(Enum):
    BUY = auto()
    SELL = auto()

    @staticmethod
    def from_str(s: str) -> Side:
        return Side.BUY if s.upper() == "BUY" else Side.SELL


class SpeciesStatus(Enum):
    ACTIVE = auto()
    CANARY = auto()
    QUARANTINED = auto()
    RETIRED = auto()


class RebalanceMode(Enum):
    NONE = auto()
    GRADUAL = auto()
    FORCED = auto()
    HARD_RESET = auto()


class RouteReason(Enum):
    CONTROL = auto()
    EXPLOIT = auto()
    EXPLORE = auto()
    FALLBACK = auto()


# ---------------------------------------------------------------------------
# Raw data (from v0.8 adapter)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RawSwapEvent:
    tx_hash: str
    log_index: int
    pair_id: str
    ts: int
    side: str
    qty_base: float
    qty_quote: float
    exec_price: float
    fee_paid: float
    acct_id: str


@dataclass(slots=True)
class NormalizedSwap:
    event_id: str
    pair_id: str
    ts: int
    side: Side
    qty_base_x18: int
    qty_quote_x18: int
    exec_price_x18: int
    fee_paid_x18: int
    acct_id: str
    source_tx_hash: str = ""


# ---------------------------------------------------------------------------
# Intent (merged: v0.4 typed + v0.8 profile system)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class IntentRecord:
    intent_id: str = ""
    acct_id: str = ""
    pair_id: str = ""
    ts: int = 0
    side: Side = Side.BUY
    qty_base_x18: int = 0
    notional_quote_x18: int = 0
    source_event_id: str = ""
    source_price_x18: int = 0
    profile: str = "BALANCED"
    max_slippage_bps: int = 50
    limit_price_x18: int = 0
    expiry_ts: int = 0
    bucket_id: str = "default"


# ---------------------------------------------------------------------------
# Fill (merged: v0.4 structure + v0.8 enrichment fields)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FillResult:
    fill_id: str = ""
    species_id: str = ""
    intent_id: str = ""
    batch_id: str = ""
    acct_id: str = ""
    pair_id: str = ""
    ts: int = 0
    side: Side = Side.BUY
    qty_filled_x18: int = 0
    exec_price_x18: int = 0
    source_price_x18: int = 0
    notional_x18: int = 0
    fee_paid_x18: int = 0
    profile: str = ""
    is_control: bool = False
    route_reason: RouteReason = RouteReason.EXPLOIT
    fill_rate_bps: int = BPS
    success: bool = True
    # enrichment (post-fill scoring)
    trader_surplus_x18: int = 0
    adverse_markout_x18: int = 0
    revenue_x18: int = 0


# ---------------------------------------------------------------------------
# Species state (from v0.4)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SpeciesState:
    species_id: str = ""
    kind: str = ""
    status: SpeciesStatus = SpeciesStatus.ACTIVE
    weight_x1e6: int = 0
    canary: bool = False
    canary_weight_cap_bps: int = 500
    # epoch accumulators
    fills_count: int = 0
    unique_accts: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Rebalance leaf (from v0.8, typed)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RebalanceLeaf:
    batch_id: str = ""
    species_id: str = ""
    ref_price_x18: int = 0
    drift_bps: float = 0.0
    mode: RebalanceMode = RebalanceMode.NONE
    kappa_reb: float = 0.0
    correction_price_x18: int = 0


# ---------------------------------------------------------------------------
# Score leaf (from v0.4, with v0.8 control fields)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ScoreLeaf:
    epoch_id: int = 0
    pair_id: str = ""
    species_id: str = ""
    bucket_id: str = ""
    # observed
    count: int = 0
    trader_surplus_bps: float = 0.0
    fill_rate_bps: float = 0.0
    adverse_markout_bps: float = 0.0
    revenue_bps: float = 0.0
    # control
    ctrl_count: int = 0
    ctrl_trader_surplus_bps: float = 0.0
    ctrl_fill_rate_bps: float = 0.0
    ctrl_adverse_markout_bps: float = 0.0
    ctrl_revenue_bps: float = 0.0
    # uplifts
    uplift_ts_bps: float = 0.0
    uplift_fr_bps: float = 0.0
    uplift_adv_bps: float = 0.0
    uplift_rev_bps: float = 0.0
    # composite
    fitness: float = 0.0
    next_weight_x1e6: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
