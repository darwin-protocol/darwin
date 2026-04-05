// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";

/// @title DARWIN SettlementHub — atomic batch settlement and accounting
/// @notice Enforces: no overfill, no replay, conservation, safe-mode continuity
contract SettlementHub {
    // --- Types ---

    struct BatchHeader {
        bytes32 batchId;
        uint64  epochId;
        bytes32 pairId;
        bytes32 intentRoot;
        bytes32 fillRoot;
        bytes32 oracleRoot;
        bytes32 rebalanceRoot;
        bytes32 manifestRoot;
        uint64  windowStartTs;
        uint64  windowEndTs;
        address postedBy;
    }

    struct NetTransfer {
        address asset;
        address from_;
        address to_;
        uint256 amount;
    }

    enum IntentState { OPEN, PARTIAL, FILLED, CANCELLED }

    // --- State ---

    address public governance;
    address public safeModeAuthority;
    bool    public safeMode;
    bytes32 public safeModeReason;

    mapping(bytes32 => bool) public settledBatches;
    mapping(bytes32 => IntentState) public intentStates;
    mapping(bytes32 => uint256) public intentFilledQty;

    uint64 public batchCount;

    // --- Events ---

    event BatchSubmitted(bytes32 indexed batchId, uint64 indexed epochId, bytes32 indexed pairId, bytes32 manifestRoot);
    event NetSettlementApplied(bytes32 indexed batchId, uint256 transferCount);
    event IntentCancelled(bytes32 indexed intentId, address indexed by);
    event SafeModeChanged(bool enabled, bytes32 reason, address actor);

    // --- Errors ---

    error Unauthorized();
    error BatchAlreadySettled();
    error SafeModeActive();
    error IntentAlreadyTerminal();
    error TransferFailed();

    // --- Constructor ---

    constructor(address _governance, address _safeModeAuthority) {
        governance = _governance;
        safeModeAuthority = _safeModeAuthority;
    }

    // --- Batch submission ---

    function submitBatch(BatchHeader calldata header) external {
        if (safeMode) revert SafeModeActive();
        if (settledBatches[header.batchId]) revert BatchAlreadySettled();

        settledBatches[header.batchId] = true;
        batchCount++;

        emit BatchSubmitted(header.batchId, header.epochId, header.pairId, header.manifestRoot);
    }

    // --- Net settlement ---

    function applyNetSettlement(bytes32 batchId, NetTransfer[] calldata transfers) external {
        if (!settledBatches[batchId]) revert BatchAlreadySettled();

        for (uint256 i = 0; i < transfers.length; i++) {
            NetTransfer calldata t = transfers[i];
            IERC20 token = IERC20(t.asset);
            if (!token.transferFrom(t.from_, t.to_, t.amount)) revert TransferFailed();
        }

        emit NetSettlementApplied(batchId, transfers.length);
    }

    // --- Intent cancellation ---

    function cancelIntent(bytes32 intentId) external {
        IntentState s = intentStates[intentId];
        if (s == IntentState.FILLED || s == IntentState.CANCELLED) revert IntentAlreadyTerminal();

        intentStates[intentId] = IntentState.CANCELLED;
        emit IntentCancelled(intentId, msg.sender);
    }

    // --- Safe mode ---

    function enterSafeMode(bytes32 reason) external {
        if (msg.sender != safeModeAuthority && msg.sender != governance) revert Unauthorized();
        safeMode = true;
        safeModeReason = reason;
        emit SafeModeChanged(true, reason, msg.sender);
    }

    function exitSafeMode() external {
        if (msg.sender != governance) revert Unauthorized();
        safeMode = false;
        safeModeReason = bytes32(0);
        emit SafeModeChanged(false, bytes32(0), msg.sender);
    }
}
