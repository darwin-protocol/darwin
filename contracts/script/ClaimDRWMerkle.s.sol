// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";

import {DRWMerkleDistributor} from "../src/DRWMerkleDistributor.sol";

contract ClaimDRWMerkle is Script {
    using stdJson for string;

    function run() external {
        string memory vnextPath = vm.envString("DARWIN_VNEXT_FILE");
        string memory manifestPath = vm.envString("DARWIN_VNEXT_DISTRIBUTION_FILE");
        uint256 claimIndex = vm.envUint("DARWIN_MERKLE_CLAIM_INDEX");
        uint256 claimSignerKey = vm.envUint("DARWIN_MERKLE_CLAIM_PRIVATE_KEY");

        string memory vnextJson = vm.readFile(vnextPath);
        string memory manifestJson = vm.readFile(manifestPath);

        address distributor = vnextJson.readAddress(".vnext.contracts.drw_merkle_distributor");
        string memory claimBase = string.concat(".claims[", vm.toString(claimIndex), "]");
        address account = manifestJson.readAddress(string.concat(claimBase, ".account"));
        uint256 amount = manifestJson.readUint(string.concat(claimBase, ".amount"));
        bytes32[] memory proof = manifestJson.readBytes32Array(string.concat(claimBase, ".proof"));

        address signer = vm.addr(claimSignerKey);
        require(signer == account, "claim signer/account mismatch");

        vm.startBroadcast(claimSignerKey);
        DRWMerkleDistributor(distributor).claim(claimIndex, account, amount, proof);
        vm.stopBroadcast();

        console2.log("DARWIN Merkle claim complete");
        console2.log("  distributor:", distributor);
        console2.log("  account:", account);
        console2.log("  index:", claimIndex);
        console2.log("  amount:", amount);
    }
}
