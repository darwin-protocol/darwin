// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "forge-std/StdInvariant.sol";

import "../src/BondVault.sol";
import "../src/SettlementHub.sol";
import "../src/SharedPairVault.sol";
import "../src/SpeciesRegistry.sol";
import "./MockWETH.sol";

contract BondVaultHandler is Test {
    BondVault internal vault;
    MockWETH internal weth;
    address internal escrow;

    address internal alice;
    address internal bob;

    constructor(BondVault _vault, MockWETH _weth, address _escrow, address _alice, address _bob) {
        vault = _vault;
        weth = _weth;
        escrow = _escrow;
        alice = _alice;
        bob = _bob;
    }

    function deposit(uint8 actorSeed, uint8 subjectTypeSeed, uint8 subjectSeed, uint96 rawAmount) external {
        address actor = _actor(actorSeed);
        BondVault.SubjectType subjectType = BondVault.SubjectType(uint256(subjectTypeSeed) % 5);
        bytes32 subjectId = _subjectId(subjectSeed);
        uint256 maxAmount = weth.balanceOf(actor);
        if (maxAmount == 0) return;
        if (maxAmount > 250 ether) maxAmount = 250 ether;
        uint256 amount = bound(uint256(rawAmount), 1, maxAmount);

        vm.prank(actor);
        vault.depositBond(subjectType, subjectId, amount);
    }

    function withdraw(uint8 actorSeed, uint8 subjectTypeSeed, uint8 subjectSeed, uint96 rawAmount) external {
        address actor = _actor(actorSeed);
        BondVault.SubjectType subjectType = BondVault.SubjectType(uint256(subjectTypeSeed) % 5);
        bytes32 subjectId = _subjectId(subjectSeed);
        (uint256 bonded,) = vault.getBond(actor, subjectType, subjectId);
        if (bonded == 0) return;

        uint256 amount = bound(uint256(rawAmount), 1, bonded);
        vm.warp(block.timestamp + vault.WITHDRAWAL_COOLDOWN() + 1);
        vm.prank(actor);
        vault.withdrawBond(subjectType, subjectId, amount);
    }

    function slash(uint8 actorSeed, uint8 subjectTypeSeed, uint8 subjectSeed, uint96 rawAmount) external {
        address actor = _actor(actorSeed);
        BondVault.SubjectType subjectType = BondVault.SubjectType(uint256(subjectTypeSeed) % 5);
        bytes32 subjectId = _subjectId(subjectSeed);
        (uint256 bonded,) = vault.getBond(actor, subjectType, subjectId);
        if (bonded == 0) return;

        uint256 amount = bound(uint256(rawAmount), 0, bonded * 2);
        vm.prank(escrow);
        vault.slashBond(actor, subjectType, subjectId, amount, bytes32("invariant"));
    }

    function _actor(uint8 seed) internal view returns (address) {
        return seed % 2 == 0 ? alice : bob;
    }

    function _subjectId(uint8 seed) internal pure returns (bytes32) {
        if (seed % 3 == 0) return bytes32("species-alpha");
        if (seed % 3 == 1) return bytes32("watcher-beta");
        return bytes32("gateway-gamma");
    }
}

contract BondVaultInvariantTest is StdInvariant, Test {
    BondVault internal vault;
    MockWETH internal weth;
    BondVaultHandler internal handler;

    address internal governance = address(0x1001);
    address internal escrow = address(0x2002);
    address internal alice = address(0xA11CE);
    address internal bob = address(0xB0B);

    function setUp() public {
        weth = new MockWETH();
        vault = new BondVault(address(weth), governance, escrow);

        weth.mint(alice, 50_000 ether);
        weth.mint(bob, 50_000 ether);

        vm.prank(alice);
        weth.approve(address(vault), type(uint256).max);
        vm.prank(bob);
        weth.approve(address(vault), type(uint256).max);

        handler = new BondVaultHandler(vault, weth, escrow, alice, bob);
        targetContract(address(handler));
    }

    function invariant_vaultBalanceMatchesOutstandingBonds() public view {
        uint256 outstanding = 0;
        address[2] memory actors = [alice, bob];
        bytes32[3] memory subjectIds = [bytes32("species-alpha"), bytes32("watcher-beta"), bytes32("gateway-gamma")];

        for (uint256 i = 0; i < actors.length; i++) {
            for (uint256 t = 0; t < 5; t++) {
                for (uint256 s = 0; s < subjectIds.length; s++) {
                    (uint256 amount,) = vault.getBond(actors[i], BondVault.SubjectType(t), subjectIds[s]);
                    outstanding += amount;
                }
            }
        }

        assertEq(weth.balanceOf(address(vault)), outstanding);
    }

    function invariant_activeFlagTracksPositiveBond() public view {
        address[2] memory actors = [alice, bob];
        bytes32[3] memory subjectIds = [bytes32("species-alpha"), bytes32("watcher-beta"), bytes32("gateway-gamma")];

        for (uint256 i = 0; i < actors.length; i++) {
            for (uint256 t = 0; t < 5; t++) {
                for (uint256 s = 0; s < subjectIds.length; s++) {
                    (uint256 amount, bool active) = vault.getBond(actors[i], BondVault.SubjectType(t), subjectIds[s]);
                    assertEq(active, amount > 0);
                }
            }
        }
    }
}

