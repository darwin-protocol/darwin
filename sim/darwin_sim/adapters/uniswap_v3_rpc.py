"""Uniswap V3 RPC adapter — fetches real swap events from an Ethereum RPC node.

Reads Swap events from the ETH/USDC 0.05% pool on Ethereum mainnet or L2.
Works with any EVM RPC endpoint (Alchemy, Infura, local node).

Usage:
    adapter = UniswapV3RpcAdapter("https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY")
    swaps = adapter.fetch_swaps(from_block=19000000, to_block=19001000)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.request import Request, urlopen
from darwin_sim.core.types import RawSwapEvent


# Uniswap V3 ETH/USDC 0.05% pool
POOL_ETH_USDC_005 = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"


class UniswapV3RpcAdapter:
    def __init__(self, rpc_url: str, pool_address: str = POOL_ETH_USDC_005):
        self.rpc_url = rpc_url
        self.pool_address = pool_address.lower()

    def _rpc_call(self, method: str, params: list) -> dict:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        req = Request(self.rpc_url, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=30)
        return json.loads(resp.read())

    def fetch_swaps(self, from_block: int, to_block: int, pair_id: str = "ETH_USDC") -> list[RawSwapEvent]:
        """Fetch Swap events from the pool contract via eth_getLogs."""
        result = self._rpc_call("eth_getLogs", [{
            "address": self.pool_address,
            "topics": [SWAP_TOPIC],
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }])

        logs = result.get("result", [])
        events: list[RawSwapEvent] = []

        for log in logs:
            try:
                tx_hash = log["transactionHash"]
                log_index = int(log["logIndex"], 16)
                block_num = int(log["blockNumber"], 16)

                # Decode Swap event data
                # Swap(address sender, address recipient, int256 amount0, int256 amount1, uint160 sqrtPriceX96, uint128 liquidity, int24 tick)
                data = bytes.fromhex(log["data"][2:])
                amount0 = int.from_bytes(data[0:32], "big", signed=True)
                amount1 = int.from_bytes(data[32:64], "big", signed=True)
                sqrt_price_x96 = int.from_bytes(data[64:96], "big", signed=False)

                # ETH/USDC: token0=USDC (6 dec), token1=WETH (18 dec)
                eth_amount = abs(amount1) / 1e18
                usdc_amount = abs(amount0) / 1e6

                if eth_amount == 0:
                    continue

                price = usdc_amount / eth_amount
                side = "BUY" if amount1 < 0 else "SELL"  # negative amount1 = pool gives ETH = user buys
                fee_paid = usdc_amount * 0.0005  # 5 bps pool fee

                # Get block timestamp (approximate with block number)
                block_ts = 1710000000 + (block_num - 19000000) * 12  # rough estimate

                sender = "0x" + log["topics"][1][-40:] if len(log["topics"]) > 1 else f"acct-{tx_hash[:10]}"

                events.append(RawSwapEvent(
                    tx_hash=tx_hash,
                    log_index=log_index,
                    pair_id=pair_id,
                    ts=block_ts,
                    side=side,
                    qty_base=round(eth_amount, 8),
                    qty_quote=round(usdc_amount, 6),
                    exec_price=round(price, 6),
                    fee_paid=round(fee_paid, 6),
                    acct_id=sender[:18],
                ))
            except (KeyError, ValueError, IndexError):
                continue

        return sorted(events, key=lambda e: (e.ts, e.log_index))

    def fetch_and_save(self, from_block: int, to_block: int, output_path: str | Path, pair_id: str = "ETH_USDC") -> int:
        """Fetch swaps and save as CSV."""
        import csv
        events = self.fetch_swaps(from_block, to_block, pair_id)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["tx_hash", "log_index", "pair_id", "ts", "side",
                         "qty_base", "qty_quote", "exec_price", "fee_paid", "acct_id"])
            for e in events:
                w.writerow([e.tx_hash, e.log_index, e.pair_id, e.ts, e.side,
                             e.qty_base, e.qty_quote, e.exec_price, e.fee_paid, e.acct_id])

        return len(events)
