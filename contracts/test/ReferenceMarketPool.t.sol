// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/ReferenceMarketPool.sol";
import "./MockWETH.sol";

contract ReferenceMarketPoolTest is Test {
    ReferenceMarketPool pool;
    MockWETH drw;
    MockWETH weth;
    address governance = address(0x1001);
    address operator = address(0x2002);
    address trader = address(0x3003);

    function setUp() public {
        drw = new MockWETH();
        weth = new MockWETH();
        pool = new ReferenceMarketPool(address(drw), address(weth), governance, operator, 30);

        drw.mint(operator, 1_000_000 ether);
        weth.mint(operator, 100 ether);
        drw.mint(trader, 10_000 ether);
        weth.mint(trader, 10 ether);

        vm.prank(operator);
        drw.approve(address(pool), type(uint256).max);
        vm.prank(operator);
        weth.approve(address(pool), type(uint256).max);
        vm.prank(trader);
        drw.approve(address(pool), type(uint256).max);
        vm.prank(trader);
        weth.approve(address(pool), type(uint256).max);
    }

    function test_seed_initial_liquidity() public {
        vm.prank(operator);
        pool.seedInitialLiquidity(500_000 ether, 5 ether);

        assertTrue(pool.seeded());
        assertEq(pool.baseReserve(), 500_000 ether);
        assertEq(pool.quoteReserve(), 5 ether);
    }

    function test_only_operator_can_seed() public {
        vm.prank(trader);
        vm.expectRevert(ReferenceMarketPool.Unauthorized.selector);
        pool.seedInitialLiquidity(500_000 ether, 5 ether);
    }

    function test_swap_quote_for_base() public {
        vm.prank(operator);
        pool.seedInitialLiquidity(500_000 ether, 5 ether);

        uint256 quoted = pool.quoteExactInput(address(weth), 1 ether);

        vm.prank(trader);
        uint256 out = pool.swapExactInput(address(weth), 1 ether, quoted, trader);

        assertEq(out, quoted);
        assertEq(pool.quoteReserve(), 6 ether);
        assertEq(pool.baseReserve(), 500_000 ether - quoted);
        assertEq(drw.balanceOf(trader), 10_000 ether + quoted);
    }

    function test_swap_base_for_quote() public {
        vm.prank(operator);
        pool.seedInitialLiquidity(500_000 ether, 5 ether);

        uint256 quoted = pool.quoteExactInput(address(drw), 5_000 ether);

        vm.prank(trader);
        uint256 out = pool.swapExactInput(address(drw), 5_000 ether, quoted, trader);

        assertEq(out, quoted);
        assertEq(pool.baseReserve(), 505_000 ether);
        assertEq(pool.quoteReserve(), 5 ether - quoted);
        assertEq(weth.balanceOf(trader), 10 ether + quoted);
    }

    function test_slippage_guard() public {
        vm.prank(operator);
        pool.seedInitialLiquidity(500_000 ether, 5 ether);

        uint256 quoted = pool.quoteExactInput(address(weth), 1 ether);

        vm.prank(trader);
        vm.expectRevert(ReferenceMarketPool.SlippageExceeded.selector);
        pool.swapExactInput(address(weth), 1 ether, quoted + 1, trader);
    }

    function test_governance_can_update_operator() public {
        address newOperator = address(0x4004);
        drw.mint(newOperator, 100_000 ether);
        weth.mint(newOperator, 1 ether);
        vm.prank(newOperator);
        drw.approve(address(pool), type(uint256).max);
        vm.prank(newOperator);
        weth.approve(address(pool), type(uint256).max);

        vm.prank(governance);
        pool.setMarketOperator(newOperator);

        vm.prank(newOperator);
        pool.seedInitialLiquidity(100_000 ether, 1 ether);

        assertEq(pool.marketOperator(), newOperator);
        assertEq(pool.baseReserve(), 100_000 ether);
    }

    function test_remove_liquidity() public {
        vm.prank(operator);
        pool.seedInitialLiquidity(500_000 ether, 5 ether);

        vm.prank(operator);
        pool.removeLiquidity(100_000 ether, 1 ether, operator);

        assertEq(pool.baseReserve(), 400_000 ether);
        assertEq(pool.quoteReserve(), 4 ether);
        assertEq(drw.balanceOf(operator), 600_000 ether);
        assertEq(weth.balanceOf(operator), 96 ether);
    }
}
