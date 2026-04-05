// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title DARWIN v1 Role Constants
library DarwinRoles {
    bytes32 internal constant GOVERNANCE_COUNCIL = keccak256("GOVERNANCE_COUNCIL_ROLE");
    bytes32 internal constant EPOCH_OPERATOR     = keccak256("EPOCH_OPERATOR_ROLE");
    bytes32 internal constant SETTLEMENT_HUB     = keccak256("SETTLEMENT_HUB_ROLE");
    bytes32 internal constant CHALLENGE_ESCROW   = keccak256("CHALLENGE_ESCROW_ROLE");
    bytes32 internal constant SAFE_MODE_SENTINEL = keccak256("SAFE_MODE_SENTINEL_ROLE");
}