contract SpeciesRegistryHandler is Test {
    SpeciesRegistry internal registry;
    address internal governance;
    address internal epochOperator;
    address internal challengeEscrow;
    address internal alice;
    address internal bob;

    constructor(
        SpeciesRegistry _registry,
        address _governance,
        address _epochOperator,
        address _challengeEscrow,
        address _alice,
        address _bob
    ) {
        registry = _registry;
        governance = _governance;
        epochOperator = _epochOperator;
        challengeEscrow = _challengeEscrow;
        alice = _alice;
        bob = _bob;
    }

    function propose(uint8 speciesSeed, uint8 sponsorSeed) external {
        address sponsor = sponsorSeed % 2 == 0 ? alice : bob;
        bytes32 speciesId = _speciesId(speciesSeed);
        vm.prank(sponsor);
        try registry.proposeSpecies(
            speciesId,
            keccak256(abi.encodePacked("genome", speciesSeed, sponsor)),
            keccak256(abi.encodePacked("manifest", speciesSeed, sponsor))
        ) {} catch {}
    }

    function setState(uint8 speciesSeed, uint8 actorSeed, uint8 rawState) external {
        bytes32 speciesId = _speciesId(speciesSeed);
        SpeciesRegistry.SpeciesState newState = SpeciesRegistry.SpeciesState(uint256(rawState) % 7);
        address actor = actorSeed % 2 == 0 ? epochOperator : governance;
        vm.prank(actor);
        try registry.setSpeciesState(speciesId, newState) {} catch {}
    }

    function slash(uint8 speciesSeed, uint96 rawAmount) external {
        bytes32 speciesId = _speciesId(speciesSeed);
        vm.prank(challengeEscrow);
        try registry.slashSpecies(speciesId, uint256(rawAmount), bytes32("invariant")) {} catch {}
    }

    function _speciesId(uint8 seed) internal pure returns (bytes32) {
        if (seed % 4 == 0) return bytes32("species-alpha");
        if (seed % 4 == 1) return bytes32("species-beta");
        if (seed % 4 == 2) return bytes32("species-gamma");
        return bytes32("species-delta");
    }
}

contract SpeciesRegistryInvariantTest is StdInvariant, Test {
    SpeciesRegistry internal registry;
    SpeciesRegistryHandler internal handler;

    address internal governance = address(0x1001);
    address internal epochOperator = address(0x1002);
    address internal challengeEscrow = address(0x2002);
    address internal alice = address(0xA11CE);
    address internal bob = address(0xB0B);
    bytes32[4] internal speciesIds = [
        bytes32("species-alpha"),
        bytes32("species-beta"),
        bytes32("species-gamma"),
        bytes32("species-delta")
    ];

    function setUp() public {
        registry = new SpeciesRegistry(governance, epochOperator, challengeEscrow);
        handler = new SpeciesRegistryHandler(registry, governance, epochOperator, challengeEscrow, alice, bob);
        targetContract(address(handler));
    }

    function invariant_countMatchesTrackedSpecies() public view {
        uint256 tracked = 0;
        for (uint256 i = 0; i < speciesIds.length; i++) {
            SpeciesRegistry.Species memory s = registry.getSpecies(speciesIds[i]);
            if (s.proposedAt != 0) {
                tracked++;
            }
        }
        assertEq(registry.getSpeciesCount(), tracked);
    }

    function invariant_speciesSlotsRemainConsistent() public view {
        for (uint256 i = 0; i < speciesIds.length; i++) {
            bytes32 speciesId = speciesIds[i];
            SpeciesRegistry.Species memory s = registry.getSpecies(speciesId);
            if (s.proposedAt == 0) {
                assertEq(s.speciesId, bytes32(0));
                assertEq(s.sponsor, address(0));
                assertEq(s.sponsorBond, 0);
                continue;
            }

            assertEq(s.speciesId, speciesId);
            assertTrue(s.sponsor != address(0));
            assertTrue(s.proposedAt > 0);

            bool expectedActive =
                s.state == SpeciesRegistry.SpeciesState.ACTIVE || s.state == SpeciesRegistry.SpeciesState.CANARY;
            assertEq(registry.isActive(speciesId), expectedActive);
        }
    }
}

