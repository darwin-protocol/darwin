// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";

import {DRWFaucet} from "../src/DRWFaucet.sol";

contract DeployDRWFaucet is Script {
    using stdJson for string;

    struct DeployConfig {
        uint256 deployerKey;
        address deployer;
        address governance;
        address token;
        string network;
        string outputPath;
        uint256 claimAmount;
        uint256 nativeDripAmount;
        uint256 claimCooldown;
    }

    struct Deployment {
        address drwFaucet;
    }

    function run() external returns (Deployment memory deployment) {
        DeployConfig memory cfg = _loadConfig();

        vm.startBroadcast(cfg.deployerKey);
        deployment.drwFaucet =
            address(new DRWFaucet(cfg.token, cfg.governance, cfg.claimAmount, cfg.nativeDripAmount, cfg.claimCooldown));
        vm.stopBroadcast();

        _writeDeploymentJson(cfg, deployment);

        console2.log("DARWIN DRW faucet deployment complete");
        console2.log("  network:", cfg.network);
        console2.log("  chain_id:", block.chainid);
        console2.log("  output:", cfg.outputPath);
        console2.log("  drw_faucet:", deployment.drwFaucet);
        console2.log("  governance:", cfg.governance);
        console2.log("  token:", cfg.token);
        console2.log("  claim_amount:", cfg.claimAmount);
        console2.log("  native_drip_amount:", cfg.nativeDripAmount);
        console2.log("  claim_cooldown:", cfg.claimCooldown);
    }

    function _loadConfig() internal view returns (DeployConfig memory cfg) {
        cfg.deployerKey = vm.envUint("DARWIN_DEPLOYER_PRIVATE_KEY");
        cfg.deployer = vm.addr(cfg.deployerKey);
        cfg.governance = vm.envAddress("DARWIN_GOVERNANCE");
        cfg.token = vm.envAddress("DARWIN_DRW_FAUCET_TOKEN");
        cfg.network = vm.envOr("DARWIN_NETWORK", string("unknown"));
        cfg.outputPath = vm.envOr(
            "DARWIN_DRW_FAUCET_FILE", string.concat(vm.projectRoot(), "/../ops/deployments/", cfg.network, ".faucet.json")
        );
        cfg.claimAmount = vm.envOr("DARWIN_DRW_FAUCET_CLAIM_AMOUNT", uint256(100 ether));
        cfg.nativeDripAmount = vm.envOr("DARWIN_DRW_FAUCET_NATIVE_DRIP_AMOUNT", uint256(0.00001 ether));
        cfg.claimCooldown = vm.envOr("DARWIN_DRW_FAUCET_CLAIM_COOLDOWN", uint256(1 days));

        uint256 expectedChainId = vm.envOr("DARWIN_EXPECT_CHAIN_ID", uint256(0));
        if (expectedChainId != 0) {
            require(block.chainid == expectedChainId, "unexpected chain id");
        }

        require(cfg.claimAmount != 0 || cfg.nativeDripAmount != 0, "invalid claim config");
        require(cfg.claimCooldown != 0, "invalid cooldown");
    }

    function _writeDeploymentJson(DeployConfig memory cfg, Deployment memory deployment) internal {
        string memory contractsJsonKey = "contracts";
        string memory contractsJson = contractsJsonKey.serialize("drw_faucet", deployment.drwFaucet);

        string memory faucetJsonKey = "faucet";
        faucetJsonKey.serialize("enabled", true);
        faucetJsonKey.serialize("governance", cfg.governance);
        faucetJsonKey.serialize("claim_amount", cfg.claimAmount);
        faucetJsonKey.serialize("native_drip_amount", cfg.nativeDripAmount);
        faucetJsonKey.serialize("claim_cooldown", cfg.claimCooldown);
        faucetJsonKey.serialize("funded", false);
        faucetJsonKey.serialize("initial_token_funding", uint256(0));
        faucetJsonKey.serialize("initial_native_funding", uint256(0));
        string memory faucetJson = faucetJsonKey.serialize("contracts", contractsJson);

        faucetJson.write(cfg.outputPath);
    }
}
