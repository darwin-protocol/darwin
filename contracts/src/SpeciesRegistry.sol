// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title DARWIN SpeciesRegistry — tracks species lifecycle, genomes, and bonds
contract SpeciesRegistry {
    // --- Types ---

    enum SpeciesState { PROPOSED, SANDBOX, BONDED, CANARY, ACTIVE, QUARANTINED, RETIRED }

    struct Species {
        bytes32 speciesId;
        bytes32 genomeHash;
        bytes32 manifestHash;
        address sponsor;
        SpeciesState state;
        uint256 sponsorBond;
        uint64  proposedAt;
    }

    // --- State ---

    address public governance;
    address public epochOperator;
    address public challengeEscrow;
    address public bondVault;

    mapping(bytes32 => Species) public species;
    bytes32[] public speciesIds;

    // --- Events ---

    event SpeciesProposed(bytes32 indexed speciesId, address indexed sponsor, bytes32 genomeHash);
    event SpeciesStateChanged(bytes32 indexed speciesId, SpeciesState oldState, SpeciesState newState);
    event SpeciesSlashed(bytes32 indexed speciesId, uint256 amount, bytes32 reason);

    // --- Errors ---

    error Unauthorized();
    error SpeciesExists();
    error InvalidTransition();

    // --- Constructor ---

    constructor(address _governance, address _epochOperator, address _challengeEscrow) {
        governance = _governance;
        epochOperator = _epochOperator;
        challengeEscrow = _challengeEscrow;
    }

    // --- Propose ---

    function proposeSpecies(bytes32 speciesId, bytes32 genomeHash, bytes32 manifestHash) external {
        if (species[speciesId].proposedAt != 0) revert SpeciesExists();

        species[speciesId] = Species({
            speciesId: speciesId,
            genomeHash: genomeHash,
            manifestHash: manifestHash,
            sponsor: msg.sender,
            state: SpeciesState.PROPOSED,
            sponsorBond: 0,
            proposedAt: uint64(block.timestamp)
        });
        speciesIds.push(speciesId);

        emit SpeciesProposed(speciesId, msg.sender, genomeHash);
    }

    // --- State transitions ---

    function setSpeciesState(bytes32 speciesId, SpeciesState newState) external {
        if (msg.sender != epochOperator && msg.sender != governance) revert Unauthorized();

        Species storage s = species[speciesId];
        SpeciesState old = s.state;

        // Validate transition
        if (newState == SpeciesState.RETIRED && old != SpeciesState.QUARANTINED && old != SpeciesState.ACTIVE) {
            revert InvalidTransition();
        }

        s.state = newState;
        emit SpeciesStateChanged(speciesId, old, newState);
    }

    // --- Slash (challenge escrow only) ---

    function slashSpecies(bytes32 speciesId, uint256 amount, bytes32 reason) external {
        if (msg.sender != challengeEscrow) revert Unauthorized();

        Species storage s = species[speciesId];
        uint256 slashAmt = amount > s.sponsorBond ? s.sponsorBond : amount;
        s.sponsorBond -= slashAmt;

        emit SpeciesSlashed(speciesId, slashAmt, reason);
    }

    // --- View ---

    function getSpecies(bytes32 speciesId) external view returns (Species memory) {
        return species[speciesId];
    }

    function getSpeciesCount() external view returns (uint256) {
        return speciesIds.length;
    }

    function isActive(bytes32 speciesId) external view returns (bool) {
        SpeciesState s = species[speciesId].state;
        return s == SpeciesState.ACTIVE || s == SpeciesState.CANARY;
    }
}
