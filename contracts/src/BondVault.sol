// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";

/// @title DARWIN BondVault — holds WETH bonds for all protocol actors
/// @notice v1 bonds are WETH only. DRW bonds are a future activation.
contract BondVault {
    // --- Types ---

    enum SubjectType { SPECIES, GATEWAY, ROUTER, SCORE_POSTER, WATCHER_STANDING }

    struct Bond {
        uint256 amount;
        uint64  depositedAt;
        bool    active;
    }

    // --- State ---

    IERC20 public immutable bondAsset; // WETH
    address public governance;
    address public challengeEscrow;

    // account => subjectType => subjectId => Bond
    mapping(address => mapping(SubjectType => mapping(bytes32 => Bond))) public bonds;

    uint64 public constant WITHDRAWAL_COOLDOWN = 7 days;

    // --- Events ---

    event BondDeposited(address indexed account, SubjectType indexed subjectType, bytes32 indexed subjectId, uint256 amount);
    event BondSlashed(address indexed account, SubjectType indexed subjectType, bytes32 indexed subjectId, uint256 amount, bytes32 reason);
    event BondWithdrawn(address indexed account, SubjectType indexed subjectType, bytes32 indexed subjectId, uint256 amount);

    // --- Errors ---

    error Unauthorized();
    error InsufficientBond();
    error CooldownNotElapsed();
    error TransferFailed();

    // --- Constructor ---

    constructor(address _bondAsset, address _governance, address _challengeEscrow) {
        bondAsset = IERC20(_bondAsset);
        governance = _governance;
        challengeEscrow = _challengeEscrow;
    }

    // --- Deposit ---

    function depositBond(SubjectType subjectType, bytes32 subjectId, uint256 amount) external {
        if (!bondAsset.transferFrom(msg.sender, address(this), amount)) revert TransferFailed();

        Bond storage b = bonds[msg.sender][subjectType][subjectId];
        b.amount += amount;
        b.depositedAt = uint64(block.timestamp);
        b.active = true;

        emit BondDeposited(msg.sender, subjectType, subjectId, amount);
    }

    // --- Slash (ChallengeEscrow only) ---

    function slashBond(
        address account,
        SubjectType subjectType,
        bytes32 subjectId,
        uint256 amount,
        bytes32 reason
    ) external {
        if (msg.sender != challengeEscrow) revert Unauthorized();

        Bond storage b = bonds[account][subjectType][subjectId];
        uint256 slashAmt = amount > b.amount ? b.amount : amount;
        b.amount -= slashAmt;
        if (b.amount == 0) b.active = false;

        // Slashed funds go to pair insurance (governance-controlled)
        if (!bondAsset.transfer(governance, slashAmt)) revert TransferFailed();

        emit BondSlashed(account, subjectType, subjectId, slashAmt, reason);
    }

    // --- Withdraw ---

    function withdrawBond(SubjectType subjectType, bytes32 subjectId, uint256 amount) external {
        Bond storage b = bonds[msg.sender][subjectType][subjectId];
        if (b.amount < amount) revert InsufficientBond();
        if (block.timestamp < b.depositedAt + WITHDRAWAL_COOLDOWN) revert CooldownNotElapsed();

        b.amount -= amount;
        if (b.amount == 0) b.active = false;

        if (!bondAsset.transfer(msg.sender, amount)) revert TransferFailed();

        emit BondWithdrawn(msg.sender, subjectType, subjectId, amount);
    }

    // --- View ---

    function getBond(address account, SubjectType subjectType, bytes32 subjectId)
        external view returns (uint256 amount, bool active)
    {
        Bond storage b = bonds[account][subjectType][subjectId];
        return (b.amount, b.active);
    }
}
