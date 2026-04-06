// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import "../src/DRWFaucet.sol";
import "./MockWETH.sol";

contract DRWFaucetTest is Test {
    DRWFaucet faucet;
    MockWETH token;

    address governance = address(0x1001);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);

    function setUp() public {
        token = new MockWETH();
        faucet = new DRWFaucet(address(token), governance, 100 ether, 0.01 ether, 1 days);
        token.mint(address(faucet), 10_000 ether);
        vm.deal(address(faucet), 1 ether);
    }

    function test_claim_transfers_token_and_native() public {
        uint256 beforeEth = alice.balance;
        vm.prank(alice);
        (uint256 tokenOut, uint256 nativeOut) = faucet.claim();

        assertEq(tokenOut, 100 ether);
        assertEq(nativeOut, 0.01 ether);
        assertEq(token.balanceOf(alice), 100 ether);
        assertEq(alice.balance, beforeEth + 0.01 ether);
        assertEq(faucet.nextClaimAt(alice), block.timestamp + 1 days);
    }

    function test_claim_respects_cooldown() public {
        vm.prank(alice);
        faucet.claim();

        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(DRWFaucet.ClaimTooEarly.selector, block.timestamp + 1 days));
        faucet.claim();
    }

    function test_claim_without_native_balance_still_transfers_token() public {
        DRWFaucet dryFaucet = new DRWFaucet(address(token), governance, 25 ether, 0.01 ether, 1 days);
        token.mint(address(dryFaucet), 100 ether);

        vm.prank(alice);
        (uint256 tokenOut, uint256 nativeOut) = dryFaucet.claim();

        assertEq(tokenOut, 25 ether);
        assertEq(nativeOut, 0);
        assertEq(token.balanceOf(alice), 25 ether);
    }

    function test_governance_can_update_config_and_pause() public {
        vm.startPrank(governance);
        faucet.setClaimConfig(50 ether, 0.005 ether, 12 hours);
        faucet.setPaused(true);
        vm.stopPrank();

        assertEq(faucet.claimAmount(), 50 ether);
        assertEq(faucet.nativeDripAmount(), 0.005 ether);
        assertEq(faucet.claimCooldown(), 12 hours);
        assertTrue(faucet.paused());

        vm.prank(alice);
        vm.expectRevert(DRWFaucet.FaucetPaused.selector);
        faucet.claim();
    }

    function test_only_governance_can_withdraw_or_reconfigure() public {
        vm.prank(alice);
        vm.expectRevert(DRWFaucet.Unauthorized.selector);
        faucet.setClaimConfig(10 ether, 0, 1 days);

        vm.prank(alice);
        vm.expectRevert(DRWFaucet.Unauthorized.selector);
        faucet.withdrawToken(bob, 1 ether);

        vm.prank(alice);
        vm.expectRevert(DRWFaucet.Unauthorized.selector);
        faucet.withdrawNative(bob, 0.1 ether);
    }

    function test_governance_can_withdraw() public {
        vm.startPrank(governance);
        faucet.withdrawToken(bob, 200 ether);
        faucet.withdrawNative(bob, 0.1 ether);
        vm.stopPrank();

        assertEq(token.balanceOf(bob), 200 ether);
        assertEq(bob.balance, 0.1 ether);
    }
}
