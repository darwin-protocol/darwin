// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";

import {DRWEpochDistributor} from "../src/DRWEpochDistributor.sol";

contract ClaimDRWEpoch is Script {
    using stdJson for string;

    function run() external {
        string memory manifestPath = vm.envString("DARWIN_EPOCH_REWARDS_FILE");
        string memory manifestJson = vm.readFile(manifestPath);

        address distributor = vm.envAddress("DARWIN_EPOCH_REWARD_DISTRIBUTOR");
        uint256 claimIndex = vm.envUint("DARWIN_EPOCH_REWARD_CLAIM_INDEX");
        uint256 signerKey = vm.envUint("DARWIN_EPOCH_REWARD_CLAIM_PRIVATE_KEY");
        uint256 epochId = manifestJson.readUint(".epoch_id");
        string memory claimBase = string.concat(".claims[", vm.toString(claimIndex), "]");
        address account = manifestJson.readAddress(string.concat(claimBase, ".account"));
        uint256 amount = manifestJson.readUint(string.concat(claimBase, ".amount"));
        bytes32[] memory proof = manifestJson.readBytes32Array(string.concat(claimBase, ".proof"));

        address signer = vm.addr(signerKey);
        require(signer == account, "claim signer/account mismatch");

        vm.startBroadcast(signerKey);
        DRWEpochDistributor(distributor).claim(epochId, claimIndex, account, amount, proof);
        vm.stopBroadcast();

        console2.log("DARWIN epoch claim complete");
        console2.log("  distributor:", distributor);
        console2.log("  epoch_id:", epochId);
        console2.log("  account:", account);
        console2.log("  index:", claimIndex);
        console2.log("  amount:", amount);
    }
}
