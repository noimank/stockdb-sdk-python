"""集成测试：RdClient 原生 K-V 读写往返（需本地 stockdb 服务）。

断言只使用实测稳定的形态：索引进纯值、``list()``/``.do()`` 物化、
协程内 ``await`` 管线（契约详见 ``stockdb_sdk._raw`` 模块说明）。
"""

import asyncio

import pytest

import stockdb_sdk as sdk
from stockdb_sdk import StockdbError

T = "sdk_raw_it"


@pytest.fixture(autouse=True)
def _clean_table():
    yield
    # 写操作须用 await 形式保证执行完成；整表清空用 delete(T, "*")
    asyncio.run(_delete_table())


async def _delete_table():
    await sdk.rd.delete(T, "*")


# ---------- 读 ----------

def test_get_exact_indexing_yields_plain_values(daily):
    day = str(daily[-1]["date"])
    bar = sdk.rd.get("日k", "000001", day)
    assert not isinstance(bar, dict)          # QueryResult 鸭子类型
    assert bar["date"] == daily[-1]["date"]
    assert bar["close"] == daily[-1]["close"]  # 索引得到纯 float


def test_get_pattern_returns_pairs(daily):
    day = str(daily[-1]["date"])
    rows = list(sdk.rd.get("日k", "000001", f"{day[:6]}*"))
    assert rows and all(k.startswith(f"日k:000001:{day[:6]}") for k, _ in rows)


def test_range_expressions(daily):
    d1, d2 = str(daily[-30]["date"]), str(daily[-20]["date"])
    # a>b 正向闭区间升序
    fwd = [b["date"] for b in sdk.rd.vals("日k", "000001", f"{d1}>{d2}").do()]
    assert fwd == sorted(fwd)
    assert fwd[0] == daily[-30]["date"] and fwd[-1] == daily[-20]["date"]
    # a<b 反向降序（从 b 到 a）
    back = [b["date"] for b in sdk.rd.vals("日k", "000001", f"{d1}<{d2}").do()]
    assert back == fwd[::-1]
    # a>N 到最新升序；左界大于右界（数值）返回空
    tail = [b["date"] for b in sdk.rd.vals("日k", "000001", f"{d2}>N").do()]
    assert tail == [b["date"] for b in daily[-20:]]
    assert list(sdk.rd.vals("日k", "000001", f"{d2}>{d1}").do()) == []


def test_vals_exact_and_table_level(daily):
    day = str(daily[-1]["date"])
    vals = list(sdk.rd.vals("日k", "000001", day))
    assert len(vals) == 1 and vals[0]["date"] == daily[-1]["date"]

    # 表级 vals 返回 [值]，物化后取首元素
    codes = sdk.rd.vals("股票代码").do()
    assert "6" in codes[0]


def test_keys_len_materialized():
    # 只到二级时仅返回该级键上恰有值的精确匹配，枚举子键须低一级通配
    assert sdk.rd.keys("日k", "000001") == []
    keys = sdk.rd.keys("日k", "000001", "202608*")
    assert keys and all(k.startswith("日k:000001:202608") for k in keys)
    assert isinstance(keys, list)                 # 已物化，可直接比较
    assert sdk.rd.len("日k", "000001", "202608*") == len(keys)


def test_projection_get_needs_do(daily):
    # .get() 列投影返回 QueryResult 包装，物化后才是纯值
    closes = sdk.rd.get("日k", "000001", f"{str(daily[-5]['date'])}>N").get("close")
    pairs = closes.do()
    assert pairs[0][0] == f"日k:000001:{daily[-5]['date']}"
    assert isinstance(pairs[0][1], float)


# ---------- 写 ----------

def test_set_overloads_and_delete():
    async def run():
        assert await sdk.rd.set(T, {"table": 1}) == 1
        assert await sdk.rd.set(T, "k1", ["a", "b"]) == 1
        assert await sdk.rd.set(T, "k1", "sub", 123) == 1
        assert (await sdk.rd.get(T))["table"] == 1
        assert list(await sdk.rd.get(T, "k1")) == ["a", "b"]
        assert await sdk.rd.get(T, "k1", "sub") == 123
        assert await sdk.rd.delete(T, "k1") == 1
        assert list(await sdk.rd.get(T, "k1")) == []
    asyncio.run(run())


def test_setl_setr_list_semantics():
    async def run():
        await sdk.rd.setr(T, "q", "a")
        await sdk.rd.setr(T, "q", "b")
        assert list(await sdk.rd.get(T, "q")) == ["a", "b"]
        await sdk.rd.setl(T, "q", "top")
        assert list(await sdk.rd.get(T, "q")) == ["top", "a", "b"]
        # 原值为标量时丢弃重建为单元素列表
        await sdk.rd.set(T, "s", 42)
        await sdk.rd.setr(T, "s", "x")
        assert list(await sdk.rd.get(T, "s")) == ["x"]
    asyncio.run(run())


def test_homogeneous_pipes():
    async def run():
        await sdk.rd.set(T, "a", 1)
        await sdk.rd.set(T, "b", 2)

        # 纯读管线：协程内 await，多命令返回结果列表
        reads = sdk.rd.pipe()
        reads.mget(T, "a").mget(T, "b")
        assert await reads == [1, 2]

        # 纯写管线
        writes = sdk.rd.pipe()
        for i in range(3):
            writes.mset(T, "pp", f"k{i}", i * 100)
        assert await writes == [1, 1, 1]
        assert await sdk.rd.get(T, "pp", "k2") == 200
    asyncio.run(run())


def test_stockdb_error_exported():
    assert issubclass(StockdbError, Exception)
