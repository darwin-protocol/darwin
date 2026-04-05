"""Species protocol — every species implements quote() and execute()."""

from __future__ import annotations

from typing import Protocol
from random import Random

from darwin_sim.core.types import (
    IntentRecord, MarketFrame, PairVaultState, EpochConfig,
    ExecutionQuote, FillResult,
)


class Species(Protocol):
    species_id: str

    def quote(
        self,
        intent: IntentRecord,
        market: MarketFrame,
        pair_state: PairVaultState,
        epoch_cfg: EpochConfig,
        rng: Random,
    ) -> ExecutionQuote: ...

    def execute(
        self,
        intent: IntentRecord,
        market: MarketFrame,
        pair_state: PairVaultState,
        epoch_cfg: EpochConfig,
        rng: Random,
    ) -> FillResult: ...
