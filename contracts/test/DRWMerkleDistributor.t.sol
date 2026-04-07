// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import "../src/DRWToken.sol";
import "../src/DRWMerkleDistributor.sol";

contract DRWMerkleDistributorTest is Test {
    address governance = address(0x1001);
    address treasury = address(0x2002);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);
    address carol = address(0xCA01);

    DRWToken token;
    DRWMerkleDistributor distributor;

    bytes32[] internal leaves;
    bytes32 internal root;

    function setUp() public {
        token = new DRWToken(governance, governance);

        leaves.push(_leaf(0, alice, 100 ether));
        leaves.push(_leaf(1, bob, 200 ether));
        leaves.push(_leaf(2, carol, 300 ether));
        leaves.push(_leaf(3, treasury, 400 ether));
        root = _root(leaves[0], leaves[1], leaves[2], leaves[3]);

        distributor = new DRWMerkleDistributor(address(token), governance, root, uint64(block.timestamp + 7 days));

        vm.startPrank(governance);
        token.mintGenesis(address(distributor), 1000 ether);
        token.finalizeGenesis();
        vm.stopPrank();
    }

    function test_claim_transfers_allocated_tokens() public {
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaves[1];
        proof[1] = _hashPair(leaves[2], leaves[3]);

        distributor.claim(0, alice, 100 ether, proof);

        assertEq(token.balanceOf(alice), 100 ether);
        assertTrue(distributor.isClaimed(0));
    }

    function test_duplicate_claim_reverts() public {
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaves[1];
        proof[1] = _hashPair(leaves[2], leaves[3]);

        distributor.claim(0, alice, 100 ether, proof);

        vm.expectRevert(DRWMerkleDistributor.AlreadyClaimed.selector);
        distributor.claim(0, alice, 100 ether, proof);
    }

    function test_invalid_proof_reverts() public {
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaves[0];
        proof[1] = _hashPair(leaves[2], leaves[2]);

        vm.expectRevert(DRWMerkleDistributor.InvalidProof.selector);
        distributor.claim(1, bob, 200 ether, proof);
    }

    function test_governance_can_sweep_after_deadline() public {
        vm.warp(block.timestamp + 8 days);

        vm.prank(governance);
        distributor.sweep(treasury, 50 ether);

        assertEq(token.balanceOf(treasury), 50 ether);
    }

    function _leaf(uint256 index, address account, uint256 amount) internal pure returns (bytes32) {
        return keccak256(bytes.concat(keccak256(abi.encode(index, account, amount))));
    }

    function _root(bytes32 a, bytes32 b, bytes32 c, bytes32 d) internal pure returns (bytes32) {
        return _hashPair(_hashPair(a, b), _hashPair(c, d));
    }

    function _hashPair(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return uint256(a) < uint256(b) ? keccak256(abi.encodePacked(a, b)) : keccak256(abi.encodePacked(b, a));
    }
}
