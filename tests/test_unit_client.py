"""离线单元测试：_client 纯函数与 FakeRawRd 上的客户端行为。"""

import pytest

from stockdb_sdk._client import (
    StockDBClient,
    _build_time_query,
    _filter_fields,
    _merge_minutes_to_period,
    _merge_to_period,
    _normalize_codes,
    _parse_pipe_results,
    _to_dataframe,
)


# ---------- 代码归一化 ----------

def test_normalize_codes():
    assert _normalize_codes("000001.SZ") == ["000001"]
    assert _normalize_codes("600633.SH") == ["600633"]
    assert _normalize_codes("000001.XSHE") == ["000001"]
    assert _normalize_codes("000001") == ["000001"]
    assert _normalize_codes(["000001.SZ", "600633"]) == ["000001", "600633"]


# ---------- 时间查询表达式 ----------

def test_build_time_query_daily():
    assert _build_time_query(None, None, "1d") == "*"
    assert _build_time_query("20260701", "20260824", "1d") == "20260701>20260824"
    # 单日退化为点查询
    assert _build_time_query("20260701", None, "1d") == "20260701"
    assert _build_time_query("20260701", "20260701", "1d") == "20260701"
    # 开区间（'N' 表示不设限）
    assert _build_time_query(None, "20260824", "1d") == "N>20260824"
    assert _build_time_query("20260701", "N", "1d") == "20260701>N"


def test_build_time_query_minute_padding():
    # 8 位日期补全为覆盖全天交易时段的 14 位时间
    assert _build_time_query("20260824", "20260824", "5m") == \
        "20260824000000>20260824235959"
    assert _build_time_query("20260824", None, "1m") == "20260824000000"
    # 已是 14 位则原样透传；日 K 不做补全
    assert _build_time_query("20260824093000", "20260824150000", "1m") == \
        "20260824093000>20260824150000"
    assert _build_time_query("20260824", None, "1d") == "20260824"


# ---------- 字段投影与 DataFrame ----------

def test_filter_fields():
    rows = [{"date": 20260701, "open": 1.0, "close": 2.0},
            {"date": 20260702, "open": 1.1, "close": 2.1}]
    assert _filter_fields(rows, None) is rows
    assert _filter_fields(rows, "date,close") == [[20260701, 2.0], [20260702, 2.1]]
    assert _filter_fields(rows, ["open"]) == [[1.0], [1.1]]
    # 保持 fields 传入顺序
    assert _filter_fields(rows, "close,date") == [[2.0, 20260701], [2.1, 20260702]]


def test_to_dataframe_single():
    df = _to_dataframe([[20260701, 10.0], [20260702, 11.0]], False, "date,open")
    assert list(df.columns) == ["date", "open"]
    assert df.shape == (2, 2)

    df = _to_dataframe([{"date": 20260701, "open": 10.0}], False)
    assert list(df.columns) == ["date", "open"]

    assert _to_dataframe([], False).empty


def test_to_dataframe_batch():
    data = {"000001": [[20260701, 10.0], [20260702, 11.0]], "600633": [[20260701, 20.0]]}
    df = _to_dataframe(data, True, "date,open")
    assert df.columns[0] == "code"
    assert set(df["code"]) == {"000001", "600633"}
    assert len(df) == 3

    df = _to_dataframe({"000001": [{"date": 20260701, "open": 2.0}]}, True)
    assert list(df.columns) == ["code", "date", "open"]
    assert _to_dataframe({}, True).empty


# ---------- pipeline 结果解析 ----------

def test_parse_pipe_results():
    codes = ["000001", "600633", "300750"]
    raw = [
        [("k:1", {"date": 1}), ("k:2", {"date": 2})],  # kv 对列表
        {"date": 3},                                    # 单 dict
        "bad",                                          # 无效项 -> 空列表
    ]
    out = _parse_pipe_results(codes, raw)
    assert out["000001"] == [{"date": 1}, {"date": 2}]
    assert out["600633"] == [{"date": 3}]
    assert out["300750"] == []
    # 非 list 返回值包一层
    assert _parse_pipe_results(["000001"], {"date": 1})["000001"] == [{"date": 1}]


# ---------- 周 / 月 K 聚合 ----------

def _day(date, open_, high, low, close, volume=100, turnover=None):
    return {"date": date, "code": "000001", "name": "测试",
            "open": open_, "high": high, "low": low, "close": close,
            "volume": volume, "amount": volume * close, "turnover": turnover}