contract SharedPairVaultHandler is Test {
    SharedPairVault internal vault;
    MockWETH internal base;
    MockWETH internal quote;
    bytes32 internal pairId;

    address internal alice;
    address internal bob;

    constructor(
        SharedPairVault _vault,
        MockWETH _base,
        MockWETH _quote,
        bytes32 _pairId,
        address _alice,
        address _bob
    ) {
        vault = _vault;
        base = _base;
        quote = _quote;
        pairId = _pairId;
        alice = _alice;
        bob = _bob;
    }

    function deposit(uint8 actorSeed, uint96 rawBase, uint96 rawQuote) external {
        address actor = actorSeed % 2 == 0 ? alice : bob;
        uint256 maxBase = base.balanceOf(actor);
        uint256 maxQuote = quote.balanceOf(actor);
        if (maxBase > 500 ether) maxBase = 500 ether;
        if (maxQuote > 500 ether) maxQuote = 500 ether;
        if (maxBase == 0 && maxQuote == 0) return;

        uint256 baseAmount = maxBase == 0 ? 0 : bound(uint256(rawBase), 0, maxBase);
        uint256 quoteAmount = maxQuote == 0 ? 0 : bound(uint256(rawQuote), 0, maxQuote);
        if (baseAmount == 0 && quoteAmount == 0) {
            if (maxBase > 0) {
                baseAmount = 1;
            } else {
                quoteAmount = 1;
            }
        }

        vm.prank(actor);
        vault.deposit(pairId, baseAmount, quoteAmount);
    }

    function withdraw(uint8 actorSeed, uint96 rawShares) external {
        address actor = actorSeed % 2 == 0 ? alice : bob;
        uint256 shares = vault.lpShares(pairId, actor);
        if (shares == 0) return;

        uint256 amount = bound(uint256(rawShares), 1, shares);
        vm.prank(actor);
        vault.withdraw(pairId, amount);
    }
}

contract SharedPairVaultInvariantTest is StdInvariant, Test {
    SharedPairVault internal vault;
    MockWETH internal base;
    MockWETH internal quote;
    SharedPairVaultHandler internal handler;

    address internal governance = address(0x1001);
    address internal settlementHub = address(0x2002);
    address internal alice = address(0xA11CE);
    address internal bob = address(0xB0B);
    bytes32 internal pairId = bytes32("ETH_USDC");

    function setUp() public {
        base = new MockWETH();
        quote = new MockWETH();
        vault = new SharedPairVault(governance, settlementHub);

        vm.prank(governance);
        vault.createPair(pairId, address(base), address(quote));

        base.mint(alice, 50_000 ether);
        base.mint(bob, 50_000 ether);
        quote.mint(alice, 50_000 ether);
        quote.mint(bob, 50_000 ether);

        vm.prank(alice);
        base.approve(address(vault), type(uint256).max);
        vm.prank(alice);
        quote.approve(address(vault), type(uint256).max);
        vm.prank(bob);
        base.approve(address(vault), type(uint256).max);
        vm.prank(bob);
        quote.approve(address(vault), type(uint256).max);

        handler = new SharedPairVaultHandler(vault, base, quote, pairId, alice, bob);
        targetContract(address(handler));
    }

    function invariant_internalBalancesMatchTokenBalances() public view {
        SharedPairVault.PairVault memory pairVault = vault.getVault(pairId);
        assertEq(base.balanceOf(address(vault)), pairVault.baseBalance);
        assertEq(quote.balanceOf(address(vault)), pairVault.quoteBalance);
        assertTrue(pairVault.enabled);
        assertEq(pairVault.baseAsset, address(base));
        assertEq(pairVault.quoteAsset, address(quote));
    }

    function invariant_totalSharesMatchLpBalances() public view {
        SharedPairVault.PairVault memory pairVault = vault.getVault(pairId);
        uint256 lpTotal = vault.lpShares(pairId, alice) + vault.lpShares(pairId, bob);
        assertEq(pairVault.totalShares, lpTotal);
    }
}

