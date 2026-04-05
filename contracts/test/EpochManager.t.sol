// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/EpochManager.sol";

contract EpochManagerTest is Test {
    EpochManager mgr;
    address governance = address(0x1001);
    address operator = address(0x3003);
    address alice = address(0xA11CE);

    function setUp() public {
        mgr = new EpochManager(governance, operator, 1800); // 30 min challenge window
    }

    function test_epoch_lifecycle() public {
        EpochManager.EpochConfig memory cfg = EpochManager.EpochConfig({
            epochId: 1,
            startsAt: 1000,
            endsAt: 4600,
            controlPolicyHash: bytes32("ctrl"),
            bucketPolicyHash: bytes32("bkt"),
            rebalancePolicyHash: bytes32("reb")
        });

        vm.prank(operator);
        mgr.openEpoch(cfg);
        assertEq(mgr.currentEpochId(), 1);

        vm.prank(operator);
        mgr.closeEpoch(1, bytes32("manifest_root"));

        // Post roots
        vm.prank(operator);
        mgr.postScoreRoot(1, bytes32("score_root"));
        vm.prank(operator);
        mgr.postWeightRoot(1, bytes32("weight_root"));
        vm.prank(operator);
        mgr.postRebalanceRoot(1, bytes32("rebalance_root"));

        // Cannot finalize during challenge window
        vm.expectRevert(EpochManager.ChallengeWindowActive.selector);
        mgr.finalizeEpoch(1);

        // Warp past challenge window
        vm.warp(block.timestamp + 1801);

        // PERMISSIONLESS finalization — alice (random user) can call it
        vm.prank(alice);
        mgr.finalizeEpoch(1);

        EpochManager.Epoch memory e = mgr.getEpoch(1);
        assertEq(uint(e.state), uint(EpochManager.EpochState.FINALIZED));
    }

    function test_cannot_finalize_without_roots() public {
        EpochManager.EpochConfig memory cfg = EpochManager.EpochConfig({
            epochId: 2, startsAt: 1000, endsAt: 4600,
            controlPolicyHash: bytes32(0), bucketPolicyHash: bytes32(0), rebalancePolicyHash: bytes32(0)
        });

        vm.prank(operator);
        mgr.openEpoch(cfg);
        vm.prank(operator);
        mgr.closeEpoch(2, bytes32("manifest"));

        vm.warp(block.timestamp + 1801);

        vm.expectRevert(EpochManager.RootsMissing.selector);
        mgr.finalizeEpoch(2);
    }

    function test_cannot_finalize_without_rebalance_root() public {
        EpochManager.EpochConfig memory cfg = EpochManager.EpochConfig({
            epochId: 4,
            startsAt: 1000,
            endsAt: 4600,
            controlPolicyHash: bytes32("ctrl"),
            bucketPolicyHash: bytes32("bkt"),
            rebalancePolicyHash: bytes32("reb")
        });

        vm.prank(operator);
        mgr.openEpoch(cfg);
        vm.prank(operator);
        mgr.closeEpoch(4, bytes32("manifest_root"));
        vm.prank(operator);
        mgr.postScoreRoot(4, bytes32("score_root"));
        vm.prank(operator);
        mgr.postWeightRoot(4, bytes32("weight_root"));

        vm.warp(block.timestamp + 1801);

        vm.expectRevert(EpochManager.RootsMissing.selector);
        mgr.finalizeEpoch(4);
    }

    function test_only_operator_can_open() public {
        EpochManager.EpochConfig memory cfg = EpochManager.EpochConfig({
            epochId: 3, startsAt: 1000, endsAt: 4600,
            controlPolicyHash: bytes32(0), bucketPolicyHash: bytes32(0), rebalancePolicyHash: bytes32(0)
        });

        vm.prank(alice);
        vm.expectRevert(EpochManager.Unauthorized.selector);
        mgr.openEpoch(cfg);
    }

    function test_cannot_reopen_existing_epoch_id() public {
        EpochManager.EpochConfig memory cfg = EpochManager.EpochConfig({
            epochId: 5,
            startsAt: 1000,
            endsAt: 4600,
            controlPolicyHash: bytes32("ctrl"),
            bucketPolicyHash: bytes32("bkt"),
            rebalancePolicyHash: bytes32("reb")
        });

        vm.prank(operator);
        mgr.openEpoch(cfg);

        vm.prank(operator);
        vm.expectRevert(EpochManager.EpochAlreadyExists.selector);
        mgr.openEpoch(cfg);
    }

    function test_rejects_invalid_epoch_config() public {
        EpochManager.EpochConfig memory zeroId = EpochManager.EpochConfig({
            epochId: 0,
            startsAt: 1000,
            endsAt: 4600,
            controlPolicyHash: bytes32("ctrl"),
            bucketPolicyHash: bytes32("bkt"),
            rebalancePolicyHash: bytes32("reb")
        });

        vm.prank(operator);
        vm.expectRevert(EpochManager.InvalidEpochConfig.selector);
        mgr.openEpoch(zeroId);

        EpochManager.EpochConfig memory invertedWindow = EpochManager.EpochConfig({
            epochId: 6,
            startsAt: 4600,
            endsAt: 1000,
            controlPolicyHash: bytes32("ctrl"),
            bucketPolicyHash: bytes32("bkt"),
            rebalancePolicyHash: bytes32("reb")
        });

        vm.prank(operator);
        vm.expectRevert(EpochManager.InvalidEpochConfig.selector);
        mgr.openEpoch(invertedWindow);
    }

    function test_root_posting_requires_closed_epoch_and_nonzero_roots() public {
        EpochManager.EpochConfig memory cfg = EpochManager.EpochConfig({
            epochId: 7,
            startsAt: 1000,
            endsAt: 4600,
            controlPolicyHash: bytes32("ctrl"),
            bucketPolicyHash: bytes32("bkt"),
            rebalancePolicyHash: bytes32("reb")
        });

        vm.prank(operator);
        mgr.openEpoch(cfg);

        vm.prank(operator);
        vm.expectRevert(EpochManager.RootsMissing.selector);
        mgr.closeEpoch(7, bytes32(0));

        vm.prank(operator);
        vm.expectRevert(EpochManager.EpochNotClosed.selector);
        mgr.postScoreRoot(7, bytes32("score_root"));

        vm.prank(operator);
        mgr.closeEpoch(7, bytes32("manifest_root"));

        vm.prank(operator);
        vm.expectRevert(EpochManager.RootsMissing.selector);
        mgr.postScoreRoot(7, bytes32(0));

        vm.prank(operator);
        vm.expectRevert(EpochManager.RootsMissing.selector);
        mgr.postWeightRoot(7, bytes32(0));

        vm.prank(operator);
        vm.expectRevert(EpochManager.RootsMissing.selector);
        mgr.postRebalanceRoot(7, bytes32(0));
    }
}