def test_merge_to_period_weekly():
    # 两组连续 ISO 周：07-06~07-10 与 07-13~07-14
    week1 = [
        _day(20260706, 10.0, 11.0, 9.5, 10.5, 100),
        _day(20260707, 10.5, 12.0, 10.0, 11.5, 200),
        _day(20260708, 11.5, 11.8, 10.8, 11.0, 150),
        _day(20260709, 11.0, 11.2, 10.5, 10.8, 120),
        _day(20260710, 10.8, 11.5, 10.6, 11.2, 180),
    ]
    week2 = [
        _day(20260713, 11.2, 11.9, 11.0, 11.6, 90, 1.0),
        _day(20260714, 11.6, 12.3, 11.3, 12.0, 160, 2.5),
    ]
    bars = _merge_to_period(week1 + week2, "1w")
    assert len(bars) == 2

    w1, w2 = bars
    assert w1["date"] == 20260710
    assert w1["open"] == 10.0 and w1["close"] == 11.2
    assert w1["high"] == 12.0 and w1["low"] == 9.5
    assert w1["volume"] == 750
    assert w1["amount"] == sum(b["amount"] for b in week1)
    assert "turnover" not in w1  # 全为 None 时不产出

    assert w2["date"] == 20260714
    assert w2["pre_close"] == w1["close"]  # 前收盘续接上一周期
    assert w2["pct_chg"] == round((w2["close"] - w1["close"]) / w1["close"] * 100, 3)
    assert w2["turnover"] == 3.5           # 换手率求和


def test_merge_to_period_monthly():
    bars = [
        _day(20260730, 10.0, 10.5, 9.8, 10.2),
        _day(20260731, 10.2, 10.8, 10.0, 10.6),
        _day(20260803, 10.6, 11.0, 10.4, 10.9),
    ]
    months = _merge_to_period(bars, "1M")
    assert len(months) == 2
    assert months[0]["date"] == 20260731
    assert months[1]["date"] == 20260803
    assert months[1]["pre_close"] == months[0]["close"]


def test_merge_to_period_skips_invalid_days():
    bars = [
        _day(20260706, 10.0, 10.5, 9.8, 10.2),
        {"date": 20260707, "code": "000001"},  # 缺 OHLC 的不完整记录
        _day(20260708, 10.3, 10.9, 10.1, 10.8),
    ]
    merged = _merge_to_period(bars, "1w")
    assert len(merged) == 1
    assert merged[0]["open"] == 10.0 and merged[0]["close"] == 10.8


# ---------- 分钟 K 聚合 ----------

def _minute(date, open_, high, low, close, volume=10):
    return {"date": date, "code": "000001", "name": "测试",
            "open": open_, "high": high, "low": low, "close": close,
            "volume": volume, "amount": volume * close}


