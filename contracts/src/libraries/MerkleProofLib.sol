// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title MerkleProofLib
/// @notice Sorted-pair Merkle proof verification for DRW claim distributions.
library MerkleProofLib {
    function verify(bytes32[] calldata proof, bytes32 root, bytes32 leaf) internal pure returns (bool) {
        bytes32 computedHash = leaf;
        for (uint256 i = 0; i < proof.length; ++i) {
            computedHash = _hashPair(computedHash, proof[i]);
        }
        return computedHash == root;
    }

    function _hashPair(bytes32 a, bytes32 b) private pure returns (bytes32) {
        return uint256(a) < uint256(b) ? keccak256(abi.encodePacked(a, b)) : keccak256(abi.encodePacked(b, a));
    }
}
