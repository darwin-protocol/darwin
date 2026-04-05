// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title DARWIN EpochManager — epoch lifecycle and finalization
/// @notice finalizeEpoch is PERMISSIONLESS after challenge window expires
contract EpochManager {
    struct EpochConfig {
        uint64  epochId;
        uint64  startsAt;
        uint64  endsAt;
        bytes32 controlPolicyHash;
        bytes32 bucketPolicyHash;
        bytes32 rebalancePolicyHash;
    }

    enum EpochState { OPEN, CLOSED, FINALIZED }

    struct Epoch {
        EpochConfig config;
        EpochState  state;
        bytes32     manifestRoot;
        bytes32     scoreRoot;
        bytes32     nextWeightRoot;
        bytes32     rebalanceRoot;
        uint64      closedAt;
        uint64      finalizedAt;
    }

    // --- State ---

    address public governance;
    address public epochOperator;
    uint64  public currentEpochId;
    uint64  public challengeWindowSec;

    mapping(uint64 => Epoch) public epochs;

    // --- Events ---

    event EpochOpened(uint64 indexed epochId, uint64 startsAt, uint64 endsAt);
    event EpochClosed(uint64 indexed epochId, bytes32 manifestRoot);
    event EpochFinalized(uint64 indexed epochId, bytes32 scoreRoot, bytes32 nextWeightRoot);

    // --- Errors ---

    error Unauthorized();
    error EpochAlreadyExists();
    error EpochNotOpen();
    error EpochNotClosed();
    error ChallengeWindowActive();
    error InvalidEpochConfig();
    error RootsMissing();

    // --- Constructor ---

    constructor(address _governance, address _epochOperator, uint64 _challengeWindowSec) {
        governance = _governance;
        epochOperator = _epochOperator;
        challengeWindowSec = _challengeWindowSec;
    }

    // --- Open ---

    function openEpoch(EpochConfig calldata config) external {
        if (msg.sender != epochOperator && msg.sender != governance) revert Unauthorized();
        if (config.epochId == 0 || config.endsAt <= config.startsAt) revert InvalidEpochConfig();
        if (epochs[config.epochId].config.epochId != 0) revert EpochAlreadyExists();

        epochs[config.epochId].config = config;
        epochs[config.epochId].state = EpochState.OPEN;
        currentEpochId = config.epochId;

        emit EpochOpened(config.epochId, config.startsAt, config.endsAt);
    }

    // --- Close ---

    function closeEpoch(uint64 epochId, bytes32 manifestRoot) external {
        if (msg.sender != epochOperator && msg.sender != governance) revert Unauthorized();
        if (epochs[epochId].state != EpochState.OPEN) revert EpochNotOpen();
        if (manifestRoot == bytes32(0)) revert RootsMissing();

        epochs[epochId].state = EpochState.CLOSED;
        epochs[epochId].manifestRoot = manifestRoot;
        epochs[epochId].closedAt = uint64(block.timestamp);

        emit EpochClosed(epochId, manifestRoot);
    }

    // --- Post roots (epoch operator) ---

    function postScoreRoot(uint64 epochId, bytes32 scoreRoot) external {
        if (msg.sender != epochOperator) revert Unauthorized();
        if (epochs[epochId].state != EpochState.CLOSED) revert EpochNotClosed();
        if (scoreRoot == bytes32(0)) revert RootsMissing();
        epochs[epochId].scoreRoot = scoreRoot;
    }

    function postWeightRoot(uint64 epochId, bytes32 nextWeightRoot) external {
        if (msg.sender != epochOperator) revert Unauthorized();
        if (epochs[epochId].state != EpochState.CLOSED) revert EpochNotClosed();
        if (nextWeightRoot == bytes32(0)) revert RootsMissing();
        epochs[epochId].nextWeightRoot = nextWeightRoot;
    }

    function postRebalanceRoot(uint64 epochId, bytes32 rebalanceRoot) external {
        if (msg.sender != epochOperator) revert Unauthorized();
        if (epochs[epochId].state != EpochState.CLOSED) revert EpochNotClosed();
        if (rebalanceRoot == bytes32(0)) revert RootsMissing();
        epochs[epochId].rebalanceRoot = rebalanceRoot;
    }

    // --- Finalize (PERMISSIONLESS after challenge window) ---

    function finalizeEpoch(uint64 epochId) external {
        Epoch storage e = epochs[epochId];
        if (e.state != EpochState.CLOSED) revert EpochNotClosed();
        if (block.timestamp < e.closedAt + challengeWindowSec) revert ChallengeWindowActive();
        if (
            e.manifestRoot == bytes32(0) || e.scoreRoot == bytes32(0) || e.nextWeightRoot == bytes32(0)
                || e.rebalanceRoot == bytes32(0)
        ) revert RootsMissing();

        e.state = EpochState.FINALIZED;
        e.finalizedAt = uint64(block.timestamp);

        emit EpochFinalized(epochId, e.scoreRoot, e.nextWeightRoot);
    }

    // --- View ---

    function getEpoch(uint64 epochId) external view returns (Epoch memory) {
        return epochs[epochId];
    }
}