def _elapsed_to_stamp(ymd, elapsed):
    """交易时段序号 -> 14 位时间戳（09:30 为 0，11:30 为 120，13:01 为 121，15:00 为 240）。"""
    mod = 570 + elapsed if elapsed <= 120 else 780 + (elapsed - 120)
    return ymd * 1000000 + (mod // 60) * 10000 + (mod % 60) * 100


def test_merge_minutes_full_day():
    ymd = 20260824
    bars = []
    price = 10.0
    for elapsed in range(0, 241):  # 09:30 .. 15:00
        bars.append(_minute(_elapsed_to_stamp(ymd, elapsed),
                            price, price + 0.2, price - 0.1, price + 0.05))
        price += 0.01

    merged = _merge_minutes_to_period(bars, "5m")
    assert len(merged) == 48
    # 首根 [09:30, 09:35]（含 09:35）
    assert merged[0]["date"] == ymd * 1000000 + 93500
    assert merged[0]["open"] == bars[0]["open"]
    assert merged[0]["close"] == bars[5]["close"]
    assert merged[0]["volume"] == 60  # 6 根 1m
    # 11:30 收盘那根（第 24 组）
    assert merged[23]["date"] == ymd * 1000000 + 113000
    # 午后第一根结束于 13:05（13:01/13:00 序号 121 归入该组）
    assert merged[24]["date"] == ymd * 1000000 + 130500
    # 最后一根 15:00
    assert merged[-1]["date"] == ymd * 1000000 + 150000
    assert merged[-1]["close"] == bars[-1]["close"]
    # pre_close 链式续接
    assert merged[1]["pre_close"] == merged[0]["close"]


def test_merge_minutes_partial_and_filtering():
    ymd = 20260824
    bars = [
        _minute(ymd * 1000000 + 93000, 10.0, 10.2, 9.9, 10.1),
        _minute(ymd * 1000000 + 93100, 10.1, 10.3, 10.0, 10.2),
        _minute(ymd * 1000000 + 93600, 10.2, 10.4, 10.1, 10.3),  # 归入 09:40 组
        _minute(ymd * 1000000 + 150000, 10.3, 10.5, 10.2, 10.4),
    ]
    merged = _merge_minutes_to_period(bars, "5m")
    assert [b["date"] % 1000000 for b in merged] == [93500, 94000, 150000]
    assert merged[0]["close"] == 10.2  # 组内最后一根

    # 非交易时段（午休 12:00）被剔除
    assert _merge_minutes_to_period([_minute(ymd * 1000000 + 120000, 1, 1, 1, 1)], "5m") == []
    # 8 位日 K 日期不参与分钟聚合
    assert _merge_minutes_to_period([_minute(20260824, 1, 1, 1, 1)], "5m") == []


# ---------- StockDBClient（FakeRawRd） ----------

FQ = [
    ["复权:600000:20260101", 1.0],
    ["复权:600000:20260601", 2.0],
]


def _daily_rows(dates, close=10.0):
    return [
        {"date": d, "code": "600000", "name": "x", "open": close - 0.5,
         "high": close + 0.5, "low": close - 1.0, "close": close,
         "volume": 100, "amount": 100 * close, "pre_close": close - 0.1}
        for d in dates
    ]


def test_client_normalizes_code(make_client):
    tables = {("日k", "600000"): _daily_rows([20260701, 20260702])}
    client = make_client(tables=tables)
    bars = client.get_data("600000.SH", start="20260701", end="20260702", fq=None)
    assert [b["date"] for b in bars] == [20260701, 20260702]


def test_client_fields_desc_limit(make_client):
    client = make_client(tables={("日k", "600000"): _daily_rows(
        [20260701, 20260702, 20260703, 20260704])})
    out = client.get_data("600000", fq=None, fields="date,close", desc=True, limit=2)
    assert out == [[20260704, 10.0], [20260703, 10.0]]


def test_client_batch_pipe(make_client):
    tables = {
        ("日k", "600000"): _daily_rows([20260701]),
        ("日k", "000001"): _daily_rows([20260701, 20260702]),
    }
    client = make_client(tables=tables)
    out = client.get_data(["600000.SH", "000001"], fq=None)
    assert set(out) == {"600000", "000001"}
    assert len(out["000001"]) == 2

    df = client.get_data(["600000", "000001"], fq=None, as_df=True)
    assert df.columns[0] == "code"
    assert len(df) == 3


def test_client_tuple_batch(make_client):
    tables = {
        ("日k", "600000"): _daily_rows([20260701]),
        ("日k", "000001"): _daily_rows([20260701]),
    }
    client = make_client(tables=tables)
    out = client.get_data(("600000.SH", "000001"), fq=None)
    assert out == {"600000": tables[("日k", "600000")],
                   "000001": tables[("日k", "000001")]}


def test_client_fq_qfq_hfq(make_client):
    # 因子：20260101 -> 1.0，20260601 -> 2.0（f_latest = 2.0）
    tables = {("日k", "600000"): _daily_rows([20260501, 20260701])}
    client = make_client(cum=FQ, tables=tables)

    raw = client.get_data("600000", fq=None)
    qfq = client.get_data("600000", fq="qfq")
    hfq = client.get_data("600000", fq="hfq")

    # 20260501 位于两次除权之间：f_current = 1.0
    assert qfq[0]["close"] == round(10.0 / 2.0, 2)  # qfq: 价格减半
    assert hfq[0]["close"] == 10.0                  # hfq: 不变
    assert raw[0]["close"] == 10.0
    # 20260701 位于最后一次除权之后：f_current = 2.0
    assert qfq[1]["close"] == 10.0                  # qfq: 不变
    assert hfq[1]["close"] == round(10.0 / 0.5, 2)  # hfq: 翻倍
    # 原记录不被就地修改
    assert raw[0]["close"] == 10.0


def test_client_fq_unknown_code_passthrough(make_client):
    tables = {("日k", "300750"): _daily_rows([20260701])}
    client = make_client(cum=FQ, tables=tables)
    assert client.get_data("300750", fq="qfq")[0]["close"] == 10.0


def test_client_fq_load_failure_warns():
    from stockdb_sdk._client import StockDBClient

    class BrokenRaw:
        def get(self, *_):
            raise RuntimeError("server down")

    with pytest.warns(RuntimeWarning, match="复权因子加载失败"):
        client = StockDBClient(_raw_client=BrokenRaw())
    assert client._fq_dates == {}


def test_client_weekly_via_get_data(make_client):
    rows = _daily_rows([20260706, 20260707, 20260708, 20260709, 20260710, 20260713])
    client = make_client(tables={("日k", "600000"): rows})
    weekly = client.get_data("600000", frequency="1w", fq=None)
    assert len(weekly) == 2
    assert weekly[0]["date"] == 20260710
    # 聚合路径下 desc 在聚合后反转
    weekly_desc = client.get_data("600000", frequency="1w", fq=None, desc=True)
    assert weekly_desc[0]["date"] == 20260713


# ---------- 模块级入口（显式签名锁定） ----------

def test_module_level_signatures_match_client():
    import inspect

    import stockdb_sdk

    for mod_fn, client_fn in (
        (stockdb_sdk.get_data, StockDBClient.get_data),
        (stockdb_sdk.get_data_async, StockDBClient.get_data_async),
    ):
        client_sig = inspect.signature(client_fn)
        params = list(client_sig.parameters.values())[1:]  # 去掉 self
        assert inspect.signature(mod_fn) == inspect.Signature(
            params, return_annotation=client_sig.return_annotation)
