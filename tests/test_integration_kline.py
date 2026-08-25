"""集成测试：K 线查询全参数覆盖（需本地 stockdb 服务，默认 127.0.0.1:7899）。"""

import bisect
import datetime as dt
from collections import defaultdict

import pandas as pd
import pytest

import stockdb_sdk as sdk

CODE = "000001"


# ---------- 日 K ----------

def test_daily_shape_and_order(daily):
    dates = [b["date"] for b in daily]
    assert dates == sorted(dates)
    assert isinstance(dates[0], int)
    for key in ("open", "high", "low", "close", "volume", "amount", "code", "name"):
        assert key in daily[0]


def test_range_and_single_day(daily):
    start, end = str(daily[20]["date"]), str(daily[60]["date"])
    bars = sdk.get_data(CODE, start=start, end=end, fq=None)
    got = [b["date"] for b in bars]
    assert got[0] == daily[20]["date"]
    assert got[-1] == daily[60]["date"]
    assert all(int(start) <= d <= int(end) for d in got)
    # start == end 退化为单日点查询
    one = sdk.get_data(CODE, start=start, end=start, fq=None)
    assert [b["date"] for b in one] == [daily[20]["date"]]
    # 只传 start 不传 end 同样按单日点查询处理
    only_start = sdk.get_data(CODE, start=start, fq=None)
    assert [b["date"] for b in only_start] == [daily[20]["date"]]


def test_desc_limit(daily):
    bars = sdk.get_data(CODE, fq=None, desc=True, limit=10)
    got = [b["date"] for b in bars]
    assert got == sorted(got, reverse=True)
    assert got[0] == daily[-1]["date"]
    assert len(got) == 10
    # 升序 limit 取最早 N 根
    first3 = sdk.get_data(CODE, fq=None, limit=3)
    assert [b["date"] for b in first3] == [b["date"] for b in daily[:3]]


def test_fields_projection(daily):
    start = str(daily[-5]["date"])
    rows = sdk.get_data(CODE, start=start, end="N", fq=None, fields="date,open,close")
    assert all(isinstance(r, list) for r in rows)
    ref = {b["date"]: b for b in daily if b["date"] >= int(start)}
    for row in rows:
        assert row == [ref[row[0]]["date"], ref[row[0]]["open"], ref[row[0]]["close"]]


def test_as_df(daily):
    start = str(daily[-10]["date"])
    df = sdk.get_data(CODE, start=start, end="N", fq=None, as_df=True)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 10
    assert {"date", "open", "close"} <= set(df.columns)


def test_suffix_normalization(daily):
    window = dict(start=str(daily[-5]["date"]), end="N", fq=None)
    assert sdk.get_data("000001.SZ", **window) == sdk.get_data(CODE, **window)


# ---------- 批量 ----------

def test_batch_and_df(daily):
    window = dict(start=str(daily[-10]["date"]), end="N", fq=None)
    out = sdk.get_data([CODE, "600633"], **window)
    assert set(out) == {CODE, "600633"}
    assert out[CODE] == sdk.get_data(CODE, **window)
    assert out["600633"] == sdk.get_data("600633", **window)
    # 带后缀的批量输入 -> 归一化键
    assert sdk.get_data(["000001.SZ", "600633.SH"], **window) == out

    df = sdk.get_data([CODE, "600633"], **window, as_df=True)
    assert df.columns[0] == "code"
    assert len(df) == sum(len(v) for v in out.values())
    assert set(df["code"]) == {CODE, "600633"}


# ---------- 复权 ----------

def test_fq_math(client):
    dates = client._fq_dates.get(CODE)
    cums = client._fq_cums.get(CODE)
    assert dates and len(set(cums)) > 1, "000001 应有多次除权的复权因子"

    start = "20200101"
    raw = sdk.get_data(CODE, start=start, end="N", fq=None)
    qfq = sdk.get_data(CODE, start=start, end="N", fq="qfq")
    hfq = sdk.get_data(CODE, start=start, end="N", fq="hfq")
    assert len(raw) == len(qfq) == len(hfq)

    f_latest = cums[-1]
    for r, q, h in zip(raw, qfq, hfq):
        idx = bisect.bisect_right(dates, str(r["date"])[:8]) - 1
        f_current = cums[idx] if idx >= 0 else 1.0
        # qfq = raw * f_current / f_latest；hfq = raw * f_current
        assert q["close"] == pytest.approx(r["close"] * f_current / f_latest, rel=1e-3)
        assert h["close"] == pytest.approx(r["close"] * f_current, rel=1e-3)
        assert q["open"] == pytest.approx(r["open"] * f_current / f_latest, rel=1e-3)
    # 最新一根 qfq 价格与不复权一致
    assert qfq[-1]["close"] == raw[-1]["close"]


