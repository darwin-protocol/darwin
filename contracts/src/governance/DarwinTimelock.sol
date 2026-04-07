// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Governable2Step} from "./Governable2Step.sol";

/// @title DarwinTimelock
/// @notice Minimal execution delay layer for vNext DARWIN governance actions.
contract DarwinTimelock is Governable2Step {
    uint64 public constant GRACE_PERIOD = 14 days;

    uint64 public minDelay;
    address public guardian;

    mapping(bytes32 => uint64) public etaOf;

    event OperationScheduled(
        bytes32 indexed operationId,
        address indexed target,
        uint256 value,
        bytes data,
        bytes32 salt,
        uint64 eta
    );
    event OperationCancelled(bytes32 indexed operationId);
    event OperationExecuted(bytes32 indexed operationId, address indexed target, uint256 value, bytes data);
    event GuardianUpdated(address indexed previousGuardian, address indexed newGuardian);
    event MinDelayUpdated(uint64 previousDelay, uint64 newDelay);

    error InvalidDelay();
    error InvalidTarget();
    error AlreadyScheduled();
    error NotScheduled();
    error NotReady(uint64 eta);
    error Expired(uint64 eta);
    error ExecutionFailed(bytes reason);

    constructor(address initialGovernance, address initialGuardian, uint64 initialMinDelay)
        Governable2Step(initialGovernance)
    {
        if (initialMinDelay == 0) revert InvalidDelay();
        minDelay = initialMinDelay;
        guardian = initialGuardian;
        emit GuardianUpdated(address(0), initialGuardian);
        emit MinDelayUpdated(0, initialMinDelay);
    }

    receive() external payable {}

    function hashOperation(address target, uint256 value, bytes calldata data, bytes32 salt)
        public
        pure
        returns (bytes32)
    {
        return keccak256(abi.encode(target, value, data, salt));
    }

    function schedule(address target, uint256 value, bytes calldata data, bytes32 salt, uint64 delay)
        external
        onlyGovernance
        returns (bytes32 operationId)
    {
        if (target == address(0)) revert InvalidTarget();
        if (delay < minDelay) revert InvalidDelay();

        operationId = hashOperation(target, value, data, salt);
        if (etaOf[operationId] != 0) revert AlreadyScheduled();

        uint64 eta = uint64(block.timestamp) + delay;
        etaOf[operationId] = eta;
        emit OperationScheduled(operationId, target, value, data, salt, eta);
    }

    function cancel(bytes32 operationId) external {
        if (msg.sender != governance && msg.sender != guardian) revert Unauthorized();
        if (etaOf[operationId] == 0) revert NotScheduled();
        delete etaOf[operationId];
        emit OperationCancelled(operationId);
    }

    function execute(address target, uint256 value, bytes calldata data, bytes32 salt)
        external
        payable
        returns (bytes memory result)
    {
        bytes32 operationId = hashOperation(target, value, data, salt);
        uint64 eta = etaOf[operationId];
        if (eta == 0) revert NotScheduled();
        if (block.timestamp < eta) revert NotReady(eta);
        if (block.timestamp > eta + GRACE_PERIOD) revert Expired(eta);

        delete etaOf[operationId];
        (bool ok, bytes memory returned) = target.call{value: value}(data);
        if (!ok) revert ExecutionFailed(returned);

        emit OperationExecuted(operationId, target, value, data);
        return returned;
    }

    function setGuardian(address newGuardian) external {
        if (msg.sender != address(this)) revert Unauthorized();
        address previousGuardian = guardian;
        guardian = newGuardian;
        emit GuardianUpdated(previousGuardian, newGuardian);
    }

    function setMinDelay(uint64 newDelay) external {
        if (msg.sender != address(this)) revert Unauthorized();
        if (newDelay == 0) revert InvalidDelay();
        uint64 previousDelay = minDelay;
        minDelay = newDelay;
        emit MinDelayUpdated(previousDelay, newDelay);
    }
}
