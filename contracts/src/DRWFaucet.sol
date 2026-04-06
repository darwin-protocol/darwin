// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";

/// @title DARWIN DRW Faucet
/// @notice Transparent testnet-only DRW distributor with an optional native-ETH drip.
contract DRWFaucet {
    IERC20 public immutable token;

    address public governance;
    uint256 public claimAmount;
    uint256 public nativeDripAmount;
    uint256 public claimCooldown;
    bool public paused;

    mapping(address => uint256) public nextClaimAt;

    event GovernanceUpdated(address indexed oldGovernance, address indexed newGovernance);
    event ClaimConfigUpdated(uint256 claimAmount, uint256 nativeDripAmount, uint256 claimCooldown);
    event PauseUpdated(bool paused);
    event Claimed(
        address indexed claimer,
        address indexed recipient,
        uint256 tokenAmount,
        uint256 nativeAmount,
        uint256 nextEligibleAt
    );
    event NativeWithdrawn(address indexed to, uint256 amount);
    event TokenWithdrawn(address indexed to, uint256 amount);

    error Unauthorized();
    error InvalidRecipient();
    error InvalidConfig();
    error FaucetPaused();
    error ClaimTooEarly(uint256 nextEligibleAt);
    error TokenTransferFailed();
    error NativeTransferFailed();
    error InsufficientTokenBalance();

    constructor(
        address _token,
        address _governance,
        uint256 _claimAmount,
        uint256 _nativeDripAmount,
        uint256 _claimCooldown
    ) {
        if (_token == address(0) || _governance == address(0)) revert InvalidRecipient();
        if (_claimAmount == 0 && _nativeDripAmount == 0) revert InvalidConfig();
        if (_claimCooldown == 0) revert InvalidConfig();

        token = IERC20(_token);
        governance = _governance;
        claimAmount = _claimAmount;
        nativeDripAmount = _nativeDripAmount;
        claimCooldown = _claimCooldown;
    }

    modifier onlyGovernance() {
        if (msg.sender != governance) revert Unauthorized();
        _;
    }

    receive() external payable {}

    function fundNative() external payable {}

    function setGovernance(address newGovernance) external onlyGovernance {
        if (newGovernance == address(0)) revert InvalidRecipient();
        address oldGovernance = governance;
        governance = newGovernance;
        emit GovernanceUpdated(oldGovernance, newGovernance);
    }

    function setClaimConfig(uint256 newClaimAmount, uint256 newNativeDripAmount, uint256 newClaimCooldown)
        external
        onlyGovernance
    {
        if (newClaimAmount == 0 && newNativeDripAmount == 0) revert InvalidConfig();
        if (newClaimCooldown == 0) revert InvalidConfig();
        claimAmount = newClaimAmount;
        nativeDripAmount = newNativeDripAmount;
        claimCooldown = newClaimCooldown;
        emit ClaimConfigUpdated(newClaimAmount, newNativeDripAmount, newClaimCooldown);
    }

    function setPaused(bool isPaused) external onlyGovernance {
        paused = isPaused;
        emit PauseUpdated(isPaused);
    }

    function claim() external returns (uint256 tokenAmountOut, uint256 nativeAmountOut) {
        if (paused) revert FaucetPaused();

        uint256 eligibleAt = nextClaimAt[msg.sender];
        if (eligibleAt != 0 && block.timestamp < eligibleAt) revert ClaimTooEarly(eligibleAt);

        tokenAmountOut = claimAmount;
        nativeAmountOut = nativeDripAmount <= address(this).balance ? nativeDripAmount : 0;

        if (tokenAmountOut != 0) {
            if (token.balanceOf(address(this)) < tokenAmountOut) revert InsufficientTokenBalance();
            if (!token.transfer(msg.sender, tokenAmountOut)) revert TokenTransferFailed();
        }

        if (nativeAmountOut != 0) {
            (bool ok,) = payable(msg.sender).call{value: nativeAmountOut}("");
            if (!ok) revert NativeTransferFailed();
        }

        uint256 nextEligibleAt = block.timestamp + claimCooldown;
        nextClaimAt[msg.sender] = nextEligibleAt;
        emit Claimed(msg.sender, msg.sender, tokenAmountOut, nativeAmountOut, nextEligibleAt);
    }

    function withdrawToken(address to, uint256 amount) external onlyGovernance {
        if (to == address(0)) revert InvalidRecipient();
        if (!token.transfer(to, amount)) revert TokenTransferFailed();
        emit TokenWithdrawn(to, amount);
    }

    function withdrawNative(address to, uint256 amount) external onlyGovernance {
        if (to == address(0)) revert InvalidRecipient();
        (bool ok,) = payable(to).call{value: amount}("");
        if (!ok) revert NativeTransferFailed();
        emit NativeWithdrawn(to, amount);
    }
}
