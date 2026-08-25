"""集成测试：异步接口与同步结果一致性（需本地 stockdb 服务）。"""

import asyncio

import pandas as pd

import stockdb_sdk as sdk

CODE = "000001"


def test_async_single_equals_sync(daily):
    window = dict(start=str(daily[-10]["date"]), end="N", fq=None)
    async_res = asyncio.run(sdk.get_data_async(CODE, **window))
    assert async_res == sdk.get_data(CODE, **window)


def test_async_batch_and_df(daily):
    window = dict(start=str(daily[-5]["date"]), end="N", fq=None)
    async_df = asyncio.run(
        sdk.get_data_async([CODE, "600633"], as_df=True, **window))
    sync_df = sdk.get_data([CODE, "600633"], as_df=True, **window)
    pd.testing.assert_frame_equal(async_df, sync_df)


def test_async_minute_aggregation(minute_day):
    day, _ = minute_day
    kw = dict(start=day, end=day, frequency="5m", fq=None)
    async_res = asyncio.run(sdk.get_data_async(CODE, **kw))
    assert async_res == sdk.get_data(CODE, **kw)


def test_async_client_desc(daily):
    client = sdk.StockDBClient()
    bars = asyncio.run(client.get_data_async(
        CODE, start=str(daily[-3]["date"]), end="N", fq=None, desc=True))
    assert [b["date"] for b in bars] == [b["date"] for b in daily[-3:]][::-1]


def test_async_raw_rd(daily):
    day = str(daily[-1]["date"])

    async def fetch():
        return await sdk.rd.vals("日k", CODE, day)

    assert asyncio.run(fetch()) == list(sdk.rd.vals("日k", CODE, day))
