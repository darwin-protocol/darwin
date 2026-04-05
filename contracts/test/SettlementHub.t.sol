// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/SettlementHub.sol";

contract SettlementHubTest is Test {
    SettlementHub hub;
    address governance = address(0x1001);
    address sentinel = address(0x5AFE);
    address alice = address(0xA11CE);

    function setUp() public {
        hub = new SettlementHub(governance, sentinel);
    }

    function test_submit_batch() public {
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: bytes32("batch1"),
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("ir"),
            fillRoot: bytes32("fr"),
            oracleRoot: bytes32("or"),
            rebalanceRoot: bytes32("rr"),
            manifestRoot: bytes32("mr"),
            windowStartTs: 1000,
            windowEndTs: 2000,
            postedBy: alice
        });

        hub.submitBatch(header);
        assertTrue(hub.settledBatches(bytes32("batch1")));
        assertEq(hub.batchCount(), 1);
    }

    function test_no_batch_replay() public {
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: bytes32("batch1"),
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("ir"),
            fillRoot: bytes32("fr"),
            oracleRoot: bytes32("or"),
            rebalanceRoot: bytes32("rr"),
            manifestRoot: bytes32("mr"),
            windowStartTs: 1000,
            windowEndTs: 2000,
            postedBy: alice
        });

        hub.submitBatch(header);

        vm.expectRevert(SettlementHub.BatchAlreadySettled.selector);
        hub.submitBatch(header);
    }

    function test_safe_mode_blocks_batches() public {
        vm.prank(sentinel);
        hub.enterSafeMode(bytes32("oracle_divergence"));
        assertTrue(hub.safeMode());

        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: bytes32("batch2"),
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32(0),
            fillRoot: bytes32(0),
            oracleRoot: bytes32(0),
            rebalanceRoot: bytes32(0),
            manifestRoot: bytes32(0),
            windowStartTs: 0,
            windowEndTs: 0,
            postedBy: alice
        });

        vm.expectRevert(SettlementHub.SafeModeActive.selector);
        hub.submitBatch(header);
    }

    function test_safe_mode_only_authorized() public {
        vm.prank(alice);
        vm.expectRevert(SettlementHub.Unauthorized.selector);
        hub.enterSafeMode(bytes32("hack"));
    }

    function test_exit_safe_mode_only_governance() public {
        vm.prank(sentinel);
        hub.enterSafeMode(bytes32("test"));

        vm.prank(sentinel);
        vm.expectRevert(SettlementHub.Unauthorized.selector);
        hub.exitSafeMode();

        vm.prank(governance);
        hub.exitSafeMode();
        assertFalse(hub.safeMode());
    }

    function test_cancel_intent() public {
        hub.cancelIntent(bytes32("intent1"));
        assertEq(uint(hub.intentStates(bytes32("intent1"))), uint(SettlementHub.IntentState.CANCELLED));

        vm.expectRevert(SettlementHub.IntentAlreadyTerminal.selector);
        hub.cancelIntent(bytes32("intent1"));
    }
}
