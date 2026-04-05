// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";

import {BondVault} from "../src/BondVault.sol";
import {ChallengeEscrow} from "../src/ChallengeEscrow.sol";
import {EpochManager} from "../src/EpochManager.sol";
import {ScoreRegistry} from "../src/ScoreRegistry.sol";
import {SettlementHub} from "../src/SettlementHub.sol";
import {SharedPairVault} from "../src/SharedPairVault.sol";
import {SpeciesRegistry} from "../src/SpeciesRegistry.sol";
import {MockWETH} from "../test/MockWETH.sol";

contract DeployDarwin is Script {
    using stdJson for string;

    struct DeployConfig {
        uint256 deployerKey;
        address deployer;
        address governance;
        address epochOperator;
        address safeModeAuthority;
        address bondAsset;
        string network;
        string outputPath;
        uint64 challengeWindowSec;
        uint64 responseWindowSec;
        bool deployMockBondAsset;
    }

    struct Deployment {
        address bondAsset;
        address challengeEscrow;
        address bondVault;
        address speciesRegistry;
        address settlementHub;
        address epochManager;
        address scoreRegistry;
        address sharedPairVault;
    }

    function run() external returns (Deployment memory deployment) {
        DeployConfig memory cfg = _loadConfig();

        vm.startBroadcast(cfg.deployerKey);
        if (cfg.deployMockBondAsset) {
            cfg.bondAsset = address(new MockWETH());
        }
        deployment = _deployContracts(cfg);
        vm.stopBroadcast();

        _writeDeploymentJson(cfg, deployment);

        console2.log("DARWIN deployment complete");
        console2.log("  network:", cfg.network);
        console2.log("  chain_id:", block.chainid);
        console2.log("  output:", cfg.outputPath);
        console2.log("  bond_asset_mode:", cfg.deployMockBondAsset ? "mock" : "external");
        console2.log("  bond_asset:", deployment.bondAsset);
        console2.log("  challenge_escrow:", deployment.challengeEscrow);
        console2.log("  bond_vault:", deployment.bondVault);
        console2.log("  species_registry:", deployment.speciesRegistry);
        console2.log("  settlement_hub:", deployment.settlementHub);
        console2.log("  epoch_manager:", deployment.epochManager);
        console2.log("  score_registry:", deployment.scoreRegistry);
        console2.log("  shared_pair_vault:", deployment.sharedPairVault);
    }

    function _loadConfig() internal view returns (DeployConfig memory cfg) {
        cfg.deployerKey = vm.envUint("DARWIN_DEPLOYER_PRIVATE_KEY");
        cfg.deployer = vm.addr(cfg.deployerKey);
        cfg.governance = vm.envAddress("DARWIN_GOVERNANCE");
        cfg.epochOperator = vm.envAddress("DARWIN_EPOCH_OPERATOR");
        cfg.safeModeAuthority = vm.envAddress("DARWIN_SAFE_MODE_AUTHORITY");
        cfg.network = vm.envOr("DARWIN_NETWORK", string("unknown"));
        cfg.outputPath =
            vm.envOr("DARWIN_DEPLOYMENT_FILE", string.concat(vm.projectRoot(), "/../ops/deployments/", cfg.network, ".json"));
        cfg.deployMockBondAsset = vm.envOr("DARWIN_DEPLOY_BOND_ASSET_MOCK", false);
        cfg.challengeWindowSec = uint64(vm.envOr("DARWIN_CHALLENGE_WINDOW_SEC", uint256(1800)));
        cfg.responseWindowSec = uint64(vm.envOr("DARWIN_RESPONSE_WINDOW_SEC", uint256(86400)));

        uint256 expectedChainId = vm.envOr("DARWIN_EXPECT_CHAIN_ID", uint256(0));
        if (expectedChainId != 0) {
            require(block.chainid == expectedChainId, "unexpected chain id");
        }

        if (!cfg.deployMockBondAsset) {
            cfg.bondAsset = vm.envAddress("DARWIN_BOND_ASSET");
        }
    }

    function _deployContracts(DeployConfig memory cfg) internal returns (Deployment memory deployment) {
        ChallengeEscrow challengeEscrow = new ChallengeEscrow(cfg.bondAsset, cfg.governance, cfg.responseWindowSec);
        BondVault bondVault = new BondVault(cfg.bondAsset, cfg.governance, address(challengeEscrow));
        SpeciesRegistry speciesRegistry = new SpeciesRegistry(cfg.governance, cfg.epochOperator, address(challengeEscrow));
        SettlementHub settlementHub = new SettlementHub(cfg.governance, cfg.safeModeAuthority, cfg.epochOperator);
        EpochManager epochManager = new EpochManager(cfg.governance, cfg.epochOperator, cfg.challengeWindowSec);
        ScoreRegistry scoreRegistry = new ScoreRegistry(cfg.epochOperator, cfg.governance);
        SharedPairVault sharedPairVault = new SharedPairVault(cfg.governance, address(settlementHub));

        deployment = Deployment({
            bondAsset: cfg.bondAsset,
            challengeEscrow: address(challengeEscrow),
            bondVault: address(bondVault),
            speciesRegistry: address(speciesRegistry),
            settlementHub: address(settlementHub),
            epochManager: address(epochManager),
            scoreRegistry: address(scoreRegistry),
            sharedPairVault: address(sharedPairVault)
        });
    }

    function _writeDeploymentJson(DeployConfig memory cfg, Deployment memory deployment) internal {
        string memory contractsJsonKey = "contracts";
        contractsJsonKey.serialize("bond_asset", deployment.bondAsset);
        contractsJsonKey.serialize("challenge_escrow", deployment.challengeEscrow);
        contractsJsonKey.serialize("bond_vault", deployment.bondVault);
        contractsJsonKey.serialize("species_registry", deployment.speciesRegistry);
        contractsJsonKey.serialize("settlement_hub", deployment.settlementHub);
        contractsJsonKey.serialize("epoch_manager", deployment.epochManager);
        contractsJsonKey.serialize("score_registry", deployment.scoreRegistry);
        string memory contractsJson = contractsJsonKey.serialize("shared_pair_vault", deployment.sharedPairVault);

        string memory rolesJsonKey = "roles";
        rolesJsonKey.serialize("governance", cfg.governance);
        rolesJsonKey.serialize("epoch_operator", cfg.epochOperator);
        rolesJsonKey.serialize("batch_operator", cfg.epochOperator);
        string memory rolesJson = rolesJsonKey.serialize("safe_mode_authority", cfg.safeModeAuthority);

        string memory rootJsonKey = "deployment";
        rootJsonKey.serialize("network", cfg.network);
        rootJsonKey.serialize("chain_id", block.chainid);
        rootJsonKey.serialize("deployer", cfg.deployer);
        rootJsonKey.serialize("deployed_at", block.timestamp);
        rootJsonKey.serialize("bond_asset_mode", cfg.deployMockBondAsset ? "mock" : "external");
        rootJsonKey.serialize("contracts", contractsJson);
        string memory finalJson = rootJsonKey.serialize("roles", rolesJson);

        finalJson.write(cfg.outputPath);
    }
}
