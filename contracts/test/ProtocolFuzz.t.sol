// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import "../src/BondVault.sol";
import "../src/ChallengeEscrow.sol";
import "../src/EpochManager.sol";
import "../src/SharedPairVault.sol";
import "../src/SettlementHub.sol";
import "../src/SpeciesRegistry.sol";
import "../src/ScoreRegistry.sol";
import "./MockWETH.sol";

contract BondVaultFuzzTest is Test {
    BondVault vault;
    MockWETH weth;

    address governance = address(0x1001);
    address escrow = address(0x2002);
    address alice = address(0xA11CE);

    function setUp() public {
        weth = new MockWETH();
        vault = new BondVault(address(weth), governance, escrow);

        weth.mint(alice, 10_000 ether);

        vm.prank(alice);
        weth.approve(address(vault), type(uint256).max);
    }

    function testFuzz_roundTripDepositWithdraw(uint96 rawAmount, uint8 rawSubjectType) public {
        uint256 amount = bound(uint256(rawAmount), 1, 1_000 ether);
        BondVault.SubjectType subjectType = BondVault.SubjectType(uint256(rawSubjectType) % 5);
        bytes32 subjectId = keccak256(abi.encodePacked("subject", rawAmount, rawSubjectType));

        uint256 aliceBefore = weth.balanceOf(alice);

        vm.prank(alice);
        vault.depositBond(subjectType, subjectId, amount);

        (uint256 bonded, bool active) = vault.getBond(alice, subjectType, subjectId);
        assertEq(bonded, amount);
        assertTrue(active);
        assertEq(weth.balanceOf(address(vault)), amount);

        vm.warp(block.timestamp + 7 days + 1);

        vm.prank(alice);
        vault.withdrawBond(subjectType, subjectId, amount);

        (bonded, active) = vault.getBond(alice, subjectType, subjectId);
        assertEq(bonded, 0);
        assertFalse(active);
        assertEq(weth.balanceOf(alice), aliceBefore);
        assertEq(weth.balanceOf(address(vault)), 0);
    }

    function testFuzz_slashCapsAtBond(uint96 rawDeposit, uint96 rawSlash) public {
        uint256 depositAmount = bound(uint256(rawDeposit), 1, 1_000 ether);
        uint256 slashAmount = bound(uint256(rawSlash), 0, 2_000 ether);
        bytes32 subjectId = keccak256(abi.encodePacked("species", rawDeposit, rawSlash));

        vm.prank(alice);
        vault.depositBond(BondVault.SubjectType.SPECIES, subjectId, depositAmount);

        vm.prank(escrow);
        vault.slashBond(alice, BondVault.SubjectType.SPECIES, subjectId, slashAmount, bytes32("fuzz"));

        uint256 expectedSlash = slashAmount > depositAmount ? depositAmount : slashAmount;
        (uint256 bonded, bool active) = vault.getBond(alice, BondVault.SubjectType.SPECIES, subjectId);

        assertEq(bonded, depositAmount - expectedSlash);
        assertEq(weth.balanceOf(governance), expectedSlash);
        assertEq(active, bonded > 0);
    }
}

