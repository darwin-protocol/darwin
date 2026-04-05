// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/SettlementHub.sol";
import "./MockWETH.sol";

contract SettlementHubTest is Test {
    SettlementHub hub;
    MockWETH token;
    address governance = address(0x1001);
    address sentinel = address(0x5AFE);
    address batchOperator = address(0xBA7C);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);

    function setUp() public {
        hub = new SettlementHub(governance, sentinel, batchOperator);
        token = new MockWETH();
        token.mint(alice, 10 ether);
        vm.prank(alice);
        token.approve(address(hub), type(uint256).max);
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
            postedBy: batchOperator
        });

        vm.prank(batchOperator);
        hub.submitBatch(header);
        assertTrue(hub.submittedBatches(bytes32("batch1")));
        assertFalse(hub.settledBatches(bytes32("batch1")));
        assertEq(hub.batchSubmitters(bytes32("batch1")), batchOperator);
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
            postedBy: batchOperator
        });

        vm.prank(batchOperator);
        hub.submitBatch(header);

        vm.prank(batchOperator);
        vm.expectRevert(SettlementHub.BatchAlreadySubmitted.selector);
        hub.submitBatch(header);
    }

    function test_submit_batch_requires_authorized_operator() public {
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: bytes32("batch-unauth"),
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("ir"),
            fillRoot: bytes32("fr"),
            oracleRoot: bytes32("or"),
            rebalanceRoot: bytes32("rr"),
            manifestRoot: bytes32("mr"),
            windowStartTs: 1000,
            windowEndTs: 2000,
            postedBy: batchOperator
        });

        vm.prank(alice);
        vm.expectRevert(SettlementHub.Unauthorized.selector);
        hub.submitBatch(header);
    }

    function test_submit_batch_rejects_invalid_header() public {
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: bytes32(0),
            epochId: 0,
            pairId: bytes32(0),
            intentRoot: bytes32("ir"),
            fillRoot: bytes32("fr"),
            oracleRoot: bytes32("or"),
            rebalanceRoot: bytes32("rr"),
            manifestRoot: bytes32("mr"),
            windowStartTs: 2000,
            windowEndTs: 1000,
            postedBy: batchOperator
        });

        vm.prank(batchOperator);
        vm.expectRevert(SettlementHub.InvalidBatchHeader.selector);
        hub.submitBatch(header);
    }

    function test_apply_net_settlement_requires_submitted_batch() public {
        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(token),
            from_: alice,
            to_: bob,
            amount: 1 ether
        });

        vm.prank(batchOperator);
        vm.expectRevert(SettlementHub.BatchNotSubmitted.selector);
        hub.applyNetSettlement(bytes32("missing-batch"), transfers);
    }

    function test_apply_net_settlement_is_single_use() public {
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: bytes32("batch-settle"),
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("ir"),
            fillRoot: bytes32("fr"),
            oracleRoot: bytes32("or"),
            rebalanceRoot: bytes32("rr"),
            manifestRoot: bytes32("mr"),
            windowStartTs: 1000,
            windowEndTs: 2000,
            postedBy: batchOperator
        });
        vm.prank(batchOperator);
        hub.submitBatch(header);

        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(token),
            from_: alice,
            to_: bob,
            amount: 1 ether
        });

        vm.prank(batchOperator);
        hub.applyNetSettlement(bytes32("batch-settle"), transfers);
        assertTrue(hub.settledBatches(bytes32("batch-settle")));
        assertEq(token.balanceOf(bob), 1 ether);

        vm.prank(batchOperator);
        vm.expectRevert(SettlementHub.NetSettlementAlreadyApplied.selector);
        hub.applyNetSettlement(bytes32("batch-settle"), transfers);
    }

    function test_apply_net_settlement_requires_submitter_or_governance() public {
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: bytes32("batch-auth"),
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("ir"),
            fillRoot: bytes32("fr"),
            oracleRoot: bytes32("or"),
            rebalanceRoot: bytes32("rr"),
            manifestRoot: bytes32("mr"),
            windowStartTs: 1000,
            windowEndTs: 2000,
            postedBy: batchOperator
        });
        vm.prank(batchOperator);
        hub.submitBatch(header);

        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(token),
            from_: alice,
            to_: bob,
            amount: 1 ether
        });

        vm.prank(alice);
        vm.expectRevert(SettlementHub.Unauthorized.selector);
        hub.applyNetSettlement(bytes32("batch-auth"), transfers);
    }

    function test_apply_net_settlement_rejects_invalid_transfer() public {
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: bytes32("batch-invalid-transfer"),
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("ir"),
            fillRoot: bytes32("fr"),
            oracleRoot: bytes32("or"),
            rebalanceRoot: bytes32("rr"),
            manifestRoot: bytes32("mr"),
            windowStartTs: 1000,
            windowEndTs: 2000,
            postedBy: batchOperator
        });
        vm.prank(batchOperator);
        hub.submitBatch(header);

        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(token),
            from_: alice,
            to_: alice,
            amount: 1 ether
        });

        vm.prank(batchOperator);
        vm.expectRevert(SettlementHub.InvalidNetTransfer.selector);
        hub.applyNetSettlement(bytes32("batch-invalid-transfer"), transfers);
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
            postedBy: batchOperator
        });

        vm.prank(batchOperator);
        vm.expectRevert(SettlementHub.SafeModeActive.selector);
        hub.submitBatch(header);
    }

    function test_safe_mode_blocks_net_settlement() public {
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: bytes32("batch-safe"),
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("ir"),
            fillRoot: bytes32("fr"),
            oracleRoot: bytes32("or"),
            rebalanceRoot: bytes32("rr"),
            manifestRoot: bytes32("mr"),
            windowStartTs: 1000,
            windowEndTs: 2000,
            postedBy: batchOperator
        });
        vm.prank(batchOperator);
        hub.submitBatch(header);

        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(token),
            from_: alice,
            to_: bob,
            amount: 1 ether
        });

        vm.prank(sentinel);
        hub.enterSafeMode(bytes32("halt_settlement"));

        vm.prank(batchOperator);
        vm.expectRevert(SettlementHub.SafeModeActive.selector);
        hub.applyNetSettlement(bytes32("batch-safe"), transfers);
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
        vm.prank(batchOperator);
        hub.cancelIntent(bytes32("intent1"));
        assertEq(uint(hub.intentStates(bytes32("intent1"))), uint(SettlementHub.IntentState.CANCELLED));

        vm.prank(batchOperator);
        vm.expectRevert(SettlementHub.IntentAlreadyTerminal.selector);
        hub.cancelIntent(bytes32("intent1"));
    }

    function test_cancel_intent_requires_authorized_operator() public {
        vm.prank(alice);
        vm.expectRevert(SettlementHub.Unauthorized.selector);
        hub.cancelIntent(bytes32("intent2"));
    }

    function test_governance_can_update_batch_operator() public {
        vm.prank(governance);
        hub.setBatchOperator(alice, true);
        assertTrue(hub.batchOperators(alice));

        vm.prank(governance);
        hub.setBatchOperator(alice, false);
        assertFalse(hub.batchOperators(alice));
    }
}
