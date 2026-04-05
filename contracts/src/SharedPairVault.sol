// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";

/// @title DARWIN SharedPairVault — pooled pair liquidity with virtual species allocation
/// @notice Species compete over execution logic. Capital settles in a shared vault.
contract SharedPairVault {
    struct PairVault {
        address baseAsset;
        address quoteAsset;
        uint256 baseBalance;
        uint256 quoteBalance;
        uint256 totalShares;
        uint256 insuranceBuffer;
        bytes32 speciesWeightRoot;
        bool    enabled;
    }

    // --- State ---

    address public governance;
    address public settlementHub;

    mapping(bytes32 => PairVault) public vaults;

    // LP shares: pairId => account => shares
    mapping(bytes32 => mapping(address => uint256)) public lpShares;

    // --- Events ---

    event Deposited(bytes32 indexed pairId, address indexed from, uint256 baseAmount, uint256 quoteAmount, uint256 shares);
    event Withdrawn(bytes32 indexed pairId, address indexed to, uint256 baseAmount, uint256 quoteAmount, uint256 shares);
    event WeightsUpdated(bytes32 indexed pairId, bytes32 weightRoot);
    event PairCreated(bytes32 indexed pairId, address baseAsset, address quoteAsset);

    // --- Errors ---

    error Unauthorized();
    error PairNotEnabled();
    error InsufficientShares();
    error TransferFailed();

    constructor(address _governance, address _settlementHub) {
        governance = _governance;
        settlementHub = _settlementHub;
    }

    // --- Pair management ---

    function createPair(bytes32 pairId, address baseAsset, address quoteAsset) external {
        if (msg.sender != governance) revert Unauthorized();
        vaults[pairId] = PairVault({
            baseAsset: baseAsset,
            quoteAsset: quoteAsset,
            baseBalance: 0,
            quoteBalance: 0,
            totalShares: 0,
            insuranceBuffer: 0,
            speciesWeightRoot: bytes32(0),
            enabled: true
        });
        emit PairCreated(pairId, baseAsset, quoteAsset);
    }

    // --- LP deposit ---

    function deposit(bytes32 pairId, uint256 baseAmount, uint256 quoteAmount) external {
        PairVault storage v = vaults[pairId];
        if (!v.enabled) revert PairNotEnabled();

        if (baseAmount > 0) {
            if (!IERC20(v.baseAsset).transferFrom(msg.sender, address(this), baseAmount)) revert TransferFailed();
            v.baseBalance += baseAmount;
        }
        if (quoteAmount > 0) {
            if (!IERC20(v.quoteAsset).transferFrom(msg.sender, address(this), quoteAmount)) revert TransferFailed();
            v.quoteBalance += quoteAmount;
        }

        // Mint shares proportional to deposit (simplified: 1:1 on first deposit)
        uint256 shares;
        if (v.totalShares == 0) {
            shares = baseAmount + quoteAmount;
        } else {
            uint256 totalValue = v.baseBalance + v.quoteBalance;
            shares = (baseAmount + quoteAmount) * v.totalShares / (totalValue - baseAmount - quoteAmount);
        }

        v.totalShares += shares;
        lpShares[pairId][msg.sender] += shares;

        emit Deposited(pairId, msg.sender, baseAmount, quoteAmount, shares);
    }

    // --- LP withdraw ---

    function withdraw(bytes32 pairId, uint256 shares) external {
        PairVault storage v = vaults[pairId];
        if (lpShares[pairId][msg.sender] < shares) revert InsufficientShares();

        uint256 baseOut = v.baseBalance * shares / v.totalShares;
        uint256 quoteOut = v.quoteBalance * shares / v.totalShares;

        v.totalShares -= shares;
        lpShares[pairId][msg.sender] -= shares;
        v.baseBalance -= baseOut;
        v.quoteBalance -= quoteOut;

        if (baseOut > 0 && !IERC20(v.baseAsset).transfer(msg.sender, baseOut)) revert TransferFailed();
        if (quoteOut > 0 && !IERC20(v.quoteAsset).transfer(msg.sender, quoteOut)) revert TransferFailed();

        emit Withdrawn(pairId, msg.sender, baseOut, quoteOut, shares);
    }

    // --- Settlement hub interactions ---

    function updateSpeciesWeights(bytes32 pairId, bytes32 weightRoot) external {
        if (msg.sender != settlementHub && msg.sender != governance) revert Unauthorized();
        vaults[pairId].speciesWeightRoot = weightRoot;
        emit WeightsUpdated(pairId, weightRoot);
    }

    // --- View ---

    function getVault(bytes32 pairId) external view returns (PairVault memory) {
        return vaults[pairId];
    }
}