# ---------- 周 K / 月 K ----------

def test_weekly(daily):
    weekly = sdk.get_data(CODE, fq=None, frequency="1w")
    assert weekly
    iso_of = {b["date"]: dt.datetime.strptime(str(b["date"]), "%Y%m%d").isocalendar()[:2]
              for b in daily}
    groups = defaultdict(list)
    for b in daily:
        groups[iso_of[b["date"]]].append(b)

    for w in weekly:
        members = groups[iso_of[w["date"]]]
        assert members
        assert w["date"] == members[-1]["date"]
        assert w["open"] == members[0]["open"]
        assert w["close"] == members[-1]["close"]
        assert w["high"] == max(m["high"] for m in members)
        assert w["low"] == min(m["low"] for m in members)
        assert w["volume"] == sum(m["volume"] for m in members)
    assert weekly[-1]["date"] == daily[-1]["date"]

    # 聚合路径下 desc 在聚合后反转
    desc = sdk.get_data(CODE, fq=None, frequency="1w", desc=True, limit=3)
    assert [b["date"] for b in desc] == [w["date"] for w in weekly[::-1][:3]]


def test_monthly(daily):
    monthly = sdk.get_data(CODE, fq=None, frequency="1M")
    assert monthly
    key_of = {b["date"]: (b["date"] // 10000, b["date"] // 100 % 100) for b in daily}
    groups = defaultdict(list)
    for b in daily:
        groups[key_of[b["date"]]].append(b)

    for m in monthly:
        members = groups[key_of[m["date"]]]
        assert m["date"] == members[-1]["date"]
        assert m["open"] == members[0]["open"]
        assert m["close"] == members[-1]["close"]
        assert m["volume"] == sum(x["volume"] for x in members)
    assert monthly[-1]["date"] == daily[-1]["date"]


# ---------- 分钟 K ----------

def test_minute_1m(minute_day):
    day, bars = minute_day
    dates = [b["date"] for b in bars]
    assert all(10**13 <= d < 10**14 for d in dates)
    assert dates == sorted(dates)
    assert all(93000 <= d % 1000000 <= 150000 for d in dates)
    # 8 位日期自动覆盖全天交易时段
    fetched = sdk.get_data(CODE, start=day, end=day, frequency="1m", fq=None)
    assert [b["date"] for b in fetched] == dates


def _elapsed(date_int):
    hh = (date_int // 10000) % 100
    mm = (date_int // 100) % 100
    mod = hh * 60 + mm
    if 570 <= mod <= 690:
        return mod - 570
    if 780 <= mod <= 900:
        return 121 if mod == 780 else 120 + (mod - 780)
    return None


def _expected_bars(minute_bars, interval):
    """独立重算的分钟聚合基准（与实现相同的对齐规则）。"""
    grouped = defaultdict(list)
    for b in minute_bars:
        e = _elapsed(b["date"])
        if e is None:
            continue
        end = interval if e <= 0 else ((e - 1) // interval + 1) * interval
        mod = 570 + end if end <= 120 else 780 + (end - 120)
        stamp = (b["date"] // 1000000) * 1000000 + (mod // 60) * 10000 + (mod % 60) * 100
        grouped[stamp].append(b)
    return {
        stamp: {
            "open": items[0]["open"],
            "high": max(i["high"] for i in items),
            "low": min(i["low"] for i in items),
            "close": items[-1]["close"],
            "volume": sum(i["volume"] for i in items),
            "amount": sum(i["amount"] for i in items),
        }
        for stamp, items in grouped.items()
    }


@pytest.mark.parametrize("frequency,interval", [
    ("5m", 5), ("15m", 15), ("30m", 30), ("60m", 60),
])
def test_minute_aggregation(minute_day, frequency, interval):
    day, bars = minute_day
    merged = sdk.get_data(CODE, start=day, end=day, frequency=frequency, fq=None)
    assert merged
    expected = _expected_bars(bars, interval)
    assert len(merged) == len(expected)
    for bar in merged:
        exp = expected[bar["date"]]
        for key, val in exp.items():
            assert bar[key] == pytest.approx(val), f"{frequency} {bar['date']} {key}"


# ---------- 原生透传与初始化 ----------

def test_rd_passthrough():
    bars = list(sdk.rd.vals("日k", CODE, "2026082*"))
    assert bars
    codes = sdk.rd.get("股票代码")
    assert CODE in codes["0"]
    # rd 是纯透传，不再挂高层 get_data
    assert not hasattr(sdk.rd, "get_data")


def test_init_default_endpoint():
    raw = sdk.init()  # 显式初始化默认端点并预热
    assert hasattr(raw, "vals")
    assert sdk.get_data(CODE, limit=1, fq=None)
