// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";

import {DRWEpochDistributor} from "../src/DRWEpochDistributor.sol";

contract ConfigureDRWEpochDistributor is Script {
    using stdJson for string;

    function run() external {
        string memory distributorPath = vm.envString("DARWIN_EPOCH_REWARDS_FILE");
        string memory distributorJson = vm.readFile(distributorPath);

        address distributor = vm.envAddress("DARWIN_EPOCH_REWARD_DISTRIBUTOR");
        uint256 signerKey = vm.envUint("DARWIN_EPOCH_REWARD_GOVERNANCE_PRIVATE_KEY");
        uint256 epochId = distributorJson.readUint(".epoch_id");
        bytes32 merkleRoot = distributorJson.readBytes32(".merkle_root");
        uint64 claimDeadline = uint64(distributorJson.readUint(".claim_deadline"));
        uint256 totalAmount = distributorJson.readUint(".total_amount");

        vm.startBroadcast(signerKey);
        DRWEpochDistributor(distributor).configureEpoch(epochId, merkleRoot, claimDeadline, totalAmount);
        vm.stopBroadcast();

        console2.log("DARWIN epoch distributor configured");
        console2.log("  distributor:", distributor);
        console2.log("  epoch_id:", epochId);
        console2.log("  merkle_root:", vm.toString(merkleRoot));
        console2.log("  claim_deadline:", uint256(claimDeadline));
        console2.log("  total_amount:", totalAmount);
    }
}
