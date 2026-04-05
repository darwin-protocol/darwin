// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/ScoreRegistry.sol";

contract ScoreRegistryTest is Test {
    ScoreRegistry reg;
    address operator = address(0x3003);
    address governance = address(0x1001);
    address alice = address(0xA11CE);

    function setUp() public {
        reg = new ScoreRegistry(operator, governance);
    }

    function test_post_score_root() public {
        vm.prank(operator);
        reg.postScoreRoot(1, bytes32("score"), bytes32("manifest"));

        assertEq(reg.scoreRoots(1), bytes32("score"));
        assertEq(reg.manifestRoots(1), bytes32("manifest"));
    }

    function test_post_weight_root() public {
        vm.prank(operator);
        reg.postWeightRoot(1, bytes32("weights"));

        assertEq(reg.weightRoots(1), bytes32("weights"));
    }

    function test_post_rebalance_root() public {
        vm.prank(operator);
        reg.postRebalanceRoot(1, bytes32("rebalance"));

        assertEq(reg.rebalanceRoots(1), bytes32("rebalance"));
    }

    function test_only_operator() public {
        vm.prank(alice);
        vm.expectRevert(ScoreRegistry.Unauthorized.selector);
        reg.postScoreRoot(1, bytes32("x"), bytes32("y"));

        vm.prank(alice);
        vm.expectRevert(ScoreRegistry.Unauthorized.selector);
        reg.postWeightRoot(1, bytes32("x"));

        vm.prank(alice);
        vm.expectRevert(ScoreRegistry.Unauthorized.selector);
        reg.postRebalanceRoot(1, bytes32("x"));
    }
}
