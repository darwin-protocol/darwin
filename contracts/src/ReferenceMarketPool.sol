// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";

/// @title DARWIN ReferenceMarketPool
/// @notice Governance- or operator-seeded constant-product DRW/quote market for testnet bootstrap.
contract ReferenceMarketPool {
    IERC20 public immutable baseToken;
    IERC20 public immutable quoteToken;
    uint16 public immutable feeBps;

    address public governance;
    address public marketOperator;
    bool public seeded;
    uint256 public baseReserve;
    uint256 public quoteReserve;

    bool private _locked;

    event GovernanceUpdated(address indexed oldGovernance, address indexed newGovernance);
    event MarketOperatorUpdated(address indexed oldOperator, address indexed newOperator);
    event InitialLiquiditySeeded(address indexed operator, uint256 baseAmount, uint256 quoteAmount);
    event LiquidityAdded(address indexed operator, uint256 baseAmount, uint256 quoteAmount);
    event LiquidityRemoved(address indexed operator, address indexed to, uint256 baseAmount, uint256 quoteAmount);
    event SwapExecuted(
        address indexed trader,
        address indexed tokenIn,
        uint256 amountIn,
        address indexed tokenOut,
        uint256 amountOut,
        address to
    );

    error Unauthorized();
    error InvalidConfig();
    error InvalidAmount();
    error InvalidRecipient();
    error PoolAlreadySeeded();
    error PoolNotSeeded();
    error UnsupportedToken();
    error InsufficientLiquidity();
    error SlippageExceeded();
    error TransferFailed();
    error Reentrancy();

    constructor(address _baseToken, address _quoteToken, address _governance, address _marketOperator, uint16 _feeBps) {
        if (
            _baseToken == address(0) || _quoteToken == address(0) || _baseToken == _quoteToken || _governance == address(0)
                || _marketOperator == address(0) || _feeBps >= 10_000
        ) revert InvalidConfig();
        baseToken = IERC20(_baseToken);
        quoteToken = IERC20(_quoteToken);
        governance = _governance;
        marketOperator = _marketOperator;
        feeBps = _feeBps;
    }

    modifier onlyGovernance() {
        if (msg.sender != governance) revert Unauthorized();
        _;
    }

    modifier onlyOperator() {
        if (msg.sender != marketOperator && msg.sender != governance) revert Unauthorized();
        _;
    }

    modifier nonReentrant() {
        if (_locked) revert Reentrancy();
        _locked = true;
        _;
        _locked = false;
    }

    function setGovernance(address newGovernance) external onlyGovernance {
        if (newGovernance == address(0)) revert InvalidRecipient();
        address oldGovernance = governance;
        governance = newGovernance;
        emit GovernanceUpdated(oldGovernance, newGovernance);
    }

    function setMarketOperator(address newOperator) external onlyGovernance {
        if (newOperator == address(0)) revert InvalidRecipient();
        address oldOperator = marketOperator;
        marketOperator = newOperator;
        emit MarketOperatorUpdated(oldOperator, newOperator);
    }

    function seedInitialLiquidity(uint256 baseAmount, uint256 quoteAmount) external onlyOperator nonReentrant {
        if (seeded) revert PoolAlreadySeeded();
        if (baseAmount == 0 || quoteAmount == 0) revert InvalidAmount();
        _pull(baseToken, msg.sender, baseAmount);
        _pull(quoteToken, msg.sender, quoteAmount);
        baseReserve = baseAmount;
        quoteReserve = quoteAmount;
        seeded = true;
        emit InitialLiquiditySeeded(msg.sender, baseAmount, quoteAmount);
    }

    function addLiquidity(uint256 baseAmount, uint256 quoteAmount) external onlyOperator nonReentrant {
        if (!seeded) revert PoolNotSeeded();
        if (baseAmount == 0 || quoteAmount == 0) revert InvalidAmount();
        _pull(baseToken, msg.sender, baseAmount);
        _pull(quoteToken, msg.sender, quoteAmount);
        baseReserve += baseAmount;
        quoteReserve += quoteAmount;
        emit LiquidityAdded(msg.sender, baseAmount, quoteAmount);
    }

    function removeLiquidity(uint256 baseAmount, uint256 quoteAmount, address to) external onlyOperator nonReentrant {
        if (!seeded) revert PoolNotSeeded();
        if (to == address(0)) revert InvalidRecipient();
        if (baseAmount == 0 && quoteAmount == 0) revert InvalidAmount();
        if (baseAmount > baseReserve || quoteAmount > quoteReserve) revert InsufficientLiquidity();
        baseReserve -= baseAmount;
        quoteReserve -= quoteAmount;
        _push(baseToken, to, baseAmount);
        _push(quoteToken, to, quoteAmount);
        emit LiquidityRemoved(msg.sender, to, baseAmount, quoteAmount);
    }

    function quoteExactInput(address tokenIn, uint256 amountIn) public view returns (uint256 amountOut) {
        if (!seeded) revert PoolNotSeeded();
        if (amountIn == 0) revert InvalidAmount();

        bool isBaseIn = tokenIn == address(baseToken);
        bool isQuoteIn = tokenIn == address(quoteToken);
        if (!isBaseIn && !isQuoteIn) revert UnsupportedToken();

        uint256 reserveIn = isBaseIn ? baseReserve : quoteReserve;
        uint256 reserveOut = isBaseIn ? quoteReserve : baseReserve;
        if (reserveIn == 0 || reserveOut == 0) revert InsufficientLiquidity();

        uint256 amountInWithFee = amountIn * (10_000 - feeBps);
        amountOut = (reserveOut * amountInWithFee) / ((reserveIn * 10_000) + amountInWithFee);
        if (amountOut == 0 || amountOut >= reserveOut) revert InsufficientLiquidity();
    }

    function swapExactInput(address tokenIn, uint256 amountIn, uint256 minAmountOut, address to)
        external
        nonReentrant
        returns (uint256 amountOut)
    {
        if (to == address(0)) revert InvalidRecipient();
        amountOut = quoteExactInput(tokenIn, amountIn);
        if (amountOut < minAmountOut) revert SlippageExceeded();

        bool isBaseIn = tokenIn == address(baseToken);
        IERC20 tokenInContract = isBaseIn ? baseToken : quoteToken;
        IERC20 tokenOutContract = isBaseIn ? quoteToken : baseToken;

        _pull(tokenInContract, msg.sender, amountIn);
        _push(tokenOutContract, to, amountOut);

        if (isBaseIn) {
            baseReserve += amountIn;
            quoteReserve -= amountOut;
            emit SwapExecuted(msg.sender, address(baseToken), amountIn, address(quoteToken), amountOut, to);
        } else {
            quoteReserve += amountIn;
            baseReserve -= amountOut;
            emit SwapExecuted(msg.sender, address(quoteToken), amountIn, address(baseToken), amountOut, to);
        }
    }

    function _pull(IERC20 token, address from, uint256 amount) internal {
        if (!token.transferFrom(from, address(this), amount)) revert TransferFailed();
    }

    function _push(IERC20 token, address to, uint256 amount) internal {
        if (amount == 0) return;
        if (!token.transfer(to, amount)) revert TransferFailed();
    }
}
