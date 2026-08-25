"""共享测试设施：离线单测替身与集成测试夹具。"""

import pytest

import stockdb_sdk as sdk


# ================= 离线单测替身 =================

class _CumView:
    def __init__(self, items):
        self._items = items

    def get(self, name):
        assert name == "cum"
        return self._items


class FakeRawRd:
    """原生 rd 的最小替身：只实现复权因子加载与 vals/pipe 取数。"""

    def __init__(self, cum=None, tables=None):
        self._cum = list(cum or [])
        self._tables = dict(tables or {})

    def get(self, pattern):
        if pattern == "复权*":
            return _CumView(self._cum)
        raise KeyError(pattern)

    def vals(self, table, code, query):
        return list(self._tables.get((table, code), []))

    def pipe(self):
        return FakePipe(self._tables)


class FakePipe:
    def __init__(self, tables):
        self._tables = tables
        self._queries = []

    def mget(self, table, code, query):
        self._queries.append((table, code, query))

    def do(self):
        out = []
        for table, code, query in self._queries:
            records = self._tables.get((table, code), [])
            out.append([(f"{table}:{code}:{i}", r) for i, r in enumerate(records)])
        return out


@pytest.fixture
def make_client():
    """构造挂接 FakeRawRd 的 StockDBClient。"""
    from stockdb_sdk._client import StockDBClient

    def _make(cum=None, tables=None, raw=None):
        return StockDBClient(
            _raw_client=raw if raw is not None else FakeRawRd(cum, tables))
    return _make


# ================= 集成测试夹具（需本地 stockdb 服务） =================

@pytest.fixture(scope="session")
def client():
    return sdk.StockDBClient()


@pytest.fixture(scope="session")
def daily():
    bars = sdk.get_data("000001", fq=None)
    assert bars, "000001 日K为空：请确认本地 stockdb 服务已启动"
    return bars


@pytest.fixture(scope="session")
def minute_day(daily):
    """返回 (day, bars)：最近一个有分钟数据的交易日。"""
    for bar in reversed(daily[-15:]):
        day = str(bar["date"])
        bars = list(sdk.rd.vals("分钟k", "000001", f"{day}*"))
        if bars:
            return day, bars
    pytest.skip("数据库中没有分钟 K 数据")
