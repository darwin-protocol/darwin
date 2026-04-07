// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import "../src/DRWToken.sol";
import "../src/DRWEpochDistributor.sol";

contract DRWEpochDistributorTest is Test {
    address governance = address(0x1001);
    address treasury = address(0x2002);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);
    address carol = address(0xCA01);

    DRWToken token;
    DRWEpochDistributor distributor;

    bytes32[] internal leaves;
    bytes32 internal root;

    function setUp() public {
        token = new DRWToken(governance, governance);

        leaves.push(_leaf(1, 0, alice, 100 ether));
        leaves.push(_leaf(1, 1, bob, 200 ether));
        leaves.push(_leaf(1, 2, carol, 300 ether));
        leaves.push(_leaf(1, 3, treasury, 400 ether));
        root = _root(leaves[0], leaves[1], leaves[2], leaves[3]);

        distributor = new DRWEpochDistributor(address(token), governance);

        vm.startPrank(governance);
        token.mintGenesis(address(distributor), 1_000 ether);
        token.finalizeGenesis();
        distributor.configureEpoch(1, root, uint64(block.timestamp + 7 days), 1_000 ether);
        vm.stopPrank();
    }

    function test_claim_transfers_epoch_allocation() public {
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaves[1];
        proof[1] = _hashPair(leaves[2], leaves[3]);

        distributor.claim(1, 0, alice, 100 ether, proof);

        assertEq(token.balanceOf(alice), 100 ether);
        assertTrue(distributor.isClaimed(1, 0));
        assertEq(distributor.epochRemaining(1), 900 ether);
    }

    function test_duplicate_claim_reverts() public {
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaves[1];
        proof[1] = _hashPair(leaves[2], leaves[3]);

        distributor.claim(1, 0, alice, 100 ether, proof);

        vm.expectRevert(DRWEpochDistributor.AlreadyClaimed.selector);
        distributor.claim(1, 0, alice, 100 ether, proof);
    }

    function test_invalid_proof_reverts() public {
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaves[0];
        proof[1] = _hashPair(leaves[2], leaves[2]);

        vm.expectRevert(DRWEpochDistributor.InvalidProof.selector);
        distributor.claim(1, 1, bob, 200 ether, proof);
    }

    function test_governance_can_sweep_after_deadline() public {
        vm.warp(block.timestamp + 8 days);

        vm.prank(governance);
        distributor.sweep(1, treasury, 50 ether);

        assertEq(token.balanceOf(treasury), 50 ether);
        assertEq(distributor.epochRemaining(1), 950 ether);
    }

    function test_configure_epoch_requires_unreserved_balance() public {
        vm.startPrank(governance);
        vm.expectRevert(DRWEpochDistributor.InsufficientReserve.selector);
        distributor.configureEpoch(2, bytes32(uint256(2)), uint64(block.timestamp + 7 days), 2_000 ether);
        vm.stopPrank();
    }

    function _leaf(uint256 epochId, uint256 index, address account, uint256 amount) internal pure returns (bytes32) {
        return keccak256(bytes.concat(keccak256(abi.encode(epochId, index, account, amount))));
    }

    function _root(bytes32 a, bytes32 b, bytes32 c, bytes32 d) internal pure returns (bytes32) {
        return _hashPair(_hashPair(a, b), _hashPair(c, d));
    }

    function _hashPair(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return uint256(a) < uint256(b) ? keccak256(abi.encodePacked(a, b)) : keccak256(abi.encodePacked(b, a));
    }
}