contract ChallengeEscrowFuzzTest is Test {
    ChallengeEscrow escrow;
    MockWETH weth;

    address governance = address(0x1001);
    address watcher = address(0x4004);

    function setUp() public {
        weth = new MockWETH();
        escrow = new ChallengeEscrow(address(weth), governance, 1 days);

        weth.mint(watcher, 1_000 ether);
        weth.mint(address(escrow), 2_000 ether);

        vm.prank(watcher);
        weth.approve(address(escrow), type(uint256).max);
    }

    function testFuzz_upheldChallengeRewardIsCapped(uint96 rawBond, uint96 rawSlash) public {
        uint256 bondAmount = bound(uint256(rawBond), 0.25 ether, 50 ether);
        uint256 slashAmount = bound(uint256(rawSlash), 0, 500 ether);
        bytes32 challengeId = keccak256(abi.encodePacked("upheld", rawBond, rawSlash));

        uint256 watcherBefore = weth.balanceOf(watcher);

        vm.prank(watcher);
        escrow.openChallenge(challengeId, 1, bytes32("root"), ChallengeEscrow.Severity.MATERIAL, bondAmount);

        vm.prank(governance);
        escrow.resolveChallenge(challengeId, true, slashAmount);

        uint256 expectedReward = slashAmount * 2500 / 10000;
        if (expectedReward > 5 ether) {
            expectedReward = 5 ether;
        }

        assertEq(weth.balanceOf(watcher), watcherBefore + expectedReward);
    }

    function testFuzz_rejectedChallengeAppliesHalfBondPenalty(uint96 rawBond) public {
        uint256 bondAmount = bound(uint256(rawBond), 0.25 ether, 50 ether);
        bytes32 challengeId = keccak256(abi.encodePacked("rejected", rawBond));

        uint256 watcherBefore = weth.balanceOf(watcher);
        uint256 governanceBefore = weth.balanceOf(governance);

        vm.prank(watcher);
        escrow.openChallenge(challengeId, 2, bytes32("root"), ChallengeEscrow.Severity.MATERIAL, bondAmount);

        vm.prank(governance);
        escrow.resolveChallenge(challengeId, false, 0);

        uint256 expectedPenalty = bondAmount * 5000 / 10000;
        assertEq(weth.balanceOf(watcher), watcherBefore - expectedPenalty);
        assertEq(weth.balanceOf(governance), governanceBefore + expectedPenalty);
    }

    function testFuzz_duplicateChallengeRejected(uint96 rawBond) public {
        uint256 bondAmount = bound(uint256(rawBond), 0.25 ether, 50 ether);
        bytes32 challengeId = keccak256(abi.encodePacked("dup", rawBond));

        vm.prank(watcher);
        escrow.openChallenge(challengeId, 1, bytes32("root"), ChallengeEscrow.Severity.MATERIAL, bondAmount);

        vm.prank(watcher);
        vm.expectRevert(ChallengeEscrow.ChallengeExists.selector);
        escrow.openChallenge(challengeId, 2, bytes32("other"), ChallengeEscrow.Severity.MATERIAL, bondAmount);
    }
}

contract EpochManagerFuzzTest is Test {
    EpochManager mgr;

    address governance = address(0x1001);
    address operator = address(0x3003);

    function setUp() public {
        mgr = new EpochManager(governance, operator, 1800);
    }

    function testFuzz_finalizeEpochRemainsPermissionless(
        uint64 rawEpochId,
        uint64 rawStartsAt,
        uint64 rawEndsAt,
        bytes32 manifestRoot,
        bytes32 scoreRoot,
        bytes32 weightRoot,
        address caller
    ) public {
        uint64 epochId = uint64(bound(uint256(rawEpochId), 1, type(uint32).max));
        uint64 startsAt = uint64(bound(uint256(rawStartsAt), 0, type(uint64).max - 1));
        uint64 endsAt = rawEndsAt;
        if (endsAt <= startsAt) {
            endsAt = startsAt + 1;
        }
        manifestRoot = manifestRoot == bytes32(0) ? bytes32("manifest") : manifestRoot;
        scoreRoot = scoreRoot == bytes32(0) ? bytes32("score") : scoreRoot;
        weightRoot = weightRoot == bytes32(0) ? bytes32("weight") : weightRoot;

        EpochManager.EpochConfig memory cfg = EpochManager.EpochConfig({
            epochId: epochId,
            startsAt: startsAt,
            endsAt: endsAt,
            controlPolicyHash: bytes32("ctrl"),
            bucketPolicyHash: bytes32("bucket"),
            rebalancePolicyHash: bytes32("reb")
        });

        vm.prank(operator);
        mgr.openEpoch(cfg);
        vm.prank(operator);
        mgr.closeEpoch(epochId, manifestRoot);
        vm.prank(operator);
        mgr.postScoreRoot(epochId, scoreRoot);
        vm.prank(operator);
        mgr.postWeightRoot(epochId, weightRoot);
        vm.prank(operator);
        mgr.postRebalanceRoot(epochId, bytes32("rebalance"));

        vm.warp(block.timestamp + 1801);
        vm.prank(caller);
        mgr.finalizeEpoch(epochId);

        EpochManager.Epoch memory epoch = mgr.getEpoch(epochId);
        assertEq(uint256(epoch.state), uint256(EpochManager.EpochState.FINALIZED));
        assertGt(epoch.finalizedAt, 0);
    }
}

