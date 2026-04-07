// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";
import {Governable2Step} from "./governance/Governable2Step.sol";
import {MerkleProofLib} from "./libraries/MerkleProofLib.sol";

/// @title DRWEpochDistributor
/// @notice Non-inflationary epoch emissions funded from a pre-minted DRW reserve.
contract DRWEpochDistributor is Governable2Step {
    struct Epoch {
        bytes32 merkleRoot;
        uint64 claimDeadline;
        uint256 totalAmount;
        uint256 distributedAmount;
    }

    IERC20 public immutable drwToken;
    uint256 public reservedAmount;

    mapping(uint256 => Epoch) public epochs;
    mapping(uint256 => mapping(uint256 => uint256)) private claimedBitMap;

    event EpochConfigured(uint256 indexed epochId, bytes32 merkleRoot, uint64 claimDeadline, uint256 totalAmount);
    event Claimed(uint256 indexed epochId, uint256 indexed index, address indexed account, uint256 amount);
    event Swept(uint256 indexed epochId, address indexed recipient, uint256 amount);

    error AlreadyClaimed();
    error ClaimClosed();
    error EpochClosed();
    error EpochNotConfigured();
    error EpochAlreadyConfigured();
    error EpochOverallocated();
    error InsufficientReserve();
    error InvalidClaimRoot();
    error InvalidDeadline();
    error InvalidAmount();
    error InvalidProof();
    error SweepLocked();
    error TransferFailed();

    constructor(address token, address initialGovernance) Governable2Step(initialGovernance) {
        if (token == address(0)) revert InvalidRecipient();
        drwToken = IERC20(token);
    }

    function configureEpoch(uint256 epochId, bytes32 root, uint64 deadline, uint256 totalAmount) external onlyGovernance {
        if (epochs[epochId].merkleRoot != bytes32(0)) revert EpochAlreadyConfigured();
        if (root == bytes32(0)) revert InvalidClaimRoot();
        if (deadline <= block.timestamp) revert InvalidDeadline();
        if (totalAmount == 0) revert InvalidAmount();

        uint256 currentBalance = drwToken.balanceOf(address(this));
        if (currentBalance < reservedAmount + totalAmount) revert InsufficientReserve();

        epochs[epochId] = Epoch({
            merkleRoot: root,
            claimDeadline: deadline,
            totalAmount: totalAmount,
            distributedAmount: 0
        });
        reservedAmount += totalAmount;

        emit EpochConfigured(epochId, root, deadline, totalAmount);
    }

    function isClaimed(uint256 epochId, uint256 index) public view returns (bool) {
        uint256 wordIndex = index / 256;
        uint256 bitIndex = index % 256;
        uint256 claimedWord = claimedBitMap[epochId][wordIndex];
        uint256 mask = uint256(1) << bitIndex;
        return claimedWord & mask == mask;
    }

    function epochRemaining(uint256 epochId) public view returns (uint256) {
        Epoch memory epoch = epochs[epochId];
        if (epoch.merkleRoot == bytes32(0)) revert EpochNotConfigured();
        return epoch.totalAmount - epoch.distributedAmount;
    }

    function availableReserve() external view returns (uint256) {
        return drwToken.balanceOf(address(this)) - reservedAmount;
    }

    function claim(uint256 epochId, uint256 index, address account, uint256 amount, bytes32[] calldata merkleProof)
        external
    {
        Epoch storage epoch = epochs[epochId];
        if (epoch.merkleRoot == bytes32(0)) revert EpochNotConfigured();
        if (block.timestamp > epoch.claimDeadline) revert ClaimClosed();
        if (account == address(0)) revert InvalidRecipient();
        if (amount == 0) revert InvalidAmount();
        if (isClaimed(epochId, index)) revert AlreadyClaimed();

        bytes32 leaf = keccak256(bytes.concat(keccak256(abi.encode(epochId, index, account, amount))));
        if (!MerkleProofLib.verify(merkleProof, epoch.merkleRoot, leaf)) revert InvalidProof();

        uint256 nextDistributed = epoch.distributedAmount + amount;
        if (nextDistributed > epoch.totalAmount) revert EpochOverallocated();

        _setClaimed(epochId, index);
        epoch.distributedAmount = nextDistributed;
        reservedAmount -= amount;

        if (!drwToken.transfer(account, amount)) revert TransferFailed();
        emit Claimed(epochId, index, account, amount);
    }

    function sweep(uint256 epochId, address recipient, uint256 amount) external onlyGovernance {
        Epoch storage epoch = epochs[epochId];
        if (epoch.merkleRoot == bytes32(0)) revert EpochNotConfigured();
        if (block.timestamp <= epoch.claimDeadline) revert SweepLocked();
        if (recipient == address(0)) revert InvalidRecipient();
        if (amount == 0) revert InvalidAmount();

        uint256 nextDistributed = epoch.distributedAmount + amount;
        if (nextDistributed > epoch.totalAmount) revert EpochOverallocated();

        epoch.distributedAmount = nextDistributed;
        reservedAmount -= amount;

        if (!drwToken.transfer(recipient, amount)) revert TransferFailed();
        emit Swept(epochId, recipient, amount);
    }

    function _setClaimed(uint256 epochId, uint256 index) internal {
        uint256 wordIndex = index / 256;
        uint256 bitIndex = index % 256;
        claimedBitMap[epochId][wordIndex] |= uint256(1) << bitIndex;
    }
}
