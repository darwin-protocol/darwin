// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title DARWIN ScoreRegistry — stores challengeable score and weight roots
contract ScoreRegistry {
    address public epochOperator;
    address public governance;

    mapping(uint64 => bytes32) public scoreRoots;
    mapping(uint64 => bytes32) public weightRoots;
    mapping(uint64 => bytes32) public rebalanceRoots;
    mapping(uint64 => bytes32) public manifestRoots;

    event ScoreRootPosted(uint64 indexed epochId, bytes32 scoreRoot, bytes32 manifestRoot);
    event WeightRootPosted(uint64 indexed epochId, bytes32 nextWeightRoot);
    event RebalanceRootPosted(uint64 indexed epochId, bytes32 rebalanceRoot);

    error Unauthorized();

    constructor(address _epochOperator, address _governance) {
        epochOperator = _epochOperator;
        governance = _governance;
    }

    function postScoreRoot(uint64 epochId, bytes32 scoreRoot, bytes32 manifestRoot) external {
        if (msg.sender != epochOperator) revert Unauthorized();
        scoreRoots[epochId] = scoreRoot;
        manifestRoots[epochId] = manifestRoot;
        emit ScoreRootPosted(epochId, scoreRoot, manifestRoot);
    }

    function postWeightRoot(uint64 epochId, bytes32 nextWeightRoot) external {
        if (msg.sender != epochOperator) revert Unauthorized();
        weightRoots[epochId] = nextWeightRoot;
        emit WeightRootPosted(epochId, nextWeightRoot);
    }

    function postRebalanceRoot(uint64 epochId, bytes32 rebalanceRoot) external {
        if (msg.sender != epochOperator) revert Unauthorized();
        rebalanceRoots[epochId] = rebalanceRoot;
        emit RebalanceRootPosted(epochId, rebalanceRoot);
    }
}