contract ScoreRegistryFuzzTest is Test {
    ScoreRegistry reg;

    address operator = address(0x3003);
    address governance = address(0x1001);

    function setUp() public {
        reg = new ScoreRegistry(operator, governance);
    }

    function testFuzz_rootsAreSingleUseAndNonZero(uint64 rawEpochId, bytes32 scoreRoot, bytes32 manifestRoot) public {
        uint64 epochId = uint64(bound(uint256(rawEpochId), 1, type(uint64).max));
        scoreRoot = scoreRoot == bytes32(0) ? bytes32("score") : scoreRoot;
        manifestRoot = manifestRoot == bytes32(0) ? bytes32("manifest") : manifestRoot;

        vm.prank(operator);
        reg.postScoreRoot(epochId, scoreRoot, manifestRoot);

        vm.prank(operator);
        vm.expectRevert(ScoreRegistry.RootAlreadyPosted.selector);
        reg.postScoreRoot(epochId, bytes32("other"), bytes32("other-manifest"));
    }
}

contract SettlementHubFuzzTest is Test {
    SettlementHub hub;
    MockWETH token;

    address governance = address(0x1001);
    address sentinel = address(0x5AFE);
    address batchOperator = address(this);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);

    function setUp() public {
        hub = new SettlementHub(governance, sentinel, batchOperator);
        token = new MockWETH();

        token.mint(alice, 10_000 ether);
        vm.prank(alice);
        token.approve(address(hub), type(uint256).max);
    }

    function testFuzz_submitBatchIsSingleUse(
        bytes32 batchId,
        uint64 epochId,
        bytes32 pairId,
        uint64 windowStartTs,
        uint64 windowEndTs
    ) public {
        batchId = batchId == bytes32(0) ? bytes32("batch") : batchId;
        windowStartTs = uint64(bound(uint256(windowStartTs), 0, type(uint64).max - 1));
        epochId = uint64(bound(uint256(epochId), 1, type(uint64).max));
        pairId = pairId == bytes32(0) ? bytes32("ETH_USDC") : pairId;
        if (windowEndTs <= windowStartTs) {
            windowEndTs = windowStartTs + 1;
        }
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: batchId,
            epochId: epochId,
            pairId: pairId,
            intentRoot: bytes32("intent"),
            fillRoot: bytes32("fill"),
            oracleRoot: bytes32("oracle"),
            rebalanceRoot: bytes32("rebalance"),
            manifestRoot: bytes32("manifest"),
            windowStartTs: windowStartTs,
            windowEndTs: windowEndTs,
            postedBy: batchOperator
        });

        hub.submitBatch(header);
        assertTrue(hub.submittedBatches(batchId));
        assertFalse(hub.settledBatches(batchId));
        assertEq(hub.batchCount(), 1);

        vm.expectRevert(SettlementHub.BatchAlreadySubmitted.selector);
        hub.submitBatch(header);
    }

    function testFuzz_invalidTransferRejected(uint96 rawAmount) public {
        uint256 amount = bound(uint256(rawAmount), 1, 1 ether);
        bytes32 batchId = bytes32("invalid-transfer");
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: batchId,
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("intent"),
            fillRoot: bytes32("fill"),
            oracleRoot: bytes32("oracle"),
            rebalanceRoot: bytes32("rebalance"),
            manifestRoot: bytes32("manifest"),
            windowStartTs: 1,
            windowEndTs: 2,
            postedBy: batchOperator
        });
        hub.submitBatch(header);

        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(token),
            from_: alice,
            to_: alice,
            amount: amount
        });

        vm.expectRevert(SettlementHub.InvalidNetTransfer.selector);
        hub.applyNetSettlement(batchId, transfers);
    }

    function testFuzz_applyNetSettlementMovesBalances(uint96 rawAmount) public {
        uint256 amount = bound(uint256(rawAmount), 1, 1_000 ether);
        bytes32 batchId = bytes32("batch-settle");
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: batchId,
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("intent"),
            fillRoot: bytes32("fill"),
            oracleRoot: bytes32("oracle"),
            rebalanceRoot: bytes32("rebalance"),
            manifestRoot: bytes32("manifest"),
            windowStartTs: 1,
            windowEndTs: 2,
            postedBy: batchOperator
        });
        hub.submitBatch(header);

        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(token),
            from_: alice,
            to_: bob,
            amount: amount
        });

        uint256 aliceBefore = token.balanceOf(alice);
        uint256 bobBefore = token.balanceOf(bob);

        hub.applyNetSettlement(batchId, transfers);

        assertTrue(hub.settledBatches(batchId));
        assertEq(token.balanceOf(alice), aliceBefore - amount);
        assertEq(token.balanceOf(bob), bobBefore + amount);
    }

    function testFuzz_applyNetSettlementIsSingleUse(uint96 rawAmount) public {
        uint256 amount = bound(uint256(rawAmount), 1, 1_000 ether);
        bytes32 batchId = bytes32("batch-settle-once");
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: batchId,
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("intent"),
            fillRoot: bytes32("fill"),
            oracleRoot: bytes32("oracle"),
            rebalanceRoot: bytes32("rebalance"),
            manifestRoot: bytes32("manifest"),
            windowStartTs: 1,
            windowEndTs: 2,
            postedBy: batchOperator
        });
        hub.submitBatch(header);

        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(token),
            from_: alice,
            to_: bob,
            amount: amount
        });

        hub.applyNetSettlement(batchId, transfers);

        vm.expectRevert(SettlementHub.NetSettlementAlreadyApplied.selector);
        hub.applyNetSettlement(batchId, transfers);
    }

    function testFuzz_safeModeBlocksSettlement(uint96 rawAmount) public {
        uint256 amount = bound(uint256(rawAmount), 1, 1_000 ether);
        bytes32 batchId = bytes32("batch-safe");
        SettlementHub.BatchHeader memory header = SettlementHub.BatchHeader({
            batchId: batchId,
            epochId: 1,
            pairId: bytes32("ETH_USDC"),
            intentRoot: bytes32("intent"),
            fillRoot: bytes32("fill"),
            oracleRoot: bytes32("oracle"),
            rebalanceRoot: bytes32("rebalance"),
            manifestRoot: bytes32("manifest"),
            windowStartTs: 1,
            windowEndTs: 2,
            postedBy: batchOperator
        });
        hub.submitBatch(header);

        SettlementHub.NetTransfer[] memory transfers = new SettlementHub.NetTransfer[](1);
        transfers[0] = SettlementHub.NetTransfer({
            asset: address(token),
            from_: alice,
            to_: bob,
            amount: amount
        });

        vm.prank(sentinel);
        hub.enterSafeMode(bytes32("pause"));

        vm.expectRevert(SettlementHub.SafeModeActive.selector);
        hub.applyNetSettlement(batchId, transfers);
    }
}

