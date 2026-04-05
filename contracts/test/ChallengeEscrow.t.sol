// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/ChallengeEscrow.sol";
import "./MockWETH.sol";

contract ChallengeEscrowTest is Test {
    ChallengeEscrow escrow;
    MockWETH weth;
    address governance = address(0x1001);
    address watcher = address(0x4004);

    function setUp() public {
        weth = new MockWETH();
        escrow = new ChallengeEscrow(address(weth), governance, 1 days);

        weth.mint(watcher, 10 ether);
        weth.mint(address(escrow), 100 ether); // pre-fund for rewards

        vm.prank(watcher);
        weth.approve(address(escrow), type(uint256).max);
    }

    function test_open_challenge() public {
        vm.prank(watcher);
        escrow.openChallenge(
            bytes32("ch1"), 1, bytes32("target"), ChallengeEscrow.Severity.MATERIAL, 0.25 ether
        );

        (bytes32 cid,,,,,,,,,) = escrow.challenges(bytes32("ch1"));
        assertEq(cid, bytes32("ch1"));
        assertEq(weth.balanceOf(watcher), 9.75 ether);
    }

    function test_insufficient_bond_rejected() public {
        vm.prank(watcher);
        vm.expectRevert(ChallengeEscrow.InsufficientBond.selector);
        escrow.openChallenge(
            bytes32("ch2"), 1, bytes32("target"), ChallengeEscrow.Severity.CRITICAL, 0.5 ether
        );
    }

    function test_upheld_challenge_rewards_watcher() public {
        uint256 before = weth.balanceOf(watcher);

        vm.prank(watcher);
        escrow.openChallenge(
            bytes32("ch3"), 1, bytes32("target"), ChallengeEscrow.Severity.MATERIAL, 0.25 ether
        );

        // Governance upholds — slash 2 ETH, watcher gets bond back + 25% of slash (0.5 ETH, capped at 5)
        vm.prank(governance);
        escrow.resolveChallenge(bytes32("ch3"), true, 2 ether);

        uint256 after_ = weth.balanceOf(watcher);
        // Watcher should have: before - 0.25 (bond) + 0.25 (bond returned) + 0.5 (reward) = before + 0.5
        assertEq(after_, before + 0.5 ether);
    }

    function test_rejected_challenge_penalizes_watcher() public {
        uint256 before = weth.balanceOf(watcher);

        vm.prank(watcher);
        escrow.openChallenge(
            bytes32("ch4"), 1, bytes32("target"), ChallengeEscrow.Severity.INFORMATIONAL, 0.05 ether
        );

        // Governance rejects — 50% penalty on bond
        vm.prank(governance);
        escrow.resolveChallenge(bytes32("ch4"), false, 0);

        uint256 after_ = weth.balanceOf(watcher);
        // Watcher gets back 50% of bond (0.025 ETH), loses 50% (0.025 ETH)
        assertEq(after_, before - 0.025 ether);
    }

    function test_only_governance_can_resolve() public {
        vm.prank(watcher);
        escrow.openChallenge(
            bytes32("ch5"), 1, bytes32("target"), ChallengeEscrow.Severity.MATERIAL, 0.25 ether
        );

        vm.prank(watcher);
        vm.expectRevert(ChallengeEscrow.Unauthorized.selector);
        escrow.resolveChallenge(bytes32("ch5"), true, 1 ether);
    }
}
