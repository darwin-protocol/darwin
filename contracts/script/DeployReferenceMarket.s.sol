// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";

import {ReferenceMarketPool} from "../src/ReferenceMarketPool.sol";

contract DeployReferenceMarket is Script {
    using stdJson for string;

    struct DeployConfig {
        uint256 deployerKey;
        address deployer;
        address governance;
        address marketOperator;
        address baseToken;
        address quoteToken;
        string network;
        string outputPath;
        uint16 feeBps;
    }

    struct Deployment {
        address referencePool;
    }

    function run() external returns (Deployment memory deployment) {
        DeployConfig memory cfg = _loadConfig();

        vm.startBroadcast(cfg.deployerKey);
        deployment.referencePool =
            address(new ReferenceMarketPool(cfg.baseToken, cfg.quoteToken, cfg.governance, cfg.marketOperator, cfg.feeBps));
        vm.stopBroadcast();

        _writeDeploymentJson(cfg, deployment);

        console2.log("DARWIN reference market deployment complete");
        console2.log("  network:", cfg.network);
        console2.log("  chain_id:", block.chainid);
        console2.log("  output:", cfg.outputPath);
        console2.log("  reference_pool:", deployment.referencePool);
        console2.log("  governance:", cfg.governance);
        console2.log("  operator:", cfg.marketOperator);
        console2.log("  base_token:", cfg.baseToken);
        console2.log("  quote_token:", cfg.quoteToken);
        console2.log("  fee_bps:", cfg.feeBps);
    }

    function _loadConfig() internal view returns (DeployConfig memory cfg) {
        cfg.deployerKey = vm.envUint("DARWIN_DEPLOYER_PRIVATE_KEY");
        cfg.deployer = vm.addr(cfg.deployerKey);
        cfg.governance = vm.envAddress("DARWIN_GOVERNANCE");
        cfg.marketOperator = vm.envOr("DARWIN_REFERENCE_MARKET_OPERATOR", cfg.governance);
        cfg.baseToken = vm.envAddress("DARWIN_REFERENCE_MARKET_BASE_TOKEN");
        cfg.quoteToken = vm.envAddress("DARWIN_REFERENCE_MARKET_QUOTE_TOKEN");
        cfg.network = vm.envOr("DARWIN_NETWORK", string("unknown"));
        cfg.outputPath = vm.envOr(
            "DARWIN_REFERENCE_MARKET_FILE",
            string.concat(vm.projectRoot(), "/../ops/deployments/.", cfg.network, ".market.json")
        );
        cfg.feeBps = uint16(vm.envOr("DARWIN_REFERENCE_MARKET_FEE_BPS", uint256(30)));

        uint256 expectedChainId = vm.envOr("DARWIN_EXPECT_CHAIN_ID", uint256(0));
        if (expectedChainId != 0) {
            require(block.chainid == expectedChainId, "unexpected chain id");
        }
    }

    function _writeDeploymentJson(DeployConfig memory cfg, Deployment memory deployment) internal {
        string memory contractsJsonKey = "contracts";
        string memory contractsJson = contractsJsonKey.serialize("reference_pool", deployment.referencePool);
        string memory venueId = "darwin_reference_pool";
        string memory venueType = "constant_product_bootstrap";

        string memory marketJsonKey = "market";
        marketJsonKey.serialize("enabled", true);
        marketJsonKey.serialize("venue_id", venueId);
        marketJsonKey.serialize("venue_type", venueType);
        marketJsonKey.serialize("governance", cfg.governance);
        marketJsonKey.serialize("market_operator", cfg.marketOperator);
        marketJsonKey.serialize("base_token", cfg.baseToken);
        marketJsonKey.serialize("quote_token", cfg.quoteToken);
        marketJsonKey.serialize("fee_bps", cfg.feeBps);
        marketJsonKey.serialize("seeded", false);
        string memory marketJson = marketJsonKey.serialize("contracts", contractsJson);

        marketJson.write(cfg.outputPath);
    }
}