contract SpeciesRegistryFuzzTest is Test {
    SpeciesRegistry reg;

    address governance = address(0x1001);
    address operator = address(0x3003);
    address escrow = address(0x2002);
    address sponsor = address(0xA11CE);

    function setUp() public {
        reg = new SpeciesRegistry(governance, operator, escrow);
    }

    function testFuzz_duplicateSpeciesRejected(bytes32 speciesId, bytes32 genomeHash, bytes32 manifestHash) public {
        speciesId = speciesId == bytes32(0) ? bytes32("S1") : speciesId;

        vm.prank(sponsor);
        reg.proposeSpecies(speciesId, genomeHash, manifestHash);

        vm.prank(sponsor);
        vm.expectRevert(SpeciesRegistry.SpeciesExists.selector);
        reg.proposeSpecies(speciesId, bytes32("other"), bytes32("other"));

        assertEq(reg.getSpeciesCount(), 1);
    }

    function testFuzz_isActiveMatchesState(uint8 rawState) public {
        bytes32 speciesId = bytes32("S1");
        vm.prank(sponsor);
        reg.proposeSpecies(speciesId, bytes32("genome"), bytes32("manifest"));

        SpeciesRegistry.SpeciesState state = SpeciesRegistry.SpeciesState(uint256(rawState) % 7);
        if (state == SpeciesRegistry.SpeciesState.RETIRED) {
            vm.prank(operator);
            reg.setSpeciesState(speciesId, SpeciesRegistry.SpeciesState.ACTIVE);
            vm.prank(governance);
            reg.setSpeciesState(speciesId, state);
        } else {
            vm.prank(operator);
            reg.setSpeciesState(speciesId, state);
        }

        bool isActive = reg.isActive(speciesId);
        bool expected = state == SpeciesRegistry.SpeciesState.ACTIVE || state == SpeciesRegistry.SpeciesState.CANARY;
        assertEq(isActive, expected);
    }

    function testFuzz_unknownSpeciesRejected(uint8 rawState, uint96 rawAmount) public {
        bytes32 speciesId = bytes32("missing");
        SpeciesRegistry.SpeciesState state = SpeciesRegistry.SpeciesState(uint256(rawState) % 7);

        vm.prank(operator);
        vm.expectRevert(SpeciesRegistry.SpeciesNotFound.selector);
        reg.setSpeciesState(speciesId, state);

        vm.prank(escrow);
        vm.expectRevert(SpeciesRegistry.SpeciesNotFound.selector);
        reg.slashSpecies(speciesId, uint256(rawAmount), bytes32("missing"));

        assertEq(reg.getSpeciesCount(), 0);
    }
}

