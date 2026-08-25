"""示例：异步 K 线查询。"""

import asyncio

import stockdb_sdk as sdk


async def main():
    sdk.init(host="127.0.0.1", port=7899)

    bars = await sdk.get_data_async("000001", start="20260801", end="20260824")
    print("异步日 K 前 3 条：")
    for b in bars[:3]:
        print(" ", b)


if __name__ == "__main__":
    asyncio.run(main())
