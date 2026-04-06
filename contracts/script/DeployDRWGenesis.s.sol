// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";

import {DRWToken} from "../src/DRWToken.sol";
import {DRWStaking} from "../src/DRWStaking.sol";

contract DeployDRWGenesis is Script {
    using stdJson for string;

    struct DeployConfig {
        uint256 deployerKey;
        address deployer;
        address governance;
        string network;
        string outputPath;
        uint256 totalSupply;
        uint256 stakingDuration;
        address treasuryRecipient;
        address insuranceRecipient;
        address sponsorRewardsRecipient;
        address communityRecipient;
        uint16 treasuryBps;
        uint16 insuranceBps;
        uint16 sponsorRewardsBps;
        uint16 stakingBps;
        uint16 communityBps;
    }

    struct Deployment {
        address drwToken;
        address drwStaking;
        uint256 treasuryAmount;
        uint256 insuranceAmount;
        uint256 sponsorRewardsAmount;
        uint256 stakingAmount;
        uint256 communityAmount;
    }

    function run() external returns (Deployment memory deployment) {
        DeployConfig memory cfg = _loadConfig();

        vm.startBroadcast(cfg.deployerKey);
        deployment = _deployContracts(cfg);
        vm.stopBroadcast();

        _writeDeploymentJson(cfg, deployment);

        console2.log("DARWIN DRW genesis complete");
        console2.log("  network:", cfg.network);
        console2.log("  chain_id:", block.chainid);
        console2.log("  output:", cfg.outputPath);
        console2.log("  drw_token:", deployment.drwToken);
        console2.log("  drw_staking:", deployment.drwStaking);
        console2.log("  total_supply:", cfg.totalSupply);
        console2.log("  treasury_amount:", deployment.treasuryAmount);
        console2.log("  insurance_amount:", deployment.insuranceAmount);
        console2.log("  sponsor_rewards_amount:", deployment.sponsorRewardsAmount);
        console2.log("  staking_amount:", deployment.stakingAmount);
        console2.log("  community_amount:", deployment.communityAmount);
    }

    function _loadConfig() internal view returns (DeployConfig memory cfg) {
        cfg.deployerKey = vm.envUint("DARWIN_DEPLOYER_PRIVATE_KEY");
        cfg.deployer = vm.addr(cfg.deployerKey);
        cfg.governance = vm.envAddress("DARWIN_GOVERNANCE");
        cfg.network = vm.envOr("DARWIN_NETWORK", string("unknown"));
        cfg.outputPath = vm.envOr(
            "DARWIN_DRW_GENESIS_FILE", string.concat(vm.projectRoot(), "/../ops/deployments/", cfg.network, ".drw.json")
        );
        // Launch annex canonical supply: 100M DRW (not 1B)
        cfg.totalSupply = vm.envOr("DARWIN_DRW_TOTAL_SUPPLY", uint256(100_000_000 ether));
        cfg.stakingDuration = vm.envOr("DARWIN_DRW_STAKING_DURATION", uint256(365 days));
        cfg.treasuryRecipient = vm.envOr("DARWIN_DRW_TREASURY_RECIPIENT", cfg.governance);
        cfg.insuranceRecipient = vm.envOr("DARWIN_DRW_INSURANCE_RECIPIENT", cfg.governance);
        cfg.sponsorRewardsRecipient = vm.envOr("DARWIN_DRW_SPONSOR_REWARDS_RECIPIENT", cfg.governance);
        cfg.communityRecipient = vm.envOr("DARWIN_DRW_COMMUNITY_RECIPIENT", cfg.governance);
        cfg.treasuryBps = uint16(vm.envOr("DARWIN_DRW_TREASURY_BPS", uint256(2000)));
        cfg.insuranceBps = uint16(vm.envOr("DARWIN_DRW_INSURANCE_BPS", uint256(2000)));
        cfg.sponsorRewardsBps = uint16(vm.envOr("DARWIN_DRW_SPONSOR_REWARDS_BPS", uint256(1000)));
        cfg.stakingBps = uint16(vm.envOr("DARWIN_DRW_STAKING_BPS", uint256(3000)));
        cfg.communityBps = uint16(vm.envOr("DARWIN_DRW_COMMUNITY_BPS", uint256(2000)));

        uint256 expectedChainId = vm.envOr("DARWIN_EXPECT_CHAIN_ID", uint256(0));
        if (expectedChainId != 0) {
            require(block.chainid == expectedChainId, "unexpected chain id");
        }

        require(cfg.totalSupply != 0, "invalid total supply");
        require(cfg.stakingDuration != 0, "invalid staking duration");
        require(
            uint256(cfg.treasuryBps) + uint256(cfg.insuranceBps) + uint256(cfg.sponsorRewardsBps) + uint256(cfg.stakingBps)
                + uint256(cfg.communityBps) == 10_000,
            "invalid bps"
        );
    }

    function _deployContracts(DeployConfig memory cfg) internal returns (Deployment memory deployment) {
        DRWToken token = new DRWToken(cfg.governance, cfg.deployer);
        DRWStaking staking = new DRWStaking(address(token), cfg.governance, cfg.deployer);

        uint256 treasuryAmount = (cfg.totalSupply * cfg.treasuryBps) / 10_000;
        uint256 insuranceAmount = (cfg.totalSupply * cfg.insuranceBps) / 10_000;
        uint256 sponsorRewardsAmount = (cfg.totalSupply * cfg.sponsorRewardsBps) / 10_000;
        uint256 stakingAmount = (cfg.totalSupply * cfg.stakingBps) / 10_000;
        uint256 communityAmount = cfg.totalSupply - treasuryAmount - insuranceAmount - sponsorRewardsAmount - stakingAmount;

        token.mintGenesis(cfg.treasuryRecipient, treasuryAmount);
        token.mintGenesis(cfg.insuranceRecipient, insuranceAmount);
        token.mintGenesis(cfg.sponsorRewardsRecipient, sponsorRewardsAmount);
        token.mintGenesis(address(staking), stakingAmount);
        token.mintGenesis(cfg.communityRecipient, communityAmount);
        staking.notifyRewardAmount(stakingAmount, cfg.stakingDuration);
        token.finalizeGenesis();

        deployment = Deployment({
            drwToken: address(token),
            drwStaking: address(staking),
            treasuryAmount: treasuryAmount,
            insuranceAmount: insuranceAmount,
            sponsorRewardsAmount: sponsorRewardsAmount,
            stakingAmount: stakingAmount,
            communityAmount: communityAmount
        });
    }

    function _writeDeploymentJson(DeployConfig memory cfg, Deployment memory deployment) internal {
        string memory contractsJsonKey = "contracts";
        contractsJsonKey.serialize("drw_token", deployment.drwToken);
        string memory contractsJson = contractsJsonKey.serialize("drw_staking", deployment.drwStaking);

        string memory allocationsJsonKey = "allocations";
        allocationsJsonKey.serialize("treasury_recipient", cfg.treasuryRecipient);
        allocationsJsonKey.serialize("treasury_amount", deployment.treasuryAmount);
        allocationsJsonKey.serialize("insurance_recipient", cfg.insuranceRecipient);
        allocationsJsonKey.serialize("insurance_amount", deployment.insuranceAmount);
        allocationsJsonKey.serialize("sponsor_rewards_recipient", cfg.sponsorRewardsRecipient);
        allocationsJsonKey.serialize("sponsor_rewards_amount", deployment.sponsorRewardsAmount);
        allocationsJsonKey.serialize("staking_recipient", deployment.drwStaking);
        allocationsJsonKey.serialize("staking_amount", deployment.stakingAmount);
        allocationsJsonKey.serialize("community_recipient", cfg.communityRecipient);
        string memory allocationsJson = allocationsJsonKey.serialize("community_amount", deployment.communityAmount);

        string memory drwJsonKey = "drw";
        drwJsonKey.serialize("enabled", true);
        drwJsonKey.serialize("total_supply", cfg.totalSupply);
        drwJsonKey.serialize("staking_duration", cfg.stakingDuration);
        drwJsonKey.serialize("contracts", contractsJson);
        string memory drwJson = drwJsonKey.serialize("allocations", allocationsJson);

        drwJson.write(cfg.outputPath);
    }
}
