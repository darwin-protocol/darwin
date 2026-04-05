// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/BondVault.sol";
import "./MockWETH.sol";

contract BondVaultTest is Test {
    BondVault vault;
    MockWETH weth;
    address governance = address(0x1001);
    address escrow = address(0x2002);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);

    function setUp() public {
        weth = new MockWETH();
        vault = new BondVault(address(weth), governance, escrow);

        weth.mint(alice, 100 ether);
        weth.mint(bob, 50 ether);

        vm.prank(alice);
        weth.approve(address(vault), type(uint256).max);
        vm.prank(bob);
        weth.approve(address(vault), type(uint256).max);
    }

    function test_deposit() public {
        vm.prank(alice);
        vault.depositBond(BondVault.SubjectType.SPECIES, bytes32("species1"), 20 ether);

        (uint256 amt, bool active) = vault.getBond(alice, BondVault.SubjectType.SPECIES, bytes32("species1"));
        assertEq(amt, 20 ether);
        assertTrue(active);
        assertEq(weth.balanceOf(address(vault)), 20 ether);
    }

    function test_slash_only_escrow() public {
        vm.prank(alice);
        vault.depositBond(BondVault.SubjectType.SPECIES, bytes32("s1"), 20 ether);

        // Non-escrow cannot slash
        vm.prank(bob);
        vm.expectRevert(BondVault.Unauthorized.selector);
        vault.slashBond(alice, BondVault.SubjectType.SPECIES, bytes32("s1"), 5 ether, bytes32("test"));

        // Escrow can slash
        vm.prank(escrow);
        vault.slashBond(alice, BondVault.SubjectType.SPECIES, bytes32("s1"), 5 ether, bytes32("test"));

        (uint256 amt,) = vault.getBond(alice, BondVault.SubjectType.SPECIES, bytes32("s1"));
        assertEq(amt, 15 ether);
        // Slashed funds go to governance
        assertEq(weth.balanceOf(governance), 5 ether);
    }

    function test_withdraw_cooldown() public {
        vm.prank(alice);
        vault.depositBond(BondVault.SubjectType.GATEWAY, bytes32("gw1"), 2 ether);

        // Cannot withdraw before cooldown
        vm.prank(alice);
        vm.expectRevert(BondVault.CooldownNotElapsed.selector);
        vault.withdrawBond(BondVault.SubjectType.GATEWAY, bytes32("gw1"), 2 ether);

        // Warp past cooldown (7 days)
        vm.warp(block.timestamp + 7 days + 1);

        vm.prank(alice);
        vault.withdrawBond(BondVault.SubjectType.GATEWAY, bytes32("gw1"), 2 ether);

        (uint256 amt, bool active) = vault.getBond(alice, BondVault.SubjectType.GATEWAY, bytes32("gw1"));
        assertEq(amt, 0);
        assertFalse(active);
    }

    function test_cannot_withdraw_more_than_bond() public {
        vm.prank(alice);
        vault.depositBond(BondVault.SubjectType.WATCHER_STANDING, bytes32("w1"), 1 ether);

        vm.warp(block.timestamp + 7 days + 1);

        vm.prank(alice);
        vm.expectRevert(BondVault.InsufficientBond.selector);
        vault.withdrawBond(BondVault.SubjectType.WATCHER_STANDING, bytes32("w1"), 2 ether);
    }

    function test_slash_caps_at_bond() public {
        vm.prank(alice);
        vault.depositBond(BondVault.SubjectType.SPECIES, bytes32("s1"), 5 ether);

        // Slash more than bond — should cap
        vm.prank(escrow);
        vault.slashBond(alice, BondVault.SubjectType.SPECIES, bytes32("s1"), 100 ether, bytes32("big"));

        (uint256 amt,) = vault.getBond(alice, BondVault.SubjectType.SPECIES, bytes32("s1"));
        assertEq(amt, 0);
        assertEq(weth.balanceOf(governance), 5 ether);
    }
}
