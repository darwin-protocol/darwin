// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";

/// @title DARWIN DRW Token
/// @notice Fixed-supply governance stake token with a one-time genesis mint window.
contract DRWToken is IERC20 {
    string public constant name = "Darwin Genomic Stake";
    string public constant symbol = "DRW";
    uint8 public constant decimals = 18;

    address public governance;
    address public genesisOperator;
    bool public genesisFinalized;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    uint256 public totalSupply;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event GovernanceUpdated(address indexed oldGovernance, address indexed newGovernance);
    event GenesisOperatorUpdated(address indexed oldOperator, address indexed newOperator);
    event GenesisMinted(address indexed to, uint256 amount);
    event GenesisFinalized(uint256 totalSupply);

    error Unauthorized();
    error InvalidRecipient();
    error InvalidAmount();
    error GenesisClosed();
    error InsufficientBalance();
    error InsufficientAllowance();

    constructor(address _governance, address _genesisOperator) {
        if (_governance == address(0) || _genesisOperator == address(0)) revert InvalidRecipient();
        governance = _governance;
        genesisOperator = _genesisOperator;
    }

    modifier onlyGovernance() {
        if (msg.sender != governance) revert Unauthorized();
        _;
    }

    modifier onlyGenesisOperator() {
        if (msg.sender != genesisOperator && msg.sender != governance) revert Unauthorized();
        _;
    }

    function setGovernance(address newGovernance) external onlyGovernance {
        if (newGovernance == address(0)) revert InvalidRecipient();
        address oldGovernance = governance;
        governance = newGovernance;
        emit GovernanceUpdated(oldGovernance, newGovernance);
    }

    function setGenesisOperator(address newGenesisOperator) external onlyGovernance {
        if (genesisFinalized) revert GenesisClosed();
        if (newGenesisOperator == address(0)) revert InvalidRecipient();
        address oldOperator = genesisOperator;
        genesisOperator = newGenesisOperator;
        emit GenesisOperatorUpdated(oldOperator, newGenesisOperator);
    }

    function mintGenesis(address to, uint256 amount) external onlyGenesisOperator {
        if (genesisFinalized) revert GenesisClosed();
        if (to == address(0)) revert InvalidRecipient();
        if (amount == 0) revert InvalidAmount();
        _mint(to, amount);
        emit GenesisMinted(to, amount);
    }

    function finalizeGenesis() external onlyGenesisOperator {
        if (genesisFinalized) revert GenesisClosed();
        genesisFinalized = true;
        genesisOperator = address(0);
        emit GenesisFinalized(totalSupply);
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed < amount) revert InsufficientAllowance();
        if (allowed != type(uint256).max) {
            allowance[from][msg.sender] = allowed - amount;
            emit Approval(from, msg.sender, allowance[from][msg.sender]);
        }
        _transfer(from, to, amount);
        return true;
    }

    function _mint(address to, uint256 amount) internal {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function _transfer(address from, address to, uint256 amount) internal {
        if (to == address(0)) revert InvalidRecipient();
        uint256 fromBalance = balanceOf[from];
        if (fromBalance < amount) revert InsufficientBalance();
        balanceOf[from] = fromBalance - amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}
