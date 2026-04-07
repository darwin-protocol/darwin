// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Governable2Step
/// @notice Minimal two-step governance handoff primitive for vNext DARWIN contracts.
abstract contract Governable2Step {
    address public governance;
    address public pendingGovernance;

    event GovernanceTransferStarted(address indexed currentGovernance, address indexed pendingGovernance);
    event GovernanceTransferred(address indexed previousGovernance, address indexed newGovernance);

    error Unauthorized();
    error InvalidRecipient();

    constructor(address initialGovernance) {
        if (initialGovernance == address(0)) revert InvalidRecipient();
        governance = initialGovernance;
        emit GovernanceTransferred(address(0), initialGovernance);
    }

    modifier onlyGovernance() {
        if (msg.sender != governance) revert Unauthorized();
        _;
    }

    function transferGovernance(address newGovernance) external onlyGovernance {
        if (newGovernance == address(0)) revert InvalidRecipient();
        pendingGovernance = newGovernance;
        emit GovernanceTransferStarted(governance, newGovernance);
    }

    function acceptGovernance() external {
        if (msg.sender != pendingGovernance) revert Unauthorized();
        address oldGovernance = governance;
        governance = msg.sender;
        pendingGovernance = address(0);
        emit GovernanceTransferred(oldGovernance, msg.sender);
    }
}
