// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import "../src/governance/Governable2Step.sol";
import "../src/governance/DarwinTimelock.sol";

contract MockGoverned is Governable2Step {
    uint256 public value;

    constructor(address initialGovernance) Governable2Step(initialGovernance) {}

    function setValue(uint256 newValue) external onlyGovernance {
        value = newValue;
    }
}

contract GovernancePrimitivesTest is Test {
    address governance = address(0x1001);
    address nextGovernance = address(0x1002);
    address guardian = address(0x1003);
    MockGoverned governed;
    DarwinTimelock timelock;

    function setUp() public {
        governed = new MockGoverned(governance);
        timelock = new DarwinTimelock(governance, guardian, 2 days);
    }

    function test_governable_two_step_handoff() public {
        vm.prank(governance);
        governed.transferGovernance(nextGovernance);

        assertEq(governed.pendingGovernance(), nextGovernance);

        vm.prank(nextGovernance);
        governed.acceptGovernance();

        assertEq(governed.governance(), nextGovernance);
        assertEq(governed.pendingGovernance(), address(0));
    }

    function test_only_pending_governance_can_accept() public {
        vm.prank(governance);
        governed.transferGovernance(nextGovernance);

        vm.prank(address(0xBEEF));
        vm.expectRevert(Governable2Step.Unauthorized.selector);
        governed.acceptGovernance();
    }

    function test_timelock_schedules_and_executes_governed_call() public {
        vm.prank(governance);
        governed.transferGovernance(address(timelock));

        vm.prank(address(timelock));
        governed.acceptGovernance();

        bytes memory data = abi.encodeCall(MockGoverned.setValue, (77));
        bytes32 salt = keccak256("set-value");

        vm.prank(governance);
        bytes32 operationId = timelock.schedule(address(governed), 0, data, salt, 2 days);

        vm.expectRevert();
        timelock.execute(address(governed), 0, data, salt);

        vm.warp(block.timestamp + 2 days);
        timelock.execute(address(governed), 0, data, salt);

        assertEq(governed.value(), 77);
        assertEq(timelock.etaOf(operationId), 0);
    }

    function test_guardian_can_cancel() public {
        bytes memory data = abi.encodeCall(MockGoverned.setValue, (99));
        bytes32 salt = keccak256("cancel");

        vm.prank(governance);
        bytes32 operationId = timelock.schedule(address(governed), 0, data, salt, 2 days);

        vm.prank(guardian);
        timelock.cancel(operationId);

        assertEq(timelock.etaOf(operationId), 0);
    }

    function test_timelock_self_updates_delay() public {
        bytes memory data = abi.encodeCall(DarwinTimelock.setMinDelay, (5 days));
        bytes32 salt = keccak256("delay-update");

        vm.prank(governance);
        timelock.schedule(address(timelock), 0, data, salt, 2 days);

        vm.warp(block.timestamp + 2 days);
        timelock.execute(address(timelock), 0, data, salt);

        assertEq(timelock.minDelay(), 5 days);
    }
}
