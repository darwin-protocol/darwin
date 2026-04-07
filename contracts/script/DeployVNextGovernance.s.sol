// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";

import {DarwinTimelock} from "../src/governance/DarwinTimelock.sol";
import {DRWMerkleDistributor} from "../src/DRWMerkleDistributor.sol";

contract DeployVNextGovernance is Script {
    using stdJson for string;

    uint64 internal constant TIMELOCK_GRACE_PERIOD = 14 days;

    struct DeployConfig {
        uint256 deployerKey;
        string network;
        string outputPath;
        address council;
        address guardian;
        address token;
        bytes32 merkleRoot;
        uint64 claimDeadline;
        uint64 minDelay;
        uint256 claimCount;
        uint256 totalAmount;
    }

    struct Deployment {
        address timelock;
        address distributor;
    }

    function run() external returns (Deployment memory deployment) {
        DeployConfig memory cfg = _loadConfig();

        vm.startBroadcast(cfg.deployerKey);
        DarwinTimelock timelock = new DarwinTimelock(cfg.council, cfg.guardian, cfg.minDelay);
        DRWMerkleDistributor distributor =
            new DRWMerkleDistributor(cfg.token, address(timelock), cfg.merkleRoot, cfg.claimDeadline);
        vm.stopBroadcast();

        deployment = Deployment({timelock: address(timelock), distributor: address(distributor)});
        _writeDeploymentJson(cfg, deployment);

        console2.log("DARWIN vNext governance deployment complete");
        console2.log("  network:", cfg.network);
        console2.log("  chain_id:", block.chainid);
        console2.log("  output:", cfg.outputPath);
        console2.log("  timelock:", deployment.timelock);
        console2.log("  distributor:", deployment.distributor);
        console2.log("  distribution_token:", cfg.token);
        console2.log("  merkle_root:", vm.toString(cfg.merkleRoot));
        console2.log("  claim_deadline:", uint256(cfg.claimDeadline));
        console2.log("  min_delay:", uint256(cfg.minDelay));
    }

    function _loadConfig() internal view returns (DeployConfig memory cfg) {
        cfg.deployerKey = vm.envUint("DARWIN_DEPLOYER_PRIVATE_KEY");
        cfg.network = vm.envOr("DARWIN_NETWORK", string("unknown"));
        cfg.outputPath = vm.envOr(
            "DARWIN_VNEXT_FILE", string.concat(vm.projectRoot(), "/../ops/deployments/", cfg.network, ".vnext.json")
        );
        cfg.council = vm.envAddress("DARWIN_VNEXT_COUNCIL");
        cfg.guardian = vm.envAddress("DARWIN_VNEXT_GUARDIAN");
        cfg.token = vm.envAddress("DARWIN_VNEXT_DISTRIBUTION_TOKEN");
        cfg.merkleRoot = vm.envBytes32("DARWIN_VNEXT_MERKLE_ROOT");
        cfg.claimDeadline = uint64(vm.envUint("DARWIN_VNEXT_CLAIM_DEADLINE"));
        cfg.minDelay = uint64(vm.envOr("DARWIN_VNEXT_TIMELOCK_MIN_DELAY", uint256(2 days)));
        cfg.claimCount = vm.envOr("DARWIN_VNEXT_CLAIM_COUNT", uint256(0));
        cfg.totalAmount = vm.envOr("DARWIN_VNEXT_TOTAL_AMOUNT", uint256(0));

        uint256 expectedChainId = vm.envOr("DARWIN_EXPECT_CHAIN_ID", uint256(0));
        if (expectedChainId != 0) {
            require(block.chainid == expectedChainId, "unexpected chain id");
        }

        require(cfg.council != address(0), "invalid council");
        require(cfg.guardian != address(0), "invalid guardian");
        require(cfg.token != address(0), "invalid token");
        require(cfg.merkleRoot != bytes32(0), "invalid merkle root");
        require(cfg.claimDeadline > block.timestamp, "invalid claim deadline");
        require(cfg.minDelay != 0, "invalid timelock delay");
    }

    function _writeDeploymentJson(DeployConfig memory cfg, Deployment memory deployment) internal {
        string memory contractsJsonKey = "contracts";
        contractsJsonKey.serialize("darwin_timelock", deployment.timelock);
        string memory contractsJson = contractsJsonKey.serialize("drw_merkle_distributor", deployment.distributor);

        string memory timelockJsonKey = "timelock";
        timelockJsonKey.serialize("min_delay", uint256(cfg.minDelay));
        string memory timelockJson = timelockJsonKey.serialize("grace_period", uint256(TIMELOCK_GRACE_PERIOD));

        string memory distributionJsonKey = "distribution";
        distributionJsonKey.serialize("token", cfg.token);
        distributionJsonKey.serialize("merkle_root", vm.toString(cfg.merkleRoot));
        distributionJsonKey.serialize("claim_deadline", uint256(cfg.claimDeadline));
        distributionJsonKey.serialize("claim_count", cfg.claimCount);
        string memory distributionJson = distributionJsonKey.serialize("total_amount", cfg.totalAmount);

        string memory vnextJsonKey = "vnext";
        vnextJsonKey.serialize("enabled", true);
        vnextJsonKey.serialize("contracts", contractsJson);
        vnextJsonKey.serialize("timelock", timelockJson);
        string memory vnextJson = vnextJsonKey.serialize("distribution", distributionJson);

        string memory rootKey = "root";
        rootKey.serialize("network", cfg.network);
        rootKey.serialize("chain_id", block.chainid);
        string memory rootJson = rootKey.serialize("vnext", vnextJson);

        rootJson.write(cfg.outputPath);
    }
}
