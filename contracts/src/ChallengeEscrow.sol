// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";

/// @title DARWIN ChallengeEscrow — severity-tiered challenge bonds and resolution
contract ChallengeEscrow {
    enum Severity { INFORMATIONAL, MATERIAL, CRITICAL }
    enum ChallengeState { OPEN, RESPONDED, UPHELD, REJECTED }

    struct Challenge {
        bytes32        challengeId;
        uint64         epochId;
        bytes32        targetRoot;
        Severity       severity;
        address        opener;
        uint256        bond;
        ChallengeState state;
        uint64         openedAt;
        uint64         expiresAt;
        uint256        slashAmount;
    }

    // --- State ---

    IERC20  public immutable bondAsset;
    address public governance;
    address public bondVault;
    uint64  public responseWindow;

    mapping(bytes32 => Challenge) public challenges;

    // Severity → minimum bond
    mapping(Severity => uint256) public minBond;

    // Watcher reward params (bps)
    uint256 public rewardShareBps = 2500;  // 25% of slash
    uint256 public rewardCapWeth = 5 ether;
    uint256 public falsePenaltyBps = 5000; // 50% of bond

    // --- Events ---

    event ChallengeOpened(bytes32 indexed challengeId, uint64 indexed epochId, address indexed opener, Severity severity);
    event ChallengeResolved(bytes32 indexed challengeId, bool upheld, uint256 slashAmount);
    event ChallengeRewardClaimed(bytes32 indexed challengeId, address indexed watcher, uint256 amount);

    // --- Errors ---

    error Unauthorized();
    error ChallengeExists();
    error InsufficientBond();
    error ChallengeNotOpen();
    error AlreadyResolved();
    error TransferFailed();

    constructor(address _bondAsset, address _governance, uint64 _responseWindow) {
        bondAsset = IERC20(_bondAsset);
        governance = _governance;
        responseWindow = _responseWindow;

        // Default minimum bonds (v0.8 spec)
        minBond[Severity.INFORMATIONAL] = 0.05 ether;
        minBond[Severity.MATERIAL]      = 0.25 ether;
        minBond[Severity.CRITICAL]      = 1.00 ether;
    }

    // --- Open challenge ---

    function openChallenge(
        bytes32 challengeId,
        uint64 epochId,
        bytes32 targetRoot,
        Severity severity,
        uint256 bondAmount
    ) external {
        if (challenges[challengeId].openedAt != 0) revert ChallengeExists();
        if (bondAmount < minBond[severity]) revert InsufficientBond();
        if (!bondAsset.transferFrom(msg.sender, address(this), bondAmount)) revert TransferFailed();

        challenges[challengeId] = Challenge({
            challengeId: challengeId,
            epochId: epochId,
            targetRoot: targetRoot,
            severity: severity,
            opener: msg.sender,
            bond: bondAmount,
            state: ChallengeState.OPEN,
            openedAt: uint64(block.timestamp),
            expiresAt: uint64(block.timestamp) + responseWindow,
            slashAmount: 0
        });

        emit ChallengeOpened(challengeId, epochId, msg.sender, severity);
    }

    // --- Resolve (governance or adjudicator) ---

    function resolveChallenge(bytes32 challengeId, bool upheld, uint256 slashAmount) external {
        if (msg.sender != governance) revert Unauthorized();

        Challenge storage c = challenges[challengeId];
        if (c.openedAt == 0) revert ChallengeNotOpen();
        if (c.state != ChallengeState.OPEN && c.state != ChallengeState.RESPONDED) revert AlreadyResolved();

        if (upheld) {
            c.state = ChallengeState.UPHELD;
            c.slashAmount = slashAmount;
            // Return bond + reward to opener
            uint256 reward = _min(slashAmount * rewardShareBps / 10000, rewardCapWeth);
            uint256 total = c.bond + reward;
            if (!bondAsset.transfer(c.opener, total)) revert TransferFailed();
        } else {
            c.state = ChallengeState.REJECTED;
            // Penalize false challenge
            uint256 penalty = c.bond * falsePenaltyBps / 10000;
            uint256 refund = c.bond - penalty;
            if (refund > 0 && !bondAsset.transfer(c.opener, refund)) revert TransferFailed();
            if (penalty > 0 && !bondAsset.transfer(governance, penalty)) revert TransferFailed();
        }

        emit ChallengeResolved(challengeId, upheld, slashAmount);
    }

    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
}
