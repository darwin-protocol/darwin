// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";
import {Governable2Step} from "./governance/Governable2Step.sol";
import {MerkleProofLib} from "./libraries/MerkleProofLib.sol";

/// @title DRWMerkleDistributor
/// @notice Rule-based DRW distribution primitive for vNext community allocations.
contract DRWMerkleDistributor is Governable2Step {
    IERC20 public immutable drwToken;
    bytes32 public immutable merkleRoot;
    uint64 public immutable claimDeadline;

    mapping(uint256 => uint256) private claimedBitMap;

    event Claimed(uint256 indexed index, address indexed account, uint256 amount);
    event Swept(address indexed recipient, uint256 amount);

    error AlreadyClaimed();
    error ClaimClosed();
    error SweepLocked();
    error InvalidClaimRoot();
    error InvalidProof();
    error InvalidDeadline();
    error InvalidAmount();
    error TransferFailed();

    constructor(address token, address initialGovernance, bytes32 root, uint64 deadline)
        Governable2Step(initialGovernance)
    {
        if (token == address(0)) revert InvalidRecipient();
        if (root == bytes32(0)) revert InvalidClaimRoot();
        if (deadline <= block.timestamp) revert InvalidDeadline();

        drwToken = IERC20(token);
        merkleRoot = root;
        claimDeadline = deadline;
    }

    function isClaimed(uint256 index) public view returns (bool) {
        uint256 wordIndex = index / 256;
        uint256 bitIndex = index % 256;
        uint256 claimedWord = claimedBitMap[wordIndex];
        uint256 mask = (uint256(1) << bitIndex);
        return claimedWord & mask == mask;
    }

    function claim(uint256 index, address account, uint256 amount, bytes32[] calldata merkleProof) external {
        if (block.timestamp > claimDeadline) revert ClaimClosed();
        if (account == address(0)) revert InvalidRecipient();
        if (amount == 0) revert InvalidAmount();
        if (isClaimed(index)) revert AlreadyClaimed();

        bytes32 leaf = keccak256(bytes.concat(keccak256(abi.encode(index, account, amount))));
        if (!MerkleProofLib.verify(merkleProof, merkleRoot, leaf)) revert InvalidProof();

        _setClaimed(index);
        if (!drwToken.transfer(account, amount)) revert TransferFailed();
        emit Claimed(index, account, amount);
    }

    function sweep(address recipient, uint256 amount) external onlyGovernance {
        if (block.timestamp <= claimDeadline) revert SweepLocked();
        if (recipient == address(0)) revert InvalidRecipient();
        if (amount == 0) revert InvalidAmount();
        if (!drwToken.transfer(recipient, amount)) revert TransferFailed();
        emit Swept(recipient, amount);
    }

    function _setClaimed(uint256 index) internal {
        uint256 wordIndex = index / 256;
        uint256 bitIndex = index % 256;
        claimedBitMap[wordIndex] = claimedBitMap[wordIndex] | (uint256(1) << bitIndex);
    }
}
