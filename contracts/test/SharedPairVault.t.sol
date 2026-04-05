// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/SharedPairVault.sol";
import "./MockWETH.sol";

contract SharedPairVaultTest is Test {
    SharedPairVault vault;
    MockWETH base;   // WETH as base
    MockWETH quote;  // USDC mock as quote
    address governance = address(0x1001);
    address hub = address(0x2002);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);
    bytes32 pairId = bytes32("ETH_USDC");

    function setUp() public {
        base = new MockWETH();
        quote = new MockWETH();
        vault = new SharedPairVault(governance, hub);

        vm.prank(governance);
        vault.createPair(pairId, address(base), address(quote));

        base.mint(alice, 100 ether);
        quote.mint(alice, 300_000 ether);
        base.mint(bob, 50 ether);
        quote.mint(bob, 150_000 ether);

        vm.prank(alice);
        base.approve(address(vault), type(uint256).max);
        vm.prank(alice);
        quote.approve(address(vault), type(uint256).max);
        vm.prank(bob);
        base.approve(address(vault), type(uint256).max);
        vm.prank(bob);
        quote.approve(address(vault), type(uint256).max);
    }

    function test_deposit() public {
        vm.prank(alice);
        vault.deposit(pairId, 10 ether, 30_000 ether);

        SharedPairVault.PairVault memory v = vault.getVault(pairId);
        assertEq(v.baseBalance, 10 ether);
        assertEq(v.quoteBalance, 30_000 ether);
        assertGt(v.totalShares, 0);
        assertEq(vault.lpShares(pairId, alice), v.totalShares);
    }

    function test_withdraw() public {
        vm.prank(alice);
        vault.deposit(pairId, 10 ether, 30_000 ether);

        uint256 shares = vault.lpShares(pairId, alice);

        vm.prank(alice);
        vault.withdraw(pairId, shares);

        assertEq(base.balanceOf(alice), 100 ether);
        assertEq(quote.balanceOf(alice), 300_000 ether);
        assertEq(vault.lpShares(pairId, alice), 0);
    }

    function test_proportional_withdraw() public {
        vm.prank(alice);
        vault.deposit(pairId, 10 ether, 30_000 ether);

        uint256 shares = vault.lpShares(pairId, alice);
        uint256 half = shares / 2;

        vm.prank(alice);
        vault.withdraw(pairId, half);

        SharedPairVault.PairVault memory v = vault.getVault(pairId);
        assertEq(v.baseBalance, 5 ether);
        assertEq(v.quoteBalance, 15_000 ether);
    }

    function test_two_lps() public {
        vm.prank(alice);
        vault.deposit(pairId, 10 ether, 30_000 ether);

        vm.prank(bob);
        vault.deposit(pairId, 10 ether, 30_000 ether);

        SharedPairVault.PairVault memory v = vault.getVault(pairId);
        assertEq(v.baseBalance, 20 ether);
        assertEq(v.quoteBalance, 60_000 ether);

        uint256 aliceShares = vault.lpShares(pairId, alice);
        uint256 bobShares = vault.lpShares(pairId, bob);
        assertEq(aliceShares, bobShares);
    }

    function test_cannot_withdraw_more_than_shares() public {
        vm.prank(alice);
        vault.deposit(pairId, 10 ether, 30_000 ether);

        uint256 shares = vault.lpShares(pairId, alice);

        vm.prank(alice);
        vm.expectRevert(SharedPairVault.InsufficientShares.selector);
        vault.withdraw(pairId, shares + 1);
    }

    function test_weight_update_only_hub() public {
        vm.prank(alice);
        vm.expectRevert(SharedPairVault.Unauthorized.selector);
        vault.updateSpeciesWeights(pairId, bytes32("weights"));

        vm.prank(hub);
        vault.updateSpeciesWeights(pairId, bytes32("weights"));

        SharedPairVault.PairVault memory v = vault.getVault(pairId);
        assertEq(v.speciesWeightRoot, bytes32("weights"));
    }

    function test_zero_value_lp_actions_rejected() public {
        vm.prank(alice);
        vm.expectRevert(SharedPairVault.InvalidAmount.selector);
        vault.deposit(pairId, 0, 0);

        vm.prank(alice);
        vm.expectRevert(SharedPairVault.InvalidAmount.selector);
        vault.withdraw(pairId, 0);
    }

    function test_weight_update_requires_existing_enabled_pair() public {
        vm.prank(hub);
        vm.expectRevert(SharedPairVault.PairNotEnabled.selector);
        vault.updateSpeciesWeights(bytes32("FAKE"), bytes32("weights"));
    }

    function test_only_governance_creates_pairs() public {
        vm.prank(alice);
        vm.expectRevert(SharedPairVault.Unauthorized.selector);
        vault.createPair(bytes32("BTC_USDC"), address(base), address(quote));
    }

    function test_cannot_recreate_pair() public {
        vm.prank(governance);
        vm.expectRevert(SharedPairVault.PairExists.selector);
        vault.createPair(pairId, address(base), address(quote));
    }

    function test_invalid_pair_config_rejected() public {
        vm.prank(governance);
        vm.expectRevert(SharedPairVault.InvalidPairConfig.selector);
        vault.createPair(bytes32(0), address(base), address(quote));

        vm.prank(governance);
        vm.expectRevert(SharedPairVault.InvalidPairConfig.selector);
        vault.createPair(bytes32("BAD1"), address(0), address(quote));

        vm.prank(governance);
        vm.expectRevert(SharedPairVault.InvalidPairConfig.selector);
        vault.createPair(bytes32("BAD2"), address(base), address(base));
    }

    function test_disabled_pair_blocks_deposit() public {
        // Pair that doesn't exist has enabled=false by default
        vm.prank(alice);
        vm.expectRevert(SharedPairVault.PairNotEnabled.selector);
        vault.deposit(bytes32("FAKE"), 1 ether, 1 ether);
    }
}