contract SettlementHubHandler is Test {
    SettlementHub internal hub;
    MockWETH internal weth;

    address internal governance;
    address internal safeModeAuthority;
    address internal alice;
    address internal bob;
    address internal carol;

    constructor(
        SettlementHub _hub,
        MockWETH _weth,
        address _governance,
        address _safeModeAuthority,
        address _alice,
        address _bob,
        address _carol
    ) {
        hub = _hub;
        weth = _weth;
        governance = _governance;
        safeModeAuthority = _safeModeAuthority;
        alice = _alice;
        bob = _bob;
        carol = _carol;
    }

    function submitBatch(uint8 batchSeed, uint64 epochSeed) external {
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: _batchId(batchSeed),
            epochId: uint64(bound(uint256(epochSeed), 1, type(uint64).max)),
            pairId: bytes32("ETH_USDC"),
            intentRoot: keccak256(abi.encodePacked("intent", batchSeed, epochSeed)),
            fillRoot: keccak256(abi.encodePacked("fill", batchSeed, epochSeed)),
            oracleRoot: keccak256(abi.encodePacked("oracle", batchSeed, epochSeed)),
            rebalanceRoot: keccak256(abi.encodePacked("rebalance", batchSeed, epochSeed)),
            manifestRoot: keccak256(abi.encodePacked("manifest", batchSeed, epochSeed)),
            windowStartTs: uint64(block.timestamp),
            windowEndTs: uint64(block.timestamp + 1),
            postedBy: address(this)
        });

        try hub.submitBatch(header) {} catch {}
    }

    function applySettlement(uint8 batchSeed, uint8 fromSeed, uint8 toSeed, uint96 rawAmount) external {
        bytes32 batchId = _batchId(batchSeed);
        address from = _actor(fromSeed);
        address to = _actor(toSeed + 1);
        if (from == to) return;

        uint256 balance = weth.balanceOf(from);
        if (balance == 0) return;

        uint256 amount = bound(uint256(rawAmount), 1, balance);
        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(weth),
            from_: from,
            to_: to,
            amount: amount
        });

        try hub.applyNetSettlement(batchId, transfers) {} catch {}
    }

    function enterSafeMode(uint8 reasonSeed) external {
        vm.prank(safeModeAuthority);
        hub.enterSafeMode(keccak256(abi.encodePacked("reason", reasonSeed)));
    }

    function exitSafeMode() external {
        vm.prank(governance);
        hub.exitSafeMode();
    }

    function _actor(uint8 seed) internal view returns (address) {
        if (seed % 3 == 0) return alice;
        if (seed % 3 == 1) return bob;
        return carol;
    }

    function _batchId(uint8 seed) internal pure returns (bytes32) {
        if (seed % 4 == 0) return bytes32("batch-alpha");
        if (seed % 4 == 1) return bytes32("batch-beta");
        if (seed % 4 == 2) return bytes32("batch-gamma");
        return bytes32("batch-delta");
    }
}

contract SettlementHubInvariantTest is StdInvariant, Test {
    SettlementHub internal hub;
    MockWETH internal weth;
    SettlementHubHandler internal handler;

    address internal governance = address(0x1001);
    address internal safeModeAuthority = address(0x1002);
    address internal alice = address(0xA11CE);
    address internal bob = address(0xB0B);
    address internal carol = address(0xCA11);
    bytes32[4] internal batchIds = [bytes32("batch-alpha"), bytes32("batch-beta"), bytes32("batch-gamma"), bytes32("batch-delta")];

    function setUp() public {
        weth = new MockWETH();
        hub = new SettlementHub(governance, safeModeAuthority, address(0));

        weth.mint(alice, 50_000 ether);
        weth.mint(bob, 50_000 ether);
        weth.mint(carol, 50_000 ether);

        vm.prank(alice);
        weth.approve(address(hub), type(uint256).max);
        vm.prank(bob);
        weth.approve(address(hub), type(uint256).max);
        vm.prank(carol);
        weth.approve(address(hub), type(uint256).max);

        handler = new SettlementHubHandler(hub, weth, governance, safeModeAuthority, alice, bob, carol);
        vm.prank(governance);
        hub.setBatchOperator(address(handler), true);
        targetContract(address(handler));
    }

    function invariant_settledBatchesWereSubmitted() public view {
        for (uint256 i = 0; i < batchIds.length; i++) {
            if (hub.settledBatches(batchIds[i])) {
                assertTrue(hub.submittedBatches(batchIds[i]));
            }
        }
    }

    function invariant_batchCountMatchesTrackedSubmissions() public view {
        uint256 submitted = 0;
        for (uint256 i = 0; i < batchIds.length; i++) {
            if (hub.submittedBatches(batchIds[i])) {
                submitted++;
            }
        }
        assertEq(hub.batchCount(), submitted);
    }

    function invariant_netSettlementConservesTrackedBalances() public view {
        uint256 total = weth.balanceOf(alice) + weth.balanceOf(bob) + weth.balanceOf(carol);
        assertEq(total, weth.totalSupply());
    }
}