contract SharedPairVaultFuzzTest is Test {
    SharedPairVault vault;
    MockWETH base;
    MockWETH quote;

    address governance = address(0x1001);
    address hub = address(0x2002);
    address alice = address(0xA11CE);
    bytes32 pairId = bytes32("ETH_USDC");

    function setUp() public {
        base = new MockWETH();
        quote = new MockWETH();
        vault = new SharedPairVault(governance, hub);

        vm.prank(governance);
        vault.createPair(pairId, address(base), address(quote));

        base.mint(alice, 10_000 ether);
        quote.mint(alice, 10_000 ether);

        vm.prank(alice);
        base.approve(address(vault), type(uint256).max);
        vm.prank(alice);
        quote.approve(address(vault), type(uint256).max);
    }

    function testFuzz_firstLpRoundTrip(uint96 rawBase, uint96 rawQuote) public {
        uint256 baseAmount = bound(uint256(rawBase), 1, 1_000 ether);
        uint256 quoteAmount = bound(uint256(rawQuote), 1, 1_000 ether);

        uint256 baseBefore = base.balanceOf(alice);
        uint256 quoteBefore = quote.balanceOf(alice);

        vm.prank(alice);
        vault.deposit(pairId, baseAmount, quoteAmount);

        uint256 shares = vault.lpShares(pairId, alice);
        assertEq(shares, baseAmount + quoteAmount);

        vm.prank(alice);
        vault.withdraw(pairId, shares);

        SharedPairVault.PairVault memory pairVault = vault.getVault(pairId);
        assertEq(pairVault.baseBalance, 0);
        assertEq(pairVault.quoteBalance, 0);
        assertEq(pairVault.totalShares, 0);
        assertEq(vault.lpShares(pairId, alice), 0);
        assertEq(base.balanceOf(alice), baseBefore);
        assertEq(quote.balanceOf(alice), quoteBefore);
    }

    function testFuzz_duplicatePairRejected(bytes32 duplicatePairId) public {
        duplicatePairId = duplicatePairId == bytes32(0) ? pairId : duplicatePairId;

        if (duplicatePairId != pairId) {
            vm.prank(governance);
            vault.createPair(duplicatePairId, address(base), address(quote));

            vm.prank(governance);
            vm.expectRevert(SharedPairVault.PairExists.selector);
            vault.createPair(duplicatePairId, address(base), address(quote));
            return;
        }

        vm.prank(governance);
        vm.expectRevert(SharedPairVault.PairExists.selector);
        vault.createPair(pairId, address(base), address(quote));
    }

    function testFuzz_zeroValueDepositRejected() public {
        vm.prank(alice);
        vm.expectRevert(SharedPairVault.InvalidAmount.selector);
        vault.deposit(pairId, 0, 0);
    }
}
