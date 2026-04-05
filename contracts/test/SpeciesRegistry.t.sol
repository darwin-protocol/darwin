// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/SpeciesRegistry.sol";

contract SpeciesRegistryTest is Test {
    SpeciesRegistry reg;
    address governance = address(0x1001);
    address operator = address(0x3003);
    address escrow = address(0x2002);
    address alice = address(0xA11CE);

    function setUp() public {
        reg = new SpeciesRegistry(governance, operator, escrow);
    }

    function test_propose_species() public {
        vm.prank(alice);
        reg.proposeSpecies(bytes32("S1"), bytes32("genome1"), bytes32("manifest1"));

        SpeciesRegistry.Species memory s = reg.getSpecies(bytes32("S1"));
        assertEq(s.sponsor, alice);
        assertEq(uint(s.state), uint(SpeciesRegistry.SpeciesState.PROPOSED));
        assertEq(reg.getSpeciesCount(), 1);
    }

    function test_no_duplicate_species() public {
        vm.prank(alice);
        reg.proposeSpecies(bytes32("S1"), bytes32("g1"), bytes32("m1"));

        vm.prank(alice);
        vm.expectRevert(SpeciesRegistry.SpeciesExists.selector);
        reg.proposeSpecies(bytes32("S1"), bytes32("g2"), bytes32("m2"));
    }

    function test_state_transitions() public {
        vm.prank(alice);
        reg.proposeSpecies(bytes32("S1"), bytes32("g1"), bytes32("m1"));

        // Operator can advance state
        vm.prank(operator);
        reg.setSpeciesState(bytes32("S1"), SpeciesRegistry.SpeciesState.CANARY);

        SpeciesRegistry.Species memory s = reg.getSpecies(bytes32("S1"));
        assertEq(uint(s.state), uint(SpeciesRegistry.SpeciesState.CANARY));

        vm.prank(operator);
        reg.setSpeciesState(bytes32("S1"), SpeciesRegistry.SpeciesState.ACTIVE);
        assertTrue(reg.isActive(bytes32("S1")));
    }

    function test_only_operator_or_governance() public {
        vm.prank(alice);
        reg.proposeSpecies(bytes32("S1"), bytes32("g1"), bytes32("m1"));

        vm.prank(alice);
        vm.expectRevert(SpeciesRegistry.Unauthorized.selector);
        reg.setSpeciesState(bytes32("S1"), SpeciesRegistry.SpeciesState.ACTIVE);
    }

    function test_set_state_requires_existing_species() public {
        vm.prank(operator);
        vm.expectRevert(SpeciesRegistry.SpeciesNotFound.selector);
        reg.setSpeciesState(bytes32("missing"), SpeciesRegistry.SpeciesState.ACTIVE);
    }

    function test_slash_only_escrow() public {
        vm.prank(alice);
        reg.proposeSpecies(bytes32("S1"), bytes32("g1"), bytes32("m1"));

        vm.prank(alice);
        vm.expectRevert(SpeciesRegistry.Unauthorized.selector);
        reg.slashSpecies(bytes32("S1"), 1 ether, bytes32("bad"));

        vm.prank(escrow);
        reg.slashSpecies(bytes32("S1"), 1 ether, bytes32("bad"));
    }

    function test_slash_requires_existing_species() public {
        vm.prank(escrow);
        vm.expectRevert(SpeciesRegistry.SpeciesNotFound.selector);
        reg.slashSpecies(bytes32("missing"), 1 ether, bytes32("bad"));
    }

    function test_retire_requires_valid_state() public {
        vm.prank(alice);
        reg.proposeSpecies(bytes32("S1"), bytes32("g1"), bytes32("m1"));

        // Cannot retire from PROPOSED
        vm.prank(governance);
        vm.expectRevert(SpeciesRegistry.InvalidTransition.selector);
        reg.setSpeciesState(bytes32("S1"), SpeciesRegistry.SpeciesState.RETIRED);

        // Can retire from ACTIVE
        vm.prank(operator);
        reg.setSpeciesState(bytes32("S1"), SpeciesRegistry.SpeciesState.ACTIVE);
        vm.prank(governance);
        reg.setSpeciesState(bytes32("S1"), SpeciesRegistry.SpeciesState.RETIRED);

        assertFalse(reg.isActive(bytes32("S1")));
    }
}
