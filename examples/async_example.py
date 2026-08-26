"""异步查询：协程内并发拉取多只股票。"""

import asyncio

import stockdb_sdk as sdk


async def main():
    # 单只
    rows = await sdk.get_async("600633", start="20260701", end="20260824")
    print(f"600633 日K {len(rows)} 根")

    # 列表并发请求；前缀 "*" 为全市场单请求后客户端过滤
    data = await sdk.get_async(
        ["600633", "000001", "300750", "688981"],
        start="20260818", end="20260824", fq=None)
    for code, bars in sorted(data.items()):
        print(f"{code}: 最新收盘 {bars[-1]['close']}")


asyncio.run(main())
