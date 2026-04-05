// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import "../src/DRWToken.sol";
import "../src/DRWStaking.sol";

contract DRWGenesisTest is Test {
    DRWToken token;
    DRWStaking staking;

    address governance = address(0x1001);
    address treasury = address(0x2002);
    address insurance = address(0x3003);
    address community = address(0x4004);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);

    function setUp() public {
        vm.startPrank(governance);
        token = new DRWToken(governance, governance);
        staking = new DRWStaking(address(token), governance, governance);

        token.mintGenesis(treasury, 200 ether);
        token.mintGenesis(insurance, 200 ether);
        token.mintGenesis(address(staking), 300 ether);
        token.mintGenesis(community, 300 ether);
        staking.notifyRewardAmount(300 ether, 30 days);
        token.finalizeGenesis();
        vm.stopPrank();

        vm.prank(community);
        token.transfer(alice, 100 ether);
        vm.prank(community);
        token.transfer(bob, 100 ether);

        vm.prank(alice);
        token.approve(address(staking), type(uint256).max);
        vm.prank(bob);
        token.approve(address(staking), type(uint256).max);
    }

    function test_genesis_supply_and_finalization() public view {
        assertEq(token.totalSupply(), 1000 ether);
        assertTrue(token.genesisFinalized());
        assertEq(token.balanceOf(treasury), 200 ether);
        assertEq(token.balanceOf(insurance), 200 ether);
        assertEq(token.balanceOf(address(staking)), 300 ether);
    }

    function test_only_governance_can_mint_or_finalize() public {
        DRWToken freshToken = new DRWToken(governance, governance);
        vm.prank(alice);
        vm.expectRevert(DRWToken.Unauthorized.selector);
        freshToken.mintGenesis(alice, 1 ether);

        vm.prank(alice);
        vm.expectRevert(DRWToken.Unauthorized.selector);
        freshToken.finalizeGenesis();
    }

    function test_cannot_mint_after_finalization() public {
        vm.prank(governance);
        vm.expectRevert(DRWToken.GenesisClosed.selector);
        token.mintGenesis(governance, 1 ether);
    }

    function test_staking_accrues_rewards() public {
        vm.startPrank(alice);
        staking.stake(50 ether);
        vm.warp(block.timestamp + 15 days);
        staking.getReward();
        vm.stopPrank();

        assertGt(token.balanceOf(alice), 50 ether);
        assertEq(staking.balances(alice), 50 ether);
    }

    function test_notify_reward_requires_available_balance() public {
        DRWToken freshToken = new DRWToken(governance, governance);
        DRWStaking freshStaking = new DRWStaking(address(freshToken), governance, governance);

        vm.prank(governance);
        vm.expectRevert(DRWStaking.InsufficientRewardBalance.selector);
        freshStaking.notifyRewardAmount(10 ether, 30 days);
    }

    function test_exit_returns_stake_and_reward() public {
        vm.prank(alice);
        staking.stake(40 ether);
        vm.warp(block.timestamp + 30 days);

        uint256 beforeBalance = token.balanceOf(alice);
        vm.prank(alice);
        staking.exit();

        assertEq(staking.balances(alice), 0);
        assertGt(token.balanceOf(alice), beforeBalance);
    }
}
