// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";

/// @title DARWIN DRW Staking
/// @notice Single-token staking pool funded from preloaded DRW rewards.
contract DRWStaking {
    IERC20 public immutable drwToken;
    address public governance;
    address public genesisOperator;

    uint256 public totalStaked;
    uint256 public rewardRate;
    uint256 public rewardDuration;
    uint256 public periodFinish;
    uint256 public lastUpdateTime;
    uint256 public rewardPerTokenStored;

    mapping(address => uint256) public balances;
    mapping(address => uint256) public userRewardPerTokenPaid;
    mapping(address => uint256) public rewards;

    event Staked(address indexed account, uint256 amount);
    event Withdrawn(address indexed account, uint256 amount);
    event RewardPaid(address indexed account, uint256 amount);
    event RewardNotified(uint256 amount, uint256 duration);
    event GovernanceUpdated(address indexed oldGovernance, address indexed newGovernance);
    event GenesisOperatorCleared(address indexed oldOperator);

    error Unauthorized();
    error InvalidAmount();
    error InvalidDuration();
    error InsufficientStake();
    error InsufficientRewardBalance();
    error TransferFailed();

    constructor(address _drwToken, address _governance, address _genesisOperator) {
        if (_drwToken == address(0) || _governance == address(0) || _genesisOperator == address(0)) revert InvalidAmount();
        drwToken = IERC20(_drwToken);
        governance = _governance;
        genesisOperator = _genesisOperator;
    }

    modifier onlyGovernance() {
        if (msg.sender != governance) revert Unauthorized();
        _;
    }

    modifier onlyRewardAdmin() {
        if (msg.sender != governance && msg.sender != genesisOperator) revert Unauthorized();
        _;
    }

    modifier updateReward(address account) {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (account != address(0)) {
            rewards[account] = earned(account);
            userRewardPerTokenPaid[account] = rewardPerTokenStored;
        }
        _;
    }

    function setGovernance(address newGovernance) external onlyGovernance {
        if (newGovernance == address(0)) revert InvalidAmount();
        address oldGovernance = governance;
        governance = newGovernance;
        emit GovernanceUpdated(oldGovernance, newGovernance);
    }

    function stake(uint256 amount) external updateReward(msg.sender) {
        if (amount == 0) revert InvalidAmount();
        totalStaked += amount;
        balances[msg.sender] += amount;
        if (!drwToken.transferFrom(msg.sender, address(this), amount)) revert TransferFailed();
        emit Staked(msg.sender, amount);
    }

    function withdraw(uint256 amount) public updateReward(msg.sender) {
        if (amount == 0) revert InvalidAmount();
        uint256 balance = balances[msg.sender];
        if (balance < amount) revert InsufficientStake();
        balances[msg.sender] = balance - amount;
        totalStaked -= amount;
        if (!drwToken.transfer(msg.sender, amount)) revert TransferFailed();
        emit Withdrawn(msg.sender, amount);
    }

    function getReward() public updateReward(msg.sender) {
        uint256 reward = rewards[msg.sender];
        if (reward == 0) return;
        rewards[msg.sender] = 0;
        if (!drwToken.transfer(msg.sender, reward)) revert TransferFailed();
        emit RewardPaid(msg.sender, reward);
    }

    function exit() external {
        withdraw(balances[msg.sender]);
        getReward();
    }

    function notifyRewardAmount(uint256 amount, uint256 duration) external onlyRewardAdmin updateReward(address(0)) {
        if (amount == 0) revert InvalidAmount();
        if (duration == 0) revert InvalidDuration();

        uint256 nextRewardRate;
        if (block.timestamp >= periodFinish) {
            nextRewardRate = amount / duration;
        } else {
            uint256 remaining = periodFinish - block.timestamp;
            uint256 leftover = remaining * rewardRate;
            nextRewardRate = (amount + leftover) / duration;
        }
        if (nextRewardRate == 0) revert InvalidAmount();

        uint256 availableRewards = drwToken.balanceOf(address(this)) - totalStaked;
        if (nextRewardRate * duration > availableRewards) revert InsufficientRewardBalance();

        rewardRate = nextRewardRate;
        rewardDuration = duration;
        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp + duration;
        if (msg.sender == genesisOperator && genesisOperator != address(0)) {
            address oldOperator = genesisOperator;
            genesisOperator = address(0);
            emit GenesisOperatorCleared(oldOperator);
        }
        emit RewardNotified(amount, duration);
    }

    function lastTimeRewardApplicable() public view returns (uint256) {
        return block.timestamp < periodFinish ? block.timestamp : periodFinish;
    }

    function rewardPerToken() public view returns (uint256) {
        if (totalStaked == 0) return rewardPerTokenStored;
        return rewardPerTokenStored + (((lastTimeRewardApplicable() - lastUpdateTime) * rewardRate * 1e18) / totalStaked);
    }

    function earned(address account) public view returns (uint256) {
        return ((balances[account] * (rewardPerToken() - userRewardPerTokenPaid[account])) / 1e18) + rewards[account];
    }
}
